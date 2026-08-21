"""Phase-2 API handlers — schema, device trust, canvas, queue."""

from __future__ import annotations

from aiohttp import web

from openpilot.common.params import Params

from ai.canvas.store import list_artifacts
from ai.core.chat.command_queue import list_queued
from ai.core.sync.device_trust import (
  check_device_trust,
  list_paired_devices,
  pair_device,
  revoke_device,
  touch_device,
)
from ai.core.sync.protocol import get_protocol_schema


async def api_sync_schema(_request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  return json_response({"ok": True, "schema": get_protocol_schema()})


async def api_device_trust(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  params: Params = request.app.get("params") or Params()
  status = check_device_trust(request, params)
  touch_device(params, status["deviceId"], status.get("fingerprint", ""))
  return json_response({
    "ok": True,
    **status,
    "devices": list_paired_devices(params),
    "queue": list_queued(),
  })


async def api_device_pair(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  params: Params = request.app.get("params") or Params()
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    body = {}
  result = pair_device(
    params,
    device_id=str(body.get("deviceId") or body.get("device_id") or "").strip(),
    fingerprint=str(body.get("fingerprint") or "").strip(),
    label=str(body.get("label") or "").strip(),
    pin=str(body.get("pin") or "").strip(),
  )
  status = 200 if result.get("ok") else 400
  return json_response(result, status=status)


async def api_device_revoke(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  params: Params = request.app.get("params") or Params()
  device_id = request.match_info.get("device_id", "")
  result = revoke_device(params, device_id)
  status = 200 if result.get("ok") else 404
  return json_response(result, status=status)


async def api_canvas(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  session_id = str(request.query.get("sessionId") or request.query.get("session_id") or "").strip()
  limit = int(request.query.get("limit", "10") or "10")
  return json_response({
    "ok": True,
    "sessionId": session_id,
    "artifacts": list_artifacts(session_id, limit=min(limit, 50)),
  })


async def api_workspace(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.core.wspace.store import list_workspace_files, read_workspace_file

  key = str(request.query.get("key") or "").strip()
  if key:
    return json_response({
      "ok": True,
      "key": key,
      "content": read_workspace_file(key),
    })
  return json_response({"ok": True, "files": list_workspace_files()})


async def api_workspace_write(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.core.wspace.store import write_workspace_file

  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    body = {}
  key = str(body.get("key") or "").strip()
  if not key:
    return json_response({"ok": False, "error": "key required"}, status=400)
  return json_response(write_workspace_file(key, str(body.get("content") or "")))


async def api_usage_detail(request: web.Request) -> web.Response:
  from ai.server.deps import json_response, params
  from ai.core.llm.usage import load_embedding_usage, load_usage

  p = request.app.get("params") or params()
  usage = load_usage(p)
  embedding_usage = load_embedding_usage(p)
  return json_response({
    "ok": True,
    "usage": usage,
    "embeddingUsage": embedding_usage,
    "byProvider": usage.get("by_provider") or {},
    "byModel": usage.get("by_model") or {},
    "embeddingByProvider": embedding_usage.get("by_provider") or {},
    "embeddingByModel": embedding_usage.get("by_model") or {},
    "recent": (usage.get("history") or [])[-20:],
    "embeddingRecent": (embedding_usage.get("history") or [])[-20:],
  })


async def api_platform_sessions_search(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.tools.session_index import search_sessions

  q = str(request.query.get("q") or request.query.get("query") or "").strip()
  limit = int(request.query.get("limit", "8") or "8")
  return json_response(search_sessions(q, limit=limit))


async def api_platform_mcp(request: web.Request) -> web.Response:
  from ai.server.deps import json_response, params
  from ai.mcp.host import list_mcp_servers, upsert_mcp_server, discover_mcp_tools

  p = request.app.get("params") or params()
  if request.method == "GET":
    return json_response(list_mcp_servers(p))
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    body = {}
  op = str(body.get("operation") or "upsert")
  if op == "discover":
    return json_response(await discover_mcp_tools(p, str(body.get("server_id") or "")))
  return json_response(upsert_mcp_server(p, body))


async def api_platform_learned_skills(request: web.Request) -> web.Response:
  from ai.server.deps import json_response, params
  from ai.tools.skill_learning import approve_learned_skill, list_learned_skills

  p = request.app.get("params") or params()
  if request.method == "GET":
    return json_response(list_learned_skills(p))
  try:
    body = await request.json()
  except Exception:
    body = {}
  skill_id = str((body or {}).get("skill_id") or (body or {}).get("skillId") or "")
  if not skill_id:
    return json_response({"ok": False, "error": "skill_id required"}, status=400)
  return json_response(approve_learned_skill(p, skill_id))


async def api_platform_toolsets(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  from ai.tools.toolsets import list_toolsets

  return json_response({"ok": True, "toolsets": list_toolsets()})


async def api_platform_backup(request: web.Request) -> web.Response:
  from ai.server.deps import json_response, params
  from ai.tools.platform_backup import (
    backup_manifest,
    build_platform_bundle,
    export_platform_bundle,
    parse_uploaded_bundle,
    parse_uploaded_payload,
    restore_platform_bundle,
  )

  p = request.app.get("params") or params()
  if request.method == "GET":
    view = str(request.query.get("view") or "manifest").strip()
    if view == "bundle":
      include_secrets = str(request.query.get("include_secrets") or "").lower() in ("1", "true", "yes")
      return json_response(build_platform_bundle(p, include_secrets=include_secrets))
    return json_response({"ok": True, "manifest": backup_manifest(p)})

  content_type = (request.content_type or "").lower()
  if content_type.startswith("multipart/"):
    reader = await request.multipart()
    file_bytes: bytes | None = None
    mode = "merge"
    confirm = False
    async for part in reader:
      if part.name == "file":
        file_bytes = await part.read()
      elif part.name == "mode":
        mode = (await part.text()) or "merge"
      elif part.name == "confirm":
        confirm = (await part.text() or "").lower() in ("1", "true", "yes")
    if file_bytes is None:
      return json_response({"ok": False, "error": "backup file required"}, status=400)
    parsed = parse_uploaded_payload(file_bytes)
    if not parsed.get("ok"):
      return json_response(parsed, status=400)
    return json_response(restore_platform_bundle(
      p,
      parsed,
      mode=str(mode or "merge"),
      confirm=confirm,
    ))

  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    body = {}
  op = str(body.get("operation") or "export").strip()

  if op == "export":
    include_secrets = bool(body.get("include_secrets"))
    result = export_platform_bundle(p, include_secrets=include_secrets)
    if body.get("direct_download"):
      dl = result.get("download") or {}
      path_str = dl.get("path")
      name = str(dl.get("filename") or "backup.opbak")
      if path_str:
        from pathlib import Path
        from aiohttp import web

        path = Path(path_str)
        if path.is_file():
          return web.FileResponse(
            path,
            headers={
              "Content-Disposition": f'attachment; filename="{name}"',
              "Content-Type": "application/gzip",
            },
          )
    return json_response(result)

  if op == "restore":
    bundle = body.get("bundle")
    if isinstance(bundle, str):
      parsed = parse_uploaded_payload(bundle)
      if not parsed.get("ok"):
        return json_response(parsed, status=400)
      bundle = parsed
    return json_response(restore_platform_bundle(
      p,
      bundle if isinstance(bundle, dict) else {},
      mode=str(body.get("mode") or "merge"),
      sections=body.get("sections") if isinstance(body.get("sections"), list) else None,
      confirm=bool(body.get("confirm")),
    ))

  return json_response({"ok": False, "error": f"unknown operation: {op}"}, status=400)


async def api_platform_workspace_health(request: web.Request) -> web.Response:
  from ai.server.deps import json_response, params
  from ai.tools.workspace_enrich import bootstrap_workspace_templates, workspace_health

  p = request.app.get("params") or params()
  if request.method == "GET":
    return json_response(workspace_health())

  try:
    body = await request.json()
  except Exception:
    body = {}
  op = str((body or {}).get("operation") or "bootstrap")
  if op == "bootstrap":
    return json_response(bootstrap_workspace_templates(force=bool((body or {}).get("force"))))
  return json_response({"ok": False, "error": "unknown operation"}, status=400)


async def api_platform_evolution(request: web.Request) -> web.Response:
  from ai.server.deps import json_response, params
  from ai.core.runtime.evolution_pipeline import pipeline_log, run_evolution_pipeline_manual
  from ai.tools.skill_evolution import analyze_execution_traces, evolution_status, evolve_skill_proposal

  p = request.app.get("params") or params()
  if request.method == "GET":
    view = str(request.query.get("view") or "status").strip()
    if view == "traces":
      limit = int(request.query.get("limit", "8") or "8")
      return json_response(analyze_execution_traces(p, limit=limit))
    if view == "pipeline":
      return json_response(pipeline_log(p))
    return json_response(evolution_status(p))

  try:
    body = await request.json()
  except Exception:
    body = {}
  op = str((body or {}).get("operation") or "propose").strip()
  if op == "gepa":
    from ai.evolution.gepa_engine import evolve_skill_gepa, gepa_status
    if str((body or {}).get("dry_run") or "").lower() in ("1", "true", "yes"):
      from ai.evolution.config import EvolutionRunConfig
      run = EvolutionRunConfig.from_params(
        skill_id=str((body or {}).get("skill_id") or (body or {}).get("skillId") or "memory-protocol"),
        dry_run=True,
      )
      return json_response(await evolve_skill_gepa(p, skill_id=run.skill_id, run=run))
    if str((body or {}).get("status") or "").lower() in ("1", "true"):
      return json_response(gepa_status())
    from ai.evolution.config import EvolutionRunConfig
    from ai.tools.skill_evolution import analyze_execution_traces
    skill_id = str((body or {}).get("skill_id") or (body or {}).get("skillId") or (body or {}).get("focus") or "memory-protocol")
    run = EvolutionRunConfig.from_params(
      skill_id=skill_id,
      focus=str((body or {}).get("focus") or ""),
      eval_source=str((body or {}).get("eval_source") or (body or {}).get("evalSource") or "sessiondb"),
      iterations=int((body or {}).get("iterations") or 0) or None,
    )
    traces = analyze_execution_traces(p, limit=12)
    return json_response(await evolve_skill_gepa(
      p,
      skill_id=skill_id,
      run=run,
      traces=traces.get("traces") or [],
    ))
  if op == "pipeline":
    return json_response(await run_evolution_pipeline_manual(
      p,
      session_id=str((body or {}).get("session_id") or (body or {}).get("sessionId") or ""),
      focus=str((body or {}).get("focus") or ""),
    ))
  return json_response(await evolve_skill_proposal(
    p,
    title=str((body or {}).get("title") or ""),
    trace_session_id=str((body or {}).get("trace_session_id") or (body or {}).get("sessionId") or ""),
    focus=str((body or {}).get("focus") or ""),
    body=str((body or {}).get("body") or ""),
    use_llm=bool((body or {}).get("use_llm", True)),
  ))


async def api_scheduler_nl(request: web.Request) -> web.Response:
  from ai.server.deps import json_response, params
  from ai.tools.scheduler import upsert_task_from_nl

  try:
    body = await request.json()
  except Exception:
    body = {}
  text = str((body or {}).get("text") or (body or {}).get("prompt") or "").strip()
  if not text:
    return json_response({"ok": False, "error": "text required"}, status=400)
  return json_response(upsert_task_from_nl(request.app.get("params") or params(), text))
