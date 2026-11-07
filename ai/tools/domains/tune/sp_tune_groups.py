"""Grouped openpilot tune settings: torque, lane change, speed limit, visuals."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params

TORQUE_BOOL_KEYS = ("LiveTorqueParamsToggle", "LiveTorqueParamsRelaxedToggle", "CustomTorqueParams", "TorqueParamsOverrideEnabled", "EnforceTorqueControl")
TORQUE_FLOAT_KEYS = ("TorqueParamsOverrideLatAccelFactor", "TorqueParamsOverrideFriction", "TorqueControlTune")
LANE_CHANGE_KEYS = ("AutoLaneChangeTimer", "AutoLaneChangeBsmDelay")
SPEED_LIMIT_KEYS = ("SpeedLimitMode", "SpeedLimitOffsetType", "SpeedLimitValueOffset", "SpeedLimitPolicy")
VISUALS_BOOL_KEYS = (
  "BlindSpot", "TorqueBar", "RainbowMode", "StandstillTimer", "RoadNameToggle",
  "GreenLightAlert", "LeadDepartAlert", "TrueVEgoUI", "HideVEgoUI", "ShowTurnSignals", "RocketFuel",
)
VISUALS_INT_KEYS = ("ChevronInfo", "DevUIInfo")


def _read_bool(params: Params, key: str) -> bool | None:
  try:
    if params.get(key) is None:
      return None
    return params.get_bool(key)
  except Exception:
    val = params.get(key)
    if val is None:
      return None
    if isinstance(val, bytes):
      val = val.decode(errors="replace")
    return str(val).lower() in ("1", "true")


def _read_scalar(params: Params, key: str) -> Any:
  try:
    return params.get(key, return_default=True)
  except Exception:
    val = params.get(key)
    if isinstance(val, bytes):
      return val.decode(errors="replace")
    return val


def _pick_writes(writes: dict[str, Any], allowed: tuple[str, ...]) -> dict[str, Any]:
  return {k: v for k, v in writes.items() if k in allowed}


def get_torque_settings(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  out = {k: _read_bool(params, k) for k in TORQUE_BOOL_KEYS}
  for k in TORQUE_FLOAT_KEYS:
    out[k] = _read_scalar(params, k)
  return {"ok": True, "section": "Torque", "settings": out}


def apply_torque_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  allowed = {**_pick_writes(writes, TORQUE_BOOL_KEYS), **_pick_writes(writes, TORQUE_FLOAT_KEYS)}
  if not allowed:
    return {"ok": False, "error": "No valid torque keys"}
  for key, val in allowed.items():
    if key in TORQUE_BOOL_KEYS:
      params.put_bool(key, val in (True, 1, "1", "true"))
    else:
      params.put(key, str(val))
  return {"ok": True, "applied": allowed, "current": get_torque_settings(params)}


def get_lane_change_settings(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  out = {k: _read_scalar(params, k) for k in LANE_CHANGE_KEYS}
  return {"ok": True, "section": "LaneChange", "settings": out}


def apply_lane_change_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  allowed = _pick_writes(writes, LANE_CHANGE_KEYS)
  if not allowed:
    return {"ok": False, "error": "No valid lane change keys"}
  for key, val in allowed.items():
    params.put(key, str(val))
  return {"ok": True, "applied": allowed, "current": get_lane_change_settings(params)}


def get_speed_limit_settings(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  out = {k: _read_scalar(params, k) for k in SPEED_LIMIT_KEYS}
  return {"ok": True, "section": "SpeedLimit", "settings": out}


def apply_speed_limit_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  allowed = _pick_writes(writes, SPEED_LIMIT_KEYS)
  if not allowed:
    return {"ok": False, "error": "No valid speed limit keys"}
  for key, val in allowed.items():
    params.put(key, str(val))
  return {"ok": True, "applied": allowed, "current": get_speed_limit_settings(params)}


def list_visuals_settings(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  out: dict[str, Any] = {}
  for k in VISUALS_BOOL_KEYS:
    out[k] = _read_bool(params, k)
  for k in VISUALS_INT_KEYS:
    out[k] = _read_scalar(params, k)
  return {"ok": True, "section": "Visuals", "settings": out}


def apply_visuals_writes(params: Params, writes: dict[str, Any]) -> dict[str, Any]:
  allowed = {**_pick_writes(writes, VISUALS_BOOL_KEYS), **_pick_writes(writes, VISUALS_INT_KEYS)}
  if not allowed:
    return {"ok": False, "error": "No valid visuals keys"}
  for key, val in allowed.items():
    if key in VISUALS_BOOL_KEYS:
      params.put_bool(key, val in (True, 1, "1", "true"))
    else:
      params.put(key, str(val))
  return {"ok": True, "applied": allowed, "current": list_visuals_settings(params)}


def preview_group_writes(params: Params, writes: dict[str, Any], group: str) -> dict[str, Any]:
  from ai.tools.diagnostics_tools import diff_params

  if group == "torque":
    allowed = {**_pick_writes(writes, TORQUE_BOOL_KEYS), **_pick_writes(writes, TORQUE_FLOAT_KEYS)}
  elif group == "lane_change":
    allowed = _pick_writes(writes, LANE_CHANGE_KEYS)
  elif group == "speed_limit":
    allowed = _pick_writes(writes, SPEED_LIMIT_KEYS)
  elif group == "visuals":
    allowed = {**_pick_writes(writes, VISUALS_BOOL_KEYS), **_pick_writes(writes, VISUALS_INT_KEYS)}
  else:
    return {"ok": False, "error": f"unknown group: {group}"}
  if not allowed:
    return {"ok": False, "error": "No valid keys for group"}
  return diff_params(params, allowed)
