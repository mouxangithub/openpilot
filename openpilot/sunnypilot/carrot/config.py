"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Unified parameter access for the Carrot/Amap module.

Ported from CarrotPilot. Falls back to ``nav_params.json`` defaults whenever a
key is not registered in the openpilot Params store, so carrot tuning can be
exposed without polluting ``common/params_keys.h``.
"""
import json
import os
from typing import Any, Optional

from openpilot.common.params import Params

try:
  # UnknownKeyName lives in common.params (params_pyx was merged into it);
  # importing it here is what lets _read_from_system/_write_to_system swallow
  # the "key not registered" error for carrot-only tuning keys.
  from openpilot.common.params import UnknownKeyName
except ImportError:
  UnknownKeyName = KeyError  # type: ignore[misc,assignment]


_DEFAULT_NAV_PARAMS: dict[str, Any] = {
  # ATC / turn offsets
  "AutoTurnDistOffset": 0,
  "AutoForkDistOffset": 30,
  "AutoDoForkBlinkerDist": 15,
  "AutoDoForkNavDist": 15,
  "AutoForkDistOffsetH": 1000,
  "AutoDoForkDecalDistH": 50,
  "AutoDoForkDecalDist": 20,
  "AutoDoForkBlinkerDistH": 30,
  "AutoDoForkNavDistH": 50,
  "AutoUpRoadLimit": 0,
  "AutoUpRoadLimit40KMH": 15,
  "AutoUpHighwayRoadLimit": 0,
  "AutoUpHighwayRoadLimit40KMH": 15,
  "RoadType": -1,
  "AutoForkDecalRateH": 80,
  "AutoForkSpeedMinH": 60,
  "AutoKeepForkSpeedH": 5,
  "AutoForkDecalRate": 80,
  "AutoForkSpeedMin": 45,
  "AutoKeepForkSpeed": 5,
  "ShowDebugLog": 0,
  "AutoCurveSpeedFactorH": 100,
  "AutoCurveSpeedAggressivenessH": 100,
  "SameSpiCamFilter": 1,
  "StockBlinkerCtrl": 0,
  "ExtBlinkerCtrlTest": 0,
  "BlinkerMode": 1,
  "LaneStabTime": 50,
  "DynamicBlindRange": 0,
  "DynamicBlindDistance": 0,
  "DisableBlindSpot": 0,
  "BsdDelayTime": 20,
  "SideBsdDelayTime": 20,
  "SideRelDistTime": 10,
  "SidevRelDistTime": 10,
  "SideRadarMinDist": 0,
  "AutoTurnInNotRoadEdge": 1,
  "ContinuousLaneChange": 1,
  "ContinuousLaneChangeCnt": 4,
  "ContinuousLaneChangeInterval": 2,
  "AutoTurnLeft": 1,
  "AutoEnTurnNewLaneTimeH": 0,
  "AutoEnTurnNewLaneTime": 0,
  "NewLaneWidthDiff": 8,
  # Speed / turn / navi tuning (aligned with cp/fp defaults).
  "AutoCurveSpeedLowerLimit": 30,
  "AutoCurveSpeedFactor": 100,
  "AutoTurnControl": 0,
  "AutoTurnControlSpeedTurn": 20,
  "AutoTurnControlTurnEnd": 6,
  "AutoTurnMapChange": 0,
  "AutoNaviSpeedCtrlEnd": 6,
  "VehicleNaviCanControl": 0,
  "VehicleNaviSchoolZoneControl": 0,
  "VehicleSpeedCameraControlMode": 1,
  "VehicleSpeedCameraDistanceTime": 60,
  "LatSuspendAngleDeg": 300,
  "AutoRoadSpeedLimitOffset": -1,
  "AutoNaviSpeedBumpTime": 1,
  "AutoNaviSpeedBumpSpeed": 35,
  "AutoNaviSpeedBumpEndDistance": 200,
  "ClusterNaviMapTheme": 1,
  "ClusterNaviMapType": 0,
  "ClusterNaviMapFps": 1,
  "CarrotNaviHudMapProfile": 0,
  "AutoNaviCountDownMode": 2,
  "TurnSpeedControlMode": 1,
  "MapTurnSpeedFactor": 100,
  # Sound / stop behavior
  "StopDistanceCarrot": 600,
  "AutoNaviSpeedCtrlMode": 2,
  "AutoNaviSpeedDecelRate": 200,
  "AutoNaviSpeedSafetyFactor": 105,
  "AutoUpRoadLimit": 0,
  "AutoUpRoadLimit40KMH": 15,
  "AutoUpHighwayRoadLimit": 0,
  "AutoUpHighwayRoadLimit40KMH": 15,
  "RoadType": -1,
  "SoundVolumeAdjust": 0,
  "SoundVolumeAdjustEngage": 0,
  # Carrot exception message persists across manager start
  "CarrotException": "",
  # ---------------------------------------------------------------------------
  # Missing carrot tuning parameters imported from CarrotPilot (179 -> 225 keys).
  # Values mirror cp/selfdrive/carrot_settings.json defaults.
  # ---------------------------------------------------------------------------
  "AChangeCostStarting": 10,
  "AdjustLaneOffset": 0,
  "AlwaysLateral": 0,
  "ApplyModelSpeed": 0,
  "AutoCruiseControl": 0,
  "AutoEngage": 0,
  "AutoGasCancelSpeed": 30,
  "AutoGasSyncSpeed": 0,
  "AutoGasTokSpeed": 0,
  "AutoRoadSpeedAdjust": 0,
  "AutoSpeedUptoRoadSpeedLimit": 0,
  "CameraYawTrimDeg": 0,
  "CancelButtonMode": 0,
  "CanfdDebug": 0,
  "CanfdHDA2": 0,
  "CarrotCruiseAtcDecel": -1,
  "CarrotCruiseDecel": -1,
  "CarrotTireTrajectory": 0,
  "CarrotYouTubeLive": 0,
  "CarrotYouTubeQuality": 0,
  "CarrotYouTubeTimestamp": 0,
  "ClusterHud": 0,
  "ClusterHudBrightness": 0,
  "ClusterHudCameraViewMode": 0,
  "ClusterHudCoreMode": 0,
  "ClusterHudDebug": 0,
  "ClusterHudEncoder": 0,
  "ClusterHudLiveFps": 1,
  "ClusterHudMirror": 0,
  "ClusterHudOrientation": 0,
  "ClusterHudPanelLayout": 0,
  "ClusterHudPriority": 10,
  "ClusterHudRadarDisplay": 0,
  "ClusterHudRadarInfo": 4,
  "ClusterHudRadarSourceColor": 0,
  "ClusterHudScreenMode": 0,
  "ClusterHudTheme": 0,
  "CruiseButtonLongDelay": 40,
  "CruiseButtonMode": 0,
  "CruiseButtonTest1": 0,
  "CruiseButtonTest2": 0,
  "CruiseButtonTest3": 0,
  "CruiseEcoControl": 2,
  "CruiseMaxVals0": 160,
  "CruiseMaxVals1": 160,
  "CruiseMaxVals2": 120,
  "CruiseMaxVals3": 100,
  "CruiseMaxVals4": 80,
  "CruiseMaxVals5": 70,
  "CruiseMaxVals6": 60,
  "CruiseOnDist": 0,
  "CruiseSpeed1": 10,
  "CruiseSpeed2": 10,
  "CruiseSpeed3": 10,
  "CruiseSpeed4": 10,
  "CruiseSpeed5": 10,
  "CruiseSpeedUnit": 10,
  "CruiseSpeedUnitBasic": 10,
  "CustomSR": 0,
  "CustomSteerDeltaDown": 0,
  "CustomSteerDeltaDownLC": 0,
  "CustomSteerDeltaUp": 0,
  "CustomSteerDeltaUpLC": 0,
  "CustomSteerMax": 0,
  "DisableDM": 0,
  "DisableMinSteerSpeed": 0,
  "DynamicTFollow": 0,
  "DynamicTFollowLC": 100,
  "EnableCornerRadar": 0,
  "EnableRadarTracks": 0,
  "EnableSpeedTF": 0,
  "HDPuse": 0,
  "HapticFeedbackWhenSpeedCamera": 0,
  "HardwareC3xLite": 0,
  "HotspotOnBoot": 0,
  "HyundaiCameraSCC": 0,
  "IsLdwsCar": 0,
  "LaneChangeBsd": 0,
  "LaneChangeDelay": 0,
  "LaneChangeNeedTorque": 0,
  "LaneLineCheck": 0,
  "LatMpcAccelCost": 100,
  "LatMpcInputOffset": 4,
  "LatMpcJerkCost": 1,
  "LatMpcMotionCost": 7,
  "LatMpcPathCost": 200,
  "LatMpcSteeringRateCost": 7,
  "LatSmoothSec": 13,
  "LateralTorqueAccelFactor": 2500,
  "LateralTorqueCustom": 1,
  "LateralTorqueFriction": 100,
  "LateralTorqueKd": 0,
  "LateralTorqueKf": 100,
  "LateralTorqueKiV": 10,
  "LateralTorqueKpV": 100,
  "LeadAccelResponse": 0,
  "LfaButtonMode": 0,
  "LongActuatorDelay": 20,
  "LongTuningKf": 100,
  "LongTuningKiV": 0,
  "LongTuningKpV": 100,
  "MapboxStyle": 0,
  "MaxAngleFrames": 89,
  "MaxTimeOffroadMin": 60,
  "MuteDoor": 0,
  "MuteSeatbelt": 0,
  "MyDrivingMode": 3,
  "MyDrivingModeAuto": 0,
  "OnnxBsdIntervalMs": 250,
  "OnnxBsdSmoothingMs": 200,
  "OnnxBsdThreshold": 45,
  "OnnxLaneIntervalMs": 400,
  "OnnxLaneThreshold": 25,
  "PaddleMode": 1,
  "PathOffset": 0,
  "RecordRoadCam": 0,
  "ShareData": 0,
  "ShowCameraWithCluster": 0,
  "ShowCustomBrightness": 100,
  "ShowDateTime": 1,
  "ShowDebugUI": 1,
  "ShowDeviceState": 1,
  "ShowLaneInfo": 1,
  "ShowModelView": 0,
  "ShowPathColor": 12,
  "ShowPathColorCruiseOff": 1,
  "ShowPathColorLane": 3,
  "ShowPathEnd": 1,
  "ShowPathMode": 9,
  "ShowPathModeLane": 11,
  "ShowPlotMode": 0,
  "ShowRadarInfo": 0,
  "ShowRouteInfo": 0,
  "ShowTpms": 1,
  "SoftHoldOnCancel": 0,
  "SoftwareMenu": 0,
  "SoundLanguageSetting": "auto",
  "SpeedFromPCM": 0,
  "SteerActuatorDelay": 30,
  "SteerRatioRate": 100,
  "StoppingAccel": -50,
  "TFollowDecelBoost": 0,
  "TFollowGap1": 110,
  "TFollowGap2": 120,
  "TFollowGap3": 140,
  "TFollowGap4": 160,
  "TrafficLightDetectMode": 2,
  "TrafficStopDistanceAdjust": -150,
  "UseLaneLineCurveSpeed": 0,
  "UseLaneLineSpeed": 0,
  "UseWideCamera": 1,
  "VEgoStopping": 50,
  # --- cp tuning alignment (missing params from CarrotPilot 185-key set) ---
  # Defaults mirror cp/selfdrive/carrot_settings.json so webui read/reset
  # works even though sp does not yet consume every key in longitudinal control.
  "CanfdStopRetry": 0,                       # CANFD stop-and-retry fallback (cp default 0)
  "CruiseGapLevels": 4,                      # number of follow-gap levels (cp default 4)
  "LeadAccelResponseTF1": -1,                # lead accel response, gap level 1 (cp default -1)
  "LeadAccelResponseTF2": -1,                # lead accel response, gap level 2 (cp default -1)
  "LeadAccelResponseTF3": -1,                # lead accel response, gap level 3 (cp default -1)
  "LeadAccelResponseTF4": -1,                # lead accel response, gap level 4 (cp default -1)
  "SpeedTFFactor": 10,                       # speed-dependent time-gap factor (cp default 10)
  "AutoNaviRearCameraHoldDistance": 100,     # navi rear-camera hold distance cm (cp default 100)
}


class UnifiedParams:
  """Single accessor for carrot parameters.

  Prefers the system-wide :class:`openpilot.common.params.Params`; for keys
  that are not registered (which is the common case for the carrot-specific
  tuning surface), reads/writes are served from ``nav_params.json`` instead so
  the daemon never crashes with ``UnknownKeyName`` while we are still
  iterating on the supported key set.
  """
  _instance: Optional["UnifiedParams"] = None
  _initialized: bool = False

  def __new__(cls, nav_json_file: str | None = None) -> "UnifiedParams":
    if cls._instance is None:
      cls._instance = super().__new__(cls)
      cls._instance._initialized = False
    return cls._instance

  def __init__(self, nav_json_file: str | None = None) -> None:
    if self._initialized:
      return
    self._system_params = Params()
    if nav_json_file is None:
      current_dir = os.path.dirname(os.path.abspath(__file__))
      nav_json_file = os.path.join(current_dir, "nav_params.json")
    self._nav_json_file = os.path.realpath(nav_json_file)
    self._nav_data: dict[str, Any] = dict(_DEFAULT_NAV_PARAMS)
    self._load_nav_params()
    self._initialized = True

  # ---- internal helpers --------------------------------------------------

  def _load_nav_params(self) -> None:
    try:
      if os.path.exists(self._nav_json_file):
        with open(self._nav_json_file, encoding="utf-8") as fh:
          on_disk = json.load(fh)
        if isinstance(on_disk, dict):
          # Disk values win over compile-time defaults; allow missing keys to
          # fall back to the defaults baked into this module.
          for key, val in on_disk.items():
            self._nav_data[key] = val
    except (OSError, json.JSONDecodeError):
      # The JSON file is optional - fall back to defaults silently.
      pass

  def _save_nav_params(self) -> None:
    try:
      with open(self._nav_json_file, "w", encoding="utf-8") as fh:
        json.dump(self._nav_data, fh, indent=2, ensure_ascii=False)
    except OSError:
      pass

  def _is_int(self, value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)

  def _is_float(self, value: Any) -> bool:
    return isinstance(value, float)

  def _is_bool(self, value: Any) -> bool:
    return isinstance(value, bool) or value in (0, 1)

  def _read_from_system(self, key: str) -> Any | None:
    """Try to read ``key`` from the global Params store.

    Returns the value on success, ``None`` on any failure (including
    ``UnknownKeyName`` for keys that have not been registered yet).
    """
    try:
      return self._system_params.get(key)
    except (KeyError, AttributeError, UnknownKeyName):
      return None

  def _write_to_system(self, key: str, value: Any) -> bool:
    """Attempt to write ``value`` to the system Params. Returns success."""
    try:
      if self._is_bool(value):
        self._system_params.put_bool(key, bool(value))
      elif self._is_int(value):
        self._system_params.put_int(key, int(value))
      elif self._is_float(value):
        self._system_params.put_float(key, float(value))
      else:
        self._system_params.put(key, str(value))
      return True
    except (KeyError, AttributeError, UnknownKeyName):
      return False
    except Exception:
      return False

  # ---- public API ---------------------------------------------------------

  def get(self, key: str, default: Any = None) -> Any:
    sys_val = self._read_from_system(key)
    if sys_val is not None and sys_val != b"":
      return sys_val
    if key in self._nav_data:
      return self._nav_data[key]
    return default

  def get_int(self, key: str, default: int = 0) -> int:
    value = self.get(key, default)
    try:
      return int(value)
    except (TypeError, ValueError):
      return default

  def get_float(self, key: str, default: float = 0.0) -> float:
    value = self.get(key, default)
    try:
      return float(value)
    except (TypeError, ValueError):
      return default

  def get_bool(self, key: str, default: bool = False) -> bool:
    value = self.get(key, default)
    if value is None:
      return default
    try:
      return bool(int(value))
    except (TypeError, ValueError):
      return default

  def put(self, key: str, value: Any) -> None:
    # Try to persist to the global store first; if the key is not
    # registered, fall back to the JSON cache so the user's choice is not
    # silently dropped.
    if not self._write_to_system(key, value):
      self._nav_data[key] = value
      self._save_nav_params()

  def put_int(self, key: str, value: int) -> None:
    self.put(key, int(value))

  def put_float(self, key: str, value: float) -> None:
    self.put(key, float(value))

  def put_bool(self, key: str, value: bool) -> None:
    self.put(key, bool(value))

  def remove(self, key: str) -> None:
    try:
      self._system_params.remove(key)
    except Exception:
      pass
    self._nav_data.pop(key, None)
    self._save_nav_params()

  def keys(self):
    return set(self._nav_data.keys())


# CarrotNaviDebug JSON key helpers, kept in one place so the UI/debug viewer
# and carrot_man.py stay in sync.
class NaviDebugKeys:
  ACTIVE_SOURCE = "activeSource"
  GPS_SOURCE = "gpsSource"
  EPOCH_TIME_MS = "epochTimeMs"
  TIME_REMAINING = "timeRemaining"
  DISTANCE_REMAINING = "distanceRemaining"
  MANEUVER = "maneuver"
  MANEUVER_TYPE = "type"
  MANEUVER_MODIFIER = "modifier"
  MANEUVER_DISTANCE = "distance"
  MANEUVER_X_TURN_INFO = "xTurnInfo"
  VEHICLE_CAN_SPEED_SOURCES = "vehicleCanSpeedSources"
  CAN_CAMERA = "camera"
  CAN_BUMP = "bump"
  CAN_SCHOOL = "school"
  CAN_SECTION = "section"
  ROAD_LIMIT = "roadLimit"
  ROAD_LIMIT_ACTIVE = "active"
  ROAD_LIMIT_SPEED_KPH = "speedKph"
  OFF_ROUTE = "offRoute"
  DESIRED_SPEED = "desiredSpeed"
  DESIRED_SOURCE = "desiredSource"


# Module-level singleton, matches CarrotPilot's pattern.
unified_params = UnifiedParams()
