"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Carrot navigation status and its live state channel.

`carrot_navi` is its own daemon and owns TCP 7714; this process does not run navigation
and must not open those ports. What it can report is what cereal already carries: the
newest `carrotNaviSP` / `carrotNaviStateSP` sample, and which carrot ports have a socket
bound at all - which is the question behind "is the nav channel up".

`/ws/carrot_navi/state` is the same raw capnp framing as `/ws/raw/{service}` with the
service fixed, so a client that already speaks the raw protocol needs no second parser.
"""
import json
import logging

from aiohttp import web

from ..services.device_info import listening_ports
from ..services.live_runtime import json_safe

logger = logging.getLogger("openpilot.carrot.server.carrot_navi")

NAVI_PORTS = (7705, 7706, 7709, 7710, 7711, 7713, 7714)

STATE_SERVICE = "carrotNaviStateSP"
CLIENT_STATE_NAME = "carrotNaviState"

COMPACT_STATE_NOTE = "compactState (Carrot Vision's packed binary) is unimplemented; use /ws/raw_multiplex"

CAPABILITIES = {
  "rawMultiplex": True,
  "camera": True,
  "compactState": False,
  "naviState": True,
  "services": ("carrotManSP", "carrotNaviSP", "carrotNaviStateSP", "carrotNaviMediaSP"),
  "note": COMPACT_STATE_NOTE,
}


def _runtime(request: web.Request):
  from .system import RUNTIME_KEY

  holder = request.app.get(RUNTIME_KEY)
  return holder.get() if holder is not None else None


async def api_status(request: web.Request) -> web.Response:
  runtime = _runtime(request)
  services = {}
  if runtime is not None:
    try:
      runtime.snapshot()
      services = {name: runtime._last.get(name) for name in ("carrotNaviSP", "carrotNaviStateSP")}
    except Exception as exc:
      logger.warning("carrot_server: carrot navi snapshot failed: %s", exc)
  navi = services.get("carrotNaviSP") or {}
  state = services.get("carrotNaviStateSP") or {}
  return web.json_response({
    "ok": True,
    "available": bool(navi or state),
    "ports": listening_ports(NAVI_PORTS),
    "navi": json_safe(navi),
    "state": json_safe(state),
  })


async def api_capabilities(_request: web.Request) -> web.Response:
  return web.json_response({"ok": True, "capabilities": CAPABILITIES})


async def ws_state(request: web.Request) -> web.WebSocketResponse:
  """Raw capnp frames for `carrotNaviState`, using the shared raw relay."""
  from .ws import _hub, _json_error

  hub = _hub(request)
  if hub is None:
    raise _json_error(web.HTTPServiceUnavailable, "cereal relay unavailable")

  ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=1024 * 1024)
  await ws.prepare(request)
  await ws.send_str(json.dumps({"type": "hello", "service": CLIENT_STATE_NAME}))
  await hub.register([(CLIENT_STATE_NAME, STATE_SERVICE)], ws)
  try:
    async for _message in ws:
      pass
  finally:
    await hub.unregister(ws)
  return ws


def register(app: web.Application) -> None:
  app.router.add_get("/api/carrot_navi/status", api_status)
  app.router.add_get("/api/carrot_navi/capabilities", api_capabilities)
  app.router.add_get("/ws/carrot_navi/state", ws_state)
