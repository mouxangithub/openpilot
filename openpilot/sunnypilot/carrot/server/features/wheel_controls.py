"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Routes for the wheel_controls input layer (``/api/wheel_controls`` family).

Read-only status + config edits + learn/test requests. Learn/test only ever mutate the
volatile control file the daemon polls; the daemon enforces the offroad gate itself, and
this layer refuses everything while engaged (409) so a moving car is never reconfigured.
"""
import asyncio
import logging

from aiohttp import web

from ..services import wheel_controls as service
from ..services.wheel_controls import WheelControlsError

logger = logging.getLogger("openpilot.carrot.server.wheel_controls")


def _error_response(exc: WheelControlsError):
  status = 409 if exc.code == "engaged" else 400
  return web.json_response({"ok": False, "error": exc.code, "message": exc.message}, status=status)


async def api_wheel_controls_status(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, **await asyncio.to_thread(service.public_status)})


async def api_wheel_controls_config(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "object required"}, status=400)
  try:
    updates = {key: body[key] for key in ("mappings", "action_slots", "enabled", "joystick_device") if key in body}
    if "joystick_device" in body and body.get("joystick_device") is None:
      updates["joystick_device"] = ""
    config = await asyncio.to_thread(service.update_config, updates)
  except WheelControlsError as exc:
    return _error_response(exc)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "config": config})


async def api_wheel_controls_mapping_delete(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    identifier = str((body or {}).get("id") or "").strip()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not identifier:
    return web.json_response({"ok": False, "error": "id required"}, status=400)
  try:
    config = await asyncio.to_thread(service.delete_mapping, identifier)
  except WheelControlsError as exc:
    return _error_response(exc)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "config": config})


async def api_wheel_controls_mappings_clear(request: web.Request) -> web.Response:
  try:
    config = await asyncio.to_thread(service.clear_mappings)
  except WheelControlsError as exc:
    return _error_response(exc)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "config": config})


async def api_wheel_controls_action_slot(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "object required"}, status=400)
  try:
    config = await asyncio.to_thread(service.set_action_slot, body.get("index"), body.get("key"), body.get("label"))
  except WheelControlsError as exc:
    return _error_response(exc)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "config": config})


async def api_wheel_controls_learn(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "object required"}, status=400)
  try:
    if body.get("cancel"):
      control = await asyncio.to_thread(service.cancel_learning)
    else:
      control = await asyncio.to_thread(service.start_learning, body.get("slot"))
  except WheelControlsError as exc:
    return _error_response(exc)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "control": control})


async def api_wheel_controls_test(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "object required"}, status=400)
  try:
    control = await asyncio.to_thread(service.set_testing, bool(body.get("active")))
  except WheelControlsError as exc:
    return _error_response(exc)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "control": control})


def register(app: web.Application) -> None:
  app.router.add_get("/api/wheel_controls", api_wheel_controls_status)
  app.router.add_post("/api/wheel_controls/config", api_wheel_controls_config)
  app.router.add_post("/api/wheel_controls/mapping/delete", api_wheel_controls_mapping_delete)
  app.router.add_post("/api/wheel_controls/mappings/clear", api_wheel_controls_mappings_clear)
  app.router.add_post("/api/wheel_controls/action_slot", api_wheel_controls_action_slot)
  app.router.add_post("/api/wheel_controls/learn", api_wheel_controls_learn)
  app.router.add_post("/api/wheel_controls/test", api_wheel_controls_test)
