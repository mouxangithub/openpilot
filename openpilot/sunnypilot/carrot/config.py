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
  from openpilot.common.params_pyx import UnknownKeyName
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
  # Sound / stop behavior
  "StopDistanceCarrot": 550,
  "AutoNaviSpeedCtrlMode": 0,
  "AutoNaviSpeedDecelRate": 150,
  "AutoNaviSpeedSafetyFactor": 100,
  "SoundVolumeAdjust": 100,
  "SoundVolumeAdjustEngage": 100,
  # Carrot exception message persists across manager start
  "CarrotException": "",
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
    if sys_val is not None:
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


# Module-level singleton, matches CarrotPilot's pattern.
unified_params = UnifiedParams()
