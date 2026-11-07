"""Bridge to Carrot tuning parameters.

Carrot's tuning surface (ATC/fork offsets, curve speed, blind spot, lane
change, navi speed, sound — mirrors ``_DEFAULT_NAV_PARAMS`` in
``openpilot/sunnypilot/carrot/config.py``) is registered in
``common/params_keys.h``, so values live in the cross-process Params store.
Carrot's ``UnifiedParams`` prefers the system Params store and falls back to
``nav_params.json`` for pre-registration values, so writes made here take
effect in the carrot daemon within its ~10 Hz ``update_params()`` refresh.

The defaults table below must stay in sync with ``_DEFAULT_NAV_PARAMS``;
it exists so the webui can display/reset correct values without importing
openpilot (which is unavailable on PC dev, where MockParams is used).
"""

from __future__ import annotations

from typing import Any

# key -> (kind, default). kind: "bool" | "int" | "float" | "str"
CARROT_TUNING_DEFAULTS: dict[str, tuple[str, Any]] = {
  # ATC / fork
  "AutoTurnDistOffset": ("int", 0),
  "AutoForkDistOffset": ("int", 30),
  "AutoDoForkBlinkerDist": ("int", 15),
  "AutoDoForkNavDist": ("int", 15),
  "AutoForkDistOffsetH": ("int", 1000),
  "AutoDoForkDecalDistH": ("int", 50),
  "AutoDoForkDecalDist": ("int", 20),
  "AutoDoForkBlinkerDistH": ("int", 30),
  "AutoDoForkNavDistH": ("int", 50),
  "AutoUpRoadLimit": ("int", 0),
  "AutoUpRoadLimit40KMH": ("int", 15),
  "AutoUpHighwayRoadLimit": ("int", 0),
  "AutoUpHighwayRoadLimit40KMH": ("int", 15),
  "RoadType": ("int", -1),
  "AutoForkDecalRateH": ("int", 80),
  "AutoForkSpeedMinH": ("int", 60),
  "AutoKeepForkSpeedH": ("int", 5),
  "AutoForkDecalRate": ("int", 80),
  "AutoForkSpeedMin": ("int", 45),
  "AutoKeepForkSpeed": ("int", 5),
  "ShowDebugLog": ("bool", 0),
  "AutoCurveSpeedFactorH": ("int", 100),
  "AutoCurveSpeedAggressivenessH": ("int", 100),
  "SameSpiCamFilter": ("bool", 1),
  "StockBlinkerCtrl": ("bool", 0),
  # Blind spot (BSD)
  "DynamicBlindRange": ("int", 0),
  "DynamicBlindDistance": ("int", 0),
  "DisableBlindSpot": ("bool", 0),
  "BsdDelayTime": ("int", 20),
  "SideBsdDelayTime": ("int", 20),
  "SideRelDistTime": ("int", 10),
  "SidevRelDistTime": ("int", 10),
  "SideRadarMinDist": ("int", 0),
  # Lane change / blinker
  "AutoTurnInNotRoadEdge": ("bool", 1),
  "ContinuousLaneChange": ("bool", 1),
  "NewLaneWidthDiff": ("int", 8),
  # Planner / cruise (float params stored as FLOAT in Params; defaults aligned
  # with openpilot/common/params_keys.h).
  # TFollowGap/CruiseMaxVals use CarrotPilot int*100 representation.
  "TFollowGap1": ("int", 110),
  "TFollowGap2": ("int", 120),
  "TFollowGap3": ("int", 140),
  "TFollowGap4": ("int", 160),
  "CruiseMaxVals0": ("int", 160),
  "CruiseMaxVals1": ("int", 160),
  "CruiseMaxVals2": ("int", 120),
  "CruiseMaxVals3": ("int", 100),
  "CruiseMaxVals4": ("int", 80),
  "CruiseMaxVals5": ("int", 70),
  "CruiseMaxVals6": ("int", 60),
  # Navi speed / sound
  "AutoNaviSpeedCtrlMode": ("int", 2),
  "AutoNaviSpeedDecelRate": ("int", 120),
  "AutoNaviSpeedSafetyFactor": ("int", 105),
  "SoundVolumeAdjust": ("int", 100),
  "SoundVolumeAdjustEngage": ("int", 100),
  # Vehicle CAN / cluster / planner control surface (P3 exposure).
  # Kinds and defaults mirror common/params_keys.h and
  # sunnypilot/carrot/config.py::_DEFAULT_NAV_PARAMS so the webui can
  # read/adjust/reset them through the same carrot tuning API.
  "VehicleNaviCanControl": ("int", 0),
  "VehicleNaviSchoolZoneControl": ("bool", 0),
  "VehicleSpeedCameraControlMode": ("int", 1),
  "VehicleNaviSectionAvgControl": ("bool", 0),
  "VehicleNaviSectionAvgMargin": ("int", 0),
  "LatSuspendAngleDeg": ("int", 300),
  "ClusterNaviMapTheme": ("int", 1),
  "ClusterNaviMapType": ("int", 0),
  "ClusterNaviMapFps": ("int", 1),
  "CarrotNaviHudMapProfile": ("bool", 0),
  # Diagnostic sink (not exposed in the panel)
  "CarrotException": ("str", ""),
  # --- Carrot longitudinal / t_follow (webui exposure) ---
  # int, not float: the parameter is declared INT (percent, consumer divides by
  # 100) and `carrot_put` casts by this kind, so a "float" here writes a float
  # into an INT key - TypeMismatch on every save.
  "DynamicTFollowLC": ("int", 100),
  "LeadAccelResponse": ("int", 0),
  "LongActuatorDelay": ("int", 20),
  "LongTuningKf": ("int", 100),
  "LongTuningKiV": ("int", 0),
  "LongTuningKpV": ("int", 100),
  "TFollowDecelBoost": ("int", 0),
  # --- Carrot cruise / acceleration (webui exposure) ---
  "CruiseButtonLongDelay": ("int", 40),
  "CruiseButtonMode": ("int", 0),
  "CruiseEcoControl": ("int", 2),
  "CruiseOnDist": ("int", 0),
  "CruiseSpeed1": ("int", 10),
  "CruiseSpeed2": ("int", 10),
  "CruiseSpeed3": ("int", 10),
  "CruiseSpeed4": ("int", 10),
  "CruiseSpeed5": ("int", 10),
  "CruiseSpeedUnit": ("int", 10),
  "CruiseSpeedUnitBasic": ("int", 10),
  # --- Carrot speed limits / road speed (webui exposure) ---
  "SpeedFromPCM": ("int", 0),
  # --- Carrot traffic stop / lights (webui exposure) ---
  "TrafficStopDistanceAdjust": ("int", -150),
  # --- Carrot lane change / blinker / lane-line (webui exposure) ---
  "LaneChangeDelay": ("int", 0),
  "LaneChangeNeedTorque": ("int", 0),
  "LaneLineCheck": ("int", 0),
  "OnnxBsdIntervalMs": ("int", 250),
  "OnnxBsdSmoothingMs": ("int", 200),
  "OnnxBsdThreshold": ("int", 94),
  "UseLaneLineCurveSpeed": ("int", 0),
  # --- Carrot steering / lateral (webui exposure) ---
  "AlwaysLateral": ("bool", 0),
  "CustomSR": ("int", 0),
  "LatMpcAccelCost": ("int", 100),
  "LatMpcJerkCost": ("int", 1),
  "LatMpcMotionCost": ("int", 7),
  "LatMpcPathCost": ("int", 200),
  "LatMpcSteeringRateCost": ("int", 7),
  "LateralTorqueCustom": ("bool", 1),
  "LateralTorqueFriction": ("int", 100),
  "LateralTorqueKd": ("int", 0),
  "LateralTorqueKf": ("int", 100),
  "LateralTorqueKiV": ("int", 10),
  "LateralTorqueKpV": ("int", 100),
  "PathOffset": ("int", 0),
  "SteerActuatorDelay": ("int", 30),
  "SteerRatioRate": ("int", 100),
  # --- Carrot vehicle / CAN / buttons (webui exposure) ---
  "AutoGasSyncSpeed": ("bool", 0),
  "CancelButtonMode": ("bool", 0),
  "LfaButtonMode": ("int", 0),
  # --- Carrot misc driving (webui exposure) ---
  "ApplyModelSpeed": ("int", 0),
  "AutoEngage": ("int", 0),
  "MyDrivingModeAuto": ("int", 0),

  # --- full alignment: remaining carrot tuning params (config 226 keys) ---
  "AutoCurveSpeedFactor": ("int", 100),
  "AutoCurveSpeedAggressiveness": ("int", 100),
  "AutoCurveSpeedLowerLimit": ("int", 30),
  "AutoNaviCountDownMode": ("int", 2),
  "AutoNaviSpeedBumpEndDistance": ("int", 200),
  # G2: now consumed by CarrotServ.rear_camera_speed (SDI 75/76 hold).
  "AutoNaviRearCameraHoldDistance": ("int", 100),
  "AutoNaviSpeedBumpSpeed": ("int", 35),
  "AutoNaviSpeedBumpTime": ("int", 1),
  "AutoNaviSpeedCtrlEnd": ("int", 6),
  "AutoRoadSpeedLimitOffset": ("int", -1),
  "AutoTurnControl": ("int", 0),
  "AutoTurnControlSpeedTurn": ("int", 20),
  "AutoTurnControlTurnEnd": ("int", 6),
  "AutoTurnMapChange": ("bool", 0),
  "CameraYawTrimDeg": ("int", 0),
  "CarrotYouTubeLive": ("bool", 0),
  "CarrotYouTubeQuality": ("int", 0),
  "CarrotYouTubeTimestamp": ("bool", 0),
  "ClusterHud": ("bool", 0),
  "ClusterHudBrightness": ("int", 0),
  "ClusterHudCameraViewMode": ("int", 0),
  "ClusterHudCoreMode": ("int", 0),
  "ClusterHudDebug": ("bool", 0),
  "ClusterHudEncoder": ("int", 0),
  "ClusterHudLiveFps": ("int", 1),
  "ClusterHudMirror": ("bool", 0),
  "ClusterHudOrientation": ("int", 0),
  "ClusterHudPanelLayout": ("int", 0),
  "ClusterHudPriority": ("int", 10),
  "ClusterHudRadarDisplay": ("bool", 0),
  "ClusterHudRadarInfo": ("int", 4),
  "ClusterHudRadarSourceColor": ("bool", 0),
  "ClusterHudScreenMode": ("int", 0),
  "ClusterHudTheme": ("int", 0),
  "EnableRadarTracks": ("bool", 0),
  "EnableSpeedTF": ("int", 0),
  "HotspotOnBoot": ("bool", 0),
  "LatMpcInputOffset": ("int", 4),
  "LatSmoothSec": ("int", 13),
  "LateralTorqueAccelFactor": ("int", 2500),
  "MapTurnSpeedFactor": ("int", 100),
  "MapboxStyle": ("int", 0),
  "MuteDoor": ("bool", 0),
  "MuteSeatbelt": ("bool", 0),
  "MyDrivingMode": ("int", 3),
  "OnnxLaneIntervalMs": ("int", 400),
  "OnnxLaneThreshold": ("int", 25),
  "RecordRoadCam": ("bool", 0),
  "ShareData": ("bool", 0),
  "ShowCameraWithCluster": ("bool", 0),
  "ShowCustomBrightness": ("int", 100),
  "ShowDateTime": ("bool", 1),
  "ShowDebugUI": ("bool", 1),
  "ShowDeviceState": ("bool", 1),
  "ShowLaneInfo": ("bool", 1),
  "ShowModelView": ("bool", 0),
  "ShowPathColor": ("int", 12),
  "ShowPathColorCruiseOff": ("int", 1),
  "ShowPathColorLane": ("int", 3),
  "ShowPathEnd": ("bool", 1),
  "ShowPathMode": ("int", 9),
  "ShowPathModeLane": ("int", 11),
  "ShowPlotMode": ("bool", 0),
  "ShowRadarInfo": ("bool", 0),
  "ShowRouteInfo": ("bool", 0),
  "ShowTpms": ("bool", 1),
  "SoftwareMenu": ("bool", 0),
  "SoundLanguageSetting": ("str", "auto"),
  "TrafficLightDetectMode": ("int", 2),
  "TurnSpeedControlMode": ("int", 1),
  "UseWideCamera": ("bool", 1),
  "VehicleSpeedCameraDistanceTime": ("int", 60),
  # --- cp tuning alignment: params present in CarrotPilot settings but missing
  # here; defaults mirror config.py::_DEFAULT_NAV_PARAMS ---
  "CruiseGapLevels": ("int", 4),
  "AutoCruiseControl": ("int", 0),
  "HapticFeedbackWhenSpeedCamera": ("int", 0),
  "BydBsdType2": ("bool", 0),
  "BydLatUseSiglin": ("bool", 0),
  "BydLowSpdLong": ("bool", 0),
  "BydModifiedStockLong": ("bool", 0),
  "BydMpcTsr": ("bool", 0),
  "EnableExtRadar": ("bool", 0),
  "UseRedPanda": ("bool", 0),
  "SpeedCorrect30": ("int", 0),
  "SpeedCorrect60": ("int", 0),
  "SpeedCorrect90": ("int", 0),
  "SpeedCorrect120": ("int", 0),
  "AutoGasCancelSpeed": ("int", 30),
  "AutoGasTokSpeed": ("int", 0),
  "PaddleMode": ("int", 0),
  "SoftHoldOnCancel": ("bool", 0),
  "UseLaneLineSpeed": ("int", 0),
  "AutoRoadSpeedAdjust": ("int", 50),
  "AutoSpeedUptoRoadSpeedLimit": ("int", 0),
  "LeadAccelResponseTF1": ("int", -1),
  "LeadAccelResponseTF2": ("int", -1),
  "LeadAccelResponseTF3": ("int", -1),
  "LeadAccelResponseTF4": ("int", -1),
  "AutoNaviRearCameraHoldDistance": ("int", 100),
  # --- unified-control killswitches (default OFF; surfaced in the Developer
  # page). Listed here so the webui read/write whitelist accepts them. ---
  "CarrotTrafficCongestionEnabled": ("bool", 0),
  "CarrotNavLaneGuideBlockEnabled": ("bool", 0),
  # The heaviest of the three: with it on, the phone app's speed target and follow
  # time reach the MPC. Registered here for the same reason as its neighbours - the
  # Developer page exposes it natively, so the webui read/write whitelist must accept
  # the key too or the two UIs would disagree about which params exist.
  "CarrotLongitudinalSourceEnabled": ("bool", 0),
  # Master switch for the xiaoge v_asm ONNX blind-spot / lane server (off unloads
  # the resident model). The Developer page exposes it natively alongside the
  # thresholds below, so the whitelist accepts it for the same reason.
  "OnnxBsdEnabled": ("bool", 0),
}

_PARAM_TYPE_NAMES = {"bool": "BOOL", "int": "INT", "float": "FLOAT", "str": "STRING"}


def _params() -> Any:
  from webui.server.bridge.params_api import _params as _op_params
  return _op_params()


def is_carrot_key(key: str) -> bool:
  return bool(key) and key in CARROT_TUNING_DEFAULTS


def carrot_keys() -> list[str]:
  return sorted(CARROT_TUNING_DEFAULTS.keys())


def _param_type_name(key: str) -> str:
  return _PARAM_TYPE_NAMES[CARROT_TUNING_DEFAULTS[key][0]]


def _serialize(key: str, value: Any) -> str:
  kind = CARROT_TUNING_DEFAULTS[key][0]
  if kind == "bool":
    return "1" if value else "0"
  return "" if value is None else str(value)


def carrot_value_str(key: str) -> str | None:
  """Read one tuning key; falls back to the compiled-in default when unset."""
  if not is_carrot_key(key):
    return None
  try:
    p = _params()
    try:
      value = p.get(key, return_default=True)
    except TypeError:
      value = p.get(key)
    if value is None:
      value = CARROT_TUNING_DEFAULTS[key][1]
  except Exception:
    value = CARROT_TUNING_DEFAULTS[key][1]
  return _serialize(key, value)


def carrot_get(key: str) -> dict[str, Any]:
  if not is_carrot_key(key):
    return {"ok": False, "error": f"unknown carrot tuning param: {key}"}
  return {
    "ok": True,
    "key": key,
    "value": carrot_value_str(key),
    "type": _param_type_name(key),
    "locked": False,
  }


def carrot_put(key: str, value: str) -> dict[str, Any]:
  if not is_carrot_key(key):
    return {"ok": False, "error": f"unknown carrot tuning param: {key}"}
  kind = CARROT_TUNING_DEFAULTS[key][0]
  try:
    if kind == "bool":
      coerced = value in ("1", "true", "True", True, 1)
    elif kind == "float":
      coerced = float(value)
    elif kind == "int":
      coerced = int(float(value)) if value not in (None, "") else CARROT_TUNING_DEFAULTS[key][1]
    else:
      coerced = str(value)
  except (TypeError, ValueError):
    return {"ok": False, "error": f"invalid value for {key}: {value!r}"}
  try:
    p = _params()
    if kind == "bool":
      p.put_bool(key, bool(coerced), block=True)
    else:
      # Params.put() casts from the Python type matching the registered key type
      # (int for INT, float for FLOAT, str for STRING); do not pre-serialize.
      p.put(key, coerced, block=True)
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
  return {"ok": True, "key": key, "value": carrot_value_str(key)}


def carrot_reset(key: str) -> dict[str, Any]:
  """Restore one tuning key to its compiled-in default (remove + default read)."""
  if not is_carrot_key(key):
    return {"ok": False, "error": f"unknown carrot tuning param: {key}"}
  try:
    _params().remove(key)
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
  return {"ok": True, "key": key, "value": carrot_value_str(key)}


def carrot_reset_all() -> dict[str, Any]:
  """Restore every tuning key to its compiled-in default."""
  count = 0
  errors: list[str] = []
  try:
    p = _params()
  except Exception as exc:
    return {"ok": False, "action": "carrot_tuning_reset", "count": 0, "errors": [str(exc)]}
  for key in CARROT_TUNING_DEFAULTS:
    try:
      p.remove(key)
      count += 1
    except Exception as exc:
      errors.append(f"{key}: {exc}")
  return {"ok": not errors, "action": "carrot_tuning_reset", "count": count, "errors": errors}
