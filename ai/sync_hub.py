"""WebSocket push hub for op助手 — sessions, config, chat job events."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

from ai.client import load_config_from_params
from ai.embedding import load_embedding_config
from ai.tools.notifications import list_notifications
from ai.tools.session_store import get_sessions


def _mask_key(key: str) -> str:
  if not key:
    return ""
  if len(key) <= 8:
    return "•" * len(key)
  return "•" * (len(key) - 4) + key[-4:]


def _read_param_str(params: Params, key: str, default: str = "") -> str:
  val = params.get(key)
  return val.decode() if isinstance(val, bytes) else (val or default)


def config_snapshot(params: Params) -> dict[str, Any]:
  from ai.timezone_util import read_ai_timezone_name

  config = load_config_from_params(params)
  embed_cfg = load_embedding_config(params, config)
  return {
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
    "webPin": _mask_key(_read_param_str(params, "ai_web_pin")),
    "timezone": read_ai_timezone_name(params),
    "configured": config.is_configured,
    "configureError": config.configuration_error,
    "embeddingMode": embed_cfg.mode,
    "embeddingProvider": embed_cfg.provider,
    "embeddingModel": embed_cfg.model,
    "embeddingApiKey": _mask_key(_read_param_str(params, "ai_embedding_api_key")) if embed_cfg.mode == "separate" else "",
    "embeddingBaseUrl": embed_cfg.base_url,
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
  data = get_sessions(params)
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
  })


def _hello_payload(request: web.Request, params: Params) -> dict[str, Any]:
  from ai.chat_jobs import list_active_jobs
  config = load_config_from_params(params)
  payload: dict[str, Any] = {
    "type": "hello",
    **get_sessions(params),
    "config": config_snapshot(params),
    "activeJobs": list_active_jobs(),
    "notifications": list_notifications(unread_only=True).get("notifications", [])[:5],
  }
  get_reader = request.app.get("get_state_reader")
  if callable(get_reader):
    try:
      state = get_reader().update(timeout=0)
      payload.update(status_payload(state, config))
    except Exception as e:
      cloudlog.warning(f"aid: hello status skipped: {e}")
  return payload


async def ws_sync(request: web.Request) -> web.WebSocketResponse:
  params: Params = request.app.get("params") or Params()
  ws = web.WebSocketResponse(heartbeat=30.0)
  await ws.prepare(request)
  HUB.add(ws)
  cloudlog.info(f"aid: sync ws connected ({HUB.client_count} clients)")

  try:
    hello = _hello_payload(request, params)
    await ws.send_str(json.dumps(hello, ensure_ascii=False, default=str))

    async for msg in ws:
      if msg.type != web.WSMsgType.TEXT:
        if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.ERROR):
          break
        continue
      try:
        data = json.loads(msg.data)
      except json.JSONDecodeError:
        continue
      if data.get("type") == "ping":
        await ws.send_str(json.dumps({"type": "pong"}))
      elif data.get("type") == "resync":
        await ws.send_str(json.dumps(_hello_payload(request, params), ensure_ascii=False, default=str))
  finally:
    HUB.remove(ws)
    cloudlog.info(f"aid: sync ws disconnected ({HUB.client_count} clients)")
  return ws


def register_sync_routes(app: web.Application) -> None:
  app.router.add_get("/api/ai/sync/ws", ws_sync)
