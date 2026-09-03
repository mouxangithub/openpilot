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
from collections import deque
from enum import IntEnum

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

    # Path tracking (used by callers that need curvature / bearing).
    self._path: deque[tuple[float, float]] = deque(maxlen=512)
    self._bearing: float = 0.0
    self._bearing_offset: float = 0.0

    # Traffic light history (2 seconds at 10 Hz).
    self._traffic_history: deque[int] = deque(maxlen=20)
    self._traffic_state: int = 0

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

    # --- Cruise advisory -------------------------------------------------
    n_road_limit = _safe_int(r.get("nRoadLimitSpeed"), 0)
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
