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
import os
import subprocess
import time
from collections import deque
from enum import IntEnum
from typing import Any

from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.carrot.config import UnifiedParams


# Countdown rearm threshold (meters). A jump larger than this means a new
# target has appeared and the countdown should reset.
COUNTDOWN_NEW_TARGET_MIN_JUMP_M = 20.0

# How long the driver can override a school-zone slowdown before it is suppressed.
SCHOOL_ZONE_GAS_OVERRIDE_TIMEOUT_S = 3.0


# Turn type -> (maneuver type, modifier, xTurnInfo). xTurnInfo follows the
# convention used by the carrot UI:
#   1 = left turn, 2 = right turn, 3 = left lane change, 4 = right lane change,
#   5 = rotary, 6 = tg, 7 = uturn, 8 = arrive / straight.
NAV_TYPE_MAPPING: dict[int, tuple[str, str, int]] = {
  12: ("turn", "left", 1),
  16: ("turn", "sharp left", 1),
  1000: ("turn", "slight left", 1),
  1001: ("turn", "slight right", 2),
  1002: ("fork", "slight left", 3),
  1003: ("fork", "slight right", 4),
  1006: ("off ramp", "left", 3),
  1007: ("off ramp", "right", 4),
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
  117: ("fork", "right", 4),
  123: ("fork", "right", 4),
  124: ("fork", "right", 4),
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
    self.goal_pos_x: float = 0.0
    self.goal_pos_y: float = 0.0
    self.sz_goal_name: str = ""

    # Road / position state (read back by carrot_man and the UI).
    self.n_road_limit_speed: int = 0
    self._n_road_limit_speed_last: int = 0
    self._n_road_limit_speed_counter: int = 0
    self.vp_pos_point_lat: float = 0.0
    self.vp_pos_point_lon: float = 0.0

    # Extended 7706 phone-packet fields (carrot > Amap > OSM arbitration).
    self.n_sdi_section: int = -1
    self.gps_speed: float = 0.0
    self.epoch_time: int = 0
    self.timezone: str = "Asia/Seoul"
    self.n_tbt_next_road_width: int = 0

    # Multi-source GPS state (7706 UDP / 7714 vehicle / phone GPS fallback).
    self._navi_gps_lat: float = 0.0
    self._navi_gps_lon: float = 0.0
    self._phone_gps_lat: float = 0.0
    self._phone_gps_lon: float = 0.0
    self._phone_gps_heading: float = 0.0
    self._phone_gps_accuracy: float = 0.0
    self._phone_gps_frame: int = 0
    self._last_update_gps_time_navi: float = 0.0
    self._last_update_gps_time_phone: float = 0.0
    # Heading of the phone/navi GPS, in degrees. Written by update_raw from the
    # 7706 packet and refreshed from the cached raw packet in derive(), so the
    # 7714 v2 vehicle stream feeds it too. Read by carrot_navi_route() to rotate
    # the route polyline into the car frame.
    self._navi_gps_angle: float = 0.0

    # Navi speed-control tuning (from UnifiedParams; safe defaults).
    self.auto_navi_speed_decel_rate: float = 0.8
    self.auto_navi_speed_ctrl_end: float = 7.0


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
    self.speed_event_gas_pressed: bool = False
    self.source_last: str = "none"
    self.school_zone_gas_override_started_at: float | None = None
    self.school_zone_suppressed: bool = False

    # Countdown state.
    self.left_spd_sec: int = 100
    self.left_tbt_sec: int = 100
    self.speed_countdown_distance_last: float = 0.0
    self.turn_countdown_distance_last: float = 0.0
    self.left_sec: int = 100
    self.max_left_sec: int = 100
    self.carrot_left_sec: int = 100
    self.sdi_inform: bool = False

    # Same-SDI cache: when SameSpiCamFilter is enabled, skip recomputing
    # xSpd* if the phone SDI fields have not changed since the last derive().
    # This suppresses stale/repeated speed-camera announcements.
    self.same_spi_cam_filter: bool = True
    self._last_sdi_type: int = -2
    self._last_sdi_speed_limit: int = -1
    self._last_sdi_dist: int = -1
    self._last_sdi_plus_type: int = -2
    self._last_sdi_ctrl_mode: int = -1
    self._last_sdi_safety_factor: float = -1.0

    # Kisa (crowdsourced nav data) activity counter.
    self.active_kisa_count: int = 0
    self._param_frame: int = 0
    self._last_cmd_index: int = -1
    self.navi_paths: str = ""

    # UI language for SDI descriptions.
    self.lang: str = "en"

    # Tuning cache (refreshed by update_params(); safe defaults here so the
    # class never crashes even if update_params() has not run yet).
    self.auto_navi_speed_safety_factor: float = 1.05
    self.auto_navi_speed_bump_speed: float = 35.0
    self.auto_navi_speed_bump_time: float = 1.0
    self.auto_navi_speed_ctrl_mode: int = 0
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
    self.auto_up_road_limit_40kmh: int = 15
    self.auto_up_highway_road_limit_40kmh: int = 15
    self.road_type: int = -1
    self.show_debug_log: int = 0
    self.is_metric: bool = True

    # Vehicle CAN speed arbitration tuning (safe defaults; update_params()
    # overwrites these from params when it runs).
    self.vehicle_speed_camera_control_mode: int = 0
    self.vehicle_navi_can_control: int = 0
    self.vehicle_navi_school_zone_control: bool = False
    self.auto_navi_speed_bump_end_distance: float = 0.0

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

    raw_limit = _safe_int(msg.get("nRoadLimitSpeed"), 0)
    if raw_limit > 0:
      if raw_limit > 200:
        raw_limit = int((raw_limit - 20) / 10)
      elif raw_limit == 120:
        raw_limit = 115
    raw_limit = self._apply_road_limit_filter(raw_limit)

    # Manual road-type override and low-limit boost (aligned with cuda).
    roadcate = _safe_int(msg.get("roadcate"), 0)
    if self.road_type >= 0:
      roadcate = self.road_type
    if 0 < raw_limit < 60:
      if roadcate <= 1 and self.auto_up_highway_road_limit:
        max_add = self.auto_up_highway_road_limit_40kmh
      elif roadcate > 1 and self.auto_up_road_limit:
        max_add = self.auto_up_road_limit_40kmh
      else:
        max_add = 0
      if max_add > 0:
        if raw_limit <= 40:
          add_val = float(max_add)
        else:
          add_val = float(max_add) * (60 - raw_limit) / 20.0
        raw_limit = int(min(raw_limit + add_val, 60))

    self._raw = {
      "nRoadLimitSpeed": raw_limit,
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
      # Carried through from the packet: derive() reads these to populate
      # vp_pos_point_*, which carrot_navi_route() uses to locate the car on the
      # route. Hardcoding 0.0 here left the route anchored at (0, 0).
      "vpPosPointLat": _safe_float(msg.get("vpPosPointLat"), 0.0),
      "vpPosPointLon": _safe_float(msg.get("vpPosPointLon"), 0.0),
      "nPosAngle": _safe_float(msg.get("nPosAngle"), 0.0),
      "nPosSpeed": _safe_float(msg.get("nPosSpeed"), 0.0),
      "carrotCmdIndex": seq,
      "carrotCmd": _safe_str(msg.get("carrotCmd"), ""),
      "carrotArg": _safe_str(msg.get("carrotArg"), ""),
      "roadcate": roadcate,
      "nSdiSection": _safe_int(msg.get("nSdiSection"), -1),
      # navipilot sends snake_case "gps_speed"; cp sends camelCase "gpsSpeed".
      "gpsSpeed": _safe_float(msg.get("gpsSpeed") if "gpsSpeed" in msg else msg.get("gps_speed"), 0.0),
      "epochTime": _safe_int(msg.get("epochTime"), 0),
      "timezone": _safe_str(msg.get("timezone"), "Asia/Seoul"),
      "nTBTNextRoadWidth": _safe_int(msg.get("nTBTNextRoadWidth"), 0),
      "goalPosX": _safe_float(msg.get("goalPosX"), 0.0),
      "goalPosY": _safe_float(msg.get("goalPosY"), 0.0),
      "szGoalName": _safe_str(msg.get("szGoalName"), ""),
      # Service area / toll gate hints (App §2.3 SAPA_* group, KEY_TYPE 10001).
      # SAPA_TYPE: 0=service/parking area, 1=toll gate, 2=checkpoint.
      "sapaName": _safe_str(msg.get("sapaName"), ""),
      "sapaDist": _safe_int(msg.get("sapaDist"), 0),   # -1 = invalid
      "sapaType": _safe_int(msg.get("sapaType"), 0),
      "sapaCnt": _safe_int(msg.get("sapaCnt"), 0),
      # TMC live traffic congestion (App §2.5, KEY_TYPE 13011). Overall status
      # is a scalar; per-segment statuses/distances are packed into compact
      # JSON strings so the array survives pycapnp without per-element List
      # management. Consumers (webui / OP assistant) json.loads() them.
      "tmcTotalDistance": _safe_int(msg.get("tmcTotalDistance"), 0),
      "tmcResidualDistance": _safe_int(msg.get("tmcResidualDistance"), 0),
      "tmcSegmentCount": _safe_int(msg.get("tmcSegmentCount"), 0),
      "tmcOverallStatus": _safe_int(msg.get("tmcOverallStatus"), 0),
      "tmcSegmentStatuses": _safe_str(msg.get("tmcSegmentStatuses"), ""),
      "tmcSegmentDistances": _safe_str(msg.get("tmcSegmentDistances"), ""),
      # Lane guidance arrow codes (App §2.2 navLaneGuide / navLaneGuideCnt).
      "navLaneGuide": _safe_str(msg.get("navLaneGuide"), ""),
      "navLaneGuideCnt": _safe_int(msg.get("navLaneGuideCnt"), 0),
    }

    if "carrotCmd" in msg:
      self._raw["carrotCmdIndex"] = seq
      self._raw["carrotCmd"] = _safe_str(msg.get("carrotCmd"), "")
      self._raw["carrotArg"] = _safe_str(msg.get("carrotArg"), "")

    # Phone GPS fallback fields (sent outside the main navi block).
    self._update_phone_gps_from_packet(msg)
    # 7706 navi GPS is authoritative while it is fresh.
    lat = _safe_float(msg.get("vpPosPointLat"), 0.0)
    lon = _safe_float(msg.get("vpPosPointLon"), 0.0)
    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and (lat != 0.0 or lon != 0.0):
      self._navi_gps_lat = lat
      self._navi_gps_lon = lon
      self._navi_gps_angle = _safe_float(msg.get("nPosAngle"), 0.0) % 360.0
      self._last_update_gps_time_navi = time.monotonic()
    # Periodic system time sync from the phone's epochTime/timezone.
    if "epochTime" in msg and seq % 60 == 0:
      self._maybe_sync_system_time(_safe_int(msg.get("epochTime"), 0),
                                   _safe_str(msg.get("timezone"), "Asia/Seoul"))

  def _apply_road_limit_filter(self, raw_limit: int) -> int:
    """5-frame confirmation filter to avoid jitter in road limit speed."""
    if raw_limit <= 0:
      self._n_road_limit_speed_last = 0
      self._n_road_limit_speed_counter = 0
      return 0
    if raw_limit != self._n_road_limit_speed_last:
      self._n_road_limit_speed_counter += 1
      if self._n_road_limit_speed_counter > 5:
        self._n_road_limit_speed_last = raw_limit
        self._n_road_limit_speed_counter = 0
      else:
        # During the confirmation window, keep reporting the previous value.
        return self.n_road_limit_speed
    else:
      self._n_road_limit_speed_counter = 0
    self._n_road_limit_speed_last = raw_limit
    return raw_limit

  def _update_phone_gps_from_packet(self, msg: dict) -> None:
    """Cache standalone phone GPS fields for the multi-source GPS fusion."""
    if "latitude" in msg:
      lat = _safe_float(msg.get("latitude"), 0.0)
      lon = _safe_float(msg.get("longitude"), 0.0)
      heading = _safe_float(msg.get("heading"), 0.0)
      accuracy = _safe_float(msg.get("accuracy"), 0.0)
      if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
        self._phone_gps_lat = lat
        self._phone_gps_lon = lon
        self._phone_gps_heading = heading % 360.0
        self._phone_gps_accuracy = accuracy
        # The freshness timestamp used to be set only by the (unused) GPS
        # fusion step, so gps_source always reported the phone as stale.
        self._last_update_gps_time_phone = time.monotonic()
        if accuracy < 15.0:
          self._phone_gps_frame += 1

  # System clock is only nudged when drift is within this window and the
  # target year is plausible. Guardrails prevent a malformed phone timestamp
  # (e.g. 1970 or 2050) from corrupting logs / route timestamps.
  _TIME_SYNC_MIN_YEAR = 2015
  _TIME_SYNC_MAX_YEAR = 2035

  def _maybe_sync_system_time(self, epoch_time: int, timezone: str) -> None:
    """Opt-in system clock/timezone sync from the phone's 7706/7714 epochTime.

    Guarded by the ``CarrotNtpTimeSync`` killswitch (default OFF) because
    modifying the system clock on a running car is dangerous and sunnypilot
    already keeps time via NTP. When enabled, the clock is only nudged when:
      * the killswitch param is on, AND
      * running on-device (not PC), AND
      * |drift| > 60s (limited drift threshold), AND
      * the target year is within a sane 2015..2035 window.
    """
    # Killswitch: must be explicitly enabled. Default-off for safety.
    if not self._params.get_bool("CarrotNtpTimeSync", False):
      return
    if epoch_time <= 0:
      return
    try:
      import openpilot.system.hardware as hardware
      PC = getattr(hardware, "PC", False)
    except Exception:
      PC = True
    if PC:
      return
    # Sanity cap: reject absurd target timestamps before touching the clock.
    try:
      target_year = time.localtime(epoch_time).tm_year
    except (ValueError, OSError):
      cloudlog.warning(f"carrot_serv: refusing time sync, bad epoch {epoch_time}")
      return
    if not (self._TIME_SYNC_MIN_YEAR <= target_year <= self._TIME_SYNC_MAX_YEAR):
      cloudlog.warning(f"carrot_serv: refusing time sync, year {target_year} out of range")
      return
    now_epoch = int(time.time())
    offset = epoch_time - now_epoch
    if abs(offset) <= 60:
      return
    try:
      localtime_path = "/data/etc/localtime"
      zoneinfo_path = f"/usr/share/zoneinfo/{timezone}"
      if os.path.exists(localtime_path) or os.path.islink(localtime_path):
        subprocess.run(["sudo", "rm", "-f", localtime_path], check=True)
      subprocess.run(["sudo", "ln", "-s", zoneinfo_path, localtime_path], check=True)
      formatted = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch_time))
      subprocess.run(["sudo", "date", "-s", formatted], check=True)
      # Persist the phone-supplied timezone as the authoritative source so the
      # device's own time-setting logic (timed.py) does not overwrite it.
      self._params.put("TimezoneName", timezone)
      self._params.put("TimezoneSource", "app")
    except Exception as e:
      cloudlog.error(f"carrot_serv: failed to sync system time: {e}")

  def update_keepalive(self, recv_mono: float = 0.0) -> None:
    """Refresh the last-seen timestamp without overwriting cached state.

    Used for heartbeat packets that only exist to keep the link alive.
    """
    self._last_packet_mono = recv_mono

  @property
  def bearing(self) -> float:
    """Heading in degrees, used to rotate the route into the car frame.

    Sourced from the phone/navi GPS heading. This used to return a value that
    only the removed GPS-fusion step ever wrote, so it was always 0.0.
    """
    return self._navi_gps_angle

  def is_stale(self, now_mono: float, timeout: float = 3.0) -> bool:
    return self._last_packet_mono > 0.0 and (now_mono - self._last_packet_mono) > timeout

  def raw_update(self, key: str, value: Any) -> None:
    """Update a single key in the cached raw packet (used by 7714 v2 merges)."""
    self._raw[key] = value

  @property
  def raw(self) -> dict:
    return dict(self._raw)

  @property
  def last_packet_mono(self) -> float:
    return self._last_packet_mono

  @property
  def gps_source(self) -> str:
    """Which navigation GPS source is currently fresh ("navi" / "phone" / "none")."""
    now = time.monotonic()
    navi_age = now - self._last_update_gps_time_navi
    phone_age = now - self._last_update_gps_time_phone
    navi_valid = navi_age < 3.0 and (self._navi_gps_lat != 0.0 or self._navi_gps_lon != 0.0)
    phone_valid = phone_age < 3.0 and (self._phone_gps_lat != 0.0 or self._phone_gps_lon != 0.0)
    if navi_valid:
      return "navi"
    if phone_valid:
      return "phone"
    return "none"

  def vehicle_speed_camera_active(self, cs: Any | None) -> bool:
    """True when vehicle CAN reports an active speed-camera zone."""
    return cs is not None and self._vehicle_speed_camera_enabled(cs)

  def vehicle_speed_bump_active(self, cs: Any | None) -> bool:
    """True when vehicle CAN reports an active speed-bump zone."""
    return cs is not None and self._vehicle_speed_bump_enabled(cs)

  def vehicle_school_zone_active(self, cs: Any | None) -> bool:
    """True when vehicle CAN reports an active school zone."""
    return cs is not None and self._vehicle_school_zone_enabled(cs)

  def vehicle_section_zone_active(self, cs: Any | None) -> bool:
    """True when vehicle CAN reports an active section-speed zone."""
    return cs is not None and self._vehicle_section_zone_enabled(cs)

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
    self.speed_event_gas_pressed = False
    self.source_last = "none"
    self.school_zone_gas_override_started_at = None
    self.school_zone_suppressed = False
    self._n_road_limit_speed_last = 0
    self._n_road_limit_speed_counter = 0
    self.left_spd_sec = 100
    self.left_tbt_sec = 100
    self.speed_countdown_distance_last = 0.0
    self.turn_countdown_distance_last = 0.0
    self.left_sec = 100
    self.max_left_sec = 100
    self.carrot_left_sec = 100
    self.sdi_inform = False
    self.active_kisa_count = 0
    self._last_x_spd_dist = 0
    self._last_x_dist_to_turn = 0
    self.n_sdi_section = -1
    self.gps_speed = 0.0
    self.epoch_time = 0
    self.timezone = "Asia/Seoul"
    self.n_tbt_next_road_width = 0
    self.goal_pos_x = 0.0
    self.goal_pos_y = 0.0
    self.sz_goal_name = ""

    self._navi_gps_lat = 0.0
    self._navi_gps_lon = 0.0
    self._phone_gps_lat = 0.0
    self._phone_gps_lon = 0.0
    self._phone_gps_heading = 0.0
    self._phone_gps_accuracy = 0.0
    self._phone_gps_frame = 0
    self._last_update_gps_time_navi = 0.0
    self._last_update_gps_time_phone = 0.0
    self._navi_gps_angle = 0.0

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

    # --- heading ---------------------------------------------------------
    # Refresh from the cache so the 7714 v2 vehicle stream (which writes
    # _raw["nPosAngle"]) updates it as well as the 7706 packet path.
    self._navi_gps_angle = _safe_float(r.get("nPosAngle"), 0.0) % 360.0

    # --- SDI -> xSpd* ----------------------------------------------------
    sdi_type = _safe_int(r.get("nSdiType"), -1)
    sdi_speed_limit = _safe_int(r.get("nSdiSpeedLimit"), 0)
    sdi_dist = _safe_int(r.get("nSdiDist"), 0)
    sdi_block_type = _safe_int(r.get("nSdiBlockType"), -1)
    sdi_block_dist = _safe_int(r.get("nSdiBlockDist"), 0)
    sdi_plus_type = _safe_int(r.get("nSdiPlusType"), -1)
    sdi_plus_dist = _safe_int(r.get("nSdiPlusDist"), 0)
    sdi_plus_speed_limit = _safe_int(r.get("nSdiPlusSpeedLimit"), 0)
    sdi_plus_block_type = _safe_int(r.get("nSdiPlusBlockType"), -1)
    sdi_plus_block_dist = _safe_int(r.get("nSdiPlusBlockDist"), 0)
    roadcate = _safe_int(r.get("roadcate"), 0)

    # Primary SDI active: a real speed camera/bump alert is in progress.
    primary_sdi_active = (
      sdi_type in SDI_SPEED_CAMERA_TYPES and sdi_speed_limit > 0 and
      not (sdi_type == 7 and self.auto_navi_speed_ctrl_mode < 3)
    ) or ((sdi_plus_type == 22 or sdi_type == 22) and roadcate > 1)

    self.sz_sdi_descr = ""
    sdi_unchanged = (
      self.same_spi_cam_filter and
      self._last_sdi_type == sdi_type and
      self._last_sdi_speed_limit == sdi_speed_limit and
      self._last_sdi_dist == sdi_dist and
      self._last_sdi_plus_type == sdi_plus_type and
      self._last_sdi_ctrl_mode == self.auto_navi_speed_ctrl_mode and
      abs(self._last_sdi_safety_factor - self.auto_navi_speed_safety_factor) < 1e-6
    )

    if not sdi_unchanged:
      self._last_sdi_type = sdi_type
      self._last_sdi_speed_limit = sdi_speed_limit
      self._last_sdi_dist = sdi_dist
      self._last_sdi_plus_type = sdi_plus_type
      self._last_sdi_ctrl_mode = self.auto_navi_speed_ctrl_mode
      self._last_sdi_safety_factor = self.auto_navi_speed_safety_factor

      if primary_sdi_active:
        if sdi_type in SDI_SPEED_CAMERA_TYPES and sdi_speed_limit > 0:
          self.x_spd_limit = int(round(sdi_speed_limit * self.auto_navi_speed_safety_factor))
          self.x_spd_dist = sdi_dist
          self.x_spd_type = sdi_type
          if sdi_block_type in (2, 3):
            self.x_spd_dist = sdi_block_dist
            self.x_spd_type = 4
        elif (sdi_plus_type == 22 or sdi_type == 22) and roadcate > 1:
          # Speed bump on non-highway road.
          self.x_spd_limit = int(round(self.auto_navi_speed_bump_speed * self.auto_navi_speed_safety_factor))
          self.x_spd_dist = sdi_plus_dist if sdi_plus_type == 22 else sdi_dist
          self.x_spd_type = 22
      elif sdi_plus_type in SDI_SPEED_CAMERA_TYPES and sdi_plus_speed_limit > 0:
        # Secondary SDI applies only when primary is absent (cp P1 gap).
        self.x_spd_limit = int(round(sdi_plus_speed_limit * self.auto_navi_speed_safety_factor))
        self.x_spd_dist = sdi_plus_dist
        self.x_spd_type = sdi_plus_type
        if sdi_plus_block_type in (2, 3):
          self.x_spd_dist = sdi_plus_block_dist
          self.x_spd_type = 4
      else:
        self.x_spd_limit = 0
        self.x_spd_type = -1
        self.x_spd_dist = 0

    if self.x_spd_type >= 0:
      self.sz_sdi_descr = self._get_sdi_descr(self.x_spd_type)

    # --- Curve speed (turn) ---------------------------------------------
    if self.x_turn_info > 0 and self.x_dist_to_turn > 0:
      self.v_turn_speed = self._interp_turn_speed(self.x_turn_info, self.x_dist_to_turn)
    else:
      self.v_turn_speed = 0

    # --- Road limit / phone position --------------------------------------
    self.n_road_limit_speed = _safe_int(r.get("nRoadLimitSpeed"), 0)
    self.vp_pos_point_lat = _safe_float(r.get("vpPosPointLat"), 0.0)
    self.vp_pos_point_lon = _safe_float(r.get("vpPosPointLon"), 0.0)

    # --- Extended 7706 fields (exported to cereal for control/UI) ----------
    self.n_sdi_section = _safe_int(r.get("nSdiSection"), -1)
    self.gps_speed = _safe_float(r.get("gpsSpeed"), 0.0)
    self.epoch_time = _safe_int(r.get("epochTime"), 0)
    self.timezone = _safe_str(r.get("timezone"), "Asia/Seoul")
    self.n_tbt_next_road_width = _safe_int(r.get("nTBTNextRoadWidth"), 0)
    self.goal_pos_x = _safe_float(r.get("goalPosX"), 0.0)
    self.goal_pos_y = _safe_float(r.get("goalPosY"), 0.0)
    self.sz_goal_name = _safe_str(r.get("szGoalName"), "")

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

  def update_map_traffic(self, state: int, countdown: int = 0) -> None:
    """Apply map/app traffic-light state (takes priority over camera detect).

    State: 0=none, 1=red, 2=green, 3=left-turn.
    """
    self.map_traffic_state = max(0, _safe_int(state, 0))
    self.map_traffic_countdown = max(0, _safe_int(countdown, 0))
    self.map_traffic_time = time.time()
    # Immediately update the published state while fresh.
    self._traffic_state = self.map_traffic_state

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
    self.n_sdi_section = -1
    self.gps_speed = 0.0
    self.epoch_time = 0
    self.timezone = "Asia/Seoul"
    self.n_tbt_next_road_width = 0
    self.goal_pos_x = 0.0
    self.goal_pos_y = 0.0
    self.sz_goal_name = ""
    # Invalidate the SDI cache so the next derive() recomputes fresh.
    self._last_sdi_type = -2
    self._last_sdi_speed_limit = -1
    self._last_sdi_dist = -1
    self._last_sdi_plus_type = -2
    self._last_sdi_ctrl_mode = -1
    self._last_sdi_safety_factor = -1.0

  # ---- parameter refresh -------------------------------------------------- #

  def update_params(self) -> None:
    """Refresh tuning parameters from UnifiedParams (throttled to 10 Hz)."""
    if (self._param_frame % 10) != 0:
      self._param_frame += 1
      return
    self._param_frame += 1

    p = self._params
    self.auto_navi_speed_decel_rate = float(p.get_int("AutoNaviSpeedDecelRate", 120)) * 0.01
    self.auto_navi_speed_ctrl_end = float(p.get_int("AutoNaviSpeedCtrlEnd", 7))
    self.auto_navi_speed_safety_factor = float(p.get_int("AutoNaviSpeedSafetyFactor", 105)) * 0.01
    self.auto_navi_speed_bump_speed = float(p.get_int("AutoNaviSpeedBumpSpeed", 35))
    self.auto_navi_speed_bump_time = float(p.get_int("AutoNaviSpeedBumpTime", 1))
    self.auto_navi_speed_ctrl_mode = p.get_int("AutoNaviSpeedCtrlMode", 0)
    self.auto_navi_count_down_mode = p.get_int("AutoNaviCountDownMode", 0)
    self.turn_speed_control_mode = p.get_int("TurnSpeedControlMode", 1)
    self.map_turn_speed_factor = float(p.get_int("MapTurnSpeedFactor", 90)) * 0.01
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
    self.auto_up_road_limit_40kmh = p.get_int("AutoUpRoadLimit40KMH", 15)
    self.auto_up_highway_road_limit_40kmh = p.get_int("AutoUpHighwayRoadLimit40KMH", 15)
    self.road_type = p.get_int("RoadType", -1)
    self.show_debug_log = p.get_int("ShowDebugLog", 0)
    self.same_spi_cam_filter = p.get_bool("SameSpiCamFilter", True)
    self.is_metric = p.get_bool("IsMetric", True)

    lang = str(p.get("LanguageSetting") or "en").strip().removeprefix("main_")
    self.lang = {"ko": "ko", "zh": "zh", "zh-CHS": "zh", "zh-CHT": "zh"}.get(lang, "en")

    # Vehicle CAN speed arbitration tuning (safe defaults for unregistered keys).
    self.vehicle_speed_camera_control_mode = min(3, max(0, p.get_int("VehicleSpeedCameraControlMode", 0)))
    self.vehicle_navi_can_control = min(3, max(0, p.get_int("VehicleNaviCanControl", 0)))
    self.vehicle_navi_school_zone_control = p.get_bool("VehicleNaviSchoolZoneControl", False)
    self.auto_navi_speed_bump_end_distance = float(min(5000, max(0, p.get_int("AutoNaviSpeedBumpEndDistance", 0)))) * 0.01

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

  # ---- vehicle CAN speed arbitration helpers ----------------------------- #

  def _vehicle_speed_camera_enabled(self, cs: Any) -> bool:
    """True when the vehicle CAN reports an active speed-limit camera."""
    return bool(
      self.vehicle_speed_camera_control_mode > 0 and
      getattr(cs, "speedLimit", 0.0) > 0 and
      getattr(cs, "speedLimitDistance", 0.0) > 0 and
      not (getattr(cs, "schoolZoneActive", False) and self.school_zone_suppressed) and
      not (self.vehicle_speed_camera_control_mode == 3 and getattr(cs, "gasPressed", False))
    )

  def _speed_bump_control_active(self, distance: float) -> bool:
    """True when the phone's speed-bump alert is still inside the configured end zone."""
    return float(distance) > self.auto_navi_speed_bump_end_distance

  def _vehicle_speed_bump_enabled(self, cs: Any) -> bool:
    """True when the vehicle CAN reports a speed bump we should slow for."""
    return bool(
      self.vehicle_navi_can_control > 0 and
      self.auto_navi_speed_ctrl_mode >= 2 and
      self._speed_bump_control_active(getattr(cs, "speedBumpDistance", 0.0))
    )

  def _vehicle_school_zone_enabled(self, cs: Any) -> bool:
    """True when the vehicle CAN reports an active school zone and we have not suppressed it."""
    if not getattr(cs, "schoolZoneActive", False):
      self.school_zone_gas_override_started_at = None
      self.school_zone_suppressed = False
      return False
    return bool(
      self.vehicle_navi_school_zone_control and
      self.vehicle_speed_camera_control_mode > 0 and
      not self.school_zone_suppressed and
      not (self.vehicle_speed_camera_control_mode == 3 and getattr(cs, "gasPressed", False))
    )

  def _vehicle_school_zone_speed(self, cs: Any) -> float:
    """Target speed (km/h) for an active school zone, or 250 when inactive."""
    return 30.0 if self._vehicle_school_zone_enabled(cs) else 250.0

  def _vehicle_section_zone_enabled(self, cs: Any) -> bool:
    """True when the vehicle CAN reports an active section-speed zone."""
    return bool(
      self.vehicle_navi_can_control > 0 and
      self.vehicle_speed_camera_control_mode > 0 and
      getattr(cs, "vehicleNaviSectionActive", False) and
      getattr(cs, "vehicleNaviSpeed", 0.0) > 0 and
      not (self.vehicle_speed_camera_control_mode == 3 and getattr(cs, "gasPressed", False))
    )

  def _vehicle_navigation_display(self, cs: Any | None) -> tuple[bool, int, bool]:
    """Compute cluster/UI display values from vehicle CAN navi state."""
    if (
      cs is None or
      self.vehicle_navi_can_control <= 0 or
      not getattr(cs, "vehicleNaviActive", False)
    ):
      return False, 0, False
    if getattr(cs, "schoolZoneActive", False):
      speed = 30
    elif getattr(cs, "vehicleNaviSpeed", 0.0) > 0:
      speed = int(getattr(cs, "vehicleNaviSpeed", 0.0) * self.auto_navi_speed_safety_factor)
    elif self._speed_bump_control_active(getattr(cs, "speedBumpDistance", 0.0)):
      speed = int(self.auto_navi_speed_bump_speed)
    else:
      speed = 0
    return speed > 0, speed, bool(getattr(cs, "vehicleNaviSectionActive", False))

  @staticmethod
  def _legacy_sdi_suppressed(x_spd_type: int, vehicle_camera_active: bool,
                              vehicle_bump_active: bool) -> bool:
    """Suppress phone SDI when the vehicle CAN already reports the same hazard.

    Keeps independent KISA/Waze hazards (100/101); only replaces navigation
    camera/section candidates that can describe the same physical alert.
    """
    same_camera = vehicle_camera_active and x_spd_type in SDI_SPEED_CAMERA_TYPES
    same_bump = vehicle_bump_active and x_spd_type == 22
    return same_camera or same_bump

  def _update_school_zone_gas_override(self, override_active: bool) -> None:
    """Track how long the driver has been overriding a school-zone slowdown."""
    if not override_active:
      self.school_zone_gas_override_started_at = None
      return
    now = time.monotonic()
    if self.school_zone_gas_override_started_at is None:
      self.school_zone_gas_override_started_at = now
    elif now - self.school_zone_gas_override_started_at >= SCHOOL_ZONE_GAS_OVERRIDE_TIMEOUT_S:
      self.school_zone_suppressed = True

  def _speed_countdown_distance(self, cs: Any | None) -> float:
    """Return the closest countdown distance from phone navi + vehicle CAN."""
    distances: list[float] = []
    legacy_bump_suppressed = self.x_spd_type == 22 and self.auto_navi_count_down_mode == 1
    if self.x_spd_dist > 0 and not legacy_bump_suppressed:
      distances.append(float(self.x_spd_dist))

    vehicle_navi_active = (
      cs is not None and self.vehicle_navi_can_control > 0 and
      getattr(cs, "vehicleNaviActive", False)
    )
    if vehicle_navi_active:
      camera_distance = getattr(cs, "speedLimitDistance", 0.0)
      if camera_distance > 0:
        distances.append(float(camera_distance))
      bump_distance = getattr(cs, "speedBumpDistance", 0.0)
      if self.auto_navi_count_down_mode >= 2 and bump_distance > 0:
        distances.append(float(bump_distance))

    return min(distances, default=0.0)

  @staticmethod
  def _countdown_channel(distance: float, previous_distance: float,
                         previous_left_sec: int, v_ego: float) -> tuple[int, float, bool]:
    """Compute one countdown channel, handling new-target rearm."""
    if distance <= 0:
      return 100, 0.0, False

    calculated = int(max(distance - v_ego, 1) / max(1, v_ego) + 0.5)
    new_target = (
      previous_distance > 0 and
      distance - previous_distance > max(COUNTDOWN_NEW_TARGET_MIN_JUMP_M, v_ego * 2.0)
    )
    rearmed = new_target and previous_left_sec <= 11
    left_sec = calculated if new_target else min(previous_left_sec, calculated)
    return (100 if rearmed else left_sec), float(distance), rearmed

  def _update_countdown_alert(self, left_sec: int, source: str, v_ego_kph: float) -> None:
    """Update the cluster-facing countdown alert state."""
    if left_sec > 11:
      self.left_sec = 100
      self.max_left_sec = 100
      self.carrot_left_sec = 100
      self.sdi_inform = False
      return

    self.sdi_inform = source in ("sdi", "cam", "hda")
    self.max_left_sec = min(11, max(6, int(v_ego_kph / 10) + 1))
    if left_sec != self.left_sec:
      if left_sec == self.max_left_sec and self.sdi_inform:
        self.carrot_left_sec = 11
      elif 1 <= left_sec < self.max_left_sec:
        self.carrot_left_sec = left_sec
      elif left_sec == 0 and self.left_sec == 1:
        self.carrot_left_sec = left_sec

      self.left_sec = left_sec

  def _get_sdi_descr(self, n_sdi_type: int) -> str:
    """Return a human-readable SDI description in the user's language."""
    sdi_ko = {
      0: "신호과속", 1: "과속 (고정식)", 2: "구간단속 시작", 3: "구간단속 끝",
      4: "구간단속중", 5: "꼬리물기단속칩", 6: "신호 단속", 7: "과속 (이동식)",
      8: "고정식 과속위험 구간(박스형)", 9: "버스전용차로구간", 10: "가변 차로 단속",
      11: "갓길 감시 지점", 12: "끼어들기 금지", 13: "교통정보 수집지점",
      14: "방범용cctv", 15: "과적차량 위험구간", 16: "적재 불량 단속",
      17: "주차단속 지점", 18: "일방통행도로", 19: "철길 건실목",
      20: "어린이 보호구역(스쿨존 시작 구간)", 21: "어린이 보호구역(스쿨존 끝 구간)",
      22: "과속방지턱", 23: "lpg충전소", 24: "터널 구간", 25: "휴게소",
      26: "톨게이트", 27: "안개주의 지역", 28: "유핍물질 지역", 29: "사고다발",
      30: "급커브지역", 31: "급커브구간1", 32: "급경사구간",
      33: "야생동물 교통사고 잦은 구간", 34: "우측시야불량지점", 35: "시야불량지점",
      36: "좌측시야불량지점", 37: "신호위반다발구간", 38: "과속운행다발구간",
      39: "교통혼잡지역", 40: "방향별차로선택지점", 41: "무단횡단사고다발지점",
      42: "갓길 사고 다발 지점", 43: "과속 사발 다발 지점", 44: "졸음 사고 다발 지점",
      45: "사고다발지점", 46: "보행자 사고다발지점", 47: "차량도난사고 상습발생지점",
      48: "낙석주의지역", 49: "결빙주의지역", 50: "병목지점", 51: "합류 도로",
      52: "추락주의지역", 53: "지하차도 구간", 54: "주택밀집지역(교통진정지역)",
      55: "인터체인지", 56: "분기점", 57: "휴게소(lpg충전가능)", 58: "교량",
      59: "제동장치사고다발지점", 60: "중앙선침범사고다발지점",
      61: "통행위반사고다발지점", 62: "목적지 건실편 안내", 63: "졸음 쉼터 안내",
      64: "노후경유차단속", 65: "터널내 차로변경단속", 66: "",
    }
    sdi_en = {
      0: "Signal speed enforcement", 1: "Speed camera (fixed)", 2: "Section control start",
      3: "Section control end", 4: "Under section control", 5: "Block-the-box camera",
      6: "Signal violation enforcement", 7: "Speed camera (mobile)",
      8: "Fixed speed camera zone (box)", 9: "Bus-only lane zone",
      10: "Reversible/variable lane enforcement", 11: "Shoulder surveillance point",
      12: "No cut-in", 13: "Traffic data collection point", 14: "Security CCTV",
      15: "Overloaded vehicle risk zone", 16: "Improper loading enforcement",
      17: "Parking enforcement point", 18: "One-way road", 19: "Railroad crossing",
      20: "School zone start", 21: "School zone end", 22: "Speed bump",
      23: "LPG station", 24: "Tunnel section", 25: "Rest area", 26: "Toll gate",
      27: "Fog caution area", 28: "Hazardous materials area", 29: "Accident-prone section",
      30: "Sharp curve area", 31: "Sharp curve section 1", 32: "Steep slope section",
      33: "Wild animal crossing area", 34: "Poor visibility (right)", 35: "Poor visibility",
      36: "Poor visibility (left)", 37: "Frequent signal violations", 38: "Frequent speeding",
      39: "Traffic congestion area", 40: "Lane selection by direction",
      41: "Frequent jaywalking accidents", 42: "Frequent shoulder accidents",
      43: "Frequent speeding accidents", 44: "Frequent drowsy driving accidents",
      45: "Accident-prone spot", 46: "Frequent pedestrian accidents",
      47: "Frequent vehicle theft", 48: "Falling rock caution area",
      49: "Icy road caution area", 50: "Bottleneck point", 51: "Merging road",
      52: "Cliff/Drop caution area", 53: "Underpass section",
      54: "Residential area (traffic calming)", 55: "Interchange", 56: "Junction",
      57: "Rest area (LPG available)", 58: "Bridge", 59: "Frequent brake failure accidents",
      60: "Center line invasion accidents", 61: "Violation-of-passage accidents",
      62: "Destination on opposite side", 63: "Drowsy rest area", 64: "Old diesel control",
      65: "Lane change enforcement in tunnel", 66: "",
    }
    sdi_zh = {
      0: "信号测速/闯灯拍照", 1: "固定测速摄像头", 2: "区间测速开始", 3: "区间测速结束",
      4: "区间测速中", 5: "路口压线摄像头", 6: "闯红灯拍照", 7: "流动测速摄像头",
      8: "测速拍照", 9: "公交专用车道区间", 10: "可变/潮汐车道拍照", 11: "应急车道拍照",
      12: "禁止加塞", 13: "交通信息采集点", 14: "治安监控", 15: "超载车辆风险区",
      16: "装载不当拍照", 17: "违停拍照点", 18: "单行道", 19: "铁路道口",
      20: "学校区域开始", 21: "学校区域结束", 22: "减速带", 23: "LPG加气站",
      24: "隧道区间", 25: "服务区", 26: "ETC计费拍照", 27: "多雾路段",
      28: "危险品区域", 29: "事故多发路段", 30: "急弯路段", 31: "急弯区段1",
      32: "陡坡路段", 33: "野生动物出没路段", 34: "右侧视野不良点", 35: "视野不良点",
      36: "左侧视野不良点", 37: "闯红灯多发", 38: "超速多发", 39: "交通拥堵区域",
      40: "按方向选择车道点", 41: "行人乱穿马路多发处", 42: "应急车道事故多发",
      43: "超速事故多发", 44: "疲劳驾驶事故多发", 45: "事故多发点",
      46: "行人事故多发点", 47: "车辆盗窃多发点", 48: "落石危险路段",
      49: "路面结冰危险", 50: "瓶颈路段", 51: "汇入道路", 52: "坠落危险路段",
      53: "地下车道区间", 54: "居民区（交通缓和）", 55: "立交", 56: "分岔点",
      57: "服务区（可加气）", 58: "桥梁", 59: "制动故障事故多发点",
      60: "越线事故多发点", 61: "违法通行事故多发点", 62: "目的地在对面",
      63: "瞌睡停车区", 64: "老旧柴油车管制", 65: "隧道内变道拍照", 66: "",
    }
    sdi_map = {"ko": sdi_ko, "zh": sdi_zh}.get(self.lang, sdi_en)
    return sdi_map.get(n_sdi_type, "")

  def _apply_speed_source_gas_floor(self, cs: Any, desired_speed: float, source: str,
                                     v_ego_kph: float,
                                     road_speed_limit_changed: bool) -> tuple[float, str]:
    """Apply driver accelerator override to the chosen speed source.

    Vehicle CAN sources (hda, hda_section, hda_bump, school) have configurable
    gas floors.  Other sources preserve the existing override semantics so road
    limits and curves are not silently disabled by vehicle-camera modes.
    """
    speed_event_gas_rising = getattr(cs, "gasPressed", False) and not self.speed_event_gas_pressed
    self.speed_event_gas_pressed = bool(getattr(cs, "gasPressed", False))

    if source in ("hda", "hda_section", "hda_bump", "school"):
      # Vehicle speed bumps always allow an intentional accelerator override.
      # Camera, section, and school sources follow mode 2 only after their
      # target has fallen below the current speed and actual deceleration is
      # requested.
      gas_floor_active = source == "hda_bump" or self.vehicle_speed_camera_control_mode == 2
      if not gas_floor_active:
        self.gas_override_speed = 0
      else:
        reset_floor = (
          source != self.source_last or
          getattr(cs, "vEgo", 0.0) < 0.1 or
          desired_speed > 150 or
          getattr(cs, "brakePressed", False) or
          road_speed_limit_changed
        )
        if reset_floor:
          self.gas_override_speed = 0
        if self.gas_override_speed <= 0:
          if (
            speed_event_gas_rising and
            not getattr(cs, "brakePressed", False) and
            getattr(cs, "vEgo", 0.0) >= 0.1 and
            desired_speed <= 150 and
            desired_speed < v_ego_kph
          ):
            # A new accelerator input during active event deceleration means
            # the driver wants to ignore the remaining slowdown.
            self.gas_override_speed = v_ego_kph
        elif getattr(cs, "gasPressed", False):
          # Keep the highest speed reached while overriding this event.
          self.gas_override_speed = max(v_ego_kph, self.gas_override_speed)

      self.source_last = source
      override_active = gas_floor_active and desired_speed < self.gas_override_speed
      if source == "school":
        self._update_school_zone_gas_override(override_active)
      elif not self.school_zone_suppressed:
        self.school_zone_gas_override_started_at = None
      if override_active:
        return self.gas_override_speed, "gas"
      return desired_speed, source

    # Vehicle speed-camera modes must not change the existing accelerator
    # override behavior for road limits, curves, or other navigation sources.
    if source != self.source_last:
      self.gas_override_speed = 0
      self.gas_pressed_state = bool(getattr(cs, "gasPressed", False))

    reset_floor = (
      getattr(cs, "vEgo", 0.0) < 0.1 or
      desired_speed > 150 or
      source in ("cam", "section", "police") or
      getattr(cs, "brakePressed", False) or
      road_speed_limit_changed
    )
    if reset_floor:
      self.gas_override_speed = 0
    elif source == "bump":
      if self.gas_override_speed <= 0:
        if speed_event_gas_rising and desired_speed < v_ego_kph:
          self.gas_override_speed = v_ego_kph
      elif getattr(cs, "gasPressed", False):
        self.gas_override_speed = max(v_ego_kph, self.gas_override_speed)
    elif getattr(cs, "gasPressed", False) and not self.gas_pressed_state:
      self.gas_override_speed = max(v_ego_kph, self.gas_override_speed)
    else:
      self.gas_pressed_state = False

    self.source_last = source
    if desired_speed < self.gas_override_speed:
      return self.gas_override_speed, "gas"
    return desired_speed, source

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
    cs = sm["carState"] if sm.alive["carState"] else None
    if cs is not None:
      v_ego = cs.vEgo
      v_ego_kph = v_ego * 3.6
    else:
      v_ego = 0.0
      v_ego_kph = 0.0

    # Re-derive TBT/SDI from the cached packet, then apply time-based decay.
    self.derive(v_ego_kph)
    road_speed_limit_changed = self.n_road_limit_speed != getattr(self, "_n_road_limit_speed_last", 0)
    self._n_road_limit_speed_last = self.n_road_limit_speed
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
    atc_desired_next, _, _, _ = self.update_auto_turn(
      v_ego_kph, sm, self.x_turn_info_next, float(self.x_dist_to_turn_next), False)
    if self.auto_turn_control not in (2, 3):
      atc_desired = atc_desired_next = 250.0
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

    # Vehicle CAN speed sources (speed camera / school zone / speed bump / section speed).
    vehicle_camera_speed = 250.0
    vehicle_bump_speed = 250.0
    vehicle_school_speed = 250.0
    vehicle_section_speed = 250.0
    vehicle_speed_camera_active = cs is not None and self._vehicle_speed_camera_enabled(cs)
    vehicle_bump_active = cs is not None and self._vehicle_speed_bump_enabled(cs)
    if cs is not None:
      speed_bump_distance = float(getattr(cs, "speedBumpDistance", 0.0) or 0.0)
      car_speed_limit = float(getattr(cs, "speedLimit", 0.0) or 0.0)

      if vehicle_speed_camera_active:
        vehicle_camera_speed = self.calculate_current_speed(
          getattr(cs, "speedLimitDistance", 0.0),
          car_speed_limit * self.auto_navi_speed_safety_factor,
          self.auto_navi_speed_ctrl_end,
          self.auto_navi_speed_decel_rate,
        )
      if vehicle_bump_active:
        vehicle_bump_speed = self.calculate_current_speed(
          speed_bump_distance, self.auto_navi_speed_bump_speed,
          self.auto_navi_speed_bump_time, self.auto_navi_speed_decel_rate,
        )
        self.active_carrot = 5

      vehicle_school_speed = self._vehicle_school_zone_speed(cs)
      if vehicle_school_speed < 250.0:
        self.active_carrot = 6
      if self._vehicle_section_zone_enabled(cs):
        vehicle_section_speed = float(getattr(cs, "vehicleNaviSpeed", 0.0) or 0.0) * self.auto_navi_speed_safety_factor
        self.active_carrot = 4

      # If no phone navi road limit is active, mirror the car's own speed limit.
      if car_speed_limit > 0.0 and self.n_road_limit_speed <= 0:
        self.n_road_limit_speed = int(car_speed_limit * 3.6 + 0.5)

    # Legacy phone SDI is suppressed when the vehicle CAN already reports the same hazard.
    legacy_sdi_active = (self.x_spd_limit > 0 and (self.x_spd_dist > 0 or self.x_spd_type in (100, 101)) and
                         self.active_carrot > 0 and
                         (self.x_spd_type != 22 or self._speed_bump_control_active(self.x_spd_dist)) and
                         not self._legacy_sdi_suppressed(self.x_spd_type, vehicle_speed_camera_active, vehicle_bump_active))
    if legacy_sdi_active:
      safe_sec = self.auto_navi_speed_bump_time if self.x_spd_type == 22 else self.auto_navi_speed_ctrl_end
      sdi_speed = min(sdi_speed, self.calculate_current_speed(self.x_spd_dist, self.x_spd_limit, safe_sec,
                                                              self.auto_navi_speed_decel_rate))
      self.active_carrot = 5 if self.x_spd_type == 22 else 3
      if self.x_spd_type == 4 or (self.x_spd_type in (100, 101) and self.x_spd_dist <= 0):
        sdi_speed = self.x_spd_limit
        self.active_carrot = 4

    speed_n_sources = [
      (atc_desired, "atc"),
      (atc_desired_next, "atc2"),
      (sdi_speed, "sdi"),
      (vehicle_camera_speed, "hda"),
      (vehicle_bump_speed, "hda_bump"),
      (vehicle_school_speed, "school"),
      (vehicle_section_speed, "hda_section"),
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

    if cs is not None:
      desired_speed, source = self._apply_speed_source_gas_floor(
        cs, desired_speed, source, v_ego_kph, road_speed_limit_changed,
      )

    self.desired_speed = int(desired_speed)
    self.desired_source = source

    # Countdowns.
    left_spd_sec = 100
    left_tbt_sec = 100
    speed_countdown_rearmed = False
    turn_countdown_rearmed = False
    if self.auto_navi_count_down_mode > 0:
      speed_countdown_distance = self._speed_countdown_distance(cs)
      left_spd_sec, self.speed_countdown_distance_last, speed_countdown_rearmed = self._countdown_channel(
        speed_countdown_distance, self.speed_countdown_distance_last, self.left_spd_sec, v_ego,
      )
      left_tbt_sec, self.turn_countdown_distance_last, turn_countdown_rearmed = self._countdown_channel(
        self.x_dist_to_turn, self.turn_countdown_distance_last, self.left_tbt_sec, v_ego,
      )
    else:
      self.speed_countdown_distance_last = 0.0
      self.turn_countdown_distance_last = 0.0

    self.left_spd_sec = left_spd_sec
    self.left_tbt_sec = left_tbt_sec

    left_sec = 100 if speed_countdown_rearmed or turn_countdown_rearmed else min(left_spd_sec, left_tbt_sec)
    self._update_countdown_alert(left_sec, source, v_ego_kph)

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
    """Apply Kisa (waze-like) crowdsourced data from the phone app.

    Accepts both JSON objects and the legacy ``key:value/key:value``
    string produced by older Kisa transmitters.
    """
    self.active_kisa_count = 100
    if "kisawazecurrentspd" in data:
      pass
    if "kisawazeroadspdlimit" in data:
      road_limit_speed = _safe_int(data["kisawazeroadspdlimit"], 0)
      if road_limit_speed > 0:
        if not self.is_metric:
          road_limit_speed = int(road_limit_speed * 1.609344)
        self.n_road_limit_speed = road_limit_speed
        self._raw["nRoadLimitSpeed"] = road_limit_speed
    if "kisawazealert" in data or "kisawazeendalert" in data:
      pass
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
        self.x_spd_limit = int((self.n_road_limit_speed + 5) * self.auto_navi_speed_safety_factor) if self.n_road_limit_speed > 0 else 0
        self.x_spd_dist = distance
        self.active_carrot = 2

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
