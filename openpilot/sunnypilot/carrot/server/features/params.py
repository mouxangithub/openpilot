"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Parameter REST API: what the companion app uses to read and write settings.

Wire contract (identical to CarrotPilot's, which navipilot / CP 搭子 implements against):

    POST /api/param_set    {"name": "ExperimentalMode", "value": 1}
      -> 200 {"ok": true, "name": ..., "value": <stored>}
      -> 400 {"ok": false, "error": "..."}

    GET  /api/params_bulk?names=ExperimentalMode,IsMetric
      -> 200 {"ok": true, "values": {"ExperimentalMode": 0, "IsMetric": 1}}
      -> 400 {"ok": false, "error": "missing names"}

Client errors are 400, not 500: an unknown key or a value of the wrong type is the
caller's mistake, and navipilot surfaces the `error` string to the driver.
"""

from aiohttp import web

from ..services.params_typed import ParamWriteError, get_param_values, json_safe, set_param_value

PARAMS_KEY = web.AppKey("carrot_server_params")


async def api_params_bulk(request: web.Request) -> web.Response:
  names = [name.strip() for name in request.query.get("names", "").split(",") if name.strip()]
  if not names:
    return web.json_response({"ok": False, "error": "missing names"}, status=400)

  params = request.app[PARAMS_KEY]
  values = get_param_values(params, [name for name in names if name != "DeviceType"])
  # DeviceType is not a parameter: it is read from the hardware layer, and the app asks
  # for it alongside real settings, so it is answered here rather than 400'd.
  if "DeviceType" in names:
    try:
      # sunnypilot keeps HARDWARE in common.hardware; openpilot upstream has it under
      # system.hardware. Try both so the answer does not depend on which layout is live.
      try:
        from openpilot.common.hardware import HARDWARE
      except ImportError:
        from openpilot.system.hardware import HARDWARE

      values["DeviceType"] = HARDWARE.get_device_type()
    except Exception:
      values["DeviceType"] = "unknown"

  # Pick up values the driving code changed behind our back (the steering-wheel gap button
  # writes some parameters directly), so the change history can explain them. Restricted to
  # catalog keys, because DeviceType and friends change on every read and are not settings.
  try:
    from ..services.param_changes import observe_param_values
    from ..services.settings_sp import carrot_defaults

    observe_param_values(values, allowed=set(carrot_defaults()))
  except Exception:  # pragma: no cover - a history miss must never fail a read
    pass
  return web.json_response({"ok": True, "values": values})


async def api_param_set(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)

  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)

  name = body.get("name")
  if "value" not in body:
    return web.json_response({"ok": False, "error": "missing value"}, status=400)

  params = request.app[PARAMS_KEY]

  # The mode switch goes through the mode state machine, not the generic
  # writer: enabling without the confirmation bit, while Safe Mode holds the
  # lock, or against a stale snapshot must be refused rather than stored.
  if name == "ExperimentalMode":
    return _set_experimental_mode(params, body)

  # Safe Mode swaps every driving knob at once, so it is a transition rather
  # than a value: it needs the parked precondition, a backup, and a read-back.
  if name == "SafeMode":
    return _set_safe_mode(params, body)

  # Read the old value before writing so the history can show what it replaced.
  before = get_param_values(params, [name] if isinstance(name, str) else []).get(name)

  try:
    stored = set_param_value(params, name, body.get("value"))
  except ParamWriteError as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=400)

  # The blacklist lives in set_param_value, which raises for a key that must not
  # change while moving. So a write that got this far is one the car allows; the
  # history still records it, because "who changed this while driving" is worth
  # knowing even when it is legal. The append never raises, so a log problem
  # cannot turn a successful write into a reported failure.
  if before != stored:
    try:
      from ..services.param_changes import append_param_change

      append_param_change(name, before, json_safe(stored), source=body.get("source", "web_ui"))
    except Exception:  # pragma: no cover - a history miss must never fail a write
      pass

  return web.json_response({"ok": True, "name": name, "value": json_safe(stored)})


def _set_experimental_mode(params, body: dict) -> web.Response:
  """Route an ExperimentalMode write through the mode state machine.

  Wire-compatible with the plain param_set contract: the same request shape
  still works. ``acknowledge`` and ``expected`` are opt-in extensions --
  ``expected`` being the caller's snapshot of {ExperimentalMode,
  ExperimentalModeConfirmed} for optimistic concurrency, and
  ``acknowledge`` standing in for the confirmation dialog the settings UI
  shows before enabling the mode.
  """
  from openpilot.sunnypilot.common.mode_state import MODE_CONFIRMED_PARAM, MODE_ON_PARAM
  from openpilot.sunnypilot.common.mode_state_runtime import ModeStateError, set_experimental_mode

  enabled = bool(body.get("value"))
  expected = body.get("expected")
  if expected is not None:
    if not isinstance(expected, dict) or any(type(expected.get(k)) is not bool
                                             for k in (MODE_ON_PARAM, MODE_CONFIRMED_PARAM)):
      return web.json_response(
        {"ok": False, "error": "expected must carry booleans for ExperimentalMode and ExperimentalModeConfirmed"},
        status=400)
    expected = {MODE_ON_PARAM: expected[MODE_ON_PARAM], MODE_CONFIRMED_PARAM: expected[MODE_CONFIRMED_PARAM]}

  try:
    result = set_experimental_mode(params, enabled, acknowledged=bool(body.get("acknowledge", False)),
                                   expected=expected)
  except ModeStateError as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=exc.status)
  except Exception:  # pragma: no cover - the store failing is not the caller's mistake
    return web.json_response({"ok": False, "error": "longitudinal mode update failed"}, status=500)

  stored = result["values"][MODE_ON_PARAM]
  try:
    from ..services.param_changes import append_param_change

    append_param_change(MODE_ON_PARAM, not enabled, stored, source=body.get("source", "web_ui"))
  except Exception:  # pragma: no cover - a history miss must never fail a write
    pass

  return web.json_response({"ok": True, "name": MODE_ON_PARAM, "value": stored,
                            "mode": result["mode"], "confirmed": result["experimental_confirmed"]})


async def api_params_ping(request: web.Request) -> web.Response:
  """Cheap liveness probe for the app's connection state and for our own smoke tests."""
  return web.json_response({"ok": True, "service": "carrot_server", "api": ["param_set", "params_bulk"]})


def _safe_mode() -> tuple:
  # Imported lazily: the runtime drags in nothing heavy, but keeping the
  # server's import graph flat keeps the module usable in tests that only
  # want one handler.
  from openpilot.sunnypilot.common.safe_mode_runtime import SafeModeError, safe_mode_status, set_safe_mode
  return SafeModeError, safe_mode_status, set_safe_mode


def _set_safe_mode(params, body: dict) -> web.Response:
  """Route a SafeMode write through the transition instead of the raw store.

  Wire-compatible with the plain param_set contract: ``{"name": "SafeMode",
  "value": true}`` still works, but the parked precondition, the backup and
  the read-back all apply. There is no way to skip them, which is the point
  of intercepting here rather than in the caller.
  """
  SafeModeError, _, set_safe_mode = _safe_mode()
  enabled = bool(body.get("value"))
  try:
    status = set_safe_mode(params, enabled)
  except SafeModeError as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=exc.status)
  return web.json_response({"ok": True, "name": "SafeMode", "value": status["active"], **status})


async def api_safe_mode_status(request: web.Request) -> web.Response:
  """What Safe Mode is doing right now, including why a toggle would be refused."""
  _, safe_mode_status, _ = _safe_mode()
  return web.json_response({"ok": True, **safe_mode_status(request.app[PARAMS_KEY])})


async def api_safe_mode_set(request: web.Request) -> web.Response:
  """Switch Safe Mode on or off, or explain why that is not allowed right now."""
  SafeModeError, _, set_safe_mode = _safe_mode()
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)

  if not isinstance(body, dict) or "enabled" not in body:
    return web.json_response({"ok": False, "error": "body must be {\"enabled\": true|false}"}, status=400)
  if not isinstance(body["enabled"], bool):
    return web.json_response({"ok": False, "error": "enabled must be a boolean"}, status=400)

  params = request.app[PARAMS_KEY]
  try:
    status = set_safe_mode(params, body["enabled"])
  except SafeModeError as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=exc.status)
  return web.json_response({"ok": True, **status})


def register(app: web.Application) -> None:
  app.router.add_post("/api/param_set", api_param_set)
  app.router.add_get("/api/params_bulk", api_params_bulk)
  app.router.add_get("/api/param_ping", api_params_ping)
  app.router.add_get("/api/safe_mode", api_safe_mode_status)
  app.router.add_post("/api/safe_mode", api_safe_mode_set)
