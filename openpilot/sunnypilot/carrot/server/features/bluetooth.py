"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Bluetooth setup over HTTP: `/api/bluetooth`.

This is the backend both the companion app and the native UI panel talk to - the panel
used to call a port that nothing listened on, so it rendered the "not installed" empty
state on every device. One endpoint now serves both, and it reads the same
`carrot.bluetooth` module and the same `/dev/shm/carrot-bluetooth` runtime files the
daemon writes, so the phone and the on-device screen can never disagree.

HTTP can configure mappings; it cannot fire them. Pairing and scanning are confined to a
stationary, disengaged device (`guard`), and every D-Bus or systemctl call is wrapped so
a missing bluez answers with JSON instead of a 500 traceback.
"""
import asyncio
import json
import logging
import os
import time
from urllib.parse import urlsplit

from aiohttp import web

logger = logging.getLogger("openpilot.carrot.server.bluetooth")

CLIENT = web.AppKey("carrot_server_bluetooth", object)
LOCK = web.AppKey("carrot_server_bluetooth_lock", asyncio.Lock)

MAX_BODY_BYTES = 32768
UART_PATH = "/dev/ttyHS1"
BTPOWER_PATH = "/dev/btpower"


def _model():
  from openpilot.sunnypilot.carrot.bluetooth import model

  return model


def _runtime() -> dict:
  model = _model()
  state = model.read_json(model.RUNTIME / "status.json", {})
  if not isinstance(state, dict):
    state = {}
  stamp = state.get("time", 0)
  state["alive"] = isinstance(stamp, (float, int)) and 0 <= time.monotonic() - stamp < 2 and not state.get("stopped")
  state["stationary"] = bool(state["alive"] and state.get("stationary"))
  return state


async def _command(argv, limit_sec: float = 20.0):
  process = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
  try:
    out, err = await asyncio.wait_for(process.communicate(), limit_sec)
  except TimeoutError:
    process.kill()
    await process.wait()
    raise ValueError("command timed out") from None
  if process.returncode:
    raise ValueError((err or out or b"").decode("utf-8", "replace")[:400])
  return (out or b"").decode("utf-8", "replace").strip()


async def _systemctl(action: str) -> None:
  await _command(["sudo", "-n", "systemctl", action, "bluetooth"])


def _has_bluez() -> bool:
  try:
    import jeepney  # noqa: F401

    from openpilot.sunnypilot.carrot.bluetooth.bluez import Bluez  # noqa: F401

    return True
  except Exception:
    return False


def _hardware_present() -> dict:
  """The two device nodes a Bluetooth-capable AGNOS build must expose."""
  return {"hasUart": os.path.exists(UART_PATH), "hasBtpower": os.path.exists(BTPOWER_PATH)}


async def _service_running() -> bool:
  try:
    await _command(["systemctl", "is-active", "bluetooth"], limit_sec=5.0)
    return True
  except ValueError:
    return False
  except FileNotFoundError:
    return False


def _guard(request: web.Request) -> None:
  """Setup is a parked-car operation: same-origin, JSON, stationary and disengaged."""
  origin = request.headers.get("Origin")
  if (origin and urlsplit(origin).netloc != request.host) or request.headers.get("Sec-Fetch-Site") == "cross-site":
    raise web.HTTPForbidden(text=json.dumps({"ok": False, "error": "same-origin requests only"}),
                            content_type="application/json")
  if request.content_type != "application/json":
    raise web.HTTPUnsupportedMediaType(text=json.dumps({"ok": False, "error": "application/json required"}),
                                       content_type="application/json")
  if not _runtime().get("stationary"):
    raise web.HTTPConflict(text=json.dumps({"ok": False, "error": "requires stationary and disengaged"}),
                           content_type="application/json")


async def api_status(request: web.Request) -> web.Response:
  model = _model()
  result = {
    "runtime": _runtime(),
    "config": model.config(),
    "actions": model.ACTIONS,
    "defaults": model.DEFAULT_MAPPING,
    "hasBluez": _has_bluez(),
    "serviceRunning": await _service_running(),
    **_hardware_present(),
  }
  try:
    result.update(await request.app[CLIENT].snapshot())
    result["available"] = True
    adapters = result.get("adapters") or []
    result["radioEnabled"] = any(a.get("powered") for a in adapters)
    result["discoverable"] = any(a.get("discoverable") for a in adapters)
    result["localName"] = (adapters[0].get("alias") or adapters[0].get("name") or "") if adapters else ""
  except Exception as exc:
    result.update(available=False, error=str(exc), devices=[], adapters=[],
                  radioEnabled=False, discoverable=False, localName="")
  return web.json_response({"ok": True, **result})


async def api_mutate(request: web.Request) -> web.Response:
  _guard(request)
  raw = await request.content.read(MAX_BODY_BYTES + 1)
  if len(raw) > MAX_BODY_BYTES:
    raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY_BYTES, actual_size=len(raw))
  try:
    body = json.loads(raw)
  except Exception:
    raise web.HTTPBadRequest(text=json.dumps({"ok": False, "error": "invalid json"}),
                             content_type="application/json") from None
  if not isinstance(body, dict):
    raise web.HTTPBadRequest(text=json.dumps({"ok": False, "error": "object required"}),
                             content_type="application/json")

  model = _model()
  client = request.app[CLIENT]
  operation = request.match_info["operation"]
  try:
    async with request.app[LOCK]:
      _guard(request)
      if operation == "scan":
        await client.scan()
      elif operation == "cancel":
        await client.cancel_pair()
      elif operation == "pair":
        await client.start_pair(model.AddressValidator().validate(body.get("address")))
      elif operation == "answer":
        client.respond(body.get("id"), body.get("value"))
      elif operation in ("connect", "disconnect", "forget"):
        mac = model.AddressValidator().validate(body.get("address"))
        await client.device_action(mac, operation)
        if operation != "connect":
          _cancel_pending(mac)
        if operation == "forget":
          settings = model.config()
          settings["devices"].pop(mac, None)
          model.atomic_json(model.CONFIG_PATH, settings)
      elif operation in ("config", "device-config"):
        previous = model.config()
        if operation == "device-config":
          mac = model.AddressValidator().validate(body.get("address"))
          settings = model.config()
          settings["devices"][mac] = body.get("device")
          settings = model.validate_config(settings)
        else:
          settings = model.validate_config(body)
        paired = {d["address"] for d in (await client.snapshot())["devices"] if d.get("paired")}
        if any(mac not in paired for mac in settings["devices"]):
          raise ValueError("pair devices before configuring input")
        model.atomic_json(model.CONFIG_PATH, settings)
        for mac, old in previous["devices"].items():
          if settings["devices"].get(mac) != old:
            _cancel_pending(mac)
      elif operation == "learn":
        mac = model.AddressValidator().validate(body.get("address"))
        if mac not in model.config()["devices"]:
          raise ValueError("save the input profile first")
        if not isinstance(body.get("enabled"), bool):
          raise ValueError("enabled must be boolean")
        model.atomic_json(model.RUNTIME / "learn.json",
                          {"address": mac, "until": time.monotonic() + 120} if body["enabled"] else {})
        _cancel_pending(mac)
      elif operation == "service":
        if not isinstance(body.get("start"), bool):
          raise ValueError("start must be boolean")
        await _systemctl("start" if body["start"] else "stop")
      elif operation == "radio":
        if not isinstance(body.get("enabled"), bool):
          raise ValueError("enabled must be boolean")
        await _command(["bluetoothctl", "power", "on" if body["enabled"] else "off"])
      elif operation == "discoverable":
        if not isinstance(body.get("enabled"), bool):
          raise ValueError("enabled must be boolean")
        await _command(["bluetoothctl", "discoverable", "on" if body["enabled"] else "off"])
      elif operation == "name":
        name = str(body.get("name") or "").strip()
        if not name:
          raise ValueError("name required")
        await _command(["bluetoothctl", "system-alias", name])
      else:
        raise web.HTTPNotFound(text=json.dumps({"ok": False, "error": f"unknown operation: {operation}"}),
                               content_type="application/json")
    return web.json_response({"ok": True})
  except (ValueError, TypeError, KeyError) as exc:
    raise web.HTTPBadRequest(text=json.dumps({"ok": False, "error": str(exc)}),
                             content_type="application/json") from exc
  except web.HTTPException:
    raise
  except Exception as exc:
    logger.exception("carrot_server: bluetooth %s failed", operation)
    raise web.HTTPBadGateway(text=json.dumps({"ok": False, "error": str(exc)}),
                             content_type="application/json") from exc


def _cancel_pending(mac: str) -> None:
  """Only the daemon writes command journals; readers reject cancelled events."""
  model = _model()
  cancelled = model.read_json(model.RUNTIME / "cancelled.json", {})
  if not isinstance(cancelled, dict):
    cancelled = {}
  cancelled[mac] = time.monotonic()
  model.atomic_json(model.RUNTIME / "cancelled.json", cancelled)


async def _close_client(app: web.Application) -> None:
  client = app.get(CLIENT)
  if client is not None:
    try:
      await client.close()
    except Exception:
      pass


def register(app: web.Application) -> None:
  try:
    from openpilot.sunnypilot.carrot.bluetooth.bluez import Bluez

    app[CLIENT] = Bluez()
  except Exception as exc:
    logger.warning("carrot_server: bluez unavailable: %s", exc)
    app[CLIENT] = None
  app[LOCK] = asyncio.Lock()
  app.router.add_get("/api/bluetooth", api_status)
  app.router.add_post("/api/bluetooth/{operation}", api_mutate)
  app.on_cleanup.append(_close_client)
