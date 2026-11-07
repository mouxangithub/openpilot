"""openpilot MADS (Modular Assistive Driving System) settings."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params

MADS_BOOL_KEYS = ("Mads", "MadsMainCruiseAllowed", "MadsUnifiedEngagementMode")
MADS_INT_KEYS = ("MadsSteeringMode",)

STEERING_MODE_LABELS = {
  0: "remain_active",
  1: "pause",
  2: "disengage",
}


def _read_bool(params: Params, key: str) -> bool | None:
  try:
    return params.get_bool(key)
  except Exception:
    val = params.get(key)
    if val is None:
      return None
    if isinstance(val, bytes):
      val = val.decode(errors="replace")
    return str(val).lower() in ("1", "true", "yes")


def _read_int(params: Params, key: str) -> int | None:
  try:
    val = params.get(key, return_default=True)
    if val is None:
      return None
    return int(val)
  except Exception:
    return None


def get_mads_settings(params: Params | None = None) -> dict[str, Any]:
  """Read MADS master toggle and sub-settings (UI: Steering → MADS)."""
  params = params or Params()
  steering_mode = _read_int(params, "MadsSteeringMode")
  return {
    "ok": True,
    "Mads": _read_bool(params, "Mads"),
    "MadsMainCruiseAllowed": _read_bool(params, "MadsMainCruiseAllowed"),
    "MadsUnifiedEngagementMode": _read_bool(params, "MadsUnifiedEngagementMode"),
    "MadsSteeringMode": steering_mode,
    "MadsSteeringMode_label": STEERING_MODE_LABELS.get(steering_mode or 0, "unknown"),
    "steering_mode_options": STEERING_MODE_LABELS,
    "hint": "Write via write_params while stationary. Some platforms limit MADS sub-options.",
  }


def preview_mads_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  from ai.tools.diagnostics_tools import diff_params

  allowed = {k: v for k, v in writes.items() if k in MADS_BOOL_KEYS or k in MADS_INT_KEYS}
  if not allowed:
    return {"ok": False, "error": "No valid MADS keys in writes"}
  return diff_params(params, allowed)


def apply_mads_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  """Apply MADS param writes (bool/int only)."""
  allowed: dict[str, Any] = {}
  for key, val in writes.items():
    if key in MADS_BOOL_KEYS:
      allowed[key] = "1" if val in (True, 1, "1", "true") else "0"
    elif key in MADS_INT_KEYS:
      mode = int(val)
      if mode not in STEERING_MODE_LABELS:
        return {"ok": False, "error": f"invalid MadsSteeringMode: {val} (0/1/2)"}
      allowed[key] = str(mode)
  if not allowed:
    return {"ok": False, "error": "No valid MADS keys"}
  for key, val in allowed.items():
    if key in MADS_BOOL_KEYS:
      params.put_bool(key, val == "1")
    else:
      params.put(key, val)
  return {"ok": True, "applied": allowed, "current": get_mads_settings(params)}
