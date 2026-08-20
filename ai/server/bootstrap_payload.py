"""Bootstrap payload builder — fast first paint, optional in-memory cache."""

from __future__ import annotations

import time
from typing import Any

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

from ai.agents.config import agents_enabled_payload
from ai.agents.office import office_snapshot as get_office_snapshot
from ai.agents.registry import list_agents
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
from ai.server.deps import mask_key, openpilot_root, read_ai_config, read_param_bool_val, read_param_str
from ai.core.llm.embedding import DEFAULT_EMBEDDING_MODELS, load_embedding_config
from ai.core.llm.model_accounts import hub_for_api
from ai.core.llm.model_router import fallbacks_for_api
from ai.core.wspace.persona import ensure_default_persona
from ai.skills.loader import list_skills, load_enabled_skill_ids
from ai.system.admin import is_admin_mode
from ai.system.host_env import get_host_environment
from ai.tools.agent_tools import tool_meta_for_host
from ai.tools.consumer_tools import consumer_bootstrap_payload
from ai.tools.notifications import list_notifications
from ai.tools.workflows import list_workflows

_CACHE: dict[str, Any] | None = None
_CACHE_AT = 0.0
_CACHE_KEY = ""
_CACHE_TTL_SEC = 15.0


def invalidate_bootstrap_cache() -> None:
  global _CACHE
  _CACHE = None


def _cache_key(params: Params) -> str:
  try:
    from ai.common.config_store import get_config_store
    store = get_config_store()
    return str(getattr(store, "_mtime", 0) or store.get("_version", 0) or "")
  except Exception:
    return read_param_str("ai_fork_id") or "0"


def _cached_fork_summary() -> dict[str, Any] | None:
  fid = (read_param_str("ai_fork_id") or "").strip()
  if not fid:
    return None
  return {
    "ok": True,
    "mode": "param_cache",
    "fork_id": fid,
    "fork_label": fid,
    "confidence": 0.5,
    "cached": True,
  }


def build_bootstrap_payload(
  params: Params,
  *,
  state: Any,
  lite: bool = True,
) -> dict[str, Any]:
  global _CACHE, _CACHE_AT, _CACHE_KEY

  key = _cache_key(params)
  now = time.monotonic()
  if _CACHE is not None and _CACHE_KEY == key and now - _CACHE_AT < _CACHE_TTL_SEC:
    return _CACHE

  ensure_default_persona(params)

  from ai.tools.memory_store import sync_vehicle_profile_from_state

  sync_vehicle_profile_from_state(
    params,
    brand=state.brand or "",
    car_fingerprint=state.car_fingerprint or "",
  )
  config = read_ai_config()
  embed_cfg = load_embedding_config(params)
  skills_on = load_enabled_skill_ids(params)
  from ai.infra.timezone import read_ai_timezone_name

  tz_name = read_ai_timezone_name(params)
  first_run_done = read_param_bool_val("ai_first_run_done")

  fork_detected: dict[str, Any] | None = None
  if lite:
    fork_detected = _cached_fork_summary()
  else:
    try:
      from ai.fork.detect_fork import detect_fork

      fork_detected = detect_fork(openpilot_root())
    except Exception as e:
      cloudlog.warning(f"aid: bootstrap fork detect skipped: {e}")
      fork_detected = {"ok": False}

  bootstrap_models: list[dict[str, Any]] = [
    {"id": mid} for mid in (AI_PROVIDER_MODEL_CATALOG.get(config.provider) or []) if mid
  ]
  models_source = "catalog"
  if config.is_configured and config.model:
    known = {m.get("id") for m in bootstrap_models}
    if config.model not in known:
      bootstrap_models.insert(0, {"id": config.model})

  payload: dict[str, Any] = {
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
      "apiKey": config.api_key,
      "baseUrl": config.base_url,
      "systemPrompt": config.system_prompt,
      "temperature": config.temperature,
      "topP": config.top_p,
      "maxTokens": config.max_tokens,
      "thinkingEnabled": config.thinking_enabled,
      "thinkingKeep": config.thinking_keep,
      "timezone": tz_name,
      "configured": config.is_configured,
      "configureError": config.configuration_error,
      "embeddingProvider": embed_cfg.provider,
      "embeddingModel": embed_cfg.model,
      "embeddingConfigured": embed_cfg.is_configured,
      "modelHub": hub_for_api(params, mask_keys=False),
      "modelFallbacks": fallbacks_for_api(params, config),
    },
    "embeddingDefaults": DEFAULT_EMBEDDING_MODELS,
    "embeddingProviders": AI_EMBEDDING_PROVIDERS,
    "embeddingProviderLabels": AI_EMBEDDING_PROVIDER_LABELS,
    "embeddingModelCatalog": AI_EMBEDDING_MODEL_CATALOG,
    "embeddingSameModeCatalog": AI_SAME_MODE_EMBEDDING_MODELS,
    "tools": tool_meta_for_host(),
    "hostEnvironment": get_host_environment(),
    "adminMode": is_admin_mode(params),
    "onboarding": {
      "firstRunDone": first_run_done,
      "showWizard": not config.is_configured,
    },
    "fork": fork_detected if fork_detected and fork_detected.get("ok") else None,
    "consumer": consumer_bootstrap_payload(),
    "notifications": list_notifications(unread_only=True).get("notifications", [])[:5],
  }

  if lite:
    payload["bootstrapLite"] = True
  else:
    payload["skills"] = list_skills()
    payload["skillsEnabled"] = sorted(skills_on) if skills_on is not None else None
    payload["workflows"] = list_workflows()
    payload["agents"] = list_agents(include_orchestrator=True)
    payload["agentsConfig"] = agents_enabled_payload(params)
    payload["office"] = get_office_snapshot()

  _CACHE = payload
  _CACHE_AT = now
  _CACHE_KEY = key
  return payload
