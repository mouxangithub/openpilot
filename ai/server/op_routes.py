"""REST/ACP route setup for the AI OP assistant P0 harness.

Routes are independent from the production server to avoid openpilot/cereal
import dependencies during local development and testing.

Also provides frontend-compatible fallbacks for the existing OP 助手 web UI
so the page can boot and chat in local-dev mode.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiohttp import web
from openpilot.common.params import Params

from ai.audit.log import AuditLog
from ai.core.agent.simple_loop import SimpleAgentLoop
from ai.core.config.schema import AIOPConfig, ConversationConfig, load_config
from ai.core.llm.client import AIConfig
from ai.core.session.manager import SessionManager
from ai.permissions.hitl import HumanInLoop
from ai.permissions.service import SandboxPolicyService
from ai.providers.offline import OfflineProvider
from ai.tools.dispatch import ToolDispatcher
from ai.tools.spill import SpillWaterfall
from ai.tools.vehicle.params import VehicleParams
from ai.tools.vehicle.schemas import build_vehicle_handlers, build_vehicle_tool_specs

# Shared chat handling logic (A-P0.5): the local-dev runner + reusable
# chat/completion handlers live in one module so this router only binds
# endpoints. Per-router authentication stays at the binding/middleware layer.
from ai.server.handlers.chat import (
  api_chat_completions_local_dev,
  api_chat_local_dev,
  extract_prompt,
  run_chat_local_dev,
)


def _cwd_from_request(request: web.Request) -> str:
  body: dict[str, Any] = {}
  if request.can_read_body:
    try:
      body = request.query
    except Exception:
      pass
  return str(body.get("cwd") or request.query.get("cwd") or str(Path.cwd()))


# The local-dev Agent construction + chat runner now live in
# ai.server.handlers.chat (A-P0.5). Keep the historical private names as thin
# aliases so existing references (jobs handler, tests) keep working without
# duplicating the logic here.
_extract_prompt = extract_prompt
_run_chat_local_dev = run_chat_local_dev


async def health(_request: web.Request) -> web.Response:
  return web.json_response({"ok": True, "service": "ai-op-assistant-enhanced"})


async def api_config_diagnose(request: web.Request) -> web.Response:
  config = request.app.get("config") or AIOPConfig()
  return web.json_response({
    "ok": True,
    "config": config.to_dict(),
    "diagnostics": {
      "agent_loop_enabled": config.conversation.ai_use_agent_loop,
      "audit_enabled": config.dev_diagnostics.enable_audit,
      "automations_enabled": config.agent_scheduler.automations_enabled,
    },
  })


async def api_config_get(request: web.Request) -> web.Response:
  config = request.app.get("config") or AIOPConfig()
  return web.json_response({
    "ok": True,
    "revision": 1,
    "config": config.to_dict(),
  })


async def api_config_post(request: web.Request) -> web.Response:
  body = await request.json()
  config = request.app.get("config") or AIOPConfig()
  raw = body.get("config") or body
  for section, values in raw.items():
    if hasattr(config, section) and isinstance(values, dict):
      current = getattr(config, section)
      for k, v in values.items():
        if hasattr(current, k):
          setattr(current, k, v)
  return web.json_response({"ok": True, "revision": 2, "config": config.to_dict()})


async def api_status(_request: web.Request) -> web.Response:
  return web.json_response({
    "ok": True,
    "service": "ai-op-assistant-enhanced",
    "mode": "local-dev",
    "driving": False,
    "state": {"enabled": False, "v_ego_m_s": 0.0, "ignition": True},
    "model": "offline-mock",
    "provider": "offline",
    "configured": True,
  })


async def api_bootstrap(request: web.Request) -> web.Response:
  lite = request.query.get("lite") == "1"
  data = {
    "ok": True,
    "service": "ai-op-assistant-enhanced",
    "mode": "local-dev",
    "config": AIOPConfig().to_dict(),
    "providers": ["offline"],
    "models": [{"id": "offline-mock", "name": "Offline Mock"}],
  }
  if not lite:
    data["agents"] = []
    data["skills"] = []
    data["tools"] = []
  return web.json_response(data)


async def api_providers(_request: web.Request) -> web.Response:
  return web.json_response({
    "ok": True,
    "providers": [
      {"id": "offline", "name": "Offline Mock", "configured": True},
    ],
  })


_JOBS: dict[str, dict[str, Any]] = {}


async def api_chat_jobs_create(request: web.Request) -> web.Response:
  body = await request.json()
  job_id = uuid.uuid4().hex
  session_id = str(body.get("session_id") or body.get("sessionId") or "").strip()
  _JOBS[job_id] = {
    "id": job_id,
    "status": "pending",
    "session_id": session_id,
    "messages": body.get("messages", []),
    "created_at": time.time(),
    "result": None,
  }
  # Execute synchronously for local-dev simplicity.
  config = AIOPConfig(conversation=ConversationConfig(ai_sandbox_mode="workspace_write"))
  cwd = "C:/Users/mouxan/AppData/Local/Temp/ai_op_job"
  prompt = _extract_prompt(_JOBS[job_id]["messages"])
  result = await _run_chat_local_dev(cwd, config, body, prompt or "help", session_id)
  _JOBS[job_id]["status"] = "done"
  _JOBS[job_id]["result"] = result
  return web.json_response({"ok": True, "job_id": job_id, "jobId": job_id, "status": "done", "data": result})


async def api_chat_jobs_get(request: web.Request) -> web.Response:
  job_id = request.match_info.get("job_id", "")
  since = int(request.query.get("since", "0") or "0")
  job = _JOBS.get(job_id, {"status": "not_found"})
  events: list[dict[str, Any]] = []
  if job.get("status") == "done":
    events.append({"type": "done", "data": job.get("result")})
  return web.json_response({"ok": True, "job_id": job_id, "status": job.get("status"), "events": events, "since": since})


async def api_chat_jobs_list(request: web.Request) -> web.Response:
  session_id = request.query.get("sessionId", "")
  jobs = [j for j in _JOBS.values() if not session_id or j.get("session_id") == session_id]
  return web.json_response({"ok": True, "jobs": jobs})


async def api_chat_jobs_stream(request: web.Request) -> web.Response:
  job_id = request.match_info.get("job_id", "")
  job = _JOBS.get(job_id, {"status": "not_found"})
  body = json.dumps({"ok": True, "job_id": job_id, "status": job.get("status"), "events": [{"type": "done", "data": job.get("result")}]})
  return web.Response(
    body=b"data: " + body.encode("utf-8") + b"\n\n",
    content_type="text/event-stream",
    headers={"Cache-Control": "no-cache"},
  )


async def api_write_confirm(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, "confirmed": True})


# Chat endpoints now delegate to the shared handlers in ai.server.handlers.chat
# (A-P0.5). Keeping the module-level names preserves the existing binding in
# setup_routes while removing the duplicated handler bodies.
api_chat = api_chat_local_dev
api_chat_completions = api_chat_completions_local_dev


async def api_session_resume(request: web.Request) -> web.Response:
  body = await request.json()
  session_id = str(body.get("session_id") or "")
  cwd = str(body.get("cwd") or str(Path.cwd()))
  sessions = SessionManager(cwd)
  session, repaired = sessions.resume(session_id)
  return web.json_response({"ok": True, "session": session.to_dict(), "repaired": repaired})


async def api_sessions(request: web.Request) -> web.Response:
  cwd = _cwd_from_request(request)
  sessions = SessionManager(cwd)
  compact = request.query.get("compact") == "1"
  contact = request.query.get("contact") == "1"
  session_id = request.query.get("session_id", "")
  if session_id:
    session = sessions.storage.load_session(session_id)
    return web.json_response({"ok": True, "sessions": [session.to_dict()] if session else []})
  if compact or contact:
    return web.json_response({"ok": True, "sessions": []})
  # Return at least a default session so the frontend has something to display.
  session = sessions.create(title="本地会话")
  return web.json_response({"ok": True, "sessions": [session.to_dict()]})


async def api_sessions_create(request: web.Request) -> web.Response:
  body = await request.json()
  cwd = _cwd_from_request(request)
  sessions = SessionManager(cwd)
  session = sessions.create(title=body.get("title", "新会话"))
  return web.json_response({"ok": True, "session": session.to_dict()})


async def api_session_log(request: web.Request) -> web.Response:
  session_id = request.match_info.get("session_id", "")
  cwd = _cwd_from_request(request)
  sessions = SessionManager(cwd)
  session = sessions.storage.load_session(session_id)
  if session is None:
    return web.json_response({"ok": False, "error": "session not found"}, status=404)
  events = sessions.storage.read_transcript(session)
  return web.json_response({"ok": True, "events": [ev.to_dict() for ev in events]})


async def api_audit_verify(request: web.Request) -> web.Response:
  cwd = str(request.query.get("cwd") or str(Path.cwd()))
  audit = AuditLog.for_session(cwd)
  ok, message = audit.verify()
  return web.json_response({"ok": ok, "message": message})


async def api_notifications(request: web.Request) -> web.Response:
  from ai.tools.domains.platform.notifications import list_notifications, mark_notifications_read

  if request.method == "POST":
    return web.json_response(mark_notifications_read())
  unread = request.query.get("unread")
  return web.json_response(list_notifications(unread_only=unread is not None))


async def api_sync_ws(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse()
  await ws.prepare(request)
  async for msg in ws:
    if msg.type == web.WSMsgType.TEXT:
      await ws.send_json({"type": "pong", "payload": msg.data})
  return ws


async def api_rag(request: web.Request) -> web.Response:
  if request.method == "POST":
    try:
      body = await request.json()
    except json.JSONDecodeError:
      return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    op = str(body.get("operation") or "").strip()
    if op == "reindex":
      return web.json_response({"ok": True, "jobId": f"reindex_{uuid.uuid4().hex[:8]}", "status": "queued"})
    if op == "wiki_ingest":
      return web.json_response({"ok": True, "jobId": f"wiki_{uuid.uuid4().hex[:8]}", "status": "queued"})
    return web.json_response({"ok": False, "error": f"unknown operation: {op}"}, status=400)

  # Try to read real doc list if available; otherwise return empty defaults.
  try:
    from ai.tools.domains.core.rag_store import list_docs
    docs = list_docs()
    embedded = [d for d in docs if d.get("embedded")]
    return web.json_response({
      "ok": True,
      "count": len(docs),
      "embedded_docs": len(embedded),
      "vector_chunks": sum(d.get("chunks", 0) for d in embedded),
    })
  except Exception:
    return web.json_response({"ok": True, "count": 0, "embedded_docs": 0, "vector_chunks": 0})


async def api_scheduler(request: web.Request) -> web.Response:
  from ai.tools.domains.platform.scheduler import list_scheduled_tasks, schedule_task, upsert_task_from_nl, remove_task

  if request.method == "GET":
    return web.json_response(list_scheduled_tasks(Params()))
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  task_id = body.get("task_id") or body.get("id")
  if body.get("delete") and task_id:
    return web.json_response(remove_task(Params(), str(task_id)))
  if body.get("nl"):
    return web.json_response(upsert_task_from_nl(Params(), str(body.get("name") or "")))
  return web.json_response(schedule_task(Params(), body))


async def api_tools_meta(request: web.Request) -> web.Response:
  from ai.tools.agent_tools import build_tool_schemas
  from ai.tools.domains.platform.tool_ui_meta import enrich_tool_meta_for_ui

  schemas = build_tool_schemas()
  meta: dict[str, dict[str, Any]] = {}
  for s in schemas:
    fn = s.get("function", {})
    name = str(fn.get("name") or "")
    if not name:
      continue
    meta[name] = {
      "name": name,
      "label": name,
      "description": fn.get("description", ""),
      "group": "read",
      "default_enabled": True,
      "driving": True,
    }
  return web.json_response({"ok": True, "tools": enrich_tool_meta_for_ui(meta)})


async def api_skills_registry(request: web.Request) -> web.Response:
  from ai.skill.registry import get_skill_registry

  registry = get_skill_registry()
  skills = [
    {
      "id": s.id,
      "name": s.name,
      "version": getattr(s, "version", ""),
      "rank": getattr(s, "rank", 600),
      "scope": getattr(s, "scope", "global"),
      "description": getattr(s, "description", ""),
    }
    for s in registry.list_skills_sorted()
  ]
  return web.json_response({"ok": True, "skills": skills})


async def api_tool_invoke(request: web.Request) -> web.Response:
  """Generic platform tool invocation endpoint for the web tools panel."""
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  tool_name = str(body.get("tool") or "").strip()
  args = body.get("args") if isinstance(body.get("args"), dict) else {}
  if not tool_name:
    return web.json_response({"ok": False, "error": "tool required"}, status=400)

  from ai.tools.domains.platform.platform_extensions import make_platform_handlers
  params = Params()
  handlers = make_platform_handlers(params=params)
  handler = handlers.get(tool_name)
  if handler is None:
    return web.json_response({"ok": False, "error": f"tool '{tool_name}' not found"}, status=404)
  try:
    if asyncio.iscoroutinefunction(handler):
      result = await handler(args)
    else:
      result = handler(args)
    if asyncio.iscoroutine(result):
      result = await result
    return web.json_response(result if isinstance(result, dict) else {"ok": True, "result": result})
  except Exception as e:
    return web.json_response({"ok": False, "error": str(e)})


async def api_files_content(request: web.Request) -> web.Response:
  """Read or write repo file content for the tools panel."""
  from ai.tools.file_search import read_repo_file_snippet

  if request.method == "GET":
    path = str(request.query.get("path") or "")
    if not path.strip():
      return web.json_response({"ok": False, "error": "path is required"}, status=400)
    return web.json_response(read_repo_file_snippet(path, max_chars=48000))

  if request.method == "POST":
    try:
      body = await request.json()
    except json.JSONDecodeError:
      return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    path = str(body.get("path") or "")
    content = body.get("content")
    if not path.strip() or not isinstance(content, str):
      return web.json_response({"ok": False, "error": "path and content required"}, status=400)

    root = Path.cwd()
    target = (root / path).resolve()
    try:
      target.relative_to(root.resolve())
    except ValueError:
      return web.json_response({"ok": False, "error": "path escapes workspace"}, status=403)

    try:
      target.parent.mkdir(parents=True, exist_ok=True)
      target.write_text(content, encoding="utf-8")
      return web.json_response({"ok": True, "path": path, "bytes": len(content.encode("utf-8"))})
    except Exception as e:
      return web.json_response({"ok": False, "error": str(e)}, status=500)

  return web.json_response({"ok": False, "error": "method not allowed"}, status=405)


async def tools_panel_page(request: web.Request) -> web.Response:
  """Serve the standalone WorkBuddy-style tools panel page."""
  web_dir = Path(__file__).resolve().parent.parent / "web" / "static"
  panel_path = web_dir / "tools-panel.html"
  if panel_path.is_file():
    return web.FileResponse(panel_path)
  return web.json_response({"ok": False, "error": "tools-panel.html not found"}, status=404)


async def api_fallback(request: web.Request) -> web.Response:
  """Catch-all fallback for unimplemented production endpoints in local-dev mode."""
  path = request.path
  if path.endswith("/ws") or path.endswith("/stream"):
    return web.json_response({"ok": True, "mode": "local-dev"})
  # Provide sensible empty defaults for common read endpoints.
  if "sessions/search" in path:
    return web.json_response({"ok": True, "sessions": []})
  if "/memory" in path:
    return web.json_response({"ok": True, "memories": []})
  if "/rag" in path:
    return web.json_response({"ok": True, "docs": []})
  if "/skills" in path or "/agents" in path:
    return web.json_response({"ok": True, "items": []})
  if "/tools" in path or "/models" in path:
    return web.json_response({"ok": True, "items": []})
  if "/notifications" in path:
    return web.json_response({"ok": True, "notifications": [], "unread": 0})
  if "/feedback" in path:
    return web.json_response({"ok": True, "feedback": []})
  if "/issues" in path:
    return web.json_response({"ok": True, "issues": []})
  if "/workflows" in path:
    return web.json_response({"ok": True, "workflows": []})
  if "/goals" in path or "/plans" in path or "/todos" in path:
    return web.json_response({"ok": True, "items": []})
  if "/transcript" in path:
    return web.json_response({"ok": True, "events": []})
  if "/audit" in path:
    return web.json_response({"ok": True, "entries": []})
  if "/usage" in path:
    return web.json_response({"ok": True, "usage": {}})
  if "/mcp" in path or "/learned-skills" in path:
    return web.json_response({"ok": True, "items": []})
  if "/harness/config" in path:
    return web.json_response({"ok": True, "config": {}})
  if "/platform/" in path or "/device/" in path or "/workspace" in path:
    return web.json_response({"ok": True})
  if "/fork/" in path or "/publish" in path or "/package/" in path:
    return web.json_response({"ok": True})
  if "/onboarding/" in path:
    return web.json_response({"ok": True})
  if "/dev-assets" in path or "/dev-cache" in path:
    return web.json_response({"ok": True, "items": []})
  if "/files/" in path or "/context/" in path:
    return web.json_response({"ok": True, "items": []})
  if "/consumer/" in path:
    return web.json_response({"ok": True, "items": []})
  if "/model-hub/" in path:
    return web.json_response({"ok": True, "models": []})
  if "/scheduler" in path:
    return web.json_response({"ok": True, "tasks": []})
  if "/pc-sessions" in path:
    return web.json_response({"ok": True, "sessions": []})
  if "/canvas" in path:
    return web.json_response({"ok": True, "canvas": []})
  if "/terminal/" in path:
    return web.json_response({"ok": True, "output": ""})
  if path.startswith("/api/eps/"):
    return web.json_response({"ok": True, "mode": "local-dev", "path": path})
  if "/write/" in path or "/tune" in path:
    return web.json_response({"ok": True})
  if "/test" in path or "/test_connection" in path:
    return web.json_response({"ok": True, "reachable": True})
  return web.json_response({"ok": True, "mode": "local-dev", "path": path})


_PATH_PARAM_RE = re.compile(r"\{([^{}:]+):[^{}]*\}")


def _canonical(path: str) -> str:
  """Normalize ``{name:regex}`` path params to aiohttp's canonical ``{name}``.

  aiohttp stores ``/api/ai/{tail:.*}`` as canonical ``/api/ai/{tail}``, so a
  naive string compare would miss an existing catch-all and re-register it.
  """
  return _PATH_PARAM_RE.sub(r"{\1}", path)


def _route_signature(route: Any) -> tuple[str, str] | None:
  """Return ``(METHOD, canonical_path)`` for a router entry, else ``None``.

  System routes (aiohttp's built-in 404/405 handlers, static mounts) carry no
  canonical resource path and are ignored.
  """
  method = getattr(route, "method", "") or ""
  resource = getattr(route, "resource", None)
  path = getattr(resource, "canonical", None)
  if path is None:
    return None
  return method.upper(), path


def _already_registered(app: web.Application, method: str, path: str) -> bool:
  """True when an equivalent path+method route is already on ``app.router``.

  aiohttp permits duplicate path+method registration and silently shadows the
  earlier one (first registration wins). ``setup_routes`` is the *fallback*
  layer, so it must not re-register endpoints the authoritative production
  router already owns — doing so only creates dead, unreachable handlers.
  """
  want = (method.upper(), _canonical(path))
  for route in app.router.routes():
    if _route_signature(route) == want:
      return True
  return False


def _bind(app: web.Application, method: str, path: str, handler: Any) -> None:
  """Register ``handler`` for ``(method, path)`` unless it already exists."""
  if _already_registered(app, method, path):
    return
  app.router.add_route(method, path, handler)


def setup_routes(app: web.Application) -> None:
  """Register the local-dev fallback routes.

  Acts as a *fallback* layer: any endpoint already registered by the
  authoritative production router (``ai.server.routes.register_routes``) is
  skipped, so this module never shadows a real handler with a degraded one.
  The non-overlapping endpoints below are the only entry points of the
  standalone local-dev server (``ai/server/app.py`` calls only this function)
  and must always be registered.
  """
  _bind(app, "GET", "/api/ai/health", health)
  _bind(app, "GET", "/api/ai/config", api_config_get)
  _bind(app, "POST", "/api/ai/config", api_config_post)
  _bind(app, "GET", "/api/ai/config/diagnose", api_config_diagnose)
  _bind(app, "GET", "/api/ai/status", api_status)
  _bind(app, "GET", "/api/ai/bootstrap", api_bootstrap)
  _bind(app, "GET", "/api/ai/providers", api_providers)
  _bind(app, "POST", "/api/ai/chat", api_chat)
  _bind(app, "POST", "/api/ai/chat/completions", api_chat_completions)
  _bind(app, "GET", "/api/ai/chat/jobs", api_chat_jobs_list)
  _bind(app, "POST", "/api/ai/chat/jobs", api_chat_jobs_create)
  _bind(app, "GET", "/api/ai/chat/jobs/{job_id}", api_chat_jobs_get)
  _bind(app, "DELETE", "/api/ai/chat/jobs/{job_id}", api_chat_jobs_get)
  _bind(app, "GET", "/api/ai/chat/jobs/{job_id}/stream", api_chat_jobs_stream)
  _bind(app, "POST", "/api/ai/write/confirm", api_write_confirm)
  _bind(app, "GET", "/api/ai/sessions", api_sessions)
  _bind(app, "POST", "/api/ai/sessions", api_sessions_create)
  _bind(app, "GET", "/api/ai/sessions/{session_id}/log", api_session_log)
  _bind(app, "POST", "/api/ai/session/resume", api_session_resume)
  _bind(app, "GET", "/api/ai/audit/verify", api_audit_verify)
  _bind(app, "GET", "/api/ai/notifications", api_notifications)
  _bind(app, "POST", "/api/ai/notifications", api_notifications)
  _bind(app, "GET", "/api/ai/sync/ws", api_sync_ws)
  _bind(app, "GET", "/api/ai/rag", api_rag)
  _bind(app, "POST", "/api/ai/rag", api_rag)
  _bind(app, "GET", "/api/ai/scheduler", api_scheduler)
  _bind(app, "POST", "/api/ai/scheduler", api_scheduler)
  _bind(app, "GET", "/api/ai/tools", api_tools_meta)
  _bind(app, "GET", "/api/ai/skills/registry", api_skills_registry)
  _bind(app, "POST", "/api/ai/tool", api_tool_invoke)
  _bind(app, "GET", "/api/ai/files/content", api_files_content)
  _bind(app, "POST", "/api/ai/files/content", api_files_content)
  _bind(app, "GET", "/tools-panel", tools_panel_page)

  # P2 skill lifecycle routes.
  from ai.server.handlers import skills as skills_lifecycle_handlers
  _bind(app, "POST", "/api/ai/skills/{id}/dispose", skills_lifecycle_handlers.api_skill_dispose)
  _bind(app, "GET", "/api/ai/skills/{id}/diagnose", skills_lifecycle_handlers.api_skill_diagnose)
  _bind(app, "POST", "/api/ai/skills/diagnose-all", skills_lifecycle_handlers.api_skill_diagnose_all)
  _bind(app, "POST", "/api/ai/skills/session/register", skills_lifecycle_handlers.api_skill_session_register)

  # Catch-all fallback: must be last. Handles all unimplemented production
  # endpoints so the local-dev UI can still render (intentionally lenient).
  _bind(app, "*", "/api/ai/{tail:.*}", api_fallback)
