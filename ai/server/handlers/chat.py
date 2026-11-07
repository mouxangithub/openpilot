"""Shared chat handling logic (A-P0.5).

The local-dev harness routes (:mod:`ai.server.op_routes`) and the production
routes (:mod:`ai.server.handlers.chat_handlers`, bound by
``ai.server.routes``) each grew their own copy of the chat request/response
plumbing: prompt extraction, reply extraction, OpenAI-compatible completion
framing and the local-dev Agent runner.  This module is the single home for
those reusable pieces so each route file only *binds* endpoints.

Design contract
---------------
- Handlers accept the aiohttp ``request`` and read the app context from
  ``request.app`` (e.g. ``request.app.get("config")``).
- Handlers never perform authentication.  Auth is a middleware / binding-layer
  concern, so the production router can keep ``ai_auth_middleware`` while the
  local-dev router stays open — both binding the *same* handler functions here.
- No import-time work beyond lightweight helpers; heavy/optional modules are
  imported lazily inside functions to keep the local-dev server bootable even
  when openpilot/cereal pieces are missing.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiohttp import web

from ai.core.config.schema import AIOPConfig
from ai.core.llm.client import AIConfig

_LOG = logging.getLogger("ai.server.handlers.chat")

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def extract_prompt(messages: list[dict[str, Any]]) -> str:
  """Extract the latest user text prompt from an OpenAI-style messages list."""
  for m in reversed(messages):
    if m.get("role") == "user":
      content = m.get("content")
      if isinstance(content, str):
        return content
      if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if p.get("type") == "text")
  return ""


def extract_reply(result: Any) -> str:
  """Extract assistant text from an Agent or fallback result."""
  if not isinstance(result, dict):
    return str(result)
  if result.get("fallback"):
    fb_result = result.get("result") or {}
    if isinstance(fb_result, dict):
      return str(fb_result.get("reply", "") or fb_result.get("answer", "") or fb_result.get("content", ""))
    return str(fb_result)
  agent_result = result.get("agent") or {}
  if isinstance(agent_result, dict):
    return str(agent_result.get("reply", "") or agent_result.get("answer", "") or agent_result.get("content", ""))
  return ""


def session_log_path(session_id: str) -> str | None:
  """Return the durable per-session JSONL log path (shared by chat handlers)."""
  if not session_id:
    return None
  try:
    from ai.system.paths import workspace_path
    path = workspace_path("ai_session_logs", mkdir=True) / f"{session_id}.jsonl"
    return str(path)
  except Exception:
    return None


def build_completion_response(text: str, *, model: str, created: int | None = None) -> dict[str, Any]:
  """Build an OpenAI-compatible ``chat.completion`` payload."""
  return {
    "id": f"chatcmpl-{uuid.uuid4().hex}",
    "object": "chat.completion",
    "created": int(created if created is not None else time.time()),
    "model": model,
    "choices": [
      {
        "index": 0,
        "message": {"role": "assistant", "content": text},
        "finish_reason": "stop",
      }
    ],
    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
  }


def completion_sse_frames(response: dict[str, Any], text: str) -> list[bytes]:
  """Build the SSE frames for a single-shot completion stream."""
  content_chunk = {
    "id": response["id"],
    "object": "chat.completion.chunk",
    "created": response["created"],
    "model": response["model"],
    "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
  }
  done_chunk = {
    "id": response["id"],
    "object": "chat.completion.chunk",
    "created": response["created"],
    "model": response["model"],
    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
  }
  frames = [
    b"data: " + json.dumps(content_chunk, ensure_ascii=False).encode("utf-8") + b"\n\n",
    b"data: " + json.dumps(done_chunk, ensure_ascii=False).encode("utf-8") + b"\n\n",
    b"data: [DONE]\n\n",
  ]
  return frames


# ---------------------------------------------------------------------------
# Local-dev Agent runner (shared construction + fallback)
# ---------------------------------------------------------------------------

def make_offline_config() -> AIConfig:
  """Offline mock config used by local-dev Agent runs."""
  return AIConfig(provider="offline", model="offline-mock", api_key="offline")


def vehicle_params_factory(cwd: str):
  """Return a ``VehicleParams`` rooted at ``<cwd>/.ai/vehicle``."""
  from ai.tools.vehicle.params import VehicleParams
  return VehicleParams(Path(cwd) / ".ai" / "vehicle")


def make_dispatcher(cwd: str, config: AIOPConfig):
  """Build the vehicle tool dispatcher used by the simple-loop fallback."""
  from ai.audit.log import AuditLog
  from ai.permissions.hitl import HumanInLoop
  from ai.permissions.service import SandboxPolicyService
  from ai.tools.dispatch import ToolDispatcher
  from ai.tools.vehicle.schemas import build_vehicle_handlers, build_vehicle_tool_specs

  schemas = build_vehicle_tool_specs()
  handlers = build_vehicle_handlers(vehicle_params_factory)
  sandbox = SandboxPolicyService(config)
  audit = AuditLog.for_session(cwd)
  hitl = HumanInLoop()
  return ToolDispatcher(handlers, schemas, sandbox, audit, hitl)


def make_tool_pipeline(config: AIOPConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  """Build schemas + handlers compatible with ``ai.core.agent.Agent``.

  Uses the same agent tool registration as production, bound to the standard
  StateReader. ToolPipeline will wrap sync/async handlers.
  """
  from openpilot.common.params import Params
  from ai.tools.agent_tools import build_tool_schemas, make_handlers

  schemas = build_tool_schemas()

  def _get_state_reader():
    from ai.selfdrive.state import StateReader
    return StateReader()

  handlers = make_handlers(get_state_reader=_get_state_reader, params=Params())
  return schemas, handlers


def make_local_dev_agent(
  cwd: str,
  config: AIOPConfig,
  body: dict[str, Any],
  emit: EmitFn,
  session_id: str,
  get_state_reader: Callable[[], Any],
):
  """Construct a local-dev ``Agent`` via the central :class:`AgentFactory`.

  AgentLoop is enabled by default and the offline mock config is passed through
  verbatim so the local-dev behaviour is unchanged while the construction seam
  is unified with the factory.
  """
  from openpilot.common.params import Params
  from ai.core.agent.factory import AgentFactory

  # Force AgentLoop default for local-dev harness.
  body = {**body, "ai_use_agent_loop": True}

  def _get_tool_handlers() -> dict[str, Any]:
    _schemas, handlers = make_tool_pipeline(config)
    return handlers

  agent_id = str(body.get("agent_id") or body.get("agentId") or "local-dev").strip() or "local-dev"
  tool_schemas, _ = make_tool_pipeline(config)

  factory = AgentFactory(params=Params(), workdir=cwd)
  return factory.create_agent(
    session_id=session_id,
    body=body,
    agent_id=agent_id,
    emit=emit,
    get_state_reader=get_state_reader,
    get_tool_handlers=_get_tool_handlers,
    tools=tool_schemas,
    session_log_path=None,
    config=make_offline_config(),
    max_tool_rounds=int(body.get("max_tool_rounds") or config.conversation.ai_max_turns or 16),
    tool_timeout=float(body.get("tool_timeout") or config.conversation.ai_tool_timeout or 60.0),
    stream_timeout=float(body.get("stream_timeout") or config.conversation.ai_stream_timeout or 120.0),
    ai_use_agent_loop=True,
  )


async def run_with_agent(
  cwd: str,
  config: AIOPConfig,
  body: dict[str, Any],
  prompt: str,
  session_id: str,
) -> dict[str, Any]:
  """Run one chat turn through the production Agent (AgentLoop by default)."""
  from ai.core.agent.registry import agent_registry

  if prompt and not body.get("messages"):
    body["messages"] = [{"role": "user", "content": prompt}]

  events: list[dict[str, Any]] = []

  async def _emit(event: dict[str, Any]) -> None:
    events.append(event)

  def _get_state_reader():
    from ai.selfdrive.state import StateReader
    return StateReader()

  agent = make_local_dev_agent(cwd, config, body, _emit, session_id, _get_state_reader)
  job_id = str(body.get("_job_id") or body.get("jobId") or "").strip()

  async def _cancel() -> bool:
    try:
      agent.cancel()
      return True
    except Exception:
      return False

  entry = agent_registry.resume(
    session_id,
    agent.agent_id,
    job_id=job_id,
    meta={"mode": str(body.get("mode") or body.get("chatMode") or "local-dev")},
    cancel_fn=_cancel,
  )
  try:
    result = await agent.run()
    return {"ok": True, "agent": result, "events": events}
  finally:
    status = "done"
    if getattr(agent, "state", None) is not None and agent.state.is_cancelled():
      status = "cancelled"
    elif entry is not None:
      agent_registry.mark_done(session_id, status)


async def run_simple_loop(
  cwd: str,
  config: AIOPConfig,
  body: dict[str, Any],
  prompt: str,
  session_id: str,
) -> dict[str, Any]:
  """Original P0 fallback loop (preserved for resilience)."""
  from ai.core.agent.simple_loop import SimpleAgentLoop
  from ai.core.session.manager import SessionManager
  from ai.providers.offline import OfflineProvider
  from ai.tools.spill import SpillWaterfall

  sessions = SessionManager(cwd)
  session = sessions.get_or_create(session_id, cwd=cwd)
  dispatcher = make_dispatcher(cwd, config)
  spill = SpillWaterfall(cwd)
  provider = OfflineProvider()
  loop = SimpleAgentLoop(session, sessions.storage, dispatcher, provider, config, spill=spill)
  result = await loop.run(prompt)
  return {"ok": True, "fallback": "simple_loop", "result": result}


async def run_chat_local_dev(
  cwd: str,
  config: AIOPConfig,
  body: dict[str, Any],
  prompt: str,
  session_id: str,
) -> dict[str, Any]:
  """Try the production Agent first, fall back to SimpleAgentLoop on failure."""
  try:
    return await run_with_agent(cwd, config, body, prompt, session_id)
  except Exception as e:
    # Log and fallback so local-dev never hard-fails when Agent deps are unavailable.
    _LOG.warning(f"Agent run failed, falling back to SimpleAgentLoop: {e}")
    return await run_simple_loop(cwd, config, body, prompt, session_id)


# ---------------------------------------------------------------------------
# Reusable handlers (take the aiohttp request / app context)
# ---------------------------------------------------------------------------

def _request_config(request: web.Request) -> AIOPConfig:
  return request.app.get("config") or AIOPConfig()


async def api_chat_local_dev(request: web.Request) -> web.Response:
  """POST ``/api/ai/chat`` (local-dev harness).

  Runs a chat turn synchronously and returns the run result as JSON.  Auth is
  intentionally absent here — the binding router decides the middleware.
  """
  body = await request.json()
  config = _request_config(request)
  if body.get("sandbox_mode"):
    config.conversation.ai_sandbox_mode = str(body.get("sandbox_mode"))
  cwd = str(body.get("cwd") or str(Path.cwd()))
  prompt = str(body.get("prompt") or "")
  session_id = str(body.get("session_id") or "")

  result = await run_chat_local_dev(cwd, config, body, prompt, session_id)
  return web.json_response(result)


async def api_chat_completions_local_dev(request: web.Request) -> web.Response:
  """OpenAI-compatible ``/api/ai/chat/completions`` used by the web UI."""
  body = await request.json()
  messages = body.get("messages", [])
  prompt = extract_prompt(messages)
  session_id = str(body.get("session_id") or body.get("sessionId") or "")
  stream = bool(body.get("stream", False))

  config = _request_config(request)
  if body.get("sandbox_mode"):
    config.conversation.ai_sandbox_mode = str(body.get("sandbox_mode"))
  cwd = str(body.get("cwd") or str(Path.cwd()))

  result = await run_chat_local_dev(cwd, config, body, prompt, session_id)

  text = extract_reply(result)
  response = build_completion_response(text, model=body.get("model", "offline-mock"))
  if stream:
    async def _sse():
      for frame in completion_sse_frames(response, text):
        yield frame
    return web.Response(body=_sse(), content_type="text/event-stream", headers={"Cache-Control": "no-cache"})
  return web.json_response(response)


def bind_local_dev_chat_routes(app: web.Application) -> None:
  """Bind the shared local-dev chat endpoints.

  Kept as a convenience for routers that want the chat surface without
  duplicating the individual ``add_post`` calls.
  """
  app.router.add_post("/api/ai/chat", api_chat_local_dev)
  app.router.add_post("/api/ai/chat/completions", api_chat_completions_local_dev)


__all__ = [
  "EmitFn",
  "api_chat_completions_local_dev",
  "api_chat_local_dev",
  "bind_local_dev_chat_routes",
  "build_completion_response",
  "completion_sse_frames",
  "extract_prompt",
  "extract_reply",
  "make_dispatcher",
  "make_local_dev_agent",
  "make_offline_config",
  "make_tool_pipeline",
  "run_chat_local_dev",
  "run_simple_loop",
  "run_with_agent",
  "session_log_path",
  "vehicle_params_factory",
]
