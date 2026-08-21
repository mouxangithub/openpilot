"""Device trust and pairing — optional device fingerprints (no LAN PIN)."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from aiohttp import web

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

PAIRED_DEVICES_KEY = "ai_paired_devices"
MAX_DEVICES = 32


def _load_devices(params: Params) -> list[dict[str, Any]]:
  raw = read_param(params, PAIRED_DEVICES_KEY)
  if not raw:
    return []
  try:
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_devices(params: Params, devices: list[dict[str, Any]]) -> None:
  write_param(params, PAIRED_DEVICES_KEY, json.dumps(devices[-MAX_DEVICES:], ensure_ascii=False))


def device_id_from_request(request: web.Request) -> str:
  did = (
    request.headers.get("X-AI-Device-Id")
    or request.headers.get("X-Device-Id")
    or request.query.get("deviceId")
    or ""
  ).strip()
  if did:
    return did[:128]
  ua = request.headers.get("User-Agent", "")
  ip = request.remote or ""
  digest = hashlib.sha256(f"{ua}|{ip}".encode()).hexdigest()[:24]
  return f"anon_{digest}"


def fingerprint_from_request(request: web.Request) -> str:
  fp = (request.headers.get("X-AI-Device-Fingerprint") or "").strip()
  if fp:
    return fp[:256]
  ua = request.headers.get("User-Agent", "")
  return hashlib.sha256(ua.encode()).hexdigest()[:32]


def is_pin_enabled(params: Params) -> bool:
  return False


def check_device_trust(request: web.Request, params: Params) -> dict[str, Any]:
  """Return trust status for a device. PIN alone still grants access."""
  device_id = device_id_from_request(request)
  fingerprint = fingerprint_from_request(request)
  devices = _load_devices(params)
  matched = next((d for d in devices if d.get("id") == device_id), None)
  trusted = bool(matched and matched.get("trusted", True))
  pin_ok = False
  if is_pin_enabled(params):
    pin = read_param(params, "ai_web_pin")
    pin_str = pin.decode() if isinstance(pin, bytes) else str(pin)
    supplied = (
      request.headers.get("X-AI-Pin")
      or request.headers.get("X-AI-Token")
      or request.query.get("pin")
      or ""
    )
    pin_ok = supplied == pin_str
  needs_pairing = is_pin_enabled(params) and not trusted and not pin_ok
  return {
    "deviceId": device_id,
    "fingerprint": fingerprint,
    "trusted": trusted or pin_ok or not is_pin_enabled(params),
    "needsPairing": needs_pairing,
    "paired": trusted,
    "label": matched.get("label", "") if matched else "",
  }


def list_paired_devices(params: Params) -> list[dict[str, Any]]:
  return [
    {
      "id": d.get("id", ""),
      "label": d.get("label", ""),
      "fingerprint": (d.get("fingerprint") or "")[:8] + "…",
      "pairedAt": d.get("pairedAt"),
      "lastSeenAt": d.get("lastSeenAt"),
      "trusted": bool(d.get("trusted", True)),
    }
    for d in _load_devices(params)
  ]


def pair_device(
  params: Params,
  *,
  device_id: str,
  fingerprint: str = "",
  label: str = "",
  pin: str = "",
) -> dict[str, Any]:
  if not device_id:
    return {"ok": False, "error": "deviceId required"}
  if is_pin_enabled(params):
    stored = read_param(params, "ai_web_pin")
    pin_str = stored.decode() if isinstance(stored, bytes) else str(stored or "")
    if pin != pin_str:
      return {"ok": False, "error": "Invalid PIN"}
  devices = _load_devices(params)
  now = int(time.time())
  entry = {
    "id": device_id[:128],
    "fingerprint": fingerprint[:256],
    "label": (label or "Browser")[:64],
    "pairedAt": now,
    "lastSeenAt": now,
    "trusted": True,
  }
  devices = [d for d in devices if d.get("id") != device_id]
  devices.append(entry)
  _save_devices(params, devices)
  return {"ok": True, "device": entry}


def touch_device(params: Params, device_id: str, fingerprint: str = "") -> None:
  if not device_id:
    return
  devices = _load_devices(params)
  changed = False
  for d in devices:
    if d.get("id") == device_id:
      d["lastSeenAt"] = int(time.time())
      if fingerprint:
        d["fingerprint"] = fingerprint[:256]
      changed = True
      break
  if changed:
    _save_devices(params, devices)


def revoke_device(params: Params, device_id: str) -> dict[str, Any]:
  devices = _load_devices(params)
  new_list = [d for d in devices if d.get("id") != device_id]
  if len(new_list) == len(devices):
    return {"ok": False, "error": "Device not found"}
  _save_devices(params, new_list)
  return {"ok": True}
