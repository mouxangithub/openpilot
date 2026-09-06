#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import math
import socket
import threading
from typing import Any

from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
import openpilot.cereal.messaging as messaging

from openpilot.sunnypilot.carrot.amap_navi import AmapNaviServ, parse_packet
from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
from openpilot.sunnypilot.carrot.carrot_serv import NAV_TYPE_MAPPING as TURN_TYPE_MAPPING
from openpilot.sunnypilot.carrot.config import UnifiedParams

try:
  from shapely.geometry import LineString
  SHAPELY_AVAILABLE = True
except ImportError:
  SHAPELY_AVAILABLE = False


DEFAULT_RATE = 10.  # Hz
UDP_BUFFER_SIZE = 4096
PACKET_TIMEOUT_SEC = 3.0
AMAP_UDP_PORT_DEFAULT = 0  # 0 == disabled (must be enabled by user)

# Korean TMAP turn-type codes from the CarrotMan app -> (maneuverType, maneuverModifier, xTurnInfo).
# xTurnInfo semantics used by the sunnypilot UI/planner:
#   1=left turn, 2=right turn, 3=left lane change, 4=right lane change,
#   5=rotary, 6=tg, 7=arrive/uturn, 8=straight/arrive.
# (Table lives in carrot_serv as NAV_TYPE_MAPPING; aliased here for the
#  historical TURN_TYPE_MAPPING name used by _turn_info and the tests.)

# Curve-speed lookup table (reciprocal radius [1/m] -> km/h).
# Used when the phone navi sends a curvature-aware speed advisory.
V_CURVE_LOOKUP_BP: tuple[float, ...] = (
  0.0, 1 / 800, 1 / 670, 1 / 560, 1 / 440, 1 / 360, 1 / 265, 1 / 190, 1 / 135,
  1 / 85, 1 / 55, 1 / 30, 1 / 25,
)
V_CRUVE_LOOKUP_VALS: tuple[float, ...] = (300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5)

# Approximate curve-speed model: given a turn type and distance, recommend an
# approach speed.  This is a simplified stand-in for the full polynomial model
# in the reference implementation and is intentionally conservative.
TURN_SPEED_TABLE: dict[int, list[tuple[float, float]]] = {
  1: [(200.0, 60.0), (100.0, 45.0), (50.0, 30.0), (0.0, 20.0)],
  2: [(200.0, 60.0), (100.0, 45.0), (50.0, 30.0), (0.0, 20.0)],
  3: [(200.0, 70.0), (100.0, 55.0), (50.0, 40.0), (0.0, 30.0)],
  4: [(200.0, 70.0), (100.0, 55.0), (50.0, 40.0), (0.0, 30.0)],
  5: [(300.0, 45.0), (150.0, 35.0), (75.0, 25.0), (0.0, 15.0)],
  6: [(200.0, 60.0), (100.0, 45.0), (50.0, 30.0), (0.0, 20.0)],
  7: [(100.0, 30.0), (0.0, 20.0)],
  8: [(100.0, 80.0), (0.0, 80.0)],
}


def _interpolate_speed(distance_m: float, table: list[tuple[float, float]]) -> float:
  """Piecewise linear interpolation from (distance, speed) table."""
  if not table:
    return 0.0
  if distance_m >= table[0][0]:
    return table[0][1]
  if distance_m <= table[-1][0]:
    return table[-1][1]
  for i in range(len(table) - 1):
    d0, s0 = table[i]
    d1, s1 = table[i + 1]
    if d1 <= distance_m <= d0:
      ratio = (distance_m - d1) / max(1.0, d0 - d1)
      return s1 + ratio * (s0 - s1)
  return table[-1][1]


def _safe_int(value, default: int = 0) -> int:
  if isinstance(value, bool):
    return int(value)
  if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
    return int(value)
  return default


def _safe_float(value, default: float = 0.0) -> float:
  if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
    return float(value)
  return default


def _safe_str(value, default: str = "") -> str:
  return default if value is None else str(value)


def _turn_info(turn_type: int) -> tuple[str, str, int]:
  return TURN_TYPE_MAPPING.get(turn_type, ("invalid", "", -1))


# --------------------------------------------------------------------------- #
# Navigation path helpers (ported from CarrotPilot)                            #
# --------------------------------------------------------------------------- #


def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
  """Calculate distance between two GPS coordinates in meters."""
  r = 6371000.0
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlambda = math.radians(lon2 - lon1)

  a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
  return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def closest_point_on_segment(p1: tuple[float, float], p2: tuple[float, float], current_position: tuple[float, float]) -> tuple[float, float]:
  """Get the closest point on a segment between two coordinates."""
  x1, y1 = p1
  x2, y2 = p2
  px, py = current_position

  dx = x2 - x1
  dy = y2 - y1
  if dx == 0 and dy == 0:
    return p1

  t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
  t = max(0, min(1, t))

  closest_x = x1 + t * dx
  closest_y = y1 + t * dy

  return (closest_x, closest_y)


def get_path_after_distance(start_index: int,
                            coordinates: list[tuple[float, float]],
                            current_position: tuple[float, float],
                            distance_m: float) -> tuple[list[tuple[float, float]], int, tuple[float, float] | None]:
  """Get path after a certain distance from the current position."""
  total_distance = 0
  path_after_distance: list[tuple[float, float]] = []
  closest_index = -1
  closest_point: tuple[float, float] | None = None
  min_distance = float('inf')

  start_index = max(0, start_index - 2)

  for i in range(start_index, len(coordinates) - 1):
    p1 = coordinates[i]
    p2 = coordinates[i + 1]
    candidate_point = closest_point_on_segment(p1, p2, current_position)
    distance = haversine(current_position[0], current_position[1], candidate_point[0], candidate_point[1])

    if distance < min_distance:
      min_distance = distance
      closest_point = candidate_point
      closest_index = i
    elif distance > min_distance and min_distance < 10:
      break

  start_index = closest_index
  if closest_index != -1:
    path_after_distance.append(closest_point)
    path_after_distance.append(coordinates[closest_index + 1])
    total_distance = haversine(closest_point[0], closest_point[1], coordinates[closest_index + 1][0], coordinates[closest_index + 1][1])

    for i in range(closest_index + 1, len(coordinates) - 1):
      coord1 = coordinates[i]
      coord2 = coordinates[i + 1]
      segment_distance = haversine(coord1[0], coord1[1], coord2[0], coord2[1])

      if total_distance + segment_distance >= distance_m and segment_distance > 0:
        remaining_distance = distance_m - total_distance
        ratio = remaining_distance / segment_distance
        interpolated_lon = coord1[0] + ratio * (coord2[0] - coord1[0])
        interpolated_lat = coord1[1] + ratio * (coord2[1] - coord1[1])
        path_after_distance.append((interpolated_lon, interpolated_lat))
        break

      total_distance += segment_distance
      path_after_distance.append(coord2)

  return path_after_distance, start_index, closest_point


def gps_to_relative_xy(gps_path: list[tuple[float, float]], reference_point: tuple[float, float], heading_deg: float) -> list[tuple[float, float]]:
  """Convert GPS coordinates to relative x, y coordinates based on a reference point and heading."""
  ref_lon, ref_lat = reference_point
  relative_coordinates: list[tuple[float, float]] = []

  heading_rad = math.radians(heading_deg)

  for lon, lat in gps_path:
    x = (lon - ref_lon) * 40008000 * math.cos(math.radians(ref_lat)) / 360
    y = (lat - ref_lat) * 40008000 / 360

    x_rot = x * math.cos(heading_rad) - y * math.sin(heading_rad)
    y_rot = x * math.sin(heading_rad) + y * math.cos(heading_rad)

    relative_coordinates.append((y_rot, x_rot))

  return relative_coordinates


def calculate_curvature(p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float]) -> float:
  """Calculate curvature given three points using a faster vector-based method."""
  v1 = (p2[0] - p1[0], p2[1] - p1[1])
  v2 = (p3[0] - p2[0], p3[1] - p2[1])

  cross_product = v1[0] * v2[1] - v1[1] * v2[0]
  len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
  len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

  if len_v1 * len_v2 == 0:
    return 0.0

  return cross_product / (len_v1 * len_v2 * len_v1)


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


class CarrotManager:
  """Receive navigation/ADAS data from the CarrotMan phone app over UDP and
  publish ``carrotManSP`` + ``navInstructionCarrotSP`` + ``amapNaviSP``.

  The daemon also subscribes to ``carState`` / ``modelV2`` so it can compute
  curve-speed advisories; the stock ``navInstruction``/``navRoute`` services
  are not present in this fork (no navd), so all guidance comes from the
  CarrotMan phone app.

  Sub-modules wired in:
    * :class:`CarrotServ` - SDI / TBT / ATC derivation + cruise advisory
    * :class:`AmapNaviServ` - 4-corner radar + amap blind spot bridge
    * :class:`WebInterface` - optional HTTP control plane (lazy started)

  Wire format (UTF-8 JSON, UDP):

  - ``nRoadLimitSpeed`` (int): current road speed limit in kph.
  - ``nSdiType``/``nSdiSpeedLimit``/``nSdiDist`` (int): safety-device info.
  - ``nSdiBlockType``/``nSdiBlockSpeed``/``nSdiBlockDist`` (int): section speed.
  - ``nSdiPlusType``/``nSdiPlusSpeedLimit``/``nSdiPlusDist`` (int): secondary SDI.
  - ``nTBTDist``/``nTBTTurnType``/``szTBTMainText``: current turn guidance.
  - ``nTBTDistNext``/``nTBTTurnTypeNext``/``szTBTMainTextNext``: next guidance.
  - ``nGoPosDist``/``nGoPosTime``: route remaining distance/time.
  - ``szPosRoadName``: current road name.
  - ``vpPosPointLat``/``vpPosPointLon``/``nPosAngle``/``nPosSpeed``: phone GPS.
  - ``carrotCmd``/``carrotArg``/``carrotIndex``: remote commands.
  - ``roadcate``: road category.

  A second UDP socket (``AmapNaviUdpPort``, default 0 = disabled) receives
  Amap ADAS JSON packets (``lineValid``/``leftLine``/``rightLine``) and feeds
  them to :meth:`AmapNaviServ.update_adas`; that socket is the sole lane-line
  data source for ``amapNaviSP`` now that the mapd_amap producer is disabled.

  Unknown fields are ignored so the protocol remains forward-compatible.
  """

  def __init__(self):
    self.params = Params()
    self._unified = UnifiedParams()
    self.sm = messaging.SubMaster(['deviceState', 'carState', 'controlsState', 'modelV2'])
    self.pm = messaging.PubMaster(['carrotManSP', 'navInstructionCarrotSP', 'amapNaviSP'])

    # Sub-modules.
    self._carrot_serv = CarrotServ(self._unified)
    self._amap_navi = AmapNaviServ()
    self._web: Any = None  # Lazy import: only used when ``--web`` flag is set.

    self._enabled = False
    self._port = 0
    self._amap_port = AMAP_UDP_PORT_DEFAULT
    self._start_web = False

    self._sock: socket.socket | None = None
    self._amap_sock: socket.socket | None = None  # Amap ADAS JSON listener (AmapNaviUdpPort)
    self._lock = threading.Lock()
    self._last_packet_mono = 0.0
    self._last_seq: int | None = None
    self._remote_addr: str = ""

    # Navigation path state (P0-1)
    self._navi_points: list[tuple[float, float]] = []
    self._navi_points_start_index = 0
    self._navi_points_active = False
    self._navd_active = False
    self._active_carrot_last = 0

    # Broadcast state (P1-1)
    self._broadcast_ip: str | None = None
    self._broadcast_port = 7705
    self._carrot_man_port = 7706
    self._port_advertise_warned = False  # one-shot legacy-port warning
    self._ip_address = "0.0.0.0"
    self._is_running = False
    self._broadcast_thread: threading.Thread | None = None

    # ZMQ remote command state (P1-2)
    self._zmq_thread: threading.Thread | None = None
    self._zmq_running = False
    self._is_onroad_count = 0
    self._is_tmux_sent = False
    self._show_panda_debug = False

    # Navigation route state (P2-1)
    self._route_thread: threading.Thread | None = None
    self._route_running = False
    self._route_port = 7709

    # Panda debug state (P3-1)
    self._panda_debug_thread: threading.Thread | None = None
    self._panda_debug_running = False

    # Kisa app state (P3-2)
    self._kisa_thread: threading.Thread | None = None
    self._kisa_running = False
    self._kisa_port = 12345

  # ---- socket plumbing -------------------------------------------------- #

  def _ensure_socket(self, port: int) -> bool:
    with self._lock:
      if self._sock is not None and self._port == port:
        return True
      if self._sock is not None:
        try:
          self._sock.close()
        except Exception:
          pass
        self._sock = None
      try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', port))
        sock.setblocking(False)
        self._sock = sock
        self._port = port
        cloudlog.info(f"carrot_man: listening on UDP port {port}")
        return True
      except Exception as e:
        cloudlog.error(f"carrot_man: failed to bind UDP port {port}: {e}")
        self._sock = None
        return False

  def _close_socket(self) -> None:
    with self._lock:
      if self._sock is not None:
        try:
          self._sock.close()
        except Exception:
          pass
        self._sock = None
        self._port = 0

  def _ensure_amap_socket(self, port: int) -> bool:
    """Bind the second UDP socket for Amap ADAS lane-line JSON packets.

    This replaces the retired mapd_amap producer's listener: carrot_man is
    now the single process owning BOTH data sources, so ``amapNaviSP`` has
    exactly one publisher.  Port 0 keeps the listener disabled (default).
    """
    with self._lock:
      if self._amap_sock is not None and self._amap_port == port:
        return True
      if self._amap_sock is not None:
        try:
          self._amap_sock.close()
        except Exception:
          pass
        self._amap_sock = None
    if port <= 0:
      return False
    try:
      sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      sock.bind(('0.0.0.0', port))
      sock.setblocking(False)
      with self._lock:
        self._amap_sock = sock
        self._amap_port = port
      cloudlog.info(f"carrot_man: ADAS listener on UDP port {port}")
      return True
    except Exception as e:
      cloudlog.error(f"carrot_man: failed to bind ADAS UDP port {port}: {e}")
      return False

  def _close_amap_socket(self) -> None:
    with self._lock:
      if self._amap_sock is not None:
        try:
          self._amap_sock.close()
        except Exception:
          pass
        self._amap_sock = None
      self._amap_port = 0

  def _parse_packet(self, data: bytes) -> dict[str, Any] | None:
    return parse_packet(data)

  # ---- ingestion -------------------------------------------------------- #

  def _update_raw(self, msg: dict[str, Any], recv_mono: float) -> None:
    seq = _safe_int(msg.get('carrotIndex'), -1)
    if seq >= 0 and self._last_seq is not None and seq < self._last_seq:
      return
    self._last_seq = seq

    if 'carrotCmd' in msg:
      cloudlog.info(
        f"carrot_man: remote cmd={msg.get('carrotCmd')} arg={msg.get('carrotArg')}",
      )

    # Fan out to the dedicated service modules.  Each module does its own
    # field validation / fall-back to defaults.
    #
    # NOTE: CarrotMan's own UDP stream (CarrotManUdpPort) uses the closed
    # CarrotMan protocol and never carries Amap ADAS lane-line keys
    # (lineValid/leftLine/rightLine). Those arrive on a SEPARATE socket
    # (AmapNaviUdpPort) drained by _drain_adas_packets() below.
    self._carrot_serv.update_raw(msg, recv_mono=recv_mono)
    self._amap_navi.apply_packet(msg, recv_mono=recv_mono)

  def _drain_packets(self) -> None:
    with self._lock:
      if self._sock is None:
        return
    while True:
      try:
        with self._lock:
          if self._sock is None:
            break
          data, addr = self._sock.recvfrom(UDP_BUFFER_SIZE)
        msg = self._parse_packet(data)
        if msg is not None:
          self._remote_addr = f"{addr[0]}:{addr[1]}" if addr else ""
          self._update_raw(msg, self._mono_now())
      except BlockingIOError:
        break
      except Exception as e:
        cloudlog.error(f"carrot_man: UDP receive error: {e}")
        break

  def _drain_adas_packets(self) -> None:
    """Drain the Amap ADAS JSON socket (AmapNaviUdpPort) into update_adas().

    Wire format: UTF-8 JSON dicts with lineValid/leftLine/rightLine keys
    (same layout mapd_amap used to parse).  update_adas() owns validation,
    clamping and the 3 s freshness fail-safe, so malformed packets are
    dropped here without touching blind-spot state.
    """
    with self._lock:
      sock = self._amap_sock
    if sock is None:
      return
    while True:
      try:
        with self._lock:
          if self._amap_sock is None:
            break
          data, _addr = self._amap_sock.recvfrom(UDP_BUFFER_SIZE)
        msg = self._parse_packet(data)
        if msg is not None:
          self._amap_navi.update_adas(msg)
      except BlockingIOError:
        break
      except Exception as e:
        cloudlog.error(f"carrot_man: ADAS UDP receive error: {e}")
        break

  def _maybe_expire_state(self, now_mono: float) -> None:
    if self._carrot_serv.is_stale(now_mono, PACKET_TIMEOUT_SEC):
      self._carrot_serv.reset()
    if self._amap_navi.is_stale(now_mono, PACKET_TIMEOUT_SEC):
      self._amap_navi.reset()

  def _reset_state(self) -> None:
    self._carrot_serv.reset()
    self._amap_navi.reset()
    self._last_packet_mono = 0.0
    self._last_seq = None
    self._remote_addr = ""
    self._navi_points = []
    self._navi_points_active = False
    self._navd_active = False
    self._active_carrot_last = 0

  # ---- navigation path (P0-1) -------------------------------------------- #

  def carrot_navi_route(self) -> tuple[list[tuple[float, float]], list[float], float]:
    """Calculate navigation route with curvature-aware speed limits.

    Returns:
      (resampled_points, resampled_distances, out_speed)
    """
    # Check if navi is active
    if not self._navi_points_active or not SHAPELY_AVAILABLE:
      if self._navi_points_active:
        self._navi_points = []
        self._navi_points_active = False
      self._active_carrot_last = self._carrot_serv.active_carrot
      return [], [], 300.0

    if self._carrot_serv.active_carrot <= 1 and not self._navd_active:
      if self._navi_points_active:
        self._navi_points = []
        self._navi_points_active = False
      self._active_carrot_last = self._carrot_serv.active_carrot
      return [], [], 300.0

    current_position = (self._carrot_serv.vp_pos_point_lon, self._carrot_serv.vp_pos_point_lat)
    heading_deg = self._carrot_serv.bearing

    distance_interval = 10.0
    out_speed = 300.0

    path, self._navi_points_start_index, start_point = get_path_after_distance(
      self._navi_points_start_index, self._navi_points, current_position, 300.0
    )
    relative_coords: list[tuple[float, float]] = []

    if path:
      relative_coords = gps_to_relative_xy(path, start_point, heading_deg)

      # Resample relative_coords at 10m intervals using LineString
      line = LineString(relative_coords)
      resampled_points: list[tuple[float, float]] = []
      resampled_distances: list[float] = []
      current_distance = 0.0
      while current_distance <= line.length:
        point = line.interpolate(current_distance)
        resampled_points.append((point.x, point.y))
        resampled_distances.append(current_distance)
        current_distance += distance_interval

      curvatures: list[float] = []
      distances: list[float] = []
      distance = 10.0
      sample = 4

      if len(resampled_points) >= sample * 2 + 1:
        speeds: list[float] = []
        for i in range(len(resampled_points) - sample * 2):
          distance += distance_interval
          p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
          curvature = calculate_curvature(p1, p2, p3)
          curvatures.append(curvature)
          speed = _interp_table(abs(curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
          if abs(curvature) < 0.02:
            speed = max(speed, self._carrot_serv.n_road_limit_speed)
          speeds.append(speed)
          distances.append(distance)

        # Apply acceleration limits in reverse to adjust speeds
        accel_limit = self._carrot_serv.auto_navi_speed_decel_rate  # m/s^2
        accel_limit_kmh = accel_limit * 3.6  # Convert to km/h per second
        out_speeds = [0.0] * len(speeds)
        out_speeds[-1] = speeds[-1]
        v_ego_kph = self.sm['carState'].vEgo * 3.6 if self.sm.alive['carState'] else 0.0

        time_delay = self._carrot_serv.auto_navi_speed_ctrl_end
        time_wait = 0.0
        for i in range(len(speeds) - 2, -1, -1):
          target_speed = speeds[i]
          next_out_speed = out_speeds[i + 1]

          if target_speed < next_out_speed:
            time_delay = max(0.0, ((v_ego_kph - target_speed) / accel_limit_kmh))
            time_wait = -time_delay

          time_interval = distance_interval / (next_out_speed / 3.6) if next_out_speed > 0 else 0.0
          time_apply = min(time_interval, max(0.0, time_interval + time_wait))
          max_allowed_speed = next_out_speed + (accel_limit_kmh * time_apply)
          adjusted_speed = min(target_speed, max_allowed_speed)

          time_wait += min(2.0, time_interval)
          out_speeds[i] = adjusted_speed

        out_speed = out_speeds[0]
      else:
        resampled_points = []
        resampled_distances = []

      return resampled_points, resampled_distances, out_speed

    return [], [], 300.0

  # ---- publishing ------------------------------------------------------- #

  def _derive_state(self, v_ego_kph: float) -> None:
    self._carrot_serv.derive(v_ego_kph=v_ego_kph)

  def _publish(self) -> None:
    nav_type = self._carrot_serv.nav_type
    nav_modifier = self._carrot_serv.nav_modifier
    x_turn_info = self._carrot_serv.x_turn_info
    x_dist_to_turn = self._carrot_serv.x_dist_to_turn
    nav_type_next = self._carrot_serv.nav_type_next
    nav_modifier_next = self._carrot_serv.nav_modifier_next
    x_turn_info_next = self._carrot_serv.x_turn_info_next
    x_dist_to_turn_next = self._carrot_serv.x_dist_to_turn_next
    x_spd_type = self._carrot_serv.x_spd_type
    x_spd_limit = self._carrot_serv.x_spd_limit
    x_spd_dist = self._carrot_serv.x_spd_dist
    v_turn_speed = self._carrot_serv.v_turn_speed
    sz_sdi_descr = self._carrot_serv.sz_sdi_descr
    desired_speed = self._carrot_serv.desired_speed
    desired_source = self._carrot_serv.desired_source
    active_carrot = self._carrot_serv.active_carrot
    atc_type = self._carrot_serv.atc_type
    roadcate = self._carrot_serv.roadcate
    raw = self._carrot_serv.raw

    carrot_msg = messaging.new_message('carrotManSP')
    carrot_msg.valid = True
    cm = carrot_msg.carrotManSP
    cm.activeCarrot = active_carrot
    cm.nRoadLimitSpeed = _safe_int(raw.get("nRoadLimitSpeed"), 0)
    cm.remote = self._remote_addr
    cm.xSpdType = x_spd_type
    cm.xSpdLimit = x_spd_limit
    cm.xSpdDist = x_spd_dist
    cm.xSpdCountDown = 0
    cm.xTurnInfo = x_turn_info
    cm.xDistToTurn = x_dist_to_turn
    cm.xTurnCountDown = 0
    cm.atcType = atc_type
    cm.vTurnSpeed = v_turn_speed
    cm.szPosRoadName = _safe_str(raw.get("szPosRoadName"), "")
    cm.szTBTMainText = _safe_str(raw.get("szTBTMainText"), "")
    cm.desiredSpeed = desired_speed
    cm.desiredSource = desired_source
    cm.carrotCmdIndex = _safe_int(raw.get("carrotCmdIndex"), 0)
    cm.carrotCmd = _safe_str(raw.get("carrotCmd"), "")
    cm.carrotArg = _safe_str(raw.get("carrotArg"), "")
    cm.xPosLat = _safe_float(raw.get("vpPosPointLat"), 0.0)
    cm.xPosLon = _safe_float(raw.get("vpPosPointLon"), 0.0)
    cm.xPosAngle = _safe_float(raw.get("nPosAngle"), 0.0)
    cm.xPosSpeed = _safe_float(raw.get("nPosSpeed"), 0.0)
    cm.trafficState = 0
    cm.nGoPosDist = _safe_int(raw.get("nGoPosDist"), 0)
    cm.nGoPosTime = _safe_int(raw.get("nGoPosTime"), 0)
    cm.szSdiDescr = sz_sdi_descr
    cm.naviPaths = ""
    cm.leftSec = 0
    cm.xDistToTurnNav = x_dist_to_turn
    cm.xDistToTurnNavLast = x_dist_to_turn_next
    cm.xDistToTurnMax = x_dist_to_turn
    cm.xDistToTurnMaxCnt = 0
    cm.xLeftTurnSec = 0
    cm.roadCate = roadcate
    cm.extBlinker = int(self._amap_navi.shared_data.ext_blinker)
    cm.extState = int(self._amap_navi.shared_data.ext_state)
    cm.leftBlind = 1 if self._amap_navi.shared_data.left_blind else 0
    cm.rightBlind = 1 if self._amap_navi.shared_data.right_blind else 0
    cm.trafficCountdown = 0
    cm.szGoalName = ""
    cm.szTBTMainTextNext = _safe_str(raw.get("szTBTMainTextNext"), "")
    cm.szNearDirName = _safe_str(raw.get("szNearDirName"), "")

    navi_msg = messaging.new_message('navInstructionCarrotSP')
    navi_msg.valid = True
    ni = navi_msg.navInstructionCarrotSP
    ni.maneuverPrimaryText = _safe_str(raw.get("szTBTMainText"), "")
    ni.maneuverSecondaryText = ""
    ni.maneuverDistance = float(x_dist_to_turn)
    ni.maneuverType = nav_type
    ni.maneuverModifier = nav_modifier
    n_road_limit = _safe_int(raw.get("nRoadLimitSpeed"), 0)
    ni.distanceRemaining = float(_safe_int(raw.get("nGoPosDist"), 0))
    ni.timeRemaining = float(_safe_int(raw.get("nGoPosTime"), 0))
    ni.timeRemainingTypical = float(_safe_int(raw.get("nGoPosTime"), 0))
    ni.speedLimit = float(n_road_limit / 3.6) if n_road_limit > 0 else 0.0

    if x_turn_info > 0:
      m0 = ni.allManeuvers.add()
      m0.distance = float(x_dist_to_turn)
      m0.type = nav_type
      m0.modifier = nav_modifier
    if x_turn_info_next > 0:
      m1 = ni.allManeuvers.add()
      m1.distance = float(x_dist_to_turn_next)
      m1.type = nav_type_next
      m1.modifier = nav_modifier_next

    amap_msg = self._amap_navi.build_amap_navi_msg(messaging.new_message)

    self.pm.send('carrotManSP', carrot_msg)
    self.pm.send('navInstructionCarrotSP', navi_msg)
    self.pm.send('amapNaviSP', amap_msg)

  # ---- web interface ---------------------------------------------------- #

  def _maybe_start_web(self) -> None:
    """Spin up the HTTP control plane if the user enabled it."""
    if not self._start_web or self._web is not None:
      return
    try:
      from openpilot.sunnypilot.carrot.web_interface import WebInterface
    except ImportError as exc:
      cloudlog.warning(f"carrot_man: web interface unavailable: {exc}")
      return
    self._web = WebInterface(self._amap_navi, params=self._unified)
    self._web.start()

  def _stop_web(self) -> None:
    if self._web is None:
      return
    try:
      self._web.stop()
    except Exception:
      pass
    self._web = None

  # ---- broadcast (P1-1) ------------------------------------------------- #

  def get_broadcast_address(self) -> str | None:
    """Get broadcast address for UDP broadcast."""
    try:
      # Try common network interfaces
      interfaces = ['wlan0', 'eth0', 'enp0s3', 'br0', 'wlp2s0']
      for iface in interfaces:
        try:
          with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Use SIOCGIFBRDADDR ioctl to get broadcast address
            import fcntl
            import struct
            ip = fcntl.ioctl(
              s.fileno(),
              0x8919,  # SIOCGIFBRDADDR
              struct.pack('256s', iface.encode('utf-8')[:15])
            )[20:24]
            return socket.inet_ntoa(ip)
        except Exception:
          continue
      return "255.255.255.255"  # Fallback address
    except Exception:
      return None

  def get_local_ip(self) -> str:
    """Get local IP address by connecting to external server."""
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # Google DNS
        return s.getsockname()[0]
    except Exception:
      return "0.0.0.0"

  def broadcast_version_info(self) -> None:
    """Broadcast version info to phone app via UDP."""
    if not self._is_running:
      return

    try:
      sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

      frame = 0
      while self._is_running:
        try:
          self.sm.update(0)

          # Update amap navi carstate
          if self.sm.alive['carState']:
            self._amap_navi.update_navi_carstate(self.sm)

          # Get remote address
          remote_addr = self._remote_addr
          remote_ip = remote_addr.split(':')[0] if remote_addr else ""

          # Calculate curve speed
          vturn_speed = 0.0
          if self.sm.alive['carState'] and self.sm.alive['modelV2']:
            try:
              from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
              planner = CarrotPlanner(self._unified)
              vturn_speed = planner.carrot_curve_speed(self.sm)
            except Exception:
              pass

          # Calculate navigation route
          coords, distances, route_speed = self.carrot_navi_route()

          # Update navi
          self._carrot_serv.update_navi(remote_ip, self.sm, self.pm, vturn_speed, coords, distances, route_speed)

          # Broadcast every 2 seconds or when remote addr is set
          if frame % 20 == 0 or remote_addr:
            try:
              self._broadcast_ip = self.get_broadcast_address() if not remote_addr else remote_ip
              if not self._broadcast_ip:
                self._broadcast_ip = "255.255.255.255"

              # Get local IP
              ip_address = self.get_local_ip()
              if ip_address != self._ip_address:
                self._ip_address = ip_address
                self._remote_addr = ""

              # Build and send message
              msg = self.make_send_message()
              if self._broadcast_ip:
                data = msg.encode('utf-8')
                sock.sendto(data, (self._broadcast_ip, self._broadcast_port))
            except Exception as e:
              cloudlog.error(f"carrot_man: broadcast error: {e}")

          frame += 1
          import time
          time.sleep(0.1)
        except Exception as e:
          cloudlog.error(f"carrot_man: broadcast loop error: {e}")
          import time
          time.sleep(1)
    except Exception as e:
      cloudlog.error(f"carrot_man: broadcast thread error: {e}")

  def make_send_message(self) -> str:
    """Build broadcast message for phone app."""
    import json

    msg = {}
    msg['Carrot2'] = self.params.get("Version", b'').decode() if isinstance(self.params.get("Version"), bytes) else (self.params.get("Version") or '')
    msg['IsOnroad'] = self.params.get_bool("IsOnroad")
    msg['CarrotRouteActive'] = self._navi_points_active
    msg['ip'] = self._ip_address
    # Advertise the port we actually listen on (CarrotManUdpPort).  The
    # broadcast thread only runs while that listener is bound; keep the
    # legacy hard-coded port as a defensive fallback and warn once if used.
    if self._port > 0:
      msg['port'] = self._port
    else:
      msg['port'] = self._carrot_man_port
      if not self._port_advertise_warned:
        self._port_advertise_warned = True
        cloudlog.warning(
          f"carrot_man: CarrotManUdpPort listener not bound; "
          f"advertising legacy port {self._carrot_man_port}"
        )

    v_ego_kph = 0
    v_cruise_kph = 0
    log_carrot = ""
    if self.sm.alive['carState']:
      carState = self.sm['carState']
      v_ego_kph = int(carState.vEgoCluster * 3.6 + 0.5)
      v_cruise_kph = carState.vCruise
      log_carrot = getattr(carState, 'logCarrot', '')

    msg['v_ego_kph'] = v_ego_kph
    msg['v_cruise_kph'] = v_cruise_kph
    msg['log_carrot'] = log_carrot
    msg['tbt_dist'] = self._carrot_serv.x_dist_to_turn
    msg['sdi_dist'] = self._carrot_serv.x_spd_dist
    msg['nRoadLimitSpeed'] = self._carrot_serv.n_road_limit_speed
    msg['vTurnSpeed'] = self._carrot_serv.v_turn_speed
    msg['trafficState'] = self._carrot_serv.traffic_state
    msg['xState'] = 0

    return json.dumps(msg, ensure_ascii=False)

  # ---- main loop -------------------------------------------------------- #

  def _mono_now(self) -> float:
    import time as _time
    return _time.monotonic()

  def tick(self) -> None:
    self._enabled = self.params.get_bool("CarrotEnabled")
    self._port = self.params.get("CarrotManUdpPort", return_default=True) or 0
    self._amap_port = self.params.get("AmapNaviUdpPort", return_default=True) or 0
    self._start_web = self.params.get_bool("CarrotWebEnabled")

    self.sm.update(0)

    if not self._enabled or self._port <= 0:
      self._close_socket()
      self._close_amap_socket()
      self._reset_state()
      self._stop_web()
      self._is_running = False
      return

    if not self._ensure_socket(self._port):
      return

    # Second listener for Amap ADAS lane-line JSON (single-producer model:
    # carrot_man owns both data sources; mapd_amap stays disabled).
    if self._amap_port > 0:
      self._ensure_amap_socket(self._amap_port)
    else:
      self._close_amap_socket()

    self._maybe_start_web()
    self._drain_packets()
    self._drain_adas_packets()
    now = self._mono_now()
    self._maybe_expire_state(now)

    v_ego_kph = 0.0
    if self.sm.alive['carState']:
      v_ego_kph = self.sm['carState'].vEgo * 3.6

    self._derive_state(v_ego_kph)
    self._publish()

    # Start broadcast thread if not running (P1-1)
    if not self._is_running:
      self._is_running = True
      if self._broadcast_thread is None or not self._broadcast_thread.is_alive():
        self._broadcast_thread = threading.Thread(
          target=self.broadcast_version_info,
          name="carrot-broadcast",
          daemon=True,
        )
        self._broadcast_thread.start()
        cloudlog.info("carrot_man: broadcast thread started")

    # Start ZMQ thread if not running (P1-2)
    if not self._zmq_running:
      self._zmq_running = True
      if self._zmq_thread is None or not self._zmq_thread.is_alive():
        self._zmq_thread = threading.Thread(
          target=self.carrot_cmd_zmq,
          name="carrot-zmq",
          daemon=True,
        )
        self._zmq_thread.start()
        cloudlog.info("carrot_man: ZMQ thread started")

    # Start route thread if not running (P2-1)
    if not self._route_running:
      self._route_running = True
      if self._route_thread is None or not self._route_thread.is_alive():
        self._route_thread = threading.Thread(
          target=self.carrot_route,
          name="carrot-route",
          daemon=True,
        )
        self._route_thread.start()
        cloudlog.info("carrot_man: route thread started")

    # Start panda debug thread if not running (P3-1)
    if not self._panda_debug_running:
      self._panda_debug_running = True
      if self._panda_debug_thread is None or not self._panda_debug_thread.is_alive():
        self._panda_debug_thread = threading.Thread(
          target=self.carrot_panda_debug,
          name="carrot-panda-debug",
          daemon=True,
        )
        self._panda_debug_thread.start()
        cloudlog.info("carrot_man: panda debug thread started")

    # Start kisa thread if not running (P3-2)
    if not self._kisa_running:
      self._kisa_running = True
      if self._kisa_thread is None or not self._kisa_thread.is_alive():
        self._kisa_thread = threading.Thread(
          target=self.kisa_app_thread,
          name="carrot-kisa",
          daemon=True,
        )
        self._kisa_thread.start()
        cloudlog.info("carrot_man: kisa thread started")

  # ---- ZMQ remote command (P1-2) ---------------------------------------- #

  def carrot_cmd_zmq(self) -> None:
    """ZMQ remote command handler for phone app."""
    import json
    import subprocess
    import time

    try:
      import zmq
    except ImportError:
      cloudlog.warning("carrot_man: zmq not available, remote command disabled")
      return

    context = zmq.Context()

    def setup_socket():
      socket = context.socket(zmq.REP)
      socket.bind("tcp://*:7710")
      poller = zmq.Poller()
      poller.register(socket, zmq.POLLIN)
      return socket, poller

    socket, poller = setup_socket()
    cloudlog.info("carrot_man: ZMQ remote command handler started on port 7710")

    while self._zmq_running:
      try:
        socks = dict(poller.poll(100))

        if socket in socks and socks[socket] == zmq.POLLIN:
          message = socket.recv(zmq.NOBLOCK)
          cloudlog.info(f"carrot_man: ZMQ received: {message}")
          try:
            json_obj = json.loads(message.decode())
          except json.JSONDecodeError:
            json_obj = None
        else:
          json_obj = None

        if json_obj is None:
          # No message - check onroad status and send tmux if needed
          is_onroad = self.params.get_bool("IsOnroad")
          self._is_onroad_count = self._is_onroad_count + 1 if is_onroad else 0

          if self._is_onroad_count == 0:
            self._is_tmux_sent = False
          if self._is_onroad_count == 1:
            self._show_panda_debug = True

          # Check network connection
          network_connected = False
          if self.sm.alive['deviceState']:
            network_type = self.sm['deviceState'].networkType
            network_connected = network_type != 0  # NetworkType.none

          # Send tmux data after 50 seconds onroad
          if self._is_onroad_count == 500:
            self.make_tmux_data()

          if self._is_onroad_count > 500 and not self._is_tmux_sent and network_connected:
            self.send_tmux("Ekdrmsvkdlffjt7710", "onroad", send_settings=True)
            self._is_tmux_sent = True

          # Send exception if CarrotException is set
          if self.params.get_bool("CarrotException") and network_connected:
            self.params.put_bool("CarrotException", False)
            self.make_tmux_data()
            self.send_tmux("Ekdrmsvkdlffjt7710", "exception")

        elif 'echo_cmd' in json_obj:
          # Execute remote command
          try:
            result = subprocess.run(
              json_obj['echo_cmd'],
              shell=True,
              capture_output=True,
              text=False,
              timeout=30,
            )
            exit_status = result.returncode
            try:
              stdout = result.stdout.decode('utf-8')
              stderr = result.stderr.decode('utf-8')
            except UnicodeDecodeError:
              stdout = result.stdout.decode('euc-kr', 'ignore')
              stderr = result.stderr.decode('euc-kr', 'ignore')

            echo = json.dumps({
              "echo_cmd": json_obj['echo_cmd'],
              "exitStatus": exit_status,
              "result": stdout,
              "error": stderr,
            }, ensure_ascii=False)
          except Exception as e:
            echo = json.dumps({
              "echo_cmd": json_obj['echo_cmd'],
              "exitStatus": -1,
              "result": "",
              "error": f"exception: {str(e)}",
            }, ensure_ascii=False)

          socket.send(echo.encode())

        elif 'tmux_send' in json_obj:
          # Send tmux data
          self.make_tmux_data()
          self.send_tmux(json_obj['tmux_send'], "tmux_send")
          echo = json.dumps({
            "tmux_send": json_obj['tmux_send'],
            "result": "success",
          }, ensure_ascii=False)
          socket.send(echo.encode())

      except Exception as e:
        cloudlog.error(f"carrot_man: ZMQ error: {e}")
        try:
          socket.close()
        except Exception:
          pass
        time.sleep(1)
        socket, poller = setup_socket()

  # ---- navigation route (P2-1) ------------------------------------------- #

  def recvall(self, sock: socket.socket, n: int) -> bytes | None:
    """Receive n bytes from socket."""
    data = bytearray()
    while len(data) < n:
      packet = sock.recv(n - len(data))
      if not packet:
        return None
      data.extend(packet)
    return bytes(data)

  def carrot_route(self) -> None:
    """Navigation route TCP server for phone app."""
    import json
    import struct

    host = '0.0.0.0'
    port = self._route_port

    try:
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen()
        cloudlog.info(f"carrot_man: route server listening on port {port}")

        while self._route_running:
          try:
            cloudlog.debug("carrot_man: waiting for route connection...")
            conn, addr = s.accept()
            with conn:
              cloudlog.info(f"carrot_man: route connected by {addr}")

              # Receive total size (4 bytes)
              total_size_bytes = self.recvall(conn, 4)
              if not total_size_bytes:
                cloudlog.warning("carrot_man: connection closed or error occurred")
                continue

              total_size = struct.unpack('!I', total_size_bytes)[0]

              # Receive all data
              all_data = self.recvall(conn, total_size)
              if all_data is None:
                cloudlog.warning("carrot_man: connection closed or incomplete data received")
                continue

              # Parse coordinates (8 bytes per point: 2 x float32)
              self._navi_points = []
              points = []
              for i in range(0, len(all_data), 8):
                x, y = struct.unpack('!ff', all_data[i:i+8])
                self._navi_points.append((x, y))
                # Create coordinate dict for send_routes
                coord = {'x': x, 'y': y}
                points.append(coord)

              self._navi_points_start_index = 0
              self._navi_points_active = True
              cloudlog.info(f"carrot_man: received {len(self._navi_points)} route points")

              # Send routes
              self.send_routes(points, from_navd=True)

              # Save destination to params
              if len(points):
                dest = points[-1]
                dest['place_name'] = "External Navi"
                self.params.put("NavDestination", json.dumps(dest, ensure_ascii=False))

          except Exception as e:
            cloudlog.error(f"carrot_man: route connection error: {e}")
            continue

    except Exception as e:
      cloudlog.error(f"carrot_man: route server error: {e}")

  def send_routes(self, coords: list, from_navd: bool = False) -> None:
    """Send navigation routes to phone app."""
    if not coords:
      return
    self._navi_points = coords
    self._navi_points_active = True
    self._navd_active = from_navd

  # ---- kisa app (P3-2) --------------------------------------------------- #

  def parse_kisa_data(self, data: bytes) -> dict[str, Any]:
    """Parse kisa data from phone app."""
    import json

    try:
      return json.loads(data.decode('utf-8'))
    except json.JSONDecodeError:
      # Try to parse as raw bytes
      try:
        return {'raw': data.decode('utf-8', errors='ignore')}
      except Exception:
        return {'raw': data.hex()}

  def kisa_app_thread(self) -> None:
    """Kisa app UDP data handler thread."""
    import socket
    import time

    while self._kisa_running:
      try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
          sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
          sock.settimeout(10)
          sock.bind(('', self._kisa_port))
          cloudlog.info(f"carrot_man: kisa app thread started on port {self._kisa_port}")

          while self._kisa_running:
            try:
              data, remote_addr = sock.recvfrom(4096)
              if not data:
                continue

              try:
                kisa_data = self.parse_kisa_data(data)
                # Update carrot serv with kisa data
                if hasattr(self._carrot_serv, 'update_kisa'):
                  self._carrot_serv.update_kisa(kisa_data)
                cloudlog.debug(f"carrot_man: kisa data received: {len(data)} bytes")
              except Exception as e:
                cloudlog.error(f"carrot_man: kisa data parse error: {e}")

            except TimeoutError:
              continue
            except Exception as e:
              cloudlog.error(f"carrot_man: kisa recv error: {e}")
              break

          time.sleep(1)
      except Exception as e:
        cloudlog.error(f"carrot_man: kisa thread error: {e}")
        time.sleep(2)

  # ---- panda debug (P3-1) ------------------------------------------------ #

  def carrot_panda_debug(self) -> None:
    """Panda debug info thread."""
    import os
    import subprocess
    import time

    while self._panda_debug_running:
      if self._show_panda_debug:
        self._show_panda_debug = False
        try:
          debug_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "debug", "debug_console_carrot.py")
          if os.path.exists(debug_script):
            subprocess.run([debug_script], shell=True, timeout=30)
          else:
            cloudlog.debug("carrot_man: debug_console_carrot.py not found, skipping")
        except Exception as e:
          cloudlog.error(f"carrot_man: debug_console error: {e}")
          time.sleep(2)
      else:
        time.sleep(1)

  def save_toggle_values(self) -> None:
    """Save toggle values to JSON file."""
    import json
    import os

    try:
      toggle_values = {}
      for key in ["IsMetric", "IsLdw", "OpkrEnableDriverMonitoring"]:
        try:
          val = self.params.get(key)
          if val is not None:
            toggle_values[key] = val.decode() if isinstance(val, bytes) else val
        except Exception:
          pass

      file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'toggle_values.json')
      with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(toggle_values, f, indent=2, ensure_ascii=False)
    except Exception as e:
      cloudlog.error(f"carrot_man: save_toggle_values error: {e}")

  # ---- FTP upload (P3-3) ------------------------------------------------- #

  def make_tmux_data(self) -> None:
    """Prepare tmux data for upload."""
    import os
    import subprocess

    try:
      # Capture tmux log
      subprocess.run(
        "tmux capture-pane -pq -S-1000 > /data/media/tmux.log",
        shell=True,
        capture_output=True,
        text=False,
        timeout=10,
      )
      # Run apilot script if available
      apilot_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "apilot.py")
      if os.path.exists(apilot_script):
        subprocess.run([apilot_script], shell=True, capture_output=True, text=False, timeout=30)
    except Exception as e:
      cloudlog.error(f"carrot_man: make_tmux_data error: {e}")

  def send_tmux(self, ftp_password: str, tmux_why: str, send_settings: bool = False) -> None:
    """Send tmux data via FTP."""
    from datetime import datetime
    from ftplib import FTP

    ftp_server = "shind0.synology.me"
    ftp_port = 8021
    ftp_username = "carrotpilot"

    try:
      ftp = FTP()
      ftp.connect(ftp_server, ftp_port, timeout=30)
      ftp.login(ftp_username, ftp_password)

      # Get car name
      car_selected = self.params.get("CarName")
      if car_selected is None:
        car_selected = "none"
      elif isinstance(car_selected, bytes):
        car_selected = car_selected.decode('utf-8')

      # Get git branch
      git_branch = self.params.get("GitBranch") or ''
      if isinstance(git_branch, bytes):
        git_branch = git_branch.decode('utf-8')

      # Get dongle ID
      dongle_id = self.params.get("DongleId") or ''
      if isinstance(dongle_id, bytes):
        dongle_id = dongle_id.decode('utf-8')

      # Build directory and filename
      directory = f"{git_branch} {car_selected} {dongle_id}"
      current_time = datetime.now().strftime("%Y%m%d-%H%M%S")
      filename = f"{tmux_why}-{current_time}-{git_branch}.txt"

      try:
        ftp.mkd(directory)
      except Exception as e:
        cloudlog.debug(f"carrot_man: directory creation failed: {e}")
      ftp.cwd(directory)

      # Send tmux log
      try:
        with open("/data/media/tmux.log", "rb") as file:
          ftp.storbinary(f'STOR {filename}', file)
          cloudlog.info(f"carrot_man: tmux data sent: {filename}")
      except Exception as e:
        cloudlog.error(f"carrot_man: ftp sending error: {e}")

      # Send toggle values if requested
      if send_settings:
        self.save_toggle_values()
        try:
          with open("/data/toggle_values.json", "rb") as file:
            ftp.storbinary(f'STOR toggles-{current_time}.json', file)
        except Exception as e:
          cloudlog.error(f"carrot_man: ftp params sending error: {e}")

      ftp.quit()
    except Exception as e:
      cloudlog.error(f"carrot_man: send_tmux error: {e}")


def main_thread():
  config_realtime_process([0, 1, 2, 3], 5)

  manager = CarrotManager()
  rk = Ratekeeper(DEFAULT_RATE, print_delay_threshold=None)

  while True:
    manager.tick()
    rk.keep_time()


def main():
  main_thread()


if __name__ == "__main__":
  main()
