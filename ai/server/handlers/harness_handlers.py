"""WorkBuddy harness API — transcript, audit, config."""

from __future__ import annotations

from aiohttp import web

from openpilot.common.params import Params

from ai.common.storage import read_param, read_param_bool, write_param, write_param_bool
from ai.tools.domains.platform.audit_store import list_audit_trail, verify_audit_chain
from ai.tools.domains.platform.transcript_store import list_events, recover_partial
from ai.tools.deferred_loading import deferred_loading_enabled
from ai.tools.result_externalize import externalize_enabled, threshold_bytes
from ai.common.model_tier import normalize_tier


async def api_harness_config(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  params: Params = request.app.get("params") or Params()
  if request.method == "GET":
    return json_response({
      "ok": True,
      "deferredTools": deferred_loading_enabled(params),
      "externalizeResults": externalize_enabled(params),
      "externalizeThreshold": threshold_bytes(params),
      "modelTier": normalize_tier(str(read_param(params, "ai_model_tier", "auto") or "auto")),
    })
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    body = {}
  if "deferredTools" in body:
    write_param_bool(params, "ai_deferred_tools", bool(body["deferredTools"]))
  if "externalizeResults" in body:
    write_param_bool(params, "ai_externalize_results", bool(body["externalizeResults"]))
  if "externalizeThreshold" in body:
    try:
      val = max(1024, min(int(body["externalizeThreshold"]), 512_000))
      write_param(params, "ai_externalize_threshold", str(val))
    except (TypeError, ValueError):
      pass
  if "modelTier" in body:
    write_param(params, "ai_model_tier", normalize_tier(str(body["modelTier"])))
  return json_response({
    "ok": True,
    "deferredTools": deferred_loading_enabled(params),
    "externalizeResults": externalize_enabled(params),
    "externalizeThreshold": threshold_bytes(params),
    "modelTier": normalize_tier(str(read_param(params, "ai_model_tier", "auto") or "auto")),
  })


async def api_audit_trail(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  limit = int(request.query.get("limit", "50") or "50")
  tool = str(request.query.get("tool") or "").strip()
  since_ms = int(request.query.get("since") or request.query.get("sinceMs") or "0" or "0")
  if tool or since_ms > 0:
    from ai.tools.domains.platform.harness_db import query_audit
    data = query_audit(limit=limit, tool=tool, since_ms=since_ms)
    chain = verify_audit_chain(limit=min(limit, 200))
    data["chain"] = chain
    data["chain_ok"] = chain.get("ok") and not chain.get("broken")
    return json_response(data)
  data = list_audit_trail(limit=limit)
  chain = verify_audit_chain(limit=min(limit, 200))
  data["chain"] = chain
  return json_response(data)


async def api_usage_summary(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  group_by = str(request.query.get("groupBy") or "model").strip()
  since_ts = int(request.query.get("since") or "0" or "0")
  limit = int(request.query.get("limit", "20") or "20")
  from ai.tools.domains.platform.harness_db import query_usage_summary
  return json_response(query_usage_summary(group_by=group_by, since_ts=since_ts, limit=limit))


async def api_profile_sync(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.tools.domains.platform.profile_sync import (
    build_manifest,
    get_stored_manifest,
    merge_remote_manifest,
  )
  params: Params = request.app.get("params") or Params()
  if request.method == "GET":
    return json_response({
      "ok": True,
      "manifest": build_manifest(params),
      "stored": get_stored_manifest(params),
    })
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    body = {}
  remote = body.get("manifest") or body
  mode = str(body.get("mode") or "merge")
  return json_response(merge_remote_manifest(params, remote, mode=mode))


async def api_workflows_custom(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.tools.domains.platform.workflow_custom import load_custom, save_custom, list_all_workflows
  if request.method == "GET":
    return json_response({
      "ok": True,
      "custom": load_custom(),
      "all": list_all_workflows(),
    })
  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  workflows = body.get("workflows") if isinstance(body, dict) else body
  if not isinstance(workflows, dict):
    return json_response({"ok": False, "error": "workflows object required"}, status=400)
  result = save_custom(workflows)
  status = 200 if result.get("ok") else 400
  return json_response(result, status=status)


async def api_transcript(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  session_id = str(
    request.query.get("sessionId") or request.query.get("session_id") or ""
  ).strip()
  if not session_id:
    return json_response({"ok": False, "error": "sessionId required"}, status=400)
  if request.path.endswith("/recover"):
    return json_response(recover_partial(session_id))
  limit = int(request.query.get("limit", "200") or "200")
  offset = int(request.query.get("offset", "0") or "0")
  return json_response(list_events(session_id, limit=limit, offset=offset))
