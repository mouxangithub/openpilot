"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""WebSocket routes for live cereal data (CarrotPilot's `/ws/raw*`).

    GET /ws/raw_multiplex?services=carState,modelV2,...   -> hello text frame, then binary
    GET /ws/raw/{service}                                 -> hello text frame, then binary

The app (navipilot / CP 搭子) opens `/ws/raw_multiplex` for vehicle and model data; it
never sends anything, so inbound frames are read and ignored purely to notice the close.

`openpilot.cereal.messaging` needs zmq, so the relay is built on first connect rather than
at import time: the process starts and serves the parameter API even if zmq is unavailable,
and a raw request then gets a clear 503 instead of the server failing to boot.
"""
import json
import logging

from aiohttp import web

from ..services.raw_protocol import build_raw_hello, build_raw_multiplex_hello
from ..services.raw_services import resolve_service, resolve_services

logger = logging.getLogger("openpilot.carrot.server.ws")

RAW_HUB_KEY = web.AppKey("carrot_server_raw_hub")
WS_HEARTBEAT_S = 10.0
MAX_INBOUND_BYTES = 1024 * 1024


def _hub(request: web.Request):
  """The shared relay, created on first use. Returns None when cereal is unavailable."""
  hub = request.app.get(RAW_HUB_KEY)
  if hub is not None:
    return hub
  try:
    from openpilot.cereal import messaging

    from ..services.raw_relay import RawRelayHub

    hub = RawRelayHub(messaging)
  except Exception as exc:
    logger.warning("carrot_server: raw relay unavailable: %s", exc)
    return None
  request.app[RAW_HUB_KEY] = hub
  return hub


def _json_error(exc_type, message: str) -> web.HTTPException:
  """HTTP errors carry JSON too - the app reads the body, not the status line."""
  return exc_type(text=json.dumps({"ok": False, "error": message}), content_type="application/json")


async def _pump(ws: web.WebSocketResponse) -> None:
  """Consume (and ignore) inbound frames so a client close is noticed promptly."""
  async for _message in ws:
    pass


async def ws_raw_multiplex(request: web.Request) -> web.WebSocketResponse:
  names = [name.strip() for name in request.query.get("services", "").split(",") if name.strip()]
  if not names:
    raise _json_error(web.HTTPBadRequest, "missing services")

  resolved = resolve_services(names)
  if not resolved:
    raise _json_error(web.HTTPBadRequest, "no supported services requested")

  hub = _hub(request)
  if hub is None:
    raise _json_error(web.HTTPServiceUnavailable, "cereal relay unavailable")

  ws = web.WebSocketResponse(heartbeat=WS_HEARTBEAT_S, max_msg_size=MAX_INBOUND_BYTES)
  await ws.prepare(request)
  await ws.send_str(json.dumps(build_raw_multiplex_hello(services=[name for name, _ in resolved])))
  await hub.register(resolved, ws)
  try:
    await _pump(ws)
  finally:
    await hub.unregister(ws)
  return ws


async def ws_raw(request: web.Request) -> web.WebSocketResponse:
  name = request.match_info.get("service", "").strip()
  device_service = resolve_service(name)
  if device_service is None:
    raise _json_error(web.HTTPNotFound, f"unsupported service {name}")

  hub = _hub(request)
  if hub is None:
    raise _json_error(web.HTTPServiceUnavailable, "cereal relay unavailable")

  ws = web.WebSocketResponse(heartbeat=WS_HEARTBEAT_S, max_msg_size=MAX_INBOUND_BYTES)
  await ws.prepare(request)
  await ws.send_str(json.dumps(build_raw_hello(service=name)))
  await hub.register([(name, device_service)], ws)
  try:
    await _pump(ws)
  finally:
    await hub.unregister(ws)
  return ws


async def _close_hub(app: web.Application) -> None:
  hub = app.get(RAW_HUB_KEY)
  if hub is not None:
    await hub.close()


def register(app: web.Application) -> None:
  app[RAW_HUB_KEY] = None
  app.router.add_get("/ws/raw_multiplex", ws_raw_multiplex)
  app.router.add_get("/ws/raw/{service}", ws_raw)
  app.on_cleanup.append(_close_hub)
