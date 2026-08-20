"""Hermes-style sidecar — JSON events for terminal tool sidebar."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

from aiohttp import web

from openpilot.common.swaglog import cloudlog

_MAX_EVENTS = 200
_recent: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)


class SidecarHub:
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


HUB = SidecarHub()


async def publish_tool_event(event: dict[str, Any]) -> None:
  payload = {"type": "sidecar_event", **event}
  _recent.append(payload)
  try:
    from ai.core.runtime.sidecar_process import enqueue_sidecar_event
    enqueue_sidecar_event(payload)
  except Exception:
    pass
  await HUB.broadcast(payload)


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
  return list(_recent)[-limit:]


async def sidecar_ws(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse(heartbeat=30.0)
  await ws.prepare(request)
  HUB.add(ws)
  try:
    await ws.send_str(json.dumps({
      "type": "sidecar_hello",
      "ok": True,
      "events": recent_events(30),
    }))
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
  finally:
    HUB.remove(ws)
  return ws


async def api_sidecar_events(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  limit = int(request.query.get("limit", "50") or "50")
  try:
    from ai.core.runtime.sidecar_process import sidecar_status
    status = sidecar_status()
  except Exception:
    status = {"running": False}
  return json_response({
    "ok": True,
    "events": recent_events(min(limit, 100)),
    "sidecar": status,
  })


def register_sidecar_routes(app: web.Application) -> None:
  try:
    from ai.core.runtime.sidecar_process import start_sidecar_process
    start_sidecar_process()
  except Exception:
    pass
  app.router.add_get("/api/ai/sidecar/ws", sidecar_ws)
  app.router.add_get("/api/ai/sidecar/events", api_sidecar_events)
  app.router.add_get("/api/ai/sidecar/status", api_sidecar_status)


async def api_sidecar_status(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  try:
    from ai.core.runtime.sidecar_process import sidecar_status
    return json_response(sidecar_status())
  except Exception as e:
    return json_response({"ok": False, "error": str(e)})
