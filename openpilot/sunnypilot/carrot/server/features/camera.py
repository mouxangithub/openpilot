"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""`/ws/camera/{camera}` - the companion app's live preview.

The hub is built on first connect, like the raw relay, so the process still serves the
parameter API on a host without zmq: a camera request then answers 503 with a reason
instead of taking the server down.
"""
import json
import logging

from aiohttp import web

from ..services.camera_relay import CameraRelayHub

logger = logging.getLogger("openpilot.carrot.server.camera")

CAMERA_HUB_KEY = web.AppKey("carrot_server_camera_hub")
WS_HEARTBEAT_S = 20.0
MAX_INBOUND_BYTES = 2 * 1024 * 1024


def _json_error(exc_type, message: str) -> web.HTTPException:
  return exc_type(text=json.dumps({"ok": False, "error": message}), content_type="application/json")


def _hub(request: web.Request):
  hub = request.app.get(CAMERA_HUB_KEY)
  if hub is not None:
    return hub
  try:
    from openpilot.cereal import messaging
  except Exception as exc:
    logger.warning("carrot_server: camera relay unavailable: %s", exc)
    return None
  hub = CameraRelayHub(messaging)
  request.app[CAMERA_HUB_KEY] = hub
  return hub


async def api_camera_status(request: web.Request) -> web.Response:
  hub = request.app.get(CAMERA_HUB_KEY)
  if hub is None:
    return web.json_response({"ok": True, "mode": "direct-encode-relay", "cameras": {}, "idle": True})
  return web.json_response(hub.status())


async def ws_camera(request: web.Request) -> web.WebSocketResponse:
  name = (request.match_info.get("camera") or "").strip()
  camera = CameraRelayHub.canonical(name)
  if camera is None:
    raise _json_error(web.HTTPNotFound, f"unknown camera: {name}")

  hub = _hub(request)
  if hub is None:
    raise _json_error(web.HTTPServiceUnavailable, "camera relay unavailable")

  ws = web.WebSocketResponse(heartbeat=WS_HEARTBEAT_S, max_msg_size=MAX_INBOUND_BYTES)
  await ws.prepare(request)
  await ws.send_str(json.dumps({"type": "hello", "camera": name, "mode": "direct-encode-relay"}))
  await hub.register(camera, ws)
  try:
    async for _message in ws:
      pass
  finally:
    await hub.unregister(camera, ws)
  return ws


async def _close_hub(app: web.Application) -> None:
  hub = app.get(CAMERA_HUB_KEY)
  if hub is not None:
    await hub.close()


def register(app: web.Application) -> None:
  app[CAMERA_HUB_KEY] = None
  app.router.add_get("/ws/camera/{camera}", ws_camera)
  app.router.add_get("/api/camera/status", api_camera_status)
  app.on_cleanup.append(_close_hub)
