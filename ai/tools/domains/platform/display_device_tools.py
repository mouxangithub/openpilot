"""Display / device openpilot settings (brightness, offroad, boot mode)."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params

DISPLAY_INT_KEYS = ("OnroadScreenOffBrightness", "OnroadScreenOffTimer", "InteractivityTimeout", "Brightness")
DEVICE_KEYS = ("MaxTimeOffroad", "DeviceBootMode", "QuietMode", "OnroadUploads", "ShowAdvancedControls")
DEV_BOOL_KEYS = ("EnableGithubRunner", "EnableCopyparty", "QuickBootToggle")


def _read_bool(params: Params, key: str) -> bool | None:
  try:
    if params.get(key) is None:
      return None
    return params.get_bool(key)
  except Exception:
    return None


def _read_scalar(params: Params, key: str) -> Any:
  try:
    return params.get(key, return_default=True)
  except Exception:
    val = params.get(key)
    if isinstance(val, bytes):
      return val.decode(errors="replace")
    return val


def get_display_settings(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  out = {k: _read_scalar(params, k) for k in DISPLAY_INT_KEYS}
  return {"ok": True, "section": "Display", "settings": out}


def apply_display_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  allowed = {k: v for k, v in writes.items() if k in DISPLAY_INT_KEYS}
  if not allowed:
    return {"ok": False, "error": "No valid display keys"}
  for key, val in allowed.items():
    params.put(key, str(val))
  return {"ok": True, "applied": allowed, "current": get_display_settings(params)}


def get_device_settings(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  out: dict[str, Any] = {}
  for k in DEVICE_KEYS:
    if k in ("QuietMode", "OnroadUploads", "ShowAdvancedControls"):
      out[k] = _read_bool(params, k)
    else:
      out[k] = _read_scalar(params, k)
  for k in DEV_BOOL_KEYS:
    out[k] = _read_bool(params, k)
  return {"ok": True, "section": "Device", "settings": out}


def apply_device_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  bool_keys = {"QuietMode", "OnroadUploads", "ShowAdvancedControls", *DEV_BOOL_KEYS}
  allowed = {k: v for k, v in writes.items() if k in DEVICE_KEYS or k in DEV_BOOL_KEYS}
  if not allowed:
    return {"ok": False, "error": "No valid device keys"}
  for key, val in allowed.items():
    if key in bool_keys:
      params.put_bool(key, val in (True, 1, "1", "true"))
    else:
      params.put(key, str(val))
  return {"ok": True, "applied": allowed, "current": get_device_settings(params)}


def preview_group_writes(params: Params, writes: dict[str, Any], group: str) -> dict[str, Any]:
  from ai.tools.diagnostics_tools import diff_params
  if group == "display":
    allowed = {k: v for k, v in writes.items() if k in DISPLAY_INT_KEYS}
  elif group == "device":
    bool_keys = {"QuietMode", "OnroadUploads", "ShowAdvancedControls", *DEV_BOOL_KEYS}
    allowed = {k: v for k, v in writes.items() if k in DEVICE_KEYS or k in bool_keys}
  else:
    return {"ok": False, "error": f"unknown group: {group}"}
  if not allowed:
    return {"ok": False, "error": "No valid keys"}
  return diff_params(params, allowed)
