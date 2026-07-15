#!/usr/bin/env python3
"""
Openpilot AI Agent service.

Serves a LAN-accessible web UI for configuring and chatting with the AI agent,
plus a small REST API consumed by the device UI.

Security model:
  - Open mode (ai_admin_mode=1, default): all tools allowed except direct vehicle control.
  - Legacy mode (ai_admin_mode=0): writes blocked while driving.
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

from ai.persona import ensure_default_persona, get_default_persona
from ai.client import (
  AIConfig,
  ChatChunk,
  chat_completion,
  expand_messages_for_api,
  load_config_from_params,
  merge_config_from_body,
  test_connection,
  list_models,
)
from ai.selfdrive.state import StateReader, VehicleState
from ai.system.safety import ACTION_RULES, is_action_allowed
from ai.system.admin import is_admin_mode
from ai.system.shell import ALLOWED_COMMANDS, run_command
from ai.common.params import (
  AI_DEFAULT_MODELS,
  AI_EMBEDDING_MODEL_CATALOG,
  AI_EMBEDDING_PROVIDER_LABELS,
  AI_EMBEDDING_PROVIDERS,
  AI_PROVIDER_LABELS,
  AI_PROVIDER_MODEL_CATALOG,
  AI_PROVIDERS,
  AI_SAME_MODE_EMBEDDING_MODELS,
)
from ai.tools.agent_tools import (
  TOOL_META,
  execute_tool_async,
  filter_tools as filter_agent_tools,
  make_handlers,
  tool_meta_for_host,
)
from ai.system.host_env import get_host_environment
from ai.tools.memory_store import get_memory, append_note, update_vehicle_profile, delete_note, format_memory_prompt, sync_vehicle_profile_from_state
from ai.model_router import resolve_chat_config
from ai.tools.scheduler import list_tasks, upsert_task, remove_task, run_due_tasks, ensure_default_scheduler_tasks
from ai.skills.loader import build_skills_prompt, list_skills, load_enabled_skill_ids, save_enabled_skill_ids
from ai.tools.write_pending import confirm_pending, list_pending
from ai.tools.rag_store import (
  format_rag_prompt,
  list_documents,
  upsert_document,
  remove_document,
  search_documents,
  reindex_all,
)
from ai.embedding import DEFAULT_EMBEDDING_MODELS, load_embedding_config
from ai.tools.workflows import list_workflows, workflow_system_prompt
from ai.tools.notifications import list_notifications, mark_notifications_read, push_notification
from ai.tools.session_store import get_sessions, save_sessions
from ai.chat_runner import ChatCancelled, run_chat_loop
from ai.chat_jobs import cancel_job, get_job, list_active_jobs, start_chat_job
from ai.web_auth import ai_auth_middleware
from ai.sync_hub import broadcast_config, broadcast_notifications, broadcast_sessions, broadcast_status, register_sync_routes
from ai.cabana import register_routes as register_cabana_routes
from ai.usage_log import load_usage, record_usage


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

_PARAMS = Params()
_STATE_READER: StateReader | None = None
_TOOL_HANDLERS: dict[str, Any] | None = None


def _get_state_reader() -> StateReader:
  global _STATE_READER
  if _STATE_READER is None:
    try:
      _STATE_READER = StateReader()
    except Exception as e:
      cloudlog.error(f"aid: failed to initialize StateReader: {e}")
      # Return a fallback reader that yields default/offline state. Never
      # re-raise, because many API endpoints need to keep working even when
      # cereal sockets are unavailable.
      _STATE_READER = StateReader.__new__(StateReader)
      _STATE_READER._params = Params()
      _STATE_READER._sm = None
      _STATE_READER._healthy = False
      _STATE_READER._services = []
  return _STATE_READER


def _json_response(data: Any, status: int = 200) -> web.Response:
  return web.Response(
    text=json.dumps(data, ensure_ascii=False, default=str),
    status=status,
    content_type="application/json",
  )


def _read_param_str(key: str, default: str = "") -> str:
  val = _PARAMS.get(key)
  return val.decode() if isinstance(val, bytes) else (val or default)


def _read_param_bool(key: str, default: bool = False) -> bool:
  val = _read_param_str(key, "1" if default else "0")
  return str(val).lower() in ("1", "true", "yes", "on")


def _mask_key(key: str) -> str:
  """Mask an API key for display; keep last 4 characters if long enough."""
  if not key:
    return ""
  if len(key) <= 8:
    return "•" * len(key)
  return "•" * (len(key) - 4) + key[-4:]


def _read_ai_config() -> AIConfig:
  return load_config_from_params(_PARAMS)


def _get_tool_handlers() -> dict[str, Any]:
  global _TOOL_HANDLERS
  if _TOOL_HANDLERS is None:
    _TOOL_HANDLERS = make_handlers(
      get_state_reader=_get_state_reader,
      params=_PARAMS,
    )
  return _TOOL_HANDLERS


_MAX_TOOL_ROUNDS = 64


def _resolve_max_tool_rounds(value: Any) -> int:
  """Always run until the model stops calling tools (practical ∞)."""
  return _MAX_TOOL_ROUNDS


def _filter_tools(enabled: bool, tool_prefs: dict[str, Any], driving: bool = False) -> list[dict[str, Any]] | None:
  return filter_agent_tools(enabled, tool_prefs, driving=driving, admin=is_admin_mode(_PARAMS))


async def _startup_rag_reindex() -> None:
  try:
    config = _read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    if not embed_cfg.is_configured:
      return
    res = await reindex_all(_PARAMS, embed_cfg)
    cloudlog.info(f"aid: RAG auto-reindex indexed={res.get('indexed')}/{res.get('total')}")
  except Exception as e:
    cloudlog.warning(f"aid: RAG auto-reindex skipped: {e}")


async def _startup_memory_index() -> None:
  try:
    config = _read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    if not embed_cfg.is_configured:
      return
    from ai.tools.memory_vectors import index_memory_notes
    res = await index_memory_notes(_PARAMS, embed_cfg)
    cloudlog.info(f"aid: memory vector index indexed={res.get('indexed', 0)}")
  except Exception as e:
    cloudlog.warning(f"aid: memory index skipped: {e}")


async def _notify_push(title: str, body: str, *, level: str = "info") -> None:
  push_notification(title, body, level=level)
  try:
    await broadcast_notifications()
  except Exception as e:
    cloudlog.warning(f"aid: broadcast_notifications failed: {e}")


async def api_workflows(request: web.Request) -> web.Response:
  return _json_response({"ok": True, "workflows": list_workflows()})


async def api_notifications(request: web.Request) -> web.Response:
  if request.method == "POST":
    mark_notifications_read()
    try:
      await broadcast_notifications()
    except Exception as e:
      cloudlog.warning(f"aid: broadcast_notifications failed: {e}")
    return _json_response({"ok": True})
  unread = request.query.get("unread", "1") != "0"
  return _json_response(list_notifications(unread_only=unread))


async def api_adaptation_bundle(request: web.Request) -> web.Response:
  project_id = request.match_info.get("project_id", "")
  from ai.tools.adaptation import export_adaptation_bundle
  result = export_adaptation_bundle(project_id)
  if not result.get("ok"):
    return _json_response(result, status=404)
  if request.query.get("download") == "1":
    filename = f"adaptation_{project_id}.json"
    return web.Response(
      body=json.dumps(result, ensure_ascii=False, indent=2),
      content_type="application/json",
      headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
  return _json_response(result)


# -----------------------------------------------------------------------------
# Streaming helpers
# -----------------------------------------------------------------------------

def _sse(data: dict[str, Any]) -> bytes:
  return ("data: " + json.dumps(data, ensure_ascii=False, default=str) + "\n\n").encode("utf-8")


# -----------------------------------------------------------------------------
# API handlers
# -----------------------------------------------------------------------------

async def api_bootstrap(request: web.Request) -> web.Response:
  """Single round-trip bootstrap: status + config + providers (faster page load)."""
  try:
    ensure_default_persona(_PARAMS)
    reader = _get_state_reader()
    state = reader.update(timeout=0)
    sync_vehicle_profile_from_state(
      _PARAMS,
      brand=state.brand or "",
      car_fingerprint=state.car_fingerprint or "",
    )
    config = _read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    skills_on = load_enabled_skill_ids(_PARAMS)
    from ai.timezone_util import read_ai_timezone_name
    tz_name = read_ai_timezone_name(_PARAMS)
    first_run_done = _read_param_bool("ai_first_run_done")
    try:
      from ai.fork.detect_fork import detect_fork
      fork_detected = detect_fork(Path(__file__).resolve().parent.parent)
    except Exception:
      fork_detected = {"ok": False}
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)

  bootstrap_models: list[dict[str, Any]] = [
    {"id": mid} for mid in (AI_PROVIDER_MODEL_CATALOG.get(config.provider) or []) if mid
  ]
  models_source = "catalog"
  if config.is_configured:
    try:
      lm = await list_models(config)
      if lm.get("ok") and lm.get("models"):
        bootstrap_models = lm["models"]
        models_source = str(lm.get("source") or "api")
    except Exception as e:
      cloudlog.warning(f"aid: bootstrap list_models failed: {e}")

  return _json_response({
    "ok": True,
    "driving": state.is_driving,
    "state": state.to_dict(),
    "ai": {
      "configured": config.is_configured,
      "provider": config.provider,
      "model": config.model,
      "configureError": config.configuration_error,
    },
    "providers": AI_PROVIDERS,
    "providerLabels": AI_PROVIDER_LABELS,
    "defaults": AI_DEFAULT_MODELS,
    "modelCatalog": AI_PROVIDER_MODEL_CATALOG,
    "models": bootstrap_models,
    "modelsSource": models_source,
    "config": {
      "provider": config.provider,
      "model": config.model,
      "apiKey": _mask_key(config.api_key),
      "baseUrl": config.base_url,
      "systemPrompt": config.system_prompt,
      "temperature": config.temperature,
      "topP": config.top_p,
      "maxTokens": config.max_tokens,
      "thinkingEnabled": config.thinking_enabled,
      "thinkingKeep": config.thinking_keep,
      "webPin": _mask_key(_read_param_str("ai_web_pin")),
      "timezone": tz_name,
      "configured": config.is_configured,
      "configureError": config.configuration_error,
      "embeddingMode": embed_cfg.mode,
      "embeddingProvider": embed_cfg.provider,
      "embeddingModel": embed_cfg.model,
      "embeddingApiKey": _mask_key(_read_param_str("ai_embedding_api_key")) if embed_cfg.mode == "separate" else "",
      "embeddingBaseUrl": embed_cfg.base_url,
      "embeddingConfigured": embed_cfg.is_configured,
    },
    "embeddingDefaults": DEFAULT_EMBEDDING_MODELS,
    "embeddingProviders": AI_EMBEDDING_PROVIDERS,
    "embeddingProviderLabels": AI_EMBEDDING_PROVIDER_LABELS,
    "embeddingModelCatalog": AI_EMBEDDING_MODEL_CATALOG,
    "embeddingSameModeCatalog": AI_SAME_MODE_EMBEDDING_MODELS,
    "tools": tool_meta_for_host(),
    "hostEnvironment": get_host_environment(),
    "skills": list_skills(),
    "skillsEnabled": sorted(skills_on) if skills_on is not None else None,
    "pinRequired": bool(_read_param_str("ai_web_pin").strip()),
    "adminMode": is_admin_mode(_PARAMS),
    "onboarding": {
      "firstRunDone": first_run_done,
      "showWizard": not first_run_done or not config.is_configured,
    },
    "fork": fork_detected if fork_detected.get("ok") else None,
    "workflows": list_workflows(),
    "notifications": list_notifications(unread_only=True).get("notifications", [])[:5],
  })


async def api_status(request: web.Request) -> web.Response:
  try:
    state = _get_state_reader().update(timeout=0)
    config = _read_ai_config()
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)
  return _json_response({
    "ok": True,
    "driving": state.is_driving,
    "state": state.to_dict(),
    "ai": {
      "configured": config.is_configured,
      "provider": config.provider,
      "model": config.model,
    },
  })


async def api_providers(request: web.Request) -> web.Response:
  return _json_response({
    "ok": True,
    "providers": AI_PROVIDERS,
    "providerLabels": AI_PROVIDER_LABELS,
    "defaults": AI_DEFAULT_MODELS,
    "modelCatalog": AI_PROVIDER_MODEL_CATALOG,
    "embeddingProviders": AI_EMBEDDING_PROVIDERS,
    "embeddingProviderLabels": AI_EMBEDDING_PROVIDER_LABELS,
    "embeddingModelCatalog": AI_EMBEDDING_MODEL_CATALOG,
    "embeddingSameModeCatalog": AI_SAME_MODE_EMBEDDING_MODELS,
    "embeddingDefaults": DEFAULT_EMBEDDING_MODELS,
    "rules": {k: {"category": v.category.value, "description": v.description}
              for k, v in ACTION_RULES.items()},
  })


async def api_get_config(request: web.Request) -> web.Response:
  from ai.timezone_util import read_ai_timezone_name

  config = _read_ai_config()
  embed_cfg = load_embedding_config(_PARAMS, config)
  return _json_response({
    "ok": True,
    "config": {
      "provider": config.provider,
      "model": config.model,
      "apiKey": _mask_key(config.api_key),
      "baseUrl": config.base_url,
      "systemPrompt": config.system_prompt,
      "temperature": config.temperature,
      "topP": config.top_p,
      "maxTokens": config.max_tokens,
      "thinkingEnabled": config.thinking_enabled,
      "thinkingKeep": config.thinking_keep,
      "webPin": _mask_key(_read_param_str("ai_web_pin")),
      "timezone": read_ai_timezone_name(_PARAMS),
      "configured": config.is_configured,
      "configureError": config.configuration_error,
      "embeddingMode": embed_cfg.mode,
      "embeddingProvider": embed_cfg.provider,
      "embeddingModel": embed_cfg.model,
      "embeddingApiKey": _mask_key(_read_param_str("ai_embedding_api_key")) if embed_cfg.mode == "separate" else "",
      "embeddingBaseUrl": embed_cfg.base_url,
      "embeddingConfigured": embed_cfg.is_configured,
    },
  })


async def api_post_config(request: web.Request) -> web.Response:
  state = _get_state_reader().update(timeout=0)
  allowed, reason = is_action_allowed("write_ai_config", state, admin=is_admin_mode(_PARAMS))
  if not allowed:
    return _json_response({"ok": False, "error": reason}, status=403)

  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)

  def _put(key: str, value: Any) -> None:
    if value is None:
      return
    if isinstance(value, bool):
      _PARAMS.put_bool(key, value)
    else:
      _PARAMS.put(key, str(value))

  try:
    _put("ai_provider", body.get("provider"))
    _put("ai_model", body.get("model"))
    api_key = body.get("apiKey", "")
    if api_key and not str(api_key).startswith("•"):
      _put("ai_api_key", str(api_key).strip())
    _put("ai_base_url", body.get("baseUrl"))
    _put("ai_system_prompt", body.get("systemPrompt"))
    _put("ai_temperature", body.get("temperature"))
    _put("ai_top_p", body.get("topP"))
    _put("ai_max_tokens", body.get("maxTokens"))
    _put("ai_thinking_enabled", body.get("thinkingEnabled"))
    _put("ai_thinking_keep", body.get("thinkingKeep"))
    web_pin = body.get("webPin", "")
    if web_pin is not None and web_pin != "" and not str(web_pin).startswith("•"):
      _put("ai_web_pin", web_pin)
    elif body.get("clearWebPin"):
      _put("ai_web_pin", "")
    _put("ai_embedding_mode", body.get("embeddingMode"))
    _put("ai_embedding_provider", body.get("embeddingProvider"))
    _put("ai_embedding_model", body.get("embeddingModel"))
    emb_key = body.get("embeddingApiKey", "")
    if emb_key and not str(emb_key).startswith("•"):
      _put("ai_embedding_api_key", emb_key)
    _put("ai_embedding_base_url", body.get("embeddingBaseUrl"))
    tz = body.get("timezone")
    if tz is not None and str(tz).strip():
      _put("ai_timezone", str(tz).strip())
  except Exception as e:
    cloudlog.error(f"aid: api_post_config failed: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)

  config = _read_ai_config()
  try:
    await broadcast_config(_PARAMS)
  except Exception as e:
    cloudlog.warning(f"aid: broadcast_config failed: {e}")
  return _json_response({
    "ok": True,
    "configured": config.is_configured,
    "configureError": config.configuration_error,
  })


async def api_models(request: web.Request) -> web.Response:
  try:
    saved = _read_ai_config()
    body = None
    if request.method == "POST":
      try:
        body = await request.json()
      except json.JSONDecodeError:
        return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)
    config = merge_config_from_body(saved, body)
    from ai.client import list_models
    result = await list_models(config)
    return _json_response({
      "ok": bool(result.get("ok")),
      "error": result.get("error"),
      "models": result.get("models", []),
      "configured": config.is_configured,
      "configureError": config.configuration_error,
    })
  except Exception as e:
    cloudlog.error(f"aid: api_models error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}", "models": []}, status=500)


async def api_test_connection(request: web.Request) -> web.Response:
  try:
    saved = _read_ai_config()
    body = None
    if request.method == "POST":
      try:
        body = await request.json()
      except json.JSONDecodeError:
        return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)
    config = merge_config_from_body(saved, body)
    if not config.is_configured:
      return _json_response({
        "ok": False,
        "error": config.configuration_error or "AI not configured",
        "configured": False,
        "configureError": config.configuration_error,
      })
    result = await test_connection(config)
    return _json_response({
      "ok": bool(result.get("ok")),
      "error": result.get("error"),
      "model_available": result.get("model_available"),
      "models_count": result.get("models_count"),
      "message": result.get("message"),
      "configured": True,
    })
  except Exception as e:
    cloudlog.error(f"aid: api_test_connection error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)


async def api_skills(request: web.Request) -> web.Response:
  """List or persist enabled agent skills."""
  if request.method == "GET":
    enabled = load_enabled_skill_ids(_PARAMS)
    return _json_response({
      "ok": True,
      "skills": list_skills(),
      "enabled": sorted(enabled) if enabled else None,
    })
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  ids = body.get("enabled") or []
  if not isinstance(ids, list):
    return _json_response({"ok": False, "error": "enabled must be a list"}, status=400)
  save_enabled_skill_ids(_PARAMS, [str(x) for x in ids if x])
  return _json_response({"ok": True, "enabled": ids})


async def api_tools_meta(request: web.Request) -> web.Response:
  return _json_response({"ok": True, "tools": tool_meta_for_host(), "hostEnvironment": get_host_environment()})


async def api_memory(request: web.Request) -> web.Response:
  if request.method == "GET":
    return _json_response(get_memory(_PARAMS))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if body.get("delete_note_id"):
    return _json_response(delete_note(_PARAMS, str(body["delete_note_id"])))
  if body.get("note"):
    return _json_response(append_note(_PARAMS, body["note"], body.get("tags")))
  if body.get("vehicle_profile"):
    return _json_response(update_vehicle_profile(_PARAMS, body["vehicle_profile"]))
  return _json_response({"ok": False, "error": "Nothing to update"}, status=400)


async def api_scheduler(request: web.Request) -> web.Response:
  if request.method == "GET":
    return _json_response(list_tasks(_PARAMS))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  op = body.get("operation", "upsert")
  if op == "remove":
    return _json_response(remove_task(_PARAMS, str(body.get("task_id", ""))))
  return _json_response(upsert_task(
    _PARAMS,
    task_id=body.get("task_id"),
    name=str(body.get("name", "")),
    action=str(body.get("action", "read_last_log")),
    interval_minutes=int(body.get("interval_minutes", 60)),
    enabled=bool(body.get("enabled", True)),
    payload=body.get("payload"),
    trigger=str(body.get("trigger", "interval")),
  ))


async def api_write_confirm(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  state = _get_state_reader().update(timeout=0)
  allowed, reason = is_action_allowed("write_param", state, admin=is_admin_mode(_PARAMS))
  if not allowed:
    return _json_response({"ok": False, "error": reason}, status=403)
  pending_id = str(body.get("pending_id", ""))
  if not pending_id:
    return _json_response({"ok": False, "error": "pending_id required"}, status=400)
  return _json_response(confirm_pending(_PARAMS, pending_id))


async def api_write_pending(request: web.Request) -> web.Response:
  return _json_response(list_pending(_PARAMS))


async def api_tune_passport(request: web.Request) -> web.Response:
  from ai.tools.tune_passport_store import list_tune_passport
  limit = int(request.query.get("limit", "30"))
  return _json_response(list_tune_passport(limit=limit))


async def api_rag(request: web.Request) -> web.Response:
  config = _read_ai_config()
  embed_cfg = load_embedding_config(_PARAMS, config)
  if request.method == "GET":
    q = request.query.get("q", "")
    if q:
      return _json_response(await search_documents(_PARAMS, q, embed_config=embed_cfg))
    return _json_response(list_documents(_PARAMS))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  op = body.get("operation", "upsert")
  if op == "remove":
    return _json_response(remove_document(_PARAMS, str(body.get("doc_id", ""))))
  if op == "reindex":
    return _json_response(await reindex_all(_PARAMS, embed_cfg))
  return _json_response(await upsert_document(
    _PARAMS,
    title=str(body.get("title", "")),
    text=str(body.get("text", "")),
    tags=body.get("tags"),
    doc_id=body.get("doc_id"),
    embed_config=embed_cfg,
    reindex=body.get("reindex", True),
  ))


async def api_sessions(request: web.Request) -> web.Response:
  if request.method == "GET":
    return _json_response(get_sessions(_PARAMS))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  result = save_sessions(_PARAMS, body)
  try:
    await broadcast_sessions(_PARAMS)
  except Exception as e:
    cloudlog.warning(f"aid: broadcast_sessions failed: {e}")
  return _json_response(result)


async def api_dev_assets(request: web.Request) -> web.Response:
  from ai.tools.dev_assets import list_dev_assets, resolve_dev_asset
  if request.method == "GET" and request.match_info.get("kind"):
    kind = request.match_info.get("kind", "")
    name = request.match_info.get("name", "")
    path = resolve_dev_asset(kind, name)
    if path is None:
      return web.Response(status=404, text="Not found")
    return web.FileResponse(path)
  limit = int(request.query.get("limit", "40"))
  return _json_response(list_dev_assets(limit=limit))


async def api_pc_sessions(request: web.Request) -> web.Response:
  try:
    from ai.tools.pc_dev_tools import pc_list_tool_sessions
    return _json_response(pc_list_tool_sessions(limit=int(request.query.get("limit", "20"))))
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)})


async def _scheduler_execute_action(action: str, _payload: dict[str, Any]) -> str:
  if action == "read_last_log":
    raw = _PARAMS.get("dp_dev_last_log")
    text = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw or "")
    return text[:400] or "empty"
  if action == "read_usage":
    u = load_usage(_PARAMS)
    return f"calls={u.get('calls')} tokens={u.get('total_tokens')}"
  if action == "read_tune_snapshot":
    from ai.tools.dp_settings import list_dp_settings
    state = _get_state_reader().update(timeout=0)
    snap = list_dp_settings(_PARAMS, brand=state.brand)
    return f"{snap.get('setting_count', 0)} settings"
  if action == "memory_ping":
    m = get_memory(_PARAMS)
    return f"notes={len(m.get('notes', []))}"
  if action == "snapshot_tune":
    from ai.tools.diagnostics_tools import snapshot_tune_state
    from ai.tools.tune_snapshot_store import save_tune_snapshot
    state = _get_state_reader().update(timeout=0)
    save_tune_snapshot(_PARAMS, label="scheduler", brand=state.brand or "")
    snap = snapshot_tune_state(_PARAMS, brand=state.brand)
    return f"params={snap.get('param_count', 0)}"
  if action == "trip_review_offroad":
    from ai.tools.diagnostics_tools import trip_review
    state = _get_state_reader().update(timeout=0)
    review = trip_review(_PARAMS, _get_state_reader, brand=state.brand or "")
    summary = "; ".join(review.get("recommendations") or [])[:300]
    append_note(_PARAMS, f"[offroad] {summary}", tags=["auto", "trip_review"])
    return summary or "trip_review ok"
  if action == "reindex_rag_wifi":
    config = _read_ai_config()
    embed_cfg = load_embedding_config(_PARAMS, config)
    if not embed_cfg.is_configured:
      return "embedding not configured"
    res = await reindex_all(_PARAMS, embed_cfg)
    return f"indexed={res.get('indexed')}/{res.get('total')}"
  if action == "check_critical_events":
    from ai.tools.diagnostics_tools import read_onroad_events
    ev = read_onroad_events(_get_state_reader)
    critical = [e.get("name") for e in (ev.get("events") or []) if e.get("no_entry") or e.get("immediate_disable")]
    if critical:
      names = ", ".join(critical[:5])
      await _notify_push("onroad 事件", names, level="warn")
      return f"critical: {names}"
    return "no critical events"
  if action == "post_drive_review_offroad":
    from ai.tools.voice_summary_tools import build_post_drive_summary
    state = _get_state_reader().update(timeout=0)
    built = build_post_drive_summary(_PARAMS, _get_state_reader, brand=state.brand or "")
    append_note(_PARAMS, f"[offroad] {built.get('text', '')[:300]}", tags=["auto", "voice_summary"])
    return built.get("text", "")[:300] or "post_drive ok"
  if action == "check_param_watchlist_offroad":
    from ai.tools.tune_passport_store import check_param_watchlist
    res = check_param_watchlist(_PARAMS)
    if res.get("drifted"):
      names = ", ".join(list((res.get("changes") or {}).keys())[:5])
      await _notify_push("参数漂移", names, level="info")
      return f"drift: {names}"
    return "watchlist ok"
  if action == "git_fetch_wifi":
    from ai.tools.git_tools import git_fetch
    res = git_fetch()
    return f"fetch ok={res.get('ok')}"
  return f"unknown action {action}"


def _device_wifi_connected() -> bool:
  try:
    out = run_command("ip_addr")
    text = out.get("stdout", "") or ""
    return "wlan" in text and "UP" in text
  except Exception:
    return False


async def _status_watch_loop(_app: web.Application) -> None:
  last_sig: str | None = None
  while True:
    await asyncio.sleep(3)
    try:
      state = _get_state_reader().update(timeout=0)
      config = _read_ai_config()
      sig = json.dumps({
        "driving": state.is_driving,
        "state": state.to_dict(),
        "model": config.model,
        "provider": config.provider,
        "configured": config.is_configured,
      }, sort_keys=True, default=str)
      if sig != last_sig:
        last_sig = sig
        await broadcast_status(state, config)
    except Exception as e:
      cloudlog.debug(f"aid: status watch: {e}")


async def _scheduler_loop(_app: web.Application) -> None:
  import asyncio
  while True:
    await asyncio.sleep(60)
    try:
      state = _get_state_reader().update(timeout=0)
      await run_due_tasks(
        _PARAMS,
        is_driving=lambda: state.is_driving,
        is_ignition=lambda: state.ignition,
        is_wifi=_device_wifi_connected,
        execute_action=_scheduler_execute_action,
      )
    except Exception as e:
      cloudlog.error(f"aid: scheduler loop error: {e}")


async def _parse_chat_body(request: web.Request) -> tuple[dict[str, Any] | None, AIConfig | None, web.Response | None]:
  config = _read_ai_config()
  if not config.is_configured:
    return None, None, _json_response({
      "ok": False,
      "error": config.configuration_error or "AI not configured. Set provider, model, and API key first.",
    }, status=400)

  try:
    body = await request.json()
  except json.JSONDecodeError:
    return None, None, _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)

  raw_messages = body.get("messages", [])
  if not isinstance(raw_messages, list) or not raw_messages:
    return None, None, _json_response({"ok": False, "error": "messages must be a non-empty list."}, status=400)
  return body, config, None


def _chat_tools_for_body(body: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, int]:
  tools_enabled = bool(body.get("tools", True))
  tool_prefs = body.get("toolPrefs") or {}
  max_tool_rounds = _resolve_max_tool_rounds(body.get("maxToolRounds"))
  drive_state = _get_state_reader().update(timeout=0)
  tools = _filter_tools(tools_enabled, tool_prefs, driving=drive_state.is_driving) if tools_enabled else None
  return tools, max_tool_rounds


async def api_chat(request: web.Request) -> web.Response:
  try:
    body, config, err = await _parse_chat_body(request)
    if err is not None:
      return err
    assert body is not None and config is not None

    tools, max_tool_rounds = _chat_tools_for_body(body)
    run_body = {**body, "_config": config}

    async def stream_response():
      response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/event-stream; charset=utf-8"},
      )
      await response.prepare(request)

      async def emit(event: dict[str, Any]) -> None:
        await response.write(_sse(event))

      try:
        await run_chat_loop(
          run_body,
          _PARAMS,
          emit,
          get_state_reader=_get_state_reader,
          get_tool_handlers=_get_tool_handlers,
          tools=tools,
          max_tool_rounds=max_tool_rounds,
        )
      except ChatCancelled:
        pass
      await response.write_eof()
      return response

    return await stream_response()
  except Exception as e:
    cloudlog.error(f"aid: api_chat error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)


async def api_chat_jobs(request: web.Request) -> web.Response:
  """POST: start background job. GET ?sessionId=: list active jobs."""
  if request.method == "GET":
    session_id = str(request.query.get("sessionId", "") or "").strip()
    jobs = list_active_jobs(session_id or None)
    return _json_response({"ok": True, "jobs": jobs})

  try:
    body, config, err = await _parse_chat_body(request)
    if err is not None:
      return err
    assert body is not None and config is not None

    session_id = str(body.get("sessionId", "") or "").strip()
    tools, max_tool_rounds = _chat_tools_for_body(body)
    job_id = await start_chat_job(
      session_id,
      body,
      _PARAMS,
      get_state_reader=_get_state_reader,
      get_tool_handlers=_get_tool_handlers,
      tools=tools,
      max_tool_rounds=max_tool_rounds,
      config=config,
    )
    return _json_response({"ok": True, "jobId": job_id, "sessionId": session_id})
  except Exception as e:
    cloudlog.error(f"aid: api_chat_jobs error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)


async def api_chat_job_detail(request: web.Request) -> web.Response:
  job_id = request.match_info.get("job_id", "")
  if request.method == "DELETE":
    ok = await cancel_job(job_id)
    if not ok:
      return _json_response({"ok": False, "error": "Job not found"}, status=404)
    return _json_response({"ok": True, "cancelled": True})

  since = int(request.query.get("since", "0") or "0")
  job = get_job(job_id, since=since)
  if not job:
    return _json_response({"ok": False, "error": "Job not found"}, status=404)
  return _json_response(job)


async def api_shell(request: web.Request) -> web.Response:
  try:
    state = _get_state_reader().update(timeout=0)
    allowed, reason = is_action_allowed("shell", state, admin=is_admin_mode(_PARAMS))
    if not allowed:
      return _json_response({"ok": False, "error": reason}, status=403)

    try:
      body = await request.json()
    except json.JSONDecodeError:
      return _json_response({"ok": False, "error": "Invalid JSON body."}, status=400)

    command_name = body.get("command", "")
    result = run_command(command_name)
    return _json_response(result)
  except Exception as e:
    cloudlog.error(f"aid: api_shell error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)


async def api_state(request: web.Request) -> web.Response:
  try:
    reader = _get_state_reader()
    reader.update(timeout=0)
    return _json_response({"ok": True, "data": reader.latest()})
  except Exception as e:
    cloudlog.error(f"aid: api_state error: {e}")
    return _json_response({"ok": False, "error": f"Internal error: {e}"}, status=500)


async def api_usage(request: web.Request) -> web.Response:
  return _json_response({"ok": True, "usage": load_usage(_PARAMS)})


async def api_package_version(request: web.Request) -> web.Response:
  try:
    from ai.version_info import check_update

    fetch = request.query.get("fetch", "1") not in ("0", "false", "no")
    return _json_response(check_update(fetch_remote=fetch))
  except Exception as e:
    cloudlog.error(f"aid: api_package_version error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_package_update(request: web.Request) -> web.Response:
  try:
    from ai.system.host_env import is_pc_dev
    from ai.version_info import run_package_update

    state = _get_state_reader().update(timeout=0)
    if state.is_driving and not is_pc_dev():
      return _json_response({"ok": False, "error": "行驶中无法更新 op助手，请停车后重试。"}, status=403)

    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    if not body.get("confirm"):
      return _json_response({
        "ok": True,
        "needs_confirmation": True,
        "hint": "将执行 git pull 并重新集成 openpilot。请 POST confirm=true。",
      })

    root = body.get("openpilot_root") or str(Path(__file__).resolve().parent.parent)
    result = run_package_update(openpilot_root=str(root))
    status = 200 if result.get("ok") else 500
    return _json_response(result, status=status)
  except Exception as e:
    cloudlog.error(f"aid: api_package_update error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_fork_detect(request: web.Request) -> web.Response:
  try:
    from ai.fork.analyze_fork import analyze_fork_with_ai
    from ai.fork.detect_fork import detect_fork

    root = Path(__file__).resolve().parent.parent
    do_analyze = request.query.get("analyze", "0") in ("1", "true", "yes")
    if do_analyze:
      result = await analyze_fork_with_ai(_PARAMS, root, force=request.query.get("force") in ("1", "true"))
      if result.get("ok"):
        result["detect"] = detect_fork(root)
      return _json_response(result, status=200 if result.get("ok") else 500)
    return _json_response(detect_fork(root))
  except Exception as e:
    cloudlog.error(f"aid: api_fork_detect error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_fork_analyze(request: web.Request) -> web.Response:
  try:
    from ai.fork.analyze_fork import analyze_fork_with_ai

    root = Path(__file__).resolve().parent.parent
    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    force = bool(body.get("force"))
    result = await analyze_fork_with_ai(_PARAMS, root, force=force)
    if result.get("ok") and result.get("analysis"):
      fid = result["analysis"].get("fork_identity") or result.get("identity", {}).get("fork_id")
      if fid:
        _PARAMS.put("ai_fork_id", str(fid))
        _PARAMS.put("ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
    return _json_response(result, status=200 if result.get("ok") else 500)
  except Exception as e:
    cloudlog.error(f"aid: api_fork_analyze error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_fork_sync(request: web.Request) -> web.Response:
  try:
    from ai.fork.fork_sync import generate_fork_drafts, list_fork_drafts

    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    if not body.get("confirm"):
      return _json_response({
        "ok": True,
        "needs_confirmation": True,
        "hint": "AI 将先阅读 openpilot 项目并分析 fork，再生成技能/文档草稿（需人工审核）。POST confirm=true。",
        "drafts": list_fork_drafts()[:5],
      })
    result = await generate_fork_drafts(
      _PARAMS,
      force_analyze=bool(body.get("force_analyze")),
    )
    if result.get("ok") and result.get("fork_id"):
      _PARAMS.put("ai_fork_id", str(result["fork_id"]))
      _PARAMS.put("ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
    return _json_response(result, status=200 if result.get("ok") else 500)
  except Exception as e:
    cloudlog.error(f"aid: api_fork_sync error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_fork_run_stream(request: web.Request) -> web.Response:
  """SSE stream: scan → analyze → draft with phase/reasoning/content events."""
  try:
    from ai.fork.fork_sync import run_fork_pipeline

    try:
      body = await request.json()
    except (json.JSONDecodeError, ValueError, aiohttp.ClientPayloadError):
      body = {}
    if not body.get("confirm"):
      return _json_response({
        "ok": False,
        "needs_confirmation": True,
        "error": "POST confirm=true to start fork analysis pipeline.",
      }, status=400)

    root = Path(__file__).resolve().parent.parent
    force = bool(body.get("force"))
    skip_draft = bool(body.get("skip_draft"))

    async def stream_response():
      response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache"},
      )
      await response.prepare(request)

      async def emit(event: dict[str, Any]) -> None:
        await response.write(_sse(event))

      result: dict[str, Any] = {"ok": False}
      try:
        result = await run_fork_pipeline(
          _PARAMS,
          root,
          force=force,
          skip_draft=skip_draft,
          emit=emit,
        )
        if result.get("ok") and result.get("fork_id"):
          _PARAMS.put("ai_fork_id", str(result["fork_id"]))
          _PARAMS.put("ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
        elif result.get("ok") and result.get("analysis"):
          fid = (result.get("analysis") or {}).get("fork_identity") or result.get("identity", {}).get("fork_id")
          if fid:
            _PARAMS.put("ai_fork_id", str(fid))
            _PARAMS.put("ai_fork_profile_applied", datetime.now(timezone.utc).isoformat())
      except Exception as e:
        cloudlog.error(f"aid: api_fork_run_stream pipeline error: {e}")
        await emit({"type": "error", "error": str(e)})
        await emit({"type": "done", "ok": False, "error": str(e)})
      await response.write_eof()
      return response

    return await stream_response()
  except Exception as e:
    cloudlog.error(f"aid: api_fork_run_stream error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_onboarding_complete(request: web.Request) -> web.Response:
  try:
    _PARAMS.put_bool("ai_first_run_done", True)
    config = _read_ai_config()
    return _json_response({
      "ok": True,
      "configured": config.is_configured,
      "configureError": config.configuration_error,
    })
  except Exception as e:
    return _json_response({"ok": False, "error": str(e)}, status=500)


async def api_integrate_openpilot(request: web.Request) -> web.Response:
  try:
    from ai.system.host_env import is_pc_dev
    from ai.install.integrate_openpilot import integrate

    state = _get_state_reader().update(timeout=0)
    if state.is_driving and not is_pc_dev():
      return _json_response({"ok": False, "error": "行驶中无法集成，请停车后重试。"}, status=403)
    root = Path(__file__).resolve().parent.parent
    result = integrate(root, root / "ai", force_compile=bool(request.query.get("force")))
    return _json_response(result, status=200 if result.get("ok") else 500)
  except Exception as e:
    cloudlog.error(f"aid: api_integrate_openpilot error: {e}")
    return _json_response({"ok": False, "error": str(e)}, status=500)


DEFAULT_PORT = 5090
WEB_DIR = Path(__file__).parent / "web" / "static"


async def index(request: web.Request) -> web.FileResponse:
  resp = web.FileResponse(WEB_DIR / "index.html")
  resp.headers["Cache-Control"] = "no-cache, must-revalidate"
  return resp


# -----------------------------------------------------------------------------
# App factory
# -----------------------------------------------------------------------------

def create_app() -> web.Application:
  import asyncio
  app = web.Application(middlewares=[ai_auth_middleware])
  app["params"] = _PARAMS

  async def _on_startup(application: web.Application) -> None:
    application["get_state_reader"] = _get_state_reader
    application["scheduler_task"] = asyncio.create_task(_scheduler_loop(application))
    application["status_watch_task"] = asyncio.create_task(_status_watch_loop(application))
    try:
      ensure_default_scheduler_tasks(_PARAMS)
      from ai.tools.rag_sync_tools import sync_knowledge_from_docs
      doc_sync = sync_knowledge_from_docs(_PARAMS, max_files=60)
      if doc_sync.get("indexed"):
        cloudlog.info(f"aid: doc sync indexed={doc_sync.get('indexed')}")
      application["memory_index_task"] = asyncio.create_task(_startup_memory_index())
    except Exception as e:
      cloudlog.warning(f"aid: default scheduler/doc sync skipped: {e}")
    try:
      from ai.tools.rag_seed import ensure_builtin_rag_docs
      from ai.tools.rag_extra_seed import ensure_extra_rag_docs
      result = ensure_builtin_rag_docs(_PARAMS)
      extra = ensure_extra_rag_docs(_PARAMS)
      if result.get("seeded") or result.get("refreshed") or extra.get("seeded"):
        cloudlog.info(
          f"aid: RAG seed builtin={result.get('seeded')} extra={extra.get('seeded')} v={extra.get('version')}"
        )
      application["rag_reindex_task"] = asyncio.create_task(_startup_rag_reindex())
    except Exception as e:
      cloudlog.warning(f"aid: builtin RAG seed skipped: {e}")

  async def _on_cleanup(application: web.Application) -> None:
    for key in ("scheduler_task", "status_watch_task"):
      task = application.get(key)
      if task:
        task.cancel()

  app.on_startup.append(_on_startup)
  app.on_cleanup.append(_on_cleanup)
  app.router.add_get("/", index)
  app.router.add_static("/static/", path=WEB_DIR, name="static")
  app.router.add_get("/api/ai/bootstrap", api_bootstrap)
  app.router.add_get("/api/ai/status", api_status)
  app.router.add_get("/api/ai/providers", api_providers)
  app.router.add_get("/api/ai/config", api_get_config)
  app.router.add_post("/api/ai/config", api_post_config)
  app.router.add_get("/api/ai/models", api_models)
  app.router.add_post("/api/ai/models", api_models)
  app.router.add_get("/api/ai/test_connection", api_test_connection)
  app.router.add_post("/api/ai/test_connection", api_test_connection)
  app.router.add_post("/api/ai/chat", api_chat)
  app.router.add_get("/api/ai/chat/jobs", api_chat_jobs)
  app.router.add_post("/api/ai/chat/jobs", api_chat_jobs)
  app.router.add_get("/api/ai/chat/jobs/{job_id}", api_chat_job_detail)
  app.router.add_delete("/api/ai/chat/jobs/{job_id}", api_chat_job_detail)
  app.router.add_post("/api/ai/shell", api_shell)
  app.router.add_get("/api/ai/state", api_state)
  app.router.add_get("/api/ai/usage", api_usage)
  app.router.add_get("/api/ai/skills", api_skills)
  app.router.add_post("/api/ai/skills", api_skills)
  app.router.add_get("/api/ai/tools", api_tools_meta)
  app.router.add_get("/api/ai/memory", api_memory)
  app.router.add_post("/api/ai/memory", api_memory)
  app.router.add_get("/api/ai/scheduler", api_scheduler)
  app.router.add_post("/api/ai/scheduler", api_scheduler)
  app.router.add_get("/api/ai/write/pending", api_write_pending)
  app.router.add_post("/api/ai/write/confirm", api_write_confirm)
  app.router.add_get("/api/ai/tune_passport", api_tune_passport)
  app.router.add_get("/api/ai/rag", api_rag)
  app.router.add_post("/api/ai/rag", api_rag)
  app.router.add_get("/api/ai/sessions", api_sessions)
  app.router.add_post("/api/ai/sessions", api_sessions)
  app.router.add_get("/api/ai/dev-assets", api_dev_assets)
  app.router.add_get("/api/ai/dev-assets/{kind}/{name}", api_dev_assets)
  app.router.add_get("/api/ai/pc-sessions", api_pc_sessions)
  app.router.add_get("/api/ai/workflows", api_workflows)
  app.router.add_get("/api/ai/notifications", api_notifications)
  app.router.add_post("/api/ai/notifications", api_notifications)
  app.router.add_get("/api/ai/adaptation/{project_id}/bundle", api_adaptation_bundle)
  app.router.add_get("/api/ai/package/version", api_package_version)
  app.router.add_post("/api/ai/package/update", api_package_update)
  app.router.add_get("/api/ai/fork/detect", api_fork_detect)
  app.router.add_post("/api/ai/fork/analyze", api_fork_analyze)
  app.router.add_post("/api/ai/fork/sync", api_fork_sync)
  app.router.add_post("/api/ai/fork/run", api_fork_run_stream)
  app.router.add_post("/api/ai/onboarding/complete", api_onboarding_complete)
  app.router.add_post("/api/ai/integrate", api_integrate_openpilot)
  register_cabana_routes(app, WEB_DIR)
  register_sync_routes(app)
  from ai.tsk_routes import register_tsk_routes
  register_tsk_routes(app)
  return app


def main() -> None:
  parser = argparse.ArgumentParser(description="Openpilot AI Agent service")
  parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port")
  parser.add_argument("--host", type=str, default="0.0.0.0", help="Listen host")
  args = parser.parse_args()

  from ai.tsk_routes import init_tsk_for_aid
  init_tsk_for_aid(args.port)

  app = create_app()
  cloudlog.info(f"aid: starting on {args.host}:{args.port} (SecOC in settings sidebar)")
  web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
  main()
