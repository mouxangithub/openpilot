"""WebSocket push hub for op助手 — sessions, config, chat job events."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

from ai.common.storage import read_param
from ai.core.llm.embedding import load_embedding_config
from ai.core.llm.model_accounts import hub_for_api, resolve_primary_config
from ai.core.llm.model_router import fallbacks_for_api
from ai.core.llm.client import load_config_from_params
from ai.tools.notifications import list_notifications
from ai.tools.session_store import get_sessions, session_state_version
from ai.agents.config import agents_enabled_payload
from ai.agents.office import office_snapshot
from ai.agents.registry import list_agents
from ai.core.sync.protocol import WS_PROTOCOL_VERSION, validate_ws_message
from ai.core.sync.device_trust import check_device_trust, touch_device


def _read_param_str(params: Params, key: str, default: str = "") -> str:
  val = read_param(params, key, default)
  return val.decode() if isinstance(val, bytes) else (val or default)


def config_snapshot(params: Params) -> dict[str, Any]:
  from ai.infra.timezone import read_ai_timezone_name

  config = resolve_primary_config(params, load_config_from_params(params))
  embed_cfg = load_embedding_config(params)
  hub = hub_for_api(params, mask_keys=False)
  return {
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
    "timezone": read_ai_timezone_name(params),
    "configured": config.is_configured,
    "configureError": config.configuration_error,
    "modelHub": hub,
    "modelFallbacks": fallbacks_for_api(params, config),
    "embeddingProvider": embed_cfg.provider,
    "embeddingModel": embed_cfg.model,
    "embeddingConfigured": embed_cfg.is_configured,
  }


class SyncHub:
  def __init__(self) -> None:
    self._clients: set[web.WebSocketResponse] = set()
    self._lock = asyncio.Lock()

  def add(self, ws: web.WebSocketResponse) -> None:
    self._clients.add(ws)

  def remove(self, ws: web.WebSocketResponse) -> None:
    self._clients.discard(ws)

  async def broadcast(self, payload: dict[str, Any]) -> None:
    ok, err = validate_ws_message(payload)
    if not ok:
      cloudlog.warning(f"aid: ws schema validation: {err}")
    msg = json.dumps(payload, ensure_ascii=False, default=str)
    dead: list[web.WebSocketResponse] = []
    async with self._lock:
      clients = list(self._clients)
    for ws in clients:
      if ws.closed:
        dead.append(ws)
        continue
      try:
        await ws.send_str(msg)
      except Exception:
        dead.append(ws)
    for ws in dead:
      self.remove(ws)

  @property
  def client_count(self) -> int:
    return len(self._clients)


HUB = SyncHub()


async def broadcast_sessions(params: Params) -> None:
  data = get_sessions(params, compact=True)
  await HUB.broadcast({"type": "sessions", **data})


async def broadcast_config(params: Params) -> None:
  await HUB.broadcast({
    "type": "config",
    "ok": True,
    "config": config_snapshot(params),
  })


def status_payload(state: Any, config: Any) -> dict[str, Any]:
  from ai.system.host_env import get_host_environment
  return {
    "type": "status",
    "ok": True,
    "driving": state.is_driving,
    "state": state.to_dict(),
    "ai": {
      "configured": config.is_configured,
      "provider": config.provider,
      "model": config.model,
    },
    "hostEnvironment": get_host_environment(),
  }


async def broadcast_status(state: Any, config: Any) -> None:
  await HUB.broadcast(status_payload(state, config))


async def broadcast_notifications() -> None:
  data = list_notifications(unread_only=False)
  await HUB.broadcast({
    "type": "notifications",
    "ok": True,
    "notifications": data.get("notifications", []),
  })


async def notify_chat_event(
  job_id: str,
  session_id: str,
  event: dict[str, Any],
  job: dict[str, Any],
) -> None:
  await HUB.broadcast({
    "type": "chat_event",
    "jobId": job_id,
    "sessionId": session_id,
    "event": event,
    "status": job.get("status"),
    "assistant": job.get("assistant"),
    "seq": event.get("_seq"),
    "nextSince": job.get("eventSeq"),
  })


async def notify_chat_status(job_id: str, session_id: str, job: dict[str, Any]) -> None:
  await HUB.broadcast({
    "type": "chat_status",
    "jobId": job_id,
    "sessionId": session_id,
    "status": job.get("status"),
    "assistant": job.get("assistant"),
    "error": job.get("error"),
    "resolvedModel": job.get("resolvedModel"),
    "nextSince": job.get("eventSeq"),
    "runId": job_id,
  })


async def broadcast_office() -> None:
  await HUB.broadcast({
    "type": "office",
    "ok": True,
    "office": office_snapshot(),
    "agents": list_agents(include_orchestrator=True),
  })


async def notify_canvas_artifact(session_id: str, artifact: dict[str, Any]) -> None:
  await HUB.broadcast({
    "type": "canvas",
    "sessionId": session_id,
    "artifact": artifact,
  })


async def notify_lifecycle(
  job_id: str,
  session_id: str,
  phase: str,
  extra: dict[str, Any] | None = None,
) -> None:
  payload: dict[str, Any] = {
    "type": "lifecycle",
    "phase": phase,
    "runId": job_id,
    "jobId": job_id,
    "sessionId": session_id,
  }
  if extra:
    payload.update(extra)
  await HUB.broadcast(payload)


def _hello_payload(request: web.Request, params: Params) -> dict[str, Any]:
  from ai.core.chat.jobs import list_active_jobs
  config = resolve_primary_config(params, load_config_from_params(params))
  payload: dict[str, Any] = {
    "type": "hello",
    **get_sessions(params, compact=True),
    "stateVersion": session_state_version(),
    "protocolVersion": WS_PROTOCOL_VERSION,
    "config": config_snapshot(params),
    "activeJobs": list_active_jobs(),
    "agents": list_agents(include_orchestrator=True),
    "agentsConfig": agents_enabled_payload(params),
    "office": office_snapshot(),
    "notifications": list_notifications(unread_only=True).get("notifications", [])[:5],
    "deviceTrust": check_device_trust(request, params),
  }
  touch_device(
    params,
    payload["deviceTrust"].get("deviceId", ""),
    payload["deviceTrust"].get("fingerprint", ""),
  )
  get_reader = request.app.get("get_state_reader")
  if callable(get_reader):
    try:
      state = get_reader().update(timeout=0)
      status = status_payload(state, config)
      status.pop("type", None)
      payload.update(status)
    except Exception as e:
      cloudlog.warning(f"aid: hello status skipped: {e}")
  return payload


async def ws_sync(request: web.Request) -> web.WebSocketResponse:
  params: Params = request.app.get("params") or Params()
  ws = web.WebSocketResponse(heartbeat=30.0)
  await ws.prepare(request)
  HUB.add(ws)
  cloudlog.info(f"aid: sync ws connected ({HUB.client_count} clients)")

  connected = False
  legacy_hello_sent = False

  async def _send_hello() -> None:
    nonlocal legacy_hello_sent
    if legacy_hello_sent:
      return
    hello = _hello_payload(request, params)
    await ws.send_str(json.dumps(hello, ensure_ascii=False, default=str))
    legacy_hello_sent = True

  try:
    async for msg in ws:
      if msg.type != web.WSMsgType.TEXT:
        if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.ERROR):
          break
        continue
      try:
        data = json.loads(msg.data)
      except json.JSONDecodeError:
        await ws.send_str(json.dumps({"type": "protocol_error", "error": "invalid JSON"}))
        continue

      ok, err = validate_ws_message(data, direction="inbound")
      if not ok:
        await ws.send_str(json.dumps({"type": "protocol_error", "error": err or "invalid message"}))
        continue

      msg_type = data.get("type")
      if msg_type == "connect":
        from ai.core.sync.protocol import negotiate_client_version
        client_ver = int(data.get("protocolVersion") or 1)
        ok_neg, neg_err = negotiate_client_version(client_ver)
        await ws.send_str(json.dumps({
          "type": "connect_ack",
          "protocolVersion": WS_PROTOCOL_VERSION,
          "ok": ok_neg,
          "error": neg_err,
        }))
        if ok_neg:
          connected = True
          await _send_hello()
        continue

      if not connected and not legacy_hello_sent:
        connected = True
        await _send_hello()

      if msg_type == "ping":
        await ws.send_str(json.dumps({"type": "pong", "protocolVersion": WS_PROTOCOL_VERSION}))
      elif msg_type == "resync":
        await ws.send_str(json.dumps(_hello_payload(request, params), ensure_ascii=False, default=str))
  finally:
    HUB.remove(ws)
    cloudlog.info(f"aid: sync ws disconnected ({HUB.client_count} clients)")
  return ws


def register_sync_routes(app: web.Application) -> None:
  from ai.server.handlers.phase2 import api_sync_schema
  app.router.add_get("/api/ai/sync/ws", ws_sync)
  app.router.add_get("/api/ai/sync/schema", api_sync_schema)
