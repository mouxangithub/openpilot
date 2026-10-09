"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Device lifecycle and status routes (CarrotPilot's `/api/system` family).

Everything that changes device state goes through Params and the manager - this process
never shells out to reboot, and never starts or stops a daemon itself. `DoReboot`,
`DoShutdown` and `OnroadCycleRequested` are the manager's own switches, so asking for a
reboot here is the same action the native UI performs, not a second path around it.

Reboot/poweroff/recalibrate are refused while engaged: `IsEngaged` plus the live
`selfdriveState` decide that, and a refused request answers 409 rather than silently
doing nothing.
"""
import asyncio
import logging
import time

from aiohttp import web

from ..services.device_info import get_calibration_status, get_device_network_snapshot, refresh_device_network
from ..services.live_runtime import RuntimeHolder

logger = logging.getLogger("openpilot.carrot.server.system")

RUNTIME_KEY = web.AppKey("carrot_server_live_runtime")

_CALIBRATION_KEYS = ("CalibrationParams", "LiveTorqueParameters", "LiveParameters", "LiveDelay")


def _params():
  from openpilot.common.params import Params

  return Params()


def _engaged(request: web.Request) -> bool:
  runtime = _runtime(request)
  if runtime is not None:
    try:
      if runtime.is_engaged():
        return True
    except Exception:
      pass
  try:
    return bool(_params().get_bool("IsEngaged"))
  except Exception:
    # Better to allow a reboot on a device we cannot read than to wedge it.
    return False


def _refuse_if_engaged(request: web.Request):
  if _engaged(request):
    return web.json_response({"ok": False, "error": "disengage openpilot first"}, status=409)
  return None


async def api_heartbeat_status(request: web.Request) -> web.Response:
  """The app's liveness probe; `hb` is the age of the last heartbeat it sent."""
  return web.json_response({"ok": True, "hb": request.app.get("hb_last"), "now": time.monotonic()})


def _runtime(request: web.Request):
  holder = request.app.get(RUNTIME_KEY)
  return holder.get() if holder is not None else None


async def api_live_runtime(request: web.Request) -> web.Response:
  runtime = _runtime(request)
  if runtime is None:
    return web.json_response({"ok": False, "error": "cereal unavailable"}, status=503)
  return web.json_response(await asyncio.to_thread(runtime.snapshot))


async def api_device_network(request: web.Request) -> web.Response:
  force = request.query.get("force") == "1"
  try:
    network = await asyncio.to_thread(refresh_device_network) if force else await asyncio.to_thread(get_device_network_snapshot)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "network": network})


async def api_calibration_status(request: web.Request) -> web.Response:
  messaging = None
  try:
    from openpilot.cereal import messaging
  except Exception:
    messaging = None
  try:
    calibration = await asyncio.to_thread(get_calibration_status, messaging)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "calibration": calibration})


async def api_reboot(request: web.Request) -> web.Response:
  blocked = _refuse_if_engaged(request)
  if blocked is not None:
    return blocked
  try:
    _params().put_bool("DoReboot", True)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "rebootRequested": True})


async def api_poweroff(request: web.Request) -> web.Response:
  blocked = _refuse_if_engaged(request)
  if blocked is not None:
    return blocked
  try:
    _params().put_bool("DoShutdown", True)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "shutdownRequested": True})


async def api_recalibrate(request: web.Request) -> web.Response:
  blocked = _refuse_if_engaged(request)
  if blocked is not None:
    return blocked
  try:
    params = _params()
    removed = []
    for key in _CALIBRATION_KEYS:
      try:
        params.remove(key)
        removed.append(key)
      except Exception:
        pass
    params.put_bool("OnroadCycleRequested", True)
    params.put_bool("DoReboot", True)
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "removed": removed, "rebootRequested": True})


async def api_set_default(request: web.Request) -> web.Response:
  """Reset the Carrot tuning surface to its documented defaults.

  Only keys in the carrot catalog are touched: vehicle identity, calibration, git and
  updater state belong to openpilot and are never cleared from here.
  """
  try:
    from ..services.settings import carrot_defaults

    defaults = carrot_defaults()
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)

  applied, failed = {}, {}
  try:
    params = _params()
  except Exception as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  for key, value in defaults.items():
    try:
      if isinstance(value, bool):
        params.put_bool(key, value)
      else:
        params.put(key, value)
      applied[key] = value
    except Exception as exc:
      failed[key] = str(exc)
  return web.json_response({"ok": not failed, "applied": applied, "failed": failed})


async def api_time_sync(request: web.Request) -> web.Response:
  """Accept the client's clock. Setting the system clock needs root, so this reports only.

  AGNOS keeps time via NTP; a phone is not a more trustworthy source. The endpoint exists
  so the app's call is answered rather than 404'd, and it always reports `applied: false`.
  """
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "object required"}, status=400)
  epoch_ms = body.get("epoch_ms")
  if not isinstance(epoch_ms, (int, float)):
    return web.json_response({"ok": False, "error": "epoch_ms required"}, status=400)
  return web.json_response({
    "ok": True,
    "applied": False,
    "reason": "device time is managed by AGNOS/NTP",
    "epoch_ms": epoch_ms,
  })


async def _close_runtime(app: web.Application) -> None:
  holder = app.get(RUNTIME_KEY)
  if holder is not None:
    try:
      holder.close()
    except Exception:
      pass


def register(app: web.Application) -> None:
  app[RUNTIME_KEY] = RuntimeHolder()
  app.router.add_get("/api/heartbeat_status", api_heartbeat_status)
  app.router.add_get("/api/live_runtime", api_live_runtime)
  app.router.add_get("/api/device_network", api_device_network)
  app.router.add_get("/api/calibration_status", api_calibration_status)
  app.router.add_post("/api/reboot", api_reboot)
  app.router.add_post("/api/poweroff", api_poweroff)
  app.router.add_post("/api/recalibrate", api_recalibrate)
  app.router.add_post("/api/set_default", api_set_default)
  app.router.add_post("/api/time_sync", api_time_sync)
  app.on_cleanup.append(_close_runtime)
