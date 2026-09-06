from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""
Carrot navigation server (in-process).

Translates the raw navigation fields sent by the Carrot phone app (UDP
packets consumed by :class:`CarrotManager`) into derived state used by the
planner + UI:

* SDI (Speed Limit Camera) -> recommended speed, distance, type
* TBT (Turn-by-Turn) -> next maneuver + curve speed
* ATC (Auto Turn Control) -> active blinker request + dist to turn
* Cruise advisory -> cap on ``v_cruise`` based on phone navi

The implementation only consumes a plain Python dict shaped like the JSON
packets the phone app emits, so the same code path can be unit-tested
without a live cereal stream.
"""

import math
import time
from collections import deque
from enum import IntEnum

from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot.carrot.config import UnifiedParams


# Turn type -> (maneuver type, modifier, xTurnInfo). xTurnInfo follows the
# convention used by the carrot UI:
#   1 = left turn, 2 = right turn, 3 = left lane change, 4 = right lane change,
#   5 = rotary, 6 = tg, 7 = uturn, 8 = arrive / straight.
NAV_TYPE_MAPPING: dict[int, tuple[str, str, int]] = {
  12: ("turn", "left", 1),
  16: ("turn", "sharp left", 1),
  13: ("turn", "right", 2),
  19: ("turn", "sharp right", 2),
  102: ("off ramp", "slight left", 3),
  105: ("off ramp", "slight left", 3),
  112: ("off ramp", "slight left", 3),
  115: ("off ramp", "slight left", 3),
  101: ("off ramp", "slight right", 4),
  104: ("off ramp", "slight right", 4),
  111: ("off ramp", "slight right", 4),
  114: ("off ramp", "slight right", 4),
  7: ("fork", "left", 3),
  44: ("fork", "left", 3),
  17: ("fork", "left", 3),
  75: ("fork", "left", 3),
  76: ("fork", "left", 3),
  118: ("fork", "left", 3),
  6: ("fork", "right", 4),
  43: ("fork", "right", 4),
  73: ("fork", "right", 4),
  74: ("fork", "right", 4),
  123: ("fork", "right", 4),
  124: ("fork", "right", 4),
  117: ("fork", "right", 4),
  131: ("rotary", "slight right", 5),
  132: ("rotary", "slight right", 5),
  140: ("rotary", "slight left", 5),
  141: ("rotary", "slight left", 5),
  133: ("rotary", "right", 5),
  134: ("rotary", "sharp right", 5),
  135: ("rotary", "sharp right", 5),
  136: ("rotary", "sharp left", 5),
  137: ("rotary", "sharp left", 5),
  138: ("rotary", "sharp left", 5),
  139: ("rotary", "left", 5),
  142: ("rotary", "straight", 5),
  14: ("turn", "uturn", 7),
  201: ("arrive", "straight", 8),
  51: ("notification", "straight", 0),
  52: ("notification", "straight", 0),
  53: ("notification", "straight", 0),
  54: ("notification", "straight", 0),
  55: ("notification", "straight", 0),
  153: ("", "", 6),
  154: ("", "", 6),
  249: ("", "", 6),
}

# Curve-speed lookup table (reciprocal radius [1/m] -> km/h).
# Used when the phone navi sends a curvature-aware speed advisory.
V_CURVE_LOOKUP_BP: tuple[float, ...] = (
  0.0, 1 / 800, 1 / 670, 1 / 560, 1 / 440, 1 / 360, 1 / 265, 1 / 190, 1 / 135,
  1 / 85, 1 / 55, 1 / 30, 1 / 25,
)
V_CURVE_LOOKUP_VALS: tuple[float, ...] = (300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5)

# SDI (Speed Limit Camera) type categories that mean "real" speed cameras.
SDI_SPEED_CAMERA_TYPES: frozenset[int] = frozenset({0, 1, 2, 3, 4, 7, 8, 75, 76})


class Blinker(IntEnum):
  NONE = 0
  LEFT = 1
  RIGHT = 2
  BOTH = 3


def _safe_int(value, default: int = 0) -> int:
  try:
    if value is None:
      return default
    if isinstance(value, bool):
      return int(value)
    return int(value)
  except (TypeError, ValueError):
    return default


def _safe_float(value, default: float = 0.0) -> float:
  try:
    if value is None:
      return default
    return float(value)
  except (TypeError, ValueError):
    return default


def _safe_str(value, default: str = "") -> str:
  if value is None:
    return default
  s = str(value)
  return default if s == "null" else s


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
  """Distance in meters between two GPS coordinates."""
  r = 6371000.0
  phi1 = math.radians(lat1)
  phi2 = math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlambda = math.radians(lon2 - lon1)
  a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
  return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class NavTypeMapper:
  """Resolves phone navi turn-type codes to (maneuver, modifier, xTurnInfo)."""

  @staticmethod
  def resolve(turn_code: int) -> tuple[str, str, int]:
    return NAV_TYPE_MAPPING.get(int(turn_code), ("invalid", "", -1))


class CarrotServ:
  """Service-side glue that turns raw phone packets into a derived state object.

  The class is stateful so that it can:

  * Reuse parameters via :class:`UnifiedParams`.
  * Track the last seen packet so the CarrotManager can detect timeouts.
  * Compute the highest-priority cruise speed cap (turn / SDI / road limit)
    that the planner should respect.
  """

  def __init__(self, params: UnifiedParams | None = None) -> None:
    self._params = params or UnifiedParams()

    # Cached navi state.
    self._raw: dict[str, object] = {}
    self._last_packet_mono: float = 0.0
    self._last_seq: int | None = None
    self._remote_addr: str = ""

    # Derived state.
    self.nav_type: str = "invalid"
    self.nav_modifier: str = ""
    self.nav_type_next: str = "invalid"
    self.nav_modifier_next: str = ""
    self.x_turn_info: int = -1
    self.x_dist_to_turn: int = 0
    self.x_turn_info_next: int = -1
    self.x_dist_to_turn_next: int = 0
    self.x_spd_type: int = -1
    self.x_spd_limit: int = 0
    self.x_spd_dist: int = 0
    self.v_turn_speed: int = 0
    self.sz_sdi_descr: str = ""
    self.active_carrot: int = 0
    self.desired_speed: int = 0
    self.desired_source: str = ""
    self.atc_type: str = ""
    self.roadcate: int = 8

    # Road / position state (read back by carrot_man and the UI).
    self.n_road_limit_speed: int = 0
    self.vp_pos_point_lat: float = 0.0
    self.vp_pos_point_lon: float = 0.0

    # Navi speed-control tuning (from UnifiedParams; safe defaults).
    self.auto_navi_speed_decel_rate: float = 0.8
    self.auto_navi_speed_ctrl_end: float = 7.0

    # Path tracking (used by callers that need curvature / bearing).
    self._path: deque[tuple[float, float]] = deque(maxlen=512)
    self._bearing: float = 0.0
    self._bearing_offset: float = 0.0

    # Traffic light history (2 seconds at 10 Hz).
    self._traffic_history: deque[int] = deque(maxlen=20)
    self._traffic_state: int = 0

    # --- CarrotPilot feature state (ported) ------------------------------- #
    # Traffic-light DETECT state machine (phone app sends camera detections).
    self._traffic_light_q: deque[tuple[float, float, str, float]] = deque(maxlen=20)
    self._traffic_light_count: int = -1
    # Map-based traffic light (from the nav app, takes priority when fresh).
    self.map_traffic_state: int = 0
    self.map_traffic_countdown: int = 0
    self.map_traffic_time: float = 0.0

    # ATC (auto turn control) state.
    self.atc_paused: bool = False
    self.atc_activate_count: int = 0
    self.atc_speed_decal: float = 0.0
    self.fork_speed_keep_time: int = -1
    self.gas_override_speed: int = 0
    self.gas_pressed_state: bool = False
    self.source_last: str = "none"

    # Countdown state.
    self.left_spd_sec: int = 100
    self.left_tbt_sec: int = 100
    self.left_sec: int = 100
    self.max_left_sec: int = 100
    self.carrot_left_sec: int = 100
    self.sdi_inform: bool = False

    # Kisa (crowdsourced nav data) activity counter.
    self.active_kisa_count: int = 0
    self._param_frame: int = 0
    self._last_cmd_index: int = -1
    self.navi_paths: str = ""

    # Tuning cache (refreshed by update_params(); safe defaults here so the
    # class never crashes even if update_params() has not run yet).
    self.auto_navi_speed_safety_factor: float = 1.05
    self.auto_navi_speed_bump_speed: float = 35.0
    self.auto_navi_speed_bump_time: float = 1.0
    self.auto_navi_count_down_mode: int = 0
    self.turn_speed_control_mode: int = 1
    self.map_turn_speed_factor: float = 1.0
    self.auto_turn_control: int = 2
    self.auto_turn_control_speed_turn: int = 20
    self.auto_turn_control_turn_end: int = 6
    self.auto_turn_map_change: int = 0
    self.auto_curve_speed_lower_limit: int = 30
    self.auto_road_speed_limit_offset: int = -1
    self.auto_turn_dist_offset: int = 0
    self.auto_fork_dist_offset: int = 30
    self.auto_fork_dist_offset_h: int = 1000
    self.auto_do_fork_blinker_dist: int = 15
    self.auto_do_fork_nav_dist: int = 15
    self.auto_do_fork_blinker_dist_h: int = 30
    self.auto_do_fork_nav_dist_h: int = 50
    self.auto_do_fork_decal_dist: int = 20
    self.auto_do_fork_decal_dist_h: int = 50
    self.auto_fork_decal_rate: float = 0.8
    self.auto_fork_decal_rate_h: float = 0.8
    self.auto_fork_speed_min: int = 45
    self.auto_fork_speed_min_h: int = 60
    self.auto_keep_fork_speed: int = 5
    self.auto_keep_fork_speed_h: int = 5
    self.auto_up_road_limit: int = 0
    self.auto_up_highway_road_limit: int = 0
    self.show_debug_log: int = 0
    self.is_metric: bool = True

  # ---- packet ingestion -------------------------------------------------- #

  def update_raw(self, msg: dict, recv_mono: float = 0.0) -> None:
    """Apply a single phone-packet dict to the cached state."""
    if not isinstance(msg, dict):
      return
    self._last_packet_mono = recv_mono

    seq = _safe_int(msg.get("carrotIndex"), -1)
    if seq >= 0 and self._last_seq is not None and seq < self._last_seq:
      return  # ignore out-of-order packets
    self._last_seq = seq

    self._raw = {
      "nRoadLimitSpeed": _safe_int(msg.get("nRoadLimitSpeed"), 0),
      "nSdiType": _safe_int(msg.get("nSdiType"), -1),
      "nSdiSpeedLimit": _safe_int(msg.get("nSdiSpeedLimit"), 0),
      "nSdiDist": _safe_int(msg.get("nSdiDist"), 0),
      "nSdiBlockType": _safe_int(msg.get("nSdiBlockType"), -1),
      "nSdiBlockSpeed": _safe_int(msg.get("nSdiBlockSpeed"), 0),
      "nSdiBlockDist": _safe_int(msg.get("nSdiBlockDist"), 0),
      "nSdiPlusType": _safe_int(msg.get("nSdiPlusType"), -1),
      "nSdiPlusSpeedLimit": _safe_int(msg.get("nSdiPlusSpeedLimit"), 0),
      "nSdiPlusDist": _safe_int(msg.get("nSdiPlusDist"), 0),
      "nSdiPlusBlockType": _safe_int(msg.get("nSdiPlusBlockType"), -1),
      "nSdiPlusBlockSpeed": _safe_int(msg.get("nSdiPlusBlockSpeed"), 0),
      "nSdiPlusBlockDist": _safe_int(msg.get("nSdiPlusBlockDist"), 0),
      "nTBTDist": _safe_int(msg.get("nTBTDist"), 0),
      "nTBTTurnType": _safe_int(msg.get("nTBTTurnType"), -1),
      "szTBTMainText": _safe_str(msg.get("szTBTMainText"), ""),
      "szNearDirName": _safe_str(msg.get("szNearDirName"), ""),
      "szFarDirName": _safe_str(msg.get("szFarDirName"), ""),
      "nTBTDistNext": _safe_int(msg.get("nTBTDistNext"), 0),
      "nTBTTurnTypeNext": _safe_int(msg.get("nTBTTurnTypeNext"), -1),
      "szTBTMainTextNext": _safe_str(msg.get("szTBTMainTextNext"), ""),
      "nGoPosDist": _safe_int(msg.get("nGoPosDist"), 0),
      "nGoPosTime": _safe_int(msg.get("nGoPosTime"), 0),
      "szPosRoadName": _safe_str(msg.get("szPosRoadName"), ""),
      "vpPosPointLat": _safe_float(msg.get("vpPosPointLat"), 0.0),
      "vpPosPointLon": _safe_float(msg.get("vpPosPointLon"), 0.0),
      "nPosAngle": _safe_float(msg.get("nPosAngle"), 0.0),
      "nPosSpeed": _safe_float(msg.get("nPosSpeed"), 0.0),
      "carrotCmdIndex": seq,
      "carrotCmd": _safe_str(msg.get("carrotCmd"), ""),
      "carrotArg": _safe_str(msg.get("carrotArg"), ""),
      "roadcate": _safe_int(msg.get("roadcate"), 0),
      "leftBlind": _safe_int(msg.get("leftBlind"), 0),
      "rightBlind": _safe_int(msg.get("rightBlind"), 0),
    }

    if "carrotCmd" in msg:
      self._raw["carrotCmdIndex"] = seq
      self._raw["carrotCmd"] = _safe_str(msg.get("carrotCmd"), "")
      self._raw["carrotArg"] = _safe_str(msg.get("carrotArg"), "")

  def is_stale(self, now_mono: float, timeout: float = 3.0) -> bool:
    return self._last_packet_mono > 0.0 and (now_mono - self._last_packet_mono) > timeout

  @property
  def raw(self) -> dict:
    return dict(self._raw)

  @property
  def last_packet_mono(self) -> float:
    return self._last_packet_mono

  @property
  def traffic_state(self) -> int:
    """Current traffic-light state: 0=none, 1=red, 2=green, 3=left-turn."""
    return self._traffic_state

  def reset(self) -> None:
    """Reset all cached + derived state (e.g. after a packet timeout)."""
    self._raw = {}
    self._last_packet_mono = 0.0
    self._last_seq = None
    self._reset_derived()
    self._traffic_history.clear()
    self._traffic_state = 0
    self._traffic_light_q.clear()
    self._traffic_light_count = -1
    self.map_traffic_state = 0
    self.map_traffic_countdown = 0
    self.map_traffic_time = 0.0
    self.atc_paused = False
    self.atc_activate_count = 0
    self.atc_speed_decal = 0.0
    self.fork_speed_keep_time = -1
    self.gas_override_speed = 0
    self.gas_pressed_state = False
    self.source_last = "none"
    self.left_spd_sec = 100
    self.left_tbt_sec = 100
    self.left_sec = 100
    self.max_left_sec = 100
    self.carrot_left_sec = 100
    self.sdi_inform = False
    self.active_kisa_count = 0

  # ---- derived state ----------------------------------------------------- #

  def derive(self, v_ego_kph: float = 0.0) -> None:
    """Recompute the derived state from the cached raw packet."""
    r = self._raw
    if not r:
      self._reset_derived()
      return

    # --- TBT turn mapping ------------------------------------------------
    self.nav_type, self.nav_modifier, self.x_turn_info = NavTypeMapper.resolve(
      _safe_int(r.get("nTBTTurnType"), -1)
    )
    self.nav_type_next, self.nav_modifier_next, self.x_turn_info_next = NavTypeMapper.resolve(
      _safe_int(r.get("nTBTTurnTypeNext"), -1)
    )
    n_tbt_dist = _safe_int(r.get("nTBTDist"), 0)
    n_tbt_dist_next = _safe_int(r.get("nTBTDistNext"), 0)
    self.x_dist_to_turn = n_tbt_dist if self.x_turn_info > 0 else 0
    if self.x_turn_info_next > 0:
      self.x_dist_to_turn_next = n_tbt_dist + n_tbt_dist_next
    else:
      self.x_dist_to_turn_next = 0

    # --- SDI -> xSpd* ----------------------------------------------------
    sdi_type = _safe_int(r.get("nSdiType"), -1)
    sdi_speed_limit = _safe_int(r.get("nSdiSpeedLimit"), 0)
    sdi_dist = _safe_int(r.get("nSdiDist"), 0)
    sdi_block_type = _safe_int(r.get("nSdiBlockType"), -1)
    sdi_block_dist = _safe_int(r.get("nSdiBlockDist"), 0)
    sdi_plus_type = _safe_int(r.get("nSdiPlusType"), -1)
    sdi_plus_dist = _safe_int(r.get("nSdiPlusDist"), 0)
    roadcate = _safe_int(r.get("roadcate"), 0)

    self.sz_sdi_descr = ""
    if sdi_type in SDI_SPEED_CAMERA_TYPES and sdi_speed_limit > 0:
      self.x_spd_limit = sdi_speed_limit
      self.x_spd_dist = sdi_dist
      self.x_spd_type = sdi_type
      if sdi_block_type in (2, 3):
        self.x_spd_dist = sdi_block_dist
        self.x_spd_type = 4
    elif (sdi_plus_type == 22 or sdi_type == 22) and roadcate > 1:
      # Speed bump on non-highway road.
      self.x_spd_limit = 25
      self.x_spd_dist = sdi_plus_dist if sdi_plus_type == 22 else sdi_dist
      self.x_spd_type = 22
    else:
      self.x_spd_limit = 0
      self.x_spd_type = -1
      self.x_spd_dist = 0

    if self.x_spd_type >= 0:
      self.sz_sdi_descr = f"sdi:{self.x_spd_type}"

    # --- Curve speed (turn) ---------------------------------------------
    if self.x_turn_info > 0 and self.x_dist_to_turn > 0:
      self.v_turn_speed = self._interp_turn_speed(self.x_turn_info, self.x_dist_to_turn)
    else:
      self.v_turn_speed = 0

    # --- Road limit / phone position --------------------------------------
    self.n_road_limit_speed = _safe_int(r.get("nRoadLimitSpeed"), 0)
    self.vp_pos_point_lat = _safe_float(r.get("vpPosPointLat"), 0.0)
    self.vp_pos_point_lon = _safe_float(r.get("vpPosPointLon"), 0.0)

    # --- Cruise advisory -------------------------------------------------
    n_road_limit = self.n_road_limit_speed
    self.desired_speed = 0
    self.desired_source = ""
    if self.x_spd_type >= 0 and (self.x_spd_dist > 0 or self.x_spd_type in (100, 101)):
      self.desired_speed = self.x_spd_limit
      self.desired_source = "sdi"
    elif self.v_turn_speed > 0 and self.x_dist_to_turn < 300:
      self.desired_speed = self.v_turn_speed
      self.desired_source = "turn"
    elif n_road_limit >= 30 and v_ego_kph > n_road_limit + 5:
      self.desired_speed = n_road_limit
      self.desired_source = "limit"

    # --- Activity flag ---------------------------------------------------
    self.active_carrot = 0
    if self.x_spd_type >= 0 or self.x_turn_info > 0 or _safe_int(r.get("nGoPosDist"), 0) > 0:
      self.active_carrot = 1  # 0=off, 1=enabled, 2=active advisory event
    if self.desired_speed > 0:
      self.active_carrot = 2

    # --- ATC type --------------------------------------------------------
    self.atc_type = _safe_str(r.get("atcType"), "")
    self.roadcate = roadcate

    # --- Traffic light smoothing ----------------------------------------
    self._traffic_history.append(_safe_int(r.get("trafficState"), 0))
    self._traffic_state = max(set(self._traffic_history), key=self._traffic_history.count) if self._traffic_history else 0

  def _reset_derived(self) -> None:
    self.nav_type = "invalid"
    self.nav_modifier = ""
    self.nav_type_next = "invalid"
    self.nav_modifier_next = ""
    self.x_turn_info = -1
    self.x_dist_to_turn = 0
    self.x_turn_info_next = -1
    self.x_dist_to_turn_next = 0
    self.x_spd_type = -1
    self.x_spd_limit = 0
    self.x_spd_dist = 0
    self.v_turn_speed = 0
    self.sz_sdi_descr = ""
    self.active_carrot = 0
    self.desired_speed = 0
    self.desired_source = ""
    self.atc_type = ""
    self.roadcate = 8
    self.n_road_limit_speed = 0
    self.vp_pos_point_lat = 0.0
    self.vp_pos_point_lon = 0.0

  # ---- parameter refresh -------------------------------------------------- #

  def update_params(self) -> None:
    """Refresh tuning parameters from UnifiedParams (throttled to 10 Hz)."""
    if (self._param_frame % 10) != 0:
      self._param_frame += 1
      return
    self._param_frame += 1

    p = self._params
    self.auto_navi_speed_decel_rate = float(p.get_int("AutoNaviSpeedDecelRate", 150)) * 0.01
    self.auto_navi_speed_ctrl_end = float(p.get_int("AutoNaviSpeedCtrlEnd", 7))
    self.auto_navi_speed_safety_factor = float(p.get_int("AutoNaviSpeedSafetyFactor", 100)) * 0.01
    self.auto_navi_speed_bump_speed = float(p.get_int("AutoNaviSpeedBumpSpeed", 35))
    self.auto_navi_speed_bump_time = float(p.get_int("AutoNaviSpeedBumpTime", 1))
    self.auto_navi_count_down_mode = p.get_int("AutoNaviCountDownMode", 0)
    self.turn_speed_control_mode = p.get_int("TurnSpeedControlMode", 1)
    self.map_turn_speed_factor = float(p.get_int("MapTurnSpeedFactor", 100)) * 0.01
    self.auto_turn_control = p.get_int("AutoTurnControl", 2)
    self.auto_turn_control_speed_turn = p.get_int("AutoTurnControlSpeedTurn", 20)
    self.auto_turn_control_turn_end = p.get_int("AutoTurnControlTurnEnd", 6)
    self.auto_turn_map_change = p.get_int("AutoTurnMapChange", 0)
    self.auto_curve_speed_lower_limit = p.get_int("AutoCurveSpeedLowerLimit", 30)
    self.auto_road_speed_limit_offset = p.get_int("AutoRoadSpeedLimitOffset", -1)
    self.auto_turn_dist_offset = p.get_int("AutoTurnDistOffset", 0)
    self.auto_fork_dist_offset = p.get_int("AutoForkDistOffset", 30)
    self.auto_fork_dist_offset_h = p.get_int("AutoForkDistOffsetH", 1000)
    self.auto_do_fork_blinker_dist = p.get_int("AutoDoForkBlinkerDist", 15)
    self.auto_do_fork_nav_dist = p.get_int("AutoDoForkNavDist", 15)
    self.auto_do_fork_blinker_dist_h = p.get_int("AutoDoForkBlinkerDistH", 30)
    self.auto_do_fork_nav_dist_h = p.get_int("AutoDoForkNavDistH", 50)
    self.auto_do_fork_decal_dist = p.get_int("AutoDoForkDecalDist", 20)
    self.auto_do_fork_decal_dist_h = p.get_int("AutoDoForkDecalDistH", 50)
    self.auto_fork_decal_rate = float(p.get_int("AutoForkDecalRate", 80)) * 0.01
    self.auto_fork_decal_rate_h = float(p.get_int("AutoForkDecalRateH", 80)) * 0.01
    self.auto_fork_speed_min = p.get_int("AutoForkSpeedMin", 45)
    self.auto_fork_speed_min_h = p.get_int("AutoForkSpeedMinH", 60)
    self.auto_keep_fork_speed = p.get_int("AutoKeepForkSpeed", 5)
    self.auto_keep_fork_speed_h = p.get_int("AutoKeepForkSpeedH", 5)
    self.auto_up_road_limit = p.get_int("AutoUpRoadLimit", 0)
    self.auto_up_highway_road_limit = p.get_int("AutoUpHighwayRoadLimit", 0)
    self.show_debug_log = p.get_int("ShowDebugLog", 0)
    self.is_metric = p.get_bool("IsMetric", True)

  def calculate_current_speed(self, left_dist: float, safe_speed_kph: float,
                              safe_time: float, safe_decel_rate: float) -> float:
    """Deceleration-aware speed target (km/h)."""
    safe_speed = safe_speed_kph / 3.6
    safe_dist = safe_speed * safe_time
    decel_dist = left_dist - safe_dist
    if decel_dist <= 0:
      return safe_speed_kph
    temp = safe_speed ** 2 + 2 * safe_decel_rate * decel_dist
    if temp < 0:
      return safe_speed_kph
    speed_mps = math.sqrt(temp)
    return max(safe_speed_kph, min(250.0, speed_mps * 3.6))

  # ---- traffic light DETECT state machine -------------------------------- #

  def _update_cmd(self) -> None:
    """Handle remote commands (e.g. DETECT) and decay the traffic-light state."""
    carrot_cmd = _safe_str(self._raw.get("carrotCmd"), "")
    carrot_arg = _safe_str(self._raw.get("carrotArg"), "")
    cmd_index = _safe_int(self._raw.get("carrotCmdIndex"), 0)
    if cmd_index != self._last_cmd_index:
      self._last_cmd_index = cmd_index
      if carrot_cmd == "DETECT":
        self._handle_detect_command(carrot_arg)

    self._traffic_light_q.append((-1.0, -1.0, "none", 0.0))
    self._traffic_light_count -= 1
    if self._traffic_light_count < 0:
      self._traffic_light_count = -1
      self._traffic_state = 0

  def _handle_detect_command(self, x_arg: str) -> None:
    elements = [e.strip() for e in x_arg.split(",")]
    if len(elements) >= 4:
      try:
        state = elements[0]
        value1 = float(elements[1])
        value2 = float(elements[2])
        value3 = float(elements[3])
        self.traffic_light(value1, value2, state, value3)
        self._traffic_light_count = int(0.5 / 0.1)
      except ValueError:
        pass

  def traffic_light(self, x: float, y: float, color: str, cnf: float) -> None:
    """Incremental traffic-light detection: accumulate confidence per color."""
    traffic_red = traffic_green = traffic_left = 0.0
    traffic_red_trig = traffic_green_trig = traffic_left_trig = 0.0
    for px, py, pcolor, pcnf in self._traffic_light_q:
      if abs(x - px) < 0.2 and abs(y - py) < 0.2:
        if pcolor in ("Green Light", "Left turn"):
          if color in ("Red Light", "Yellow Light"):
            traffic_red_trig += cnf
            traffic_red += cnf
          elif color in ("Green Light", "Left turn"):
            traffic_green += cnf
        elif pcolor in ("Red Light", "Yellow Light"):
          if color == "Green Light":
            traffic_green_trig += cnf
            traffic_green += cnf
          elif color == "Left turn":
            traffic_left_trig += cnf
            traffic_left += cnf
          elif color in ("Red Light", "Yellow Light"):
            traffic_red += cnf

    if traffic_red_trig > 0:
      self._traffic_state = 1
    elif traffic_green_trig > 0 and traffic_green > traffic_red:
      self._traffic_state = 2
    elif traffic_left_trig > 0:
      self._traffic_state = 3
    elif traffic_red > 0:
      self._traffic_state = 1
    elif traffic_green > 0:
      self._traffic_state = 2
    else:
      self._traffic_state = 0

    self._traffic_light_q.append((x, y, color, cnf))

  # ---- ATC (auto turn control) ------------------------------------------- #

  def update_auto_turn(self, v_ego_kph: float, sm, x_turn_info: int, x_dist_to_turn: float,
                       check_steer: bool = False) -> tuple[float, str, float, float]:
    """Decide the auto-turn action (type / target speed / decel distance).

    Returns:
      (desired_speed_kmh, atc_type, atc_speed, atc_dist)
    """
    turn_speed = float(self.auto_turn_control_speed_turn)
    fork_speed = float(self.n_road_limit_speed)
    stop_speed = 1.0
    turn_dist_for_speed = self.auto_turn_control_turn_end * turn_speed / 3.6
    fork_dist_for_speed = self.auto_turn_control_turn_end * fork_speed / 3.6
    stop_dist_for_speed = 5.0

    if self.roadcate > 1:
      fork_dist_offset = float(self.auto_fork_dist_offset)
      start_fork_dist = _interp_table(self.n_road_limit_speed, (30, 50, 100), (160, 200, 350)) + fork_dist_offset
      do_fork_dist = fork_dist_for_speed + self.auto_do_fork_blinker_dist
      do_speed_decal_dist = fork_dist_for_speed + self.auto_do_fork_decal_dist
      auto_decel_rate = self.auto_fork_decal_rate
      decel_speed_min = float(self.auto_fork_speed_min)
      do_fork_nav_dist = float(self.auto_do_fork_nav_dist)
      fork_speed_keep_time = float(self.auto_keep_fork_speed)
    else:
      fork_dist_offset = float(self.auto_fork_dist_offset_h)
      start_fork_dist = _interp_table(self.n_road_limit_speed, (30, 50, 100), (160, 200, 350)) + fork_dist_offset
      do_fork_dist = fork_dist_for_speed + self.auto_do_fork_blinker_dist_h
      do_speed_decal_dist = fork_dist_for_speed + self.auto_do_fork_decal_dist_h
      auto_decel_rate = self.auto_fork_decal_rate_h
      decel_speed_min = float(self.auto_fork_speed_min_h)
      do_fork_nav_dist = float(self.auto_do_fork_nav_dist_h)
      fork_speed_keep_time = float(self.auto_keep_fork_speed_h)

    if do_fork_nav_dist > 0:
      do_fork_dist = max(do_fork_dist, do_fork_nav_dist)

    max_dist = float(self.x_dist_to_turn) * 0.8
    if do_fork_dist > max_dist:
      do_fork_dist = max_dist
    if start_fork_dist > max_dist:
      start_fork_dist = max_dist

    start_turn_dist = _interp_table(7.5, (5, 10), (43, 60)) + self.auto_turn_dist_offset
    turn_info_mapping: dict[int, dict[str, object]] = {
      1: {"type": "turn left", "speed": turn_speed, "dist": turn_dist_for_speed, "start": start_fork_dist},
      2: {"type": "turn right", "speed": turn_speed, "dist": turn_dist_for_speed, "start": start_fork_dist},
      5: {"type": "straight", "speed": turn_speed, "dist": turn_dist_for_speed, "start": start_turn_dist},
      3: {"type": "fork left", "speed": fork_speed, "dist": do_fork_dist, "start": start_fork_dist},
      4: {"type": "fork right", "speed": fork_speed, "dist": do_fork_dist, "start": start_fork_dist},
      6: {"type": "straight", "speed": fork_speed, "dist": fork_dist_for_speed, "start": start_fork_dist},
      7: {"type": "straight", "speed": stop_speed, "dist": stop_dist_for_speed, "start": 1000.0},
      8: {"type": "straight", "speed": stop_speed, "dist": stop_dist_for_speed, "start": 1000.0},
    }
    default_mapping = {"type": "none", "speed": 0.0, "dist": 0.0, "start": 1000.0}
    mapping = turn_info_mapping.get(x_turn_info, default_mapping)

    atc_type = str(mapping["type"])
    atc_speed = float(mapping["speed"])
    atc_dist = float(mapping["dist"])
    atc_start_dist = float(mapping["start"])
    atc_type_org = atc_type
    atc_speed_org = atc_speed

    if x_dist_to_turn > atc_start_dist:
      atc_type += " prepare"
      if check_steer:
        self.atc_activate_count = min(0, self.atc_activate_count - 1)
    else:
      if check_steer:
        self.atc_activate_count = max(0, self.atc_activate_count + 1)

      if atc_type in ("turn left", "turn right") and x_dist_to_turn > start_turn_dist:
        atc_type = "atc left" if "left" in atc_type else "atc right"
      elif atc_type in ("fork left", "fork right"):
        if fork_dist_offset > 0 and x_dist_to_turn > do_fork_dist:
          atc_type = "atc left" if "left" in atc_type else "atc right"
        elif do_fork_nav_dist > 0 and x_dist_to_turn <= do_fork_nav_dist:
          atc_type += " now"
        if x_dist_to_turn < do_speed_decal_dist:
          if auto_decel_rate > 0:
            if atc_speed > decel_speed_min:
              atc_speed = max(decel_speed_min, atc_speed * auto_decel_rate)
          if check_steer:
            self.atc_speed_decal = atc_speed
            self.fork_speed_keep_time = int(fork_speed_keep_time / DT_MDL)

    if check_steer:
      if atc_type_org in ("fork left", "fork right") and self.atc_speed_decal > 0:
        self.fork_speed_keep_time = min(-1, self.fork_speed_keep_time - 1)
        if self.fork_speed_keep_time > 0:
          atc_speed = min(atc_speed, self.atc_speed_decal)
        if self.fork_speed_keep_time == 0:
          self.atc_speed_decal = 0.0
      else:
        self.fork_speed_keep_time = -1
        self.atc_speed_decal = 0.0

    if self.auto_turn_map_change > 0 and check_steer:
      if self.atc_activate_count == 2:
        self._raw["carrotCmdIndex"] = _safe_int(self._raw.get("carrotCmdIndex"), 0) + 100
        self._raw["carrotCmd"] = "DISPLAY"
        self._raw["carrotArg"] = "MAP"
      elif self.atc_activate_count == -50:
        self._raw["carrotCmdIndex"] = _safe_int(self._raw.get("carrotCmdIndex"), 0) + 100
        self._raw["carrotCmd"] = "DISPLAY"
        self._raw["carrotArg"] = "ROAD"

    if check_steer:
      if 0 <= x_dist_to_turn < atc_start_dist and atc_type in ("fork left", "fork right"):
        if not self.atc_paused:
          try:
            steering_pressed = sm["carState"].steeringPressed
            steering_torque = sm["carState"].steeringTorque
            if steering_pressed and steering_torque < 0 and atc_type in ("fork left", "atc left"):
              self.atc_paused = True
            elif steering_pressed and steering_torque > 0 and atc_type in ("fork right", "atc right"):
              self.atc_paused = True
          except (KeyError, AttributeError):
            pass
      else:
        self.atc_paused = False

      if self.atc_paused:
        atc_type += " canceled"

    atc_desired = 250.0
    if atc_speed > 0 and x_dist_to_turn > 0:
      decel = self.auto_navi_speed_decel_rate
      atc_desired = min(atc_desired, self.calculate_current_speed(x_dist_to_turn - atc_dist, atc_speed, 2.0, decel))

    return atc_desired, atc_type, atc_speed, atc_dist

  # ---- main per-packet navigation update ---------------------------------- #

  def update_navi(self, remote_ip: str, sm, pm, vturn_speed: float,
                  coords: list, distances: list, route_speed: float) -> None:
    """Full navigation update (reference-carrot semantics, no publish).

    ``pm`` is accepted for API compatibility; the caller owns publishing.
    """
    self.update_params()
    if sm.alive["carState"]:
      v_ego = sm["carState"].vEgo
      v_ego_kph = v_ego * 3.6
    else:
      v_ego = 0.0
      v_ego_kph = 0.0

    # Re-derive TBT/SDI from the cached packet, then apply time-based decay.
    self.derive(v_ego_kph)
    delta_dist = v_ego * DT_MDL
    self.x_spd_dist = max(self.x_spd_dist - int(delta_dist), -1000)
    self.x_dist_to_turn = int(self.x_dist_to_turn - delta_dist)
    self.x_dist_to_turn_next = int(self.x_dist_to_turn_next - delta_dist)
    self.active_kisa_count = max(self.active_kisa_count - 1, 0)

    if self.x_spd_type < 0 or (self.x_spd_type not in (100, 101) and self.x_spd_dist <= 0) or \
       (self.x_spd_type in (100, 101) and self.x_spd_dist < -250):
      self.x_spd_type = -1
      self.x_spd_dist = self.x_spd_limit = 0
    if self.x_turn_info < 0 or self.x_dist_to_turn < -50:
      if self.x_dist_to_turn > 0:
        self.x_dist_to_turn = 0
      self.x_turn_info = -1
      self.x_dist_to_turn_next = 0
      self.x_turn_info_next = -1

    # ATC decision.
    atc_desired, self.atc_type, _atc_speed, _atc_dist = self.update_auto_turn(
      v_ego_kph, sm, self.x_turn_info, float(self.x_dist_to_turn), True)
    if self.auto_turn_control not in (2, 3):
      atc_desired = 250.0
    if self.auto_turn_control not in (1, 2):
      self.atc_type = "none"

    # Speed-source synthesis (turn / SDI / road / curve).
    sdi_speed = 250.0
    if (self.x_spd_dist > 0 or self.x_spd_type in (100, 101)) and self.active_carrot > 0:
      safe_sec = self.auto_navi_speed_bump_time if self.x_spd_type == 22 else self.auto_navi_speed_ctrl_end
      sdi_speed = min(sdi_speed, self.calculate_current_speed(self.x_spd_dist, self.x_spd_limit,
                                                              safe_sec, self.auto_navi_speed_decel_rate))
    limit_speed = 200.0
    if self.auto_road_speed_limit_offset >= 0 and self.active_carrot >= 2:
      if self.n_road_limit_speed >= 30:
        limit_speed = self.n_road_limit_speed + self.auto_road_speed_limit_offset
      elif self.n_road_limit_speed > 0:
        limit_speed = 30.0

    speed_n_sources = [
      (atc_desired, "atc"),
      (sdi_speed, "sdi"),
      (limit_speed, "road"),
    ]
    if self.turn_speed_control_mode in (1, 2):
      speed_n_sources.append((max(abs(vturn_speed), self.auto_curve_speed_lower_limit), "vturn"))

    if self.turn_speed_control_mode == 2 and -500 < self.x_dist_to_turn < 500:
      speed_n_sources.append((max(route_speed * self.map_turn_speed_factor,
                                  self.auto_curve_speed_lower_limit), "route"))
    elif self.turn_speed_control_mode == 3:
      speed_n_sources.append((max(route_speed * self.map_turn_speed_factor,
                                  self.auto_curve_speed_lower_limit), "route"))

    desired_speed, source = min(speed_n_sources, key=lambda x: x[0])
    self.desired_speed = int(desired_speed)
    self.desired_source = source

    # Countdowns.
    if self.x_dist_to_turn > 0:
      left_turn_sec = min(1000, int(min(200000, max(self.x_dist_to_turn - v_ego, 1)) / max(1, v_ego) + 0.5))
    else:
      left_turn_sec = 0
    left_spd_sec = 100
    left_tbt_sec = 100
    if self.auto_navi_count_down_mode > 0:
      if self.x_spd_dist > 0:
        left_spd_sec = min(self.left_spd_sec, int(max(self.x_spd_dist - v_ego, 1) / max(1, v_ego) + 0.5))
      if self.x_dist_to_turn > 0:
        left_tbt_sec = min(self.left_tbt_sec, int(max(self.x_dist_to_turn - v_ego, 1) / max(1, v_ego) + 0.5))
    self.left_spd_sec = left_spd_sec
    self.left_tbt_sec = left_tbt_sec

    left_sec = min(left_spd_sec, left_tbt_sec)
    if left_sec > 11:
      self.left_sec = 100
      self.max_left_sec = 100
    else:
      self.sdi_inform = source in ("sdi", "hda")
      self.max_left_sec = min(11, max(6, int(v_ego_kph / 10) + 1))

    if left_sec != self.left_sec:
      if left_sec == self.max_left_sec and self.sdi_inform:
        self.carrot_left_sec = 11
      elif 1 <= left_sec < self.max_left_sec:
        self.carrot_left_sec = left_sec
      elif left_sec == 0 and self.left_sec == 1:
        self.carrot_left_sec = left_sec
      self.left_sec = left_sec

    # Traffic light state machine.
    self._update_cmd()
    if self.map_traffic_state > 0 and time.time() - self.map_traffic_time < 5.0:
      self._traffic_state = self.map_traffic_state

    # Store navi path for the publisher.
    if coords and distances:
      self.navi_paths = ";".join(
        f"{x:.2f},{y:.2f},{d:.2f}" for (x, y), d in zip(coords, distances, strict=False)
      )
    else:
      self.navi_paths = ""

  # ---- Kisa (crowdsourced nav data) -------------------------------------- #

  def update_kisa(self, data: dict) -> None:
    """Apply Kisa (waze-like) crowdsourced data from the phone app."""
    self.active_kisa_count = 100
    if "kisawazeroadspdlimit" in data:
      road_limit_speed = _safe_int(data["kisawazeroadspdlimit"], 0)
      if road_limit_speed > 0:
        if not self.is_metric:
          road_limit_speed = int(road_limit_speed * 1.609344)
        self.n_road_limit_speed = road_limit_speed
        self._raw["nRoadLimitSpeed"] = road_limit_speed
    if "kisawazeroadname" in data:
      self._raw["szPosRoadName"] = _safe_str(data["kisawazeroadname"], "")

    report_id = data.get("kisawazereportid")
    alert_dist = data.get("kisawazealertdist")
    if report_id is not None and alert_dist is not None:
      import re
      match = re.search(r"(\d+)", str(alert_dist).lower())
      distance = int(match.group(1)) if match else 0
      if not self.is_metric:
        distance = int(distance * 0.3048)
      x_spd_type = -1
      if "camera" in str(report_id):
        x_spd_type = 101
      elif "police" in str(report_id):
        x_spd_type = 100
      if x_spd_type >= 0:
        self.x_spd_type = x_spd_type
        self.x_spd_limit = self.n_road_limit_speed + 5
        self.x_spd_dist = distance
        self.active_carrot = 2

  # ---- path / curvature helpers ------------------------------------------ #

  def push_position(self, lon: float, lat: float) -> None:
    self._path.append((float(lon), float(lat)))
    if len(self._path) >= 3:
      self._update_bearing()

  def _update_bearing(self) -> None:
    # Use the last 3 points to estimate bearing.
    a, b, _ = self._path[-3], self._path[-2], self._path[-1]
    if a == b:
      return
    d_lon = b[0] - a[0]
    d_lat = b[1] - a[1]
    self._bearing = math.degrees(math.atan2(d_lon, d_lat))

  @property
  def bearing(self) -> float:
    return self._bearing

  def curvature_at(self, distance_m: float) -> float:
    """Approximate 1/r curvature from the last few GPS points."""
    if len(self._path) < 3:
      return 0.0
    a, b, c = self._path[-3], self._path[-2], self._path[-1]
    cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
    len_ab = math.hypot(b[0] - a[0], b[1] - a[1])
    len_bc = math.hypot(c[0] - b[0], c[1] - b[1])
    if len_ab == 0 or len_bc == 0:
      return 0.0
    # Sign conveys left/right turn; magnitude is roughly 1/r in degrees^-1.
    return cross / (len_ab * len_bc * len_ab) * (180.0 / math.pi) / max(distance_m, 1.0)

  def _interp_turn_speed(self, x_turn_info: int, distance_m: float) -> int:
    """Pick a safe curve speed for a turn of the given xTurnInfo class."""
    # Conservative table: tighter for sharper maneuvers, looser as we approach.
    table = {
      1: [(200.0, 55.0), (100.0, 40.0), (50.0, 25.0), (0.0, 15.0)],  # left turn
      2: [(200.0, 55.0), (100.0, 40.0), (50.0, 25.0), (0.0, 15.0)],  # right turn
      3: [(200.0, 70.0), (100.0, 55.0), (50.0, 40.0), (0.0, 30.0)],  # left lane change
      4: [(200.0, 70.0), (100.0, 55.0), (50.0, 40.0), (0.0, 30.0)],  # right lane change
      5: [(300.0, 40.0), (150.0, 30.0), (75.0, 20.0), (0.0, 12.0)],   # rotary
      6: [(200.0, 60.0), (100.0, 45.0), (50.0, 30.0), (0.0, 20.0)],   # tg
      7: [(100.0, 30.0), (0.0, 20.0)],                              # uturn
      8: [(100.0, 80.0), (0.0, 80.0)],                              # arrive/straight
    }
    speeds = table.get(x_turn_info, [])
    for d, s in speeds:
      if distance_m <= d:
        return int(s)
    return 0

  def lookup_curve_speed(self, curvature: float) -> float:
    """Look up a recommended km/h for the given curvature (1/m)."""
    if curvature <= 0:
      return 0.0
    return float(_interp_table(curvature, V_CURVE_LOOKUP_BP, V_CURVE_LOOKUP_VALS))


def _interp_table(x: float, bp: tuple[float, ...], vals: tuple[float, ...]) -> float:
  """Plain 1-D table lookup. ``bp`` must be sorted ascending."""
  if not bp or not vals:
    return 0.0
  if x <= bp[0]:
    return float(vals[0])
  if x >= bp[-1]:
    return float(vals[-1])
  for i in range(len(bp) - 1):
    if bp[i] <= x <= bp[i + 1]:
      span = bp[i + 1] - bp[i]
      if span <= 0:
        return float(vals[i])
      ratio = (x - bp[i]) / span
      return float(vals[i] + ratio * (vals[i + 1] - vals[i]))
  return float(vals[-1])
