"""Bluetooth setup HTTP API for webui.

HTTP can configure mappings and device management (scan/pair/config/connect/disconnect).
Vehicle command safety (accelCruise etc.) is enforced by the daemon's evdev reader
via _guard_stationary() in bluetoothd, not here.

Requires:
  - jeepney (D-Bus async, for BlueZ integration)
  - sudo access (for systemctl bluetooth, chgrp/chmod on evdev nodes)

Endpoints exposed via routes/__init__.py:
  GET  /api/opui/bluetooth           → status snapshot
  POST /api/opui/bluetooth/scan     → start discovery
  POST /api/opui/bluetooth/pair     → begin pairing
  POST /api/opui/bluetooth/cancel    → cancel ongoing pairing
  POST /api/opui/bluetooth/answer   → respond to pairing prompt
  POST /api/opui/bluetooth/connect  → connect to device
  POST /api/opui/bluetooth/disconnect → disconnect device
  POST /api/opui/bluetooth/forget  → remove device
  POST /api/opui/bluetooth/config   → save full config
  POST /api/opui/bluetooth/device-config → save per-device config
  POST /api/opui/bluetooth/learn    → enter/exit learning mode
  POST /api/opui/bluetooth/radio   → enable/disable BT radio
"""

from __future__ import annotations

import asyncio
import os
import time
from urllib.parse import urlsplit

from aiohttp import web

from openpilot.sunnypilot.carrot.bluetooth import (
  ACTIONS,
  CONFIG_PATH,
  DEFAULT_MAPPING,
  RUNTIME,
  AddressValidator,
  AtomicJSON,
  config,
  read_json,
  validate_config,
)
from openpilot.sunnypilot.carrot.bluetooth.bluez import Bluez


# ---------------------------------------------------------------------------
# Module-level Bluez client (one per app lifetime)
# ---------------------------------------------------------------------------
_bluez_client: Bluez | None = None
_bluez_lock: asyncio.Lock | None = None


def _get_client() -> tuple[Bluez, asyncio.Lock]:
  global _bluez_client, _bluez_lock
  if _bluez_client is None:
    _bluez_client = Bluez()
    _bluez_lock = asyncio.Lock()
  return _bluez_client, _bluez_lock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _has_bluez() -> bool:
  """Check whether the bluetoothd daemon binary is present."""
  process = await asyncio.create_subprocess_exec(
    'bash', '-c', 'command -v bluetoothd',
    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
  )
  try:
    stdout, _ = await asyncio.wait_for(process.communicate(), 3)
    return process.returncode == 0 and bool(stdout.strip())
  except TimeoutError:
    process.kill()
    await process.wait()
    return False


async def _service_running() -> bool:
  """Check whether the bluetooth systemd service is active."""
  process = await asyncio.create_subprocess_exec(
    'systemctl', 'is-active', '--quiet', 'bluetooth',
    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
  )
  try:
    return await asyncio.wait_for(process.wait(), 3) == 0
  except TimeoutError:
    process.kill()
    await process.wait()
    return False


async def _radio_enabled() -> bool:
  """Check if the Bluetooth radio is enabled via /data/bluetooth/ENABLED."""
  process = await asyncio.create_subprocess_exec(
    'sudo', '-n', 'test', '-f', '/data/bluetooth/ENABLED',
    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
  )
  try:
    return await asyncio.wait_for(process.wait(), 3) == 0
  except TimeoutError:
    process.kill()
    await process.wait()
    return False




def _runtime_status() -> dict:
  """Read and annotate daemon runtime status from /dev/shm/carrot-bluetooth/status.json."""
  state = read_json(RUNTIME / 'status.json', {})
  if not isinstance(state, dict):
    state = {}
  stamp = state.get('time', 0)
  state['alive'] = (
    isinstance(stamp, (float, int))
    and 0 <= time.monotonic() - stamp < 2
    and not state.get('stopped')
  )
  state['stationary'] = bool(state['alive'] and state.get('stationary'))
  return state


def _guard_stationary(request: web.Request) -> None:
  """Raise HTTP 409 if the vehicle is not stationary or cruise is engaged."""
  origin = request.headers.get('Origin')
  if origin and urlsplit(origin).netloc != request.host \
     or request.headers.get('Sec-Fetch-Site') == 'cross-site':
    raise web.HTTPForbidden(text='same-origin requests only')
  if request.content_type != 'application/json':
    raise web.HTTPUnsupportedMediaType(text='application/json required')
  if not _runtime_status()['stationary']:
    raise web.HTTPConflict(text='setup requires fresh stationary and disengaged state')


def _cancel_pending(mac: str) -> None:
  """Record that all commands from mac are cancelled (graceful disconnect)."""
  cancelled = read_json(RUNTIME / 'cancelled.json', {})
  if not isinstance(cancelled, dict):
    cancelled = {}
  cancelled[mac] = time.monotonic()
  AtomicJSON(RUNTIME / 'cancelled.json', cancelled)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def api_bluetooth_status(request: web.Request) -> web.Response:
  """GET /api/opui/bluetooth — full status snapshot."""
  has_bluez = await _has_bluez()
  service_running = await _service_running() if has_bluez else False

  result: dict = {
    'runtime': _runtime_status(),
    'config': config(),
    'actions': ACTIONS,
    'defaults': DEFAULT_MAPPING,
    'hasBluez': has_bluez,
    'serviceRunning': service_running,
    'radioEnabled': await _radio_enabled(),
    'discoverable': False,
    'localName': None,
    'hasUart': os.path.exists('/dev/ttyHS1'),
    'hasBtpower': os.path.exists('/dev/btpower'),
  }

  client, _ = _get_client()
  try:
    snapshot = await client.snapshot()
    result.update(snapshot)
    result['available'] = len(snapshot.get('adapters', [])) > 0
    result.update(_adapter_props_real(snapshot))
  except Exception as exc:
    error_str = str(exc)
    # DBus service unavailable — provide a clean user-facing message
    if "ServiceUnknown" in error_str or "org.bluez" in error_str:
      if not has_bluez:
        error_str = "Bluetooth is not installed."
      elif not service_running:
        error_str = "Bluetooth service is stopped."
      else:
        error_str = "Bluetooth adapter not found."
    result.update(available=False, error=error_str, devices=[], adapters=[])
  return web.json_response(result)


def _adapter_props_real(snapshot: dict) -> dict:
  """Extract localName/discoverable/radioEnabled from the first adapter."""
  for adapter in snapshot.get('adapters', []):
    return {
      'localName': adapter.get('name') or adapter.get('alias'),
      'discoverable': bool(adapter.get('discoverable')),
      'radioEnabled': bool(adapter.get('powered')),
    }
  return {}


async def api_bluetooth_mutate(request: web.Request) -> web.Response:
  """POST /api/opui/bluetooth/{operation} — all state-changing operations.

  Note: This HTTP API handles Bluetooth configuration only (scan/pair/config).
  Vehicle command safety is enforced by the daemon's evdev reader via
  _guard_stationary() in bluetoothd, not here.
  """

  if request.content_length is not None and request.content_length > 32768:
    raise web.HTTPRequestEntityTooLarge(max_size=32768, actual_size=request.content_length)
  raw = await request.content.read(32769)
  if len(raw) > 32768:
    raise web.HTTPRequestEntityTooLarge(max_size=32768, actual_size=len(raw))

  import json
  try:
    body = json.loads(raw)
    if not isinstance(body, dict):
      raise ValueError('object required')
  except json.JSONDecodeError as exc:
    raise web.HTTPBadRequest(text=str(exc)) from exc

  operation = request.match_info.get('operation', '')
  client, lock = _get_client()

  async with lock:
    try:
      if operation == 'scan':
        await client.scan()

      elif operation == 'pair':
        await client.start_pair(AddressValidator.validate(body.get('address', '')))

      elif operation == 'cancel':
        await client.cancel_pair()

      elif operation == 'answer':
        client.respond(body.get('id'), body.get('value'))

      elif operation in ('connect', 'disconnect', 'forget'):
        mac = AddressValidator.validate(body.get('address', ''))
        await client.device_action(mac, operation)
        if operation != 'connect':
          _cancel_pending(mac)
        if operation == 'forget':
          settings = config()
          settings['devices'].pop(mac, None)
          AtomicJSON(CONFIG_PATH, settings)

      elif operation in ('config', 'device-config'):
        previous = config()
        if operation == 'device-config':
          mac = AddressValidator.validate(body.get('address', ''))
          settings = config()
          settings['devices'][mac] = body.get('device')
          settings = validate_config(settings)
        else:
          settings = validate_config(body)
        # Ensure all configured devices are actually paired before saving.
        paired = {
          d['address'] for d in (await client.snapshot())['devices'] if d['paired']
        }
        if any(mac not in paired for mac in settings['devices']):
          raise ValueError('pair devices before configuring input')
        AtomicJSON(CONFIG_PATH, settings)
        for mac, old in previous['devices'].items():
          if settings['devices'].get(mac) != old:
            _cancel_pending(mac)

      elif operation == 'learn':
        mac = AddressValidator.validate(body.get('address', ''))
        if mac not in config()['devices']:
          raise ValueError('save the input profile first')
        if type(body.get('enabled')) is not bool:
          raise ValueError('enabled must be boolean')
        AtomicJSON(
          RUNTIME / 'learn.json',
          {'address': mac, 'until': time.monotonic() + 120} if body['enabled'] else {},
        )
        _cancel_pending(mac)

      elif operation == 'radio':
        if type(body.get('enabled')) is not bool:
          raise ValueError('enabled must be boolean')
        await client.close()
        commands = (
          [['sudo', '-n', 'mkdir', '-p', '/data/bluetooth'],
           ['sudo', '-n', 'touch', '/data/bluetooth/ENABLED'],
           ['sudo', '-n', 'systemctl', 'start', 'carrot-bluetooth-radio']]
          if body['enabled']
          else [['sudo', '-n', 'rm', '-f', '/data/bluetooth/ENABLED'],
                 ['sudo', '-n', 'systemctl', 'stop', 'carrot-bluetooth-radio'],
                 ['sudo', '-n', 'systemctl', 'stop', 'bluetooth']]
        )
        for command in commands:
          proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
          )
          try:
            _, error = await asyncio.wait_for(proc.communicate(), 20)
          except TimeoutError:
            proc.kill()
            await proc.wait()
            raise ValueError('radio operation timed out') from None
          if proc.returncode:
            raise ValueError(error.decode(errors='replace')[:500])

      elif operation == 'install':
        proc = await asyncio.create_subprocess_exec(
          'sudo', '-n', 'bash', '-c',
          'apt-get update && apt-get install -y bluez && systemctl start bluetooth',
          stdout=asyncio.subprocess.PIPE,
          stderr=asyncio.subprocess.PIPE,
        )
        try:
          _, error = await asyncio.wait_for(proc.communicate(), 180)
        except TimeoutError:
          proc.kill()
          await proc.wait()
          raise ValueError('bluez installation timed out') from None
        if proc.returncode:
          raise ValueError(error.decode(errors='replace')[:1000])

      elif operation == 'service':
        if type(body.get('start')) is not bool:
          raise ValueError('start must be boolean')
        command = ['sudo', '-n', 'systemctl', 'start', 'bluetooth'] if body['start'] else ['sudo', '-n', 'systemctl', 'stop', 'bluetooth']
        proc = await asyncio.create_subprocess_exec(
          *command,
          stdout=asyncio.subprocess.DEVNULL,
          stderr=asyncio.subprocess.PIPE,
        )
        try:
          _, error = await asyncio.wait_for(proc.communicate(), 30)
        except TimeoutError:
          proc.kill()
          await proc.wait()
          raise ValueError('service operation timed out') from None
        if proc.returncode:
          raise ValueError(error.decode(errors='replace')[:500])

      elif operation == 'name':
        name = str(body.get('name', '')).strip()
        if not 1 <= len(name) <= 248:
          raise ValueError('device name must be 1 to 248 characters')
        adapters = [p for p, interfaces in (await client.objects()).items() if 'org.bluez.Adapter1' in interfaces]
        if not adapters:
          raise ValueError('Bluetooth adapter unavailable')
        await client.call(adapters[0], 'org.freedesktop.DBus.Properties', 'Set', 'ssv', ('org.bluez.Adapter1', 'Alias', ('s', name)))

      elif operation == 'discoverable':
        if type(body.get('enabled')) is not bool:
          raise ValueError('enabled must be boolean')
        adapters = [p for p, interfaces in (await client.objects()).items() if 'org.bluez.Adapter1' in interfaces]
        if not adapters:
          raise ValueError('Bluetooth adapter unavailable')
        await client.call(adapters[0], 'org.freedesktop.DBus.Properties', 'Set', 'ssv', ('org.bluez.Adapter1', 'Discoverable', ('b', body['enabled'])))

      else:
        raise web.HTTPNotFound()

    except (ValueError, TypeError, KeyError) as exc:
      raise web.HTTPBadRequest(text=str(exc)) from exc
    except web.HTTPException:
      raise
    except Exception as exc:
      raise web.HTTPBadGateway(text=str(exc)) from exc

  return web.json_response({'ok': True})
