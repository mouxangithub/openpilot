from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""
AmapNaviServ - high-level adapter for the Amap / CarrotMan phone app.

The real CarrotPilot implementation owns a UDP server bound on
``AmapNaviUdpPort`` (default 4211) and a TCP channel on the broadcast
address.  In sunnypilot the UDP listener is owned by ``CarrotManager``;
this module is the **pure data path** that:

* parses the small JSON payload the phone app sends (see
  :func:`parse_packet`);
* keeps a :class:`SharedData` snapshot used by ``desire_helper``,
  ``carState``-fusing code, and the HUD; and
* publishes an ``amapNaviSP`` message every tick.

A separate file (``mapd/amap/mapd_amap.py``) already handles the MAPD
side of amap data; this module is the smaller, lower-latency bridge that
only touches ``AmapNaviSP``/``carState``-side state.
"""

import json
import time
import threading
import socket
import fcntl
import struct
import queue
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import cereal.messaging as messaging
from openpilot.system.hardware import PC

lock = threading.Lock()
data_queue = queue.Queue()

DT_BROADCAST = 0.1


BLINKER_NONE = 0
BLINKER_LEFT = 1
BLINKER_RIGHT = 2
BLINKER_BOTH = 3


def _safe_int(value: Any, default: int = 0) -> int:
  try:
    if value is None:
      return default
    if isinstance(value, bool):
      return int(value)
    return int(value)
  except (TypeError, ValueError):
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
  try:
    if value is None:
      return default
    return float(value)
  except (TypeError, ValueError):
    return default


@dataclass
class SharedData:
  """Cross-module state published by AmapNaviServ.

  The dataclass keeps a stable, mutable surface so other daemons
  (``desire_helper``, ``carrot_man``, ``hud_renderer``) can read the
  latest values without going through the cereal bus.
  """
  # Blind spot signals.
  left_blind: bool = False
  right_blind: bool = False
  lidar_left_blind: bool = False
  lidar_right_blind: bool = False
  lidar_car_left_blind: bool = False
  lidar_car_right_blind: bool = False
  camera_left: bool = False
  camera_right: bool = False
  lidar_left: bool = False
  lidar_right: bool = False

  # Radar lead data (4 corners).
  lf_drel: dict[str, float] = field(default_factory=dict)
  lb_drel: dict[str, float] = field(default_factory=dict)
  rf_drel: dict[str, float] = field(default_factory=dict)
  rb_drel: dict[str, float] = field(default_factory=dict)
  lf_xrel: dict[str, float] = field(default_factory=dict)
  lb_xrel: dict[str, float] = field(default_factory=dict)
  rf_xrel: dict[str, float] = field(default_factory=dict)
  rb_xrel: dict[str, float] = field(default_factory=dict)
  lf_vrel: float | None = None
  lb_vrel: float | None = None
  rf_vrel: float | None = None
  rb_vrel: float | None = None

  # Main radar mirrors.
  main_lf_xrel: float | None = None
  main_lb_xrel: float | None = None
  main_rf_xrel: float | None = None
  main_rb_xrel: float | None = None
  main_lf_drel: float | None = None
  main_lb_drel: float | None = None
  main_rf_drel: float | None = None
  main_rb_drel: float | None = None

  # Status / commands.
  op_blocked: bool = False
  road_blocked: bool = False
  cmd_index: int = -1
  remote_cmd: str = ""
  remote_arg: str = ""
  ext_blinker: int = BLINKER_NONE
  ext_state: int = 0

  # Road context.
  roadcate: int | None = None
  lat_a: float | None = None
  max_curve: float | None = None

  # desire_helper data.
  left_front_blind: bool | None = None
  right_front_blind: bool | None = None

  # carState data.
  car_state: bool = False
  v_ego_kph: int | None = None
  v_cruise_kph: int | None = None
  v_ego_m: float | None = None
  v_ego: float | None = None
  a_ego: float | None = None
  steer_angle: float | None = None
  gas_press: bool | None = None
  break_press: bool | None = None
  engaged: bool | None = None
  cruise_valid: bool | None = None
  cruise_enable: bool | None = None
  selfdrive_active: bool | None = None
  left_blindspot: int | None = None
  right_blindspot: int | None = None

  # Debug.
  show_debug_log: int = 0

  # Map-based traffic light.
  map_traffic_state: int = 0       # 0=none, 1=red, 2=green, 3=left-turn green
  map_traffic_countdown: int = 0
  map_traffic_time: float = 0.0

  # Client tracking.
  ext_state: int = 0


@dataclass
class RadarSpeedEstimator:
  """Robust radial speed estimate from noisy radar distance samples.

  The real CarrotPilot implementation uses this to derive a smoother
  ``vRel`` for each of the four corners.  We keep the same surface so
  downstream consumers (e.g. smart-cruise-control) can hook into the
  estimator without caring about the wire format.
  """

  max_acc: float = 4.0
  smooth_n: int = 5
  lost_timeout_ms: int = 500

  def __post_init__(self) -> None:
    self.last_dist_m: float | None = None
    self.last_t_ms: float | None = None
    self.last_speed: float | None = None
    self.speed_hist: deque[float] = deque(maxlen=self.smooth_n)

  def update(self, dist_mm: float | None, t_ms: float) -> float | None:
    if dist_mm is None:
      if self.last_t_ms is None:
        return None
      if t_ms - self.last_t_ms < self.lost_timeout_ms:
        return self.last_speed
      self.last_dist_m = None
      self.last_t_ms = None
      self.last_speed = None
      self.speed_hist.clear()
      return None
    dist_m = float(dist_mm) / 1000.0
    if self.last_dist_m is None or self.last_t_ms is None:
      self.last_dist_m = dist_m
      self.last_t_ms = t_ms
      self.last_speed = 0.0
      self._update_hist(0.0)
      return None
    dt_ms = t_ms - self.last_t_ms
    if dt_ms <= 0:
      return self.last_speed
    dt = dt_ms / 1000.0
    raw_speed = (dist_m - self.last_dist_m) / dt
    allowed_dv = self.max_acc * dt
    low = (self.last_speed or 0.0) - allowed_dv
    high = (self.last_speed or 0.0) + allowed_dv
    filtered = max(low, min(raw_speed, high))
    self.last_dist_m = dist_m
    self.last_t_ms = t_ms
    self.last_speed = filtered
    return self._update_hist(filtered)

  def _update_hist(self, speed: float) -> float:
    self.speed_hist.append(speed)
    if not self.speed_hist:
      return 0.0
    return sum(self.speed_hist) / len(self.speed_hist)


def parse_packet(raw: bytes | str) -> dict[str, Any] | None:
  """Decode a single UDP packet from the CarrotMan/Amap app.

  The wire format is UTF-8 JSON.  Unknown shapes are ignored so the
  protocol can grow without breaking old builds.
  """
  if isinstance(raw, (bytes, bytearray)):
    try:
      raw = raw.decode("utf-8")
    except UnicodeDecodeError:
      return None
  try:
    obj = json.loads(raw)
  except (TypeError, ValueError):
    return None
  if not isinstance(obj, dict):
    return None
  return obj


class AmapNaviServ:
  """In-process Amap data bridge.

  Holds the :class:`SharedData` snapshot and emits ``amapNaviSP`` messages.
  No sockets are owned here: the actual UDP listener lives in
  ``CarrotManager`` so that a single process can be the source of truth for
  Carrot/Amap/Phone packets without the threading complexity of the original
  CarrotPilot design.
  """

  def __init__(self) -> None:
    self.shared_data = SharedData()
    self._last_packet_mono: float = 0.0
    self._seq: int | None = None
    self._blinker_alive: bool = False
    self._blinker_time: float = 0.0
    self._lead_left_right: bool = False

    # Per-corner speed estimators.
    self._lf_speed = RadarSpeedEstimator()
    self._lb_speed = RadarSpeedEstimator()
    self._rf_speed = RadarSpeedEstimator()
    self._rb_speed = RadarSpeedEstimator()

    # Additional speed estimators (sunnypilot-cuda uses leftFrontTarget etc.).
    self._left_front_target = RadarSpeedEstimator()
    self._left_behind_target = RadarSpeedEstimator()
    self._right_front_target = RadarSpeedEstimator()
    self._right_behind_target = RadarSpeedEstimator()

    # Parameter cache (P2-2).
    self._frame: int = 0
    self._side_bsd_delay_time = 2.0
    self._side_rel_dist_time = 1.0
    self._side_vrel_dist_time = 1.0
    self._min_drel_vego_time = 1.0
    self._min_vrel_vego_time = 1.0
    self._min_object_detected_count_thr = -10
    self._disable_blind_spot = False
    self._dynamic_blind_range = 0
    self._dynamic_blind_distance = 0

    # Per-corner object detection counters.
    self._lf_object_detected_count: int = 0
    self._lb_object_detected_count: int = 0
    self._rf_object_detected_count: int = 0
    self._rb_object_detected_count: int = 0
    self._min_object_detected_count: int = int(-60.0 / DT_BROADCAST)
    self._min_object_detected_count_thr_val: int = int(-2.0 / DT_BROADCAST)

    self._lf_object_detected: bool = False
    self._lb_object_detected: bool = False
    self._rf_object_detected: bool = False
    self._rb_object_detected: bool = False

    self._lf_side_object_detected: bool = False
    self._lb_side_object_detected: bool = False
    self._rf_side_object_detected: bool = False
    self._rb_side_object_detected: bool = False

    self._model_event_type: int = 0
    self._sec_count_down: int = 0

    # Multi-client management.
    self._clients: dict[str, dict] = {}
    self._client_queues: dict[str, queue.Queue] = {}
    self._client_active: dict[str, bool] = {}
    self._clients_copy: dict[str, dict] = {}
    self._active_clients: list = []

    # Network config.
    self._broadcast_ip: str | None = None
    self._broadcast_port: int = 4210
    self._listen_port: int = 4211
    self._local_ip_address: str = "0.0.0.0"

  # ---- packet ingestion ------------------------------------------------- #

  def apply_packet(self, packet: dict[str, Any], recv_mono: float | None = None) -> None:
    """Apply a decoded phone packet to the cached state."""
    if recv_mono is None:
      recv_mono = time.monotonic()

    seq = _safe_int(packet.get("carrotIndex"), -1)
    if seq >= 0 and self._seq is not None and seq < self._seq:
      return
    self._seq = seq
    self._last_packet_mono = recv_mono

    sd = self.shared_data
    sd.left_blind = bool(_safe_int(packet.get("leftBlind"), 0))
    sd.right_blind = bool(_safe_int(packet.get("rightBlind"), 0))
    sd.lidar_left_blind = bool(_safe_int(packet.get("lidarLBlind"), 0))
    sd.lidar_right_blind = bool(_safe_int(packet.get("lidarRBlind"), 0))
    sd.lidar_car_left_blind = bool(_safe_int(packet.get("lidarCarLBlind"), 0))
    sd.lidar_car_right_blind = bool(_safe_int(packet.get("lidarCarRBlind"), 0))
    sd.camera_left = bool(_safe_int(packet.get("cameraL"), 0))
    sd.camera_right = bool(_safe_int(packet.get("cameraR"), 0))
    sd.lidar_left = bool(_safe_int(packet.get("lidarL"), 0))
    sd.lidar_right = bool(_safe_int(packet.get("lidarR"), 0))
    sd.op_blocked = bool(_safe_int(packet.get("opBlocked"), 0))
    sd.road_blocked = bool(_safe_int(packet.get("roadBlocked"), 0))
    sd.ext_blinker = _safe_int(packet.get("extBlinker"), BLINKER_NONE)
    sd.ext_state = _safe_int(packet.get("extState"), 0)
    sd.cmd_index = seq
    sd.remote_cmd = str(packet.get("carrotCmd", "") or "")
    sd.remote_arg = str(packet.get("carrotArg", "") or "")

    # Per-corner radar distance samples.
    self._update_corner(sd.lf_drel, packet, "lfDrel", "lfDrelTime")
    self._update_corner(sd.lb_drel, packet, "lbDrel", "lbDrelTime")
    self._update_corner(sd.rf_drel, packet, "rfDrel", "rfDrelTime")
    self._update_corner(sd.rb_drel, packet, "rbDrel", "rbDrelTime")
    self._update_corner(sd.lf_xrel, packet, "lfXrel", "lfXrelTime")
    self._update_corner(sd.lb_xrel, packet, "lbXrel", "lbXrelTime")
    self._update_corner(sd.rf_xrel, packet, "rfXrel", "rfXrelTime")
    self._update_corner(sd.rb_xrel, packet, "rbXrel", "rbXrelTime")

    t_now = recv_mono * 1000.0
    sd.lf_vrel = self._lf_speed.update(_safe_float(packet.get("lfDrel"), None), t_now)
    sd.lb_vrel = self._lb_speed.update(_safe_float(packet.get("lbDrel"), None), t_now)
    sd.rf_vrel = self._rf_speed.update(_safe_float(packet.get("rfDrel"), None), t_now)
    sd.rb_vrel = self._rb_speed.update(_safe_float(packet.get("rbDrel"), None), t_now)

    # Map-based traffic light.
    sd.map_traffic_state = _safe_int(packet.get("mapTrafficState"), 0)
    sd.map_traffic_countdown = _safe_int(packet.get("mapTrafficCountdown"), 0)
    sd.map_traffic_time = float(recv_mono)

  def _update_corner(self, target: dict[str, float], packet: dict[str, Any],
                     key: str, time_key: str) -> None:
    value = _safe_float(packet.get(key), None)
    t_value = _safe_float(packet.get(time_key), None)
    if value is None or t_value is None:
      return
    target[f"{t_value:.0f}"] = value
    # Trim old samples (>2 s old) to keep the dict small.
    cutoff = t_value - 2000.0
    for k in [k for k, v in list(target.items()) if float(k) < cutoff]:
      target.pop(k, None)

  def is_stale(self, now_mono: float | None = None, timeout: float = 3.0) -> bool:
    if self._last_packet_mono == 0.0:
      return True
    if now_mono is None:
      now_mono = time.monotonic()
    return (now_mono - self._last_packet_mono) > timeout

  def reset(self) -> None:
    """Reset cached state when the phone app disconnects."""
    sd = self.shared_data
    sd.left_blind = False
    sd.right_blind = False
    sd.lidar_left_blind = False
    sd.lidar_right_blind = False
    sd.lidar_car_left_blind = False
    sd.lidar_car_right_blind = False
    sd.camera_left = False
    sd.camera_right = False
    sd.lidar_left = False
    sd.lidar_right = False
    sd.op_blocked = False
    sd.road_blocked = False
    sd.lf_vrel = None
    sd.lb_vrel = None
    sd.rf_vrel = None
    sd.rb_vrel = None
    sd.lf_drel.clear()
    sd.lb_drel.clear()
    sd.rf_drel.clear()
    sd.rb_drel.clear()
    sd.lf_xrel.clear()
    sd.lb_xrel.clear()
    sd.rf_xrel.clear()
    sd.rb_xrel.clear()
    self._seq = None
    self._last_packet_mono = 0.0

  # ---- message publishing --------------------------------------------- #

  def build_amap_navi_msg(self, new_message) -> Any:
    """Populate a new ``amapNaviSP`` message from the current state.

    The function takes a ``messaging.new_message`` callable so that the
    unit tests can pass a fake without importing the cereal module.
    """
    sd = self.shared_data
    msg = new_message("amapNaviSP")
    msg.valid = not self.is_stale()
    navi = msg.amapNaviSP
    navi.leftBlind = 1 if sd.left_blind else 0
    navi.rightBlind = 1 if sd.right_blind else 0
    navi.lineValid = bool(sd.lf_xrel or sd.lb_xrel or sd.rf_xrel or sd.rb_xrel)
    navi.leftLine = 0
    navi.rightLine = 0
    return msg

  # ---- radar data (P2-2) ------------------------------------------------ #

  def update_param(self, params: Any) -> None:
    """Update cached parameters from UnifiedParams."""
    if self._frame % 100 == 0:
      self._side_bsd_delay_time = params.get_float("SideBsdDelayTime") * 0.1
      self._side_rel_dist_time = params.get_float("SideRelDistTime") * 0.1
      self._side_vrel_dist_time = params.get_float("SidevRelDistTime") * 0.1
      self._min_drel_vego_time = self._side_rel_dist_time
      self._min_vrel_vego_time = self._side_vrel_dist_time
      self._min_object_detected_count_thr = int(-1 * self._side_bsd_delay_time / 0.1)
      self._disable_blind_spot = params.get_bool("DisableBlindSpot")
      self._dynamic_blind_range = params.get_int("DynamicBlindRange")
      self._dynamic_blind_distance = params.get_int("DynamicBlindDistance")
    self._frame += 1

  def lidar_object_blind(self, sm: Any) -> tuple[bool, bool, bool, bool]:
    """Dynamic blind spot masking based on navigation guidance.

    Returns:
      (lf_blind_mask, lb_blind_mask, rf_blind_mask, rb_blind_mask)
    """
    lf_blind_mask = False
    lb_blind_mask = False
    rf_blind_mask = False
    rb_blind_mask = False

    # Dynamic blind range adjustment
    if self._dynamic_blind_range >= 1:
      carrot_man = sm['carrotMan']
      model_v2 = sm['modelV2']
      meta = model_v2.meta

      atc_type = carrot_man.atcType
      lane_width_left = round(getattr(meta, 'laneWidthLeft', 0.0), 1)
      lane_width_right = round(getattr(meta, 'laneWidthRight', 0.0), 1)

      atc_blinker_state = BLINKER_NONE
      turn_left_right = False
      fork_left_right = False
      atc_left_right = False

      # Check navigation control type
      if atc_type in ["turn left", "turn right"]:
        atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
        turn_left_right = True
      elif atc_type in ["fork left", "fork right"]:
        atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
        fork_left_right = True
      elif atc_type in ["fork left now", "fork right now"]:
        atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
        fork_left_right = True
      elif atc_type in ["atc left", "atc right"]:
        atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
        atc_left_right = True

      # Dynamically limit lidar blind spot side and front/back ranges
      if (fork_left_right or atc_left_right or turn_left_right) and self._dynamic_blind_range >= 1:
        sd = self.shared_data
        if sd.main_lf_xrel is not None and sd.main_lf_xrel > lane_width_left * 1000.0:
          lf_blind_mask = True
        if sd.main_lb_xrel is not None and sd.main_lb_xrel > lane_width_left * 1000.0:
          lb_blind_mask = True
        if sd.main_rf_xrel is not None and sd.main_rf_xrel > lane_width_right * 1000.0:
          rf_blind_mask = True
        if sd.main_rb_xrel is not None and sd.main_rb_xrel > lane_width_right * 1000.0:
          rb_blind_mask = True

        if fork_left_right:
          if atc_blinker_state == BLINKER_LEFT:
            if sd.main_lf_drel is not None and sd.main_lf_drel > 5000:
              lf_blind_mask = True
            if sd.main_lb_drel is not None and sd.main_lb_drel < -10000:
              lb_blind_mask = True
          elif atc_blinker_state == BLINKER_RIGHT:
            if sd.main_rf_drel is not None and sd.main_rf_drel > 5000:
              rf_blind_mask = True
            if sd.main_rb_drel is not None and sd.main_rb_drel < -10000:
              rb_blind_mask = True

    return lf_blind_mask, lb_blind_mask, rf_blind_mask, rb_blind_mask

  def update_navi_carstate(self, sm: Any) -> None:
    """Update carState with amap blind spot data."""
    if not sm.alive['carState']:
      return

    sd = self.shared_data

    # Merge blind spot data into carState
    if sd.left_blind or sd.lidar_left_blind or sd.lidar_car_left_blind:
      sm['carState'].leftBlindspot = True
    if sd.right_blind or sd.lidar_right_blind or sd.lidar_car_right_blind:
      sm['carState'].rightBlindspot = True

  def get_radar_data(self) -> dict[str, Any]:
    """Get radar data for web display."""
    sd = self.shared_data
    return {
      'points': [],
      'tracks': [],
      'leads': [],
      'timestamp': time.monotonic(),
      'lf_drel': dict(sd.lf_drel),
      'lb_drel': dict(sd.lb_drel),
      'rf_drel': dict(sd.rf_drel),
      'rb_drel': dict(sd.rb_drel),
      'lf_vrel': sd.lf_vrel,
      'lb_vrel': sd.lb_vrel,
      'rf_vrel': sd.rf_vrel,
      'rb_vrel': sd.rb_vrel,
    }

  # ---- sunnypilot-cuda multi-client methods -------------------------------- #

  def public_amap_navi(self) -> None:
    """Publish amapNavi message to the cereal bus."""
    try:
      msg = messaging.new_message('amapNavi')
      msg.valid = True
      sd = self.shared_data
      msg.amapNavi.leftBlind = (
        (4 if sd.lidar_car_left_blind else 0) +
        (2 if sd.left_blind else 0) +
        (1 if sd.lidar_left_blind else 0)
      )
      msg.amapNavi.rightBlind = (
        (4 if sd.lidar_car_right_blind else 0) +
        (2 if sd.right_blind else 0) +
        (1 if sd.lidar_right_blind else 0)
      )
      messaging.PubMaster(['amapNavi']).send('amapNavi', msg)
    except Exception:
      pass

  def left_blindspot(self) -> bool:
    return self.shared_data.left_blind or self.shared_data.lidar_left_blind

  def right_blindspot(self) -> bool:
    return self.shared_data.right_blind or self.shared_data.lidar_right_blind

  def _capnp_list_to_list(self, capnp_list: Any, max_items: int | None = None) -> list:
    """Convert capnp list to Python list."""
    if capnp_list is None:
      return []
    try:
      result = [float(x) for x in capnp_list]
      if max_items is not None:
        return result[:max_items]
      return result
    except (TypeError, AttributeError):
      return []

  def _f1(self, x: float) -> float:
    return round(float(x), 1)

  def _f2(self, x: float) -> float:
    return round(float(x), 2)

  # ---- threads ----------------------------------------------------------- #

  def start_navi_comm(self) -> None:
    """Start all UDP communication threads."""
    threading.Thread(target=self._udp_recv_thread, daemon=True).start()
    threading.Thread(target=self._clean_clients_thread, daemon=True).start()
    threading.Thread(target=self._data_deal_thread, daemon=True).start()
    threading.Thread(target=self.navi_broadcast_info, daemon=True).start()

  def _udp_recv_thread(self) -> None:
    """Receive UDP packets and dispatch to per-client worker threads."""
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(10)
        sock.bind(('0.0.0.0', self._listen_port))
        while True:
          try:
            data, addr = sock.recvfrom(4096)
            ip, _port = addr
            with lock:
              if ip not in self._client_queues:
                q = queue.Queue()
                self._client_queues[ip] = q
                self._client_active[ip] = True
                threading.Thread(target=self._client_worker, args=(ip,), daemon=True).start()
              self._client_queues[ip].put((data, addr))
          except socket.timeout:
            continue
          except Exception:
            time.sleep(1)
    except Exception:
      pass

  def _client_worker(self, ip: str) -> None:
    """Per-client data processing worker thread."""
    q = self._client_queues[ip]
    while True:
      try:
        try:
          data, addr = q.get(timeout=1)
          self._process_single_packet(data, addr)
        except queue.Empty:
          with lock:
            if not self._client_active.get(ip, False):
              if ip in self._client_queues:
                del self._client_queues[ip]
              if ip in self._client_active:
                del self._client_active[ip]
              break
      except Exception:
        pass

  def _data_deal_thread(self) -> None:
    """Aggregate sensor data from all clients and publish messages at ~20 Hz."""
    rk = Ratekeeper(20, print_delay_threshold=0.02)
    _clients: dict = {}
    _active_clients: list = []

    while True:
      try:
        # Copy client list.
        with lock:
          _clients = getattr(self, "_clients", {}).copy()
        _active_clients = list(_clients.keys())

        # Reset per-frame local variables.
        lidar_l = lidar_r = camera_l = camera_r = False
        lidar_lblind = lidar_rblind = left_blind = right_blind = False
        lidar_car_lblind = lidar_car_rblind = False

        if _active_clients:
          # Clear old data before aggregation.
          sd = self.shared_data
          for field in ["lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel"]:
            getattr(sd, field).clear()

          left_lidar_id = right_lidar_id = 0

          for ip, info in _clients.items():
            try:
              device_type = info.get("device", None)
              detect_side = info.get("detect_side", 0)

              if device_type in ("lidar", "camera"):
                if device_type == "lidar":
                  if (detect_side & 1) > 0:
                    lidar_l = True
                  if (detect_side & 2) > 0:
                    lidar_r = True
                if device_type == "camera":
                  if (detect_side & 1) > 0:
                    camera_l = True
                  if (detect_side & 2) > 0:
                    camera_r = True

                if device_type == "lidar":
                  self.lidar_data_timeout(ip, info)
                if device_type == "lidar":
                  self.camera_data_timeout(ip, info)

                if info.get("lidar_lblind", False):
                  lidar_lblind = True
                  _lf_drel = info.get("lf_drel")
                  _lb_drel = info.get("lb_drel")
                  lf_limit_val = max(3000 + (_lb_drel if _lb_drel is not None else -2000), 1000)
                  if (_lf_drel is not None and _lf_drel < lf_limit_val) or (
                    _lb_drel is not None and _lb_drel > -2000):
                    lidar_car_lblind = True

                if info.get("lidar_rblind", False):
                  lidar_rblind = True
                  _rf_drel = info.get("rf_drel")
                  _rb_drel = info.get("rb_drel")
                  lf_limit_val = max(3000 + (_rb_drel if _rb_drel is not None else -2000), 1000)
                  if (_rf_drel is not None and _rf_drel < lf_limit_val) or (
                    _rb_drel is not None and _rb_drel > -2000):
                    lidar_car_rblind = True

                if info.get("left_blind", False):
                  left_blind = True
                if info.get("right_blind", False):
                  right_blind = True

                if (detect_side & 0x01) > 0:
                  sd.lf_drel[left_lidar_id] = info.get("lf_drel")
                  sd.lb_drel[left_lidar_id] = info.get("lb_drel")
                  sd.lf_xrel[left_lidar_id] = info.get("lf_xrel")
                  sd.lb_xrel[left_lidar_id] = info.get("lb_xrel")
                  left_lidar_id += 1

                if (detect_side & 0x02) > 0:
                  sd.rf_drel[right_lidar_id] = info.get("rf_drel")
                  sd.rb_drel[right_lidar_id] = info.get("rb_drel")
                  sd.rf_xrel[right_lidar_id] = info.get("rf_xrel")
                  sd.rb_xrel[right_lidar_id] = info.get("rb_xrel")
                  right_lidar_id += 1

            except Exception:
              pass

          # Update blind spot state.
          if self._dynamic_blind_distance == 0 and self._dynamic_blind_range == 0:
            sd.lidar_left_blind = lidar_lblind
            sd.lidar_right_blind = lidar_rblind
          else:
            sd.lidar_left_blind = self._lf_side_object_detected or self._lb_side_object_detected
            sd.lidar_right_blind = self._rf_side_object_detected or self._rb_side_object_detected

          sd.lidar_car_left_blind = lidar_car_lblind
          sd.lidar_car_right_blind = lidar_car_rblind
          sd.left_blind = left_blind
          sd.right_blind = right_blind

        sd = self.shared_data
        sd.lidar_l = lidar_l
        sd.lidar_r = lidar_r
        sd.camera_l = camera_l
        sd.camera_r = camera_r

        self.public_amap_navi()
        rk.keep_time()

      except Exception:
        time.sleep(1)

  def _clean_clients_thread(self) -> None:
    """Periodically remove clients that have not sent data for >1 second."""
    while True:
      now_mono = time.monotonic()
      with lock:
        active_clients = {
          ip: info for ip, info in self._clients.items()
          if now_mono - info.get("last_seen", 0) < 1.0
        }
        for ip, info in self._clients.items():
          if ip not in active_clients and ip in self._client_active:
            self._client_active[ip] = False
        self._clients = active_clients
        sd = self.shared_data
        if self._clients:
          sd.ext_state = len(self._clients)
        else:
          sd.ext_state = 0
          sd.ext_blinker = BLINKER_NONE
      time.sleep(0.2)

  def navi_broadcast_info(self) -> None:
    """Broadcast device status to all clients at ~10 Hz."""
    try:
      sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except Exception:
      return

    frame = 0
    rk = Ratekeeper(10, print_delay_threshold=0.03)

    while True:
      try:
        with lock:
          self._clients_copy = getattr(self, "_clients", {}).copy()
          self._active_clients = list(self._clients_copy.keys())

        if frame % 20 == 0 or self._active_clients:
          try:
            ip_address = self.navi_get_local_ip()
            if ip_address != self._local_ip_address:
              self._local_ip_address = ip_address
              self._clients_copy = {}
              with lock:
                self._clients = {}

            navi_msg = navi_dat = lidar_msg = lidar_dat = blinker_msg = blinker_dat = None

            if self._active_clients:
              for ip, info in self._clients_copy.items():
                try:
                  port_val = info.get("port", self._broadcast_port)
                  port = int(port_val) if port_val is not None else self._broadcast_port
                  device_type = info.get("device")
                  detect_side = info.get("detect_side", 0)

                  if device_type in ("overtake", "navi"):
                    if navi_msg is None:
                      navi_msg = self.make_navi_message()
                      navi_dat = navi_msg.encode('utf-8')
                    if navi_dat is not None:
                      sock.sendto(navi_dat, (ip, port))
                  elif device_type == "lidar" or (device_type == "camera" and (frame % 10) == 0):
                    if lidar_msg is None:
                      lidar_msg = self.make_lidar_message()
                      lidar_dat = lidar_msg.encode('utf-8')
                    if lidar_dat is not None:
                      sock.sendto(lidar_dat, (ip, port))
                  elif ((frame + 3) % 5) == 0:
                    if blinker_msg is None:
                      blinker_msg = self.make_blinker_message()
                      blinker_dat = blinker_msg.encode('utf-8')
                    if blinker_dat is not None:
                      sock.sendto(blinker_dat, (ip, port))
                except Exception:
                  pass

            # Broadcast own info every 2 seconds.
            if frame % 20 == 0:
              broadcast_msg = self.make_broadcast_message()
              broadcast_dat = broadcast_msg.encode('utf-8')
              if self._broadcast_ip is not None and broadcast_dat is not None:
                self._broadcast_ip = self.navi_get_broadcast_address()
                sock.sendto(broadcast_dat, (self._broadcast_ip, self._broadcast_port))

          except Exception:
            pass

        rk.keep_time()
        frame += 1

      except Exception:
        time.sleep(1)

  # ---- packet processing ------------------------------------------------ #

  def _process_single_packet(self, data: bytes, addr: tuple) -> None:
    """Process a single incoming UDP packet."""
    ip, _port = addr
    now_mono = time.monotonic()
    with lock:
      old_info = self._clients.get(ip, {})

    try:
      json_obj = json.loads(data.decode())
      self._update_blinker(json_obj, ip, old_info, now_mono)
      self._update_command(json_obj, ip)
      self._update_sensors(json_obj, ip, old_info, now_mono)
      self._update_traffic_light(json_obj)
    except Exception:
      pass

  def _update_blinker(self, json_obj: dict, ip: str, old_info: dict, now_mono: float) -> None:
    """Update turn signal state from incoming packet."""
    if "blinker" not in json_obj:
      return
    val = json_obj.get("blinker")
    with lock:
      if val in ["left", "stockleft"]:
        self.shared_data.ext_blinker = BLINKER_LEFT
      elif val in ["right", "stockright"]:
        self.shared_data.ext_blinker = BLINKER_RIGHT
      else:
        self.shared_data.ext_blinker = BLINKER_NONE
      self._blinker_alive = True
      self._blinker_time = now_mono

  def _update_command(self, json_obj: dict, ip: str) -> None:
    """Update carrotCmd/carrotArg command from incoming packet."""
    with lock:
      if "index" in json_obj:
        self.shared_data.cmd_index = int(json_obj.get("index"))
      if "cmd" in json_obj:
        self.shared_data.remote_cmd = str(json_obj.get("cmd") or "")
        self.shared_data.remote_arg = str(json_obj.get("arg") or "")

  def _update_traffic_light(self, json_obj: dict) -> None:
    """Update map-based traffic light state from incoming packet.

    Supported formats:
      {"trafficLight": {"state": 1, "countdown": 25}}
      {"cmd": "TRAFFIC", "arg": "state,countdown", "index": N}
    """
    if "trafficLight" in json_obj:
      tl = json_obj["trafficLight"]
      if isinstance(tl, dict):
        state = int(tl.get("state", 0))
        countdown = int(tl.get("countdown", 0))
      elif isinstance(tl, (list, tuple)) and len(tl) >= 2:
        state = int(tl[0])
        countdown = int(tl[1])
      else:
        return
      with lock:
        self.shared_data.map_traffic_state = state
        self.shared_data.map_traffic_countdown = countdown
        self.shared_data.map_traffic_time = time.monotonic()
      return

    cmd = json_obj.get("cmd", "")
    if cmd == "TRAFFIC":
      arg = json_obj.get("arg", "")
      parts = [p.strip() for p in arg.split(",")]
      if len(parts) >= 1:
        try:
          state = int(parts[0])
          countdown = int(parts[1]) if len(parts) >= 2 else 0
          with lock:
            self.shared_data.map_traffic_state = state
            self.shared_data.map_traffic_countdown = countdown
            self.shared_data.map_traffic_time = time.monotonic()
        except ValueError:
          pass

  def _update_sensors(self, json_obj: dict, ip: str, old_info: dict, now_mono: float) -> None:
    """Update sensor (lidar/camera) blind spot and distance data from incoming packet."""
    left_blind: bool | None = None
    right_blind: bool | None = None
    lidar_lblind: bool | None = None
    lidar_rblind: bool | None = None

    lf_drel: int | None = None
    lb_drel: int | None = None
    rf_drel: int | None = None
    rb_drel: int | None = None

    lf_xrel: int | None = None
    lb_xrel: int | None = None
    rf_xrel: int | None = None
    rb_xrel: int | None = None

    lf_drel_alive = lb_drel_alive = rf_drel_alive = rb_drel_alive = False
    lf_xrel_alive = lb_xrel_alive = rf_xrel_alive = rb_xrel_alive = False

    camera_data = False
    lidar_data = False
    dist_timems: int | None = None

    device = json_obj.get("device", old_info.get("device", ""))

    if "resp" in json_obj:
      resp = json_obj.get("resp")

      if resp == "cam_blind":
        camera_data = True
        left_blind = json_obj.get("left_blind")
        right_blind = json_obj.get("right_blind")

      if resp == "blindspot":
        lidar_data = True
        lidar_id = int(json_obj.get("lidar_id", 0))
        detect_side = json_obj.get("detect_side", 0)
        dist_timems = json_obj.get("dist_time", None)
        lidar_lblind = json_obj.get("lidar_lblind")
        lidar_rblind = json_obj.get("lidar_rblind")

        # Update blind spot immediately if not using dynamic blind spot.
        if self._dynamic_blind_range == 0 and self._dynamic_blind_distance == 0:
          if lidar_lblind is not None and lidar_lblind:
            self.shared_data.lidar_left_blind = True
          if lidar_rblind is not None and lidar_rblind:
            self.shared_data.lidar_right_blind = True

        # Parse distance data.
        for f in ["lf_drel", "lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel"]:
          if f in json_obj:
            val = int(json_obj[f])
            if f.endswith("_drel"):
              if f == "lf_drel":
                lf_drel, lf_drel_alive = val, True
              if f == "lb_drel":
                lb_drel, lb_drel_alive = val, True
              if f == "rf_drel":
                rf_drel, rf_drel_alive = val, True
              if f == "rb_drel":
                rb_drel, rb_drel_alive = val, True
            else:
              if f == "lf_xrel":
                lf_xrel, lf_xrel_alive = val, True
              if f == "lb_xrel":
                lb_xrel, lb_xrel_alive = val, True
              if f == "rf_xrel":
                rf_xrel, rf_xrel_alive = val, True
              if f == "rb_xrel":
                rb_xrel, rb_xrel_alive = val, True

        sd = self.shared_data

        if lidar_id == 0:
          # Left-front.
          if detect_side & 1:
            sd.main_lf_drel = lf_drel
            sd.main_lf_xrel = lf_xrel
            if lf_drel is None:
              lf_drel = old_info.get("lf_drel")
            sd.lf_vrel = self._left_front_target.update(lf_drel, dist_timems)
            self._lb_object_detected = self.is_side_object_risky(
              lf_drel, sd.lf_vrel, sd.v_ego_m,
              self._min_vrel_vego_time, self._min_drel_vego_time
            )

          # Left-rear.
          if detect_side & 1:
            sd.main_lb_drel = lb_drel
            sd.main_lb_xrel = lb_xrel
            if lb_drel is None:
              lb_drel = old_info.get("lb_drel")
            sd.lb_vrel = self._left_behind_target.update(lb_drel, dist_timems)
            self._lf_object_detected = self.is_side_object_risky(
              lb_drel, sd.lb_vrel, sd.v_ego_m,
              self._min_vrel_vego_time, self._min_drel_vego_time
            )

          # Right-front.
          if detect_side & 2:
            sd.main_rf_drel = rf_drel
            sd.main_rf_xrel = rf_xrel
            if rf_drel is None:
              rf_drel = old_info.get("rf_drel")
            sd.rf_vrel = self._right_front_target.update(rf_drel, dist_timems)
            self._rb_object_detected = self.is_side_object_risky(
              rf_drel, sd.rf_vrel, sd.v_ego_m,
              self._min_vrel_vego_time, self._min_drel_vego_time
            )

          # Right-rear.
          if detect_side & 2:
            sd.main_rb_drel = rb_drel
            sd.main_rb_xrel = rb_xrel
            if rb_drel is None:
              rb_drel = old_info.get("rb_drel")
            sd.rb_vrel = self._right_behind_target.update(rb_drel, dist_timems)
            self._rf_object_detected = self.is_side_object_risky(
              rb_drel, sd.rb_vrel, sd.v_ego_m,
              self._min_vrel_vego_time, self._min_drel_vego_time
            )

    if device == "lidar":
      if not lidar_data:
        if lf_drel is None:
          lf_drel = old_info.get("lf_drel")
        if lb_drel is None:
          lb_drel = old_info.get("lb_drel")
        if rf_drel is None:
          rf_drel = old_info.get("rf_drel")
        if rb_drel is None:
          rb_drel = old_info.get("rb_drel")
        if lf_xrel is None:
          lf_xrel = old_info.get("lf_xrel")
        if lb_xrel is None:
          lb_xrel = old_info.get("lb_xrel")
        if rf_xrel is None:
          rf_xrel = old_info.get("rf_xrel")
        if rb_xrel is None:
          rb_xrel = old_info.get("rb_xrel")

      lf_drel_time = now_mono if lf_drel_alive else old_info.get("lf_drel_time", now_mono)
      lb_drel_time = now_mono if lb_drel_alive else old_info.get("lb_drel_time", now_mono)
      rf_drel_time = now_mono if rf_drel_alive else old_info.get("rf_drel_time", now_mono)
      rb_drel_time = now_mono if rb_drel_alive else old_info.get("rb_drel_time", now_mono)
      lf_xrel_time = now_mono if lf_xrel_alive else old_info.get("lf_xrel_time", now_mono)
      lb_xrel_time = now_mono if lb_xrel_alive else old_info.get("lb_xrel_time", now_mono)
      rf_xrel_time = now_mono if rf_xrel_alive else old_info.get("rf_xrel_time", now_mono)
      rb_xrel_time = now_mono if rb_xrel_alive else old_info.get("rb_xrel_time", now_mono)

      # Timeout: clear stale data after 1 second.
      if (now_mono - lf_drel_time) > 1.0 and lf_drel is not None:
        lf_drel = None
      if (now_mono - lb_drel_time) > 1.0 and lb_drel is not None:
        lb_drel = None
      if (now_mono - rf_drel_time) > 1.0 and rf_drel is not None:
        rf_drel = None
      if (now_mono - rb_drel_time) > 1.0 and rb_drel is not None:
        rb_drel = None
      if (now_mono - lf_xrel_time) > 1.0 and lf_xrel is not None:
        lf_xrel = None
      if (now_mono - lb_xrel_time) > 1.0 and lb_xrel is not None:
        lb_xrel = None
      if (now_mono - rf_xrel_time) > 1.0 and rf_xrel is not None:
        rf_xrel = None
      if (now_mono - rb_xrel_time) > 1.0 and rb_xrel is not None:
        rb_xrel = None

      # Blind spot timeout: clear after 2 seconds.
      lidar_lblind_time = old_info.get("lidar_lblind_time", now_mono)
      lidar_rblind_time = old_info.get("lidar_rblind_time", now_mono)
      if (now_mono - lidar_lblind_time) > 2.0 and lidar_lblind is not None:
        lidar_lblind = False
      if (now_mono - lidar_rblind_time) > 2.0 and lidar_rblind is not None:
        lidar_rblind = False

      with lock:
        self._clients[ip] = {
          "port": int(json_obj.get("port", self._broadcast_port)),
          "last_seen": now_mono,
          "device": device,
          "detect_side": json_obj.get("detect_side", old_info.get("detect_side", 0)),
          "dist_time": dist_timems,
          "lidar_lblind": lidar_lblind if lidar_lblind is not None else old_info.get("lidar_lblind", False),
          "lidar_rblind": lidar_rblind if lidar_rblind is not None else old_info.get("lidar_rblind", False),
          "lf_drel": lf_drel,
          "lb_drel": lb_drel,
          "rf_drel": rf_drel,
          "rb_drel": rb_drel,
          "lf_xrel": lf_xrel,
          "lb_xrel": lb_xrel,
          "rf_xrel": rf_xrel,
          "rb_xrel": rb_xrel,
          "lidar_lblind_time": now_mono if lidar_lblind is not None else old_info.get("lidar_lblind_time", now_mono),
          "lidar_rblind_time": now_mono if lidar_rblind is not None else old_info.get("lidar_rblind_time", now_mono),
          "lf_drel_time": lf_drel_time,
          "lb_drel_time": lb_drel_time,
          "rf_drel_time": rf_drel_time,
          "rb_drel_time": rb_drel_time,
          "lf_xrel_time": lf_xrel_time,
          "lb_xrel_time": lb_xrel_time,
          "rf_xrel_time": rf_xrel_time,
          "rb_xrel_time": rb_xrel_time,
        }

    elif device == "camera":
      l_blindspot_time = old_info.get("l_blindspot_time", now_mono)
      r_blindspot_time = old_info.get("r_blindspot_time", now_mono)
      if (now_mono - l_blindspot_time) > 2.0 and left_blind is not None:
        left_blind = False
      if (now_mono - r_blindspot_time) > 2.0 and right_blind is not None:
        right_blind = False

      with lock:
        self._clients[ip] = {
          "port": int(json_obj.get("port", self._broadcast_port)),
          "last_seen": now_mono,
          "device": device,
          "left_blind": left_blind if left_blind is not None else old_info.get("left_blind", False),
          "right_blind": right_blind if right_blind is not None else old_info.get("right_blind", False),
          "l_blindspot_time": now_mono if left_blind is not None else old_info.get("l_blindspot_time", now_mono),
          "r_blindspot_time": now_mono if right_blind is not None else old_info.get("r_blindspot_time", now_mono),
        }

    else:
      with lock:
        self._clients[ip] = {
          "port": int(json_obj.get("port", self._broadcast_port)),
          "last_seen": now_mono,
          "device": device,
        }

  def is_side_object_risky(
    self,
    drel_mm: float | None,
    vrel_mps: float | None,
    v_ego_mps: float | None,
    time_horizon: float = 3.0,
    min_drel_scale: float = 1.0,
  ) -> bool:
    """Determine if a side-lane object poses collision risk.

    Args:
      drel_mm: Relative distance in mm (positive=front, negative=rear).
      vrel_mps: Relative speed in m/s (other_vehicle - ego).
      v_ego_mps: Ego speed in m/s.
      time_horizon: Prediction window in seconds.
      min_drel_scale: Safety distance scale factor.

    Returns:
      True if the object is risky, False otherwise.
    """
    if drel_mm is None or vrel_mps is None or v_ego_mps is None:
      return False

    drel = abs(drel_mm) / 1000.0
    v_other = v_ego_mps + vrel_mps

    if drel_mm > 0:
      closing_speed = max(v_ego_mps - v_other, 0.0)
      danger_dist = max(v_ego_mps * min_drel_scale, 10.0)
    else:
      closing_speed = max(v_other - v_ego_mps, 0.0)
      danger_dist = max(v_ego_mps * min_drel_scale, 15.0)

    future_dist = drel - closing_speed * time_horizon * 3.0

    risk = (
      future_dist < danger_dist or
      drel < danger_dist
    )
    return risk

  def camera_data_timeout(self, ip: str, info: dict) -> None:
    """Clear stale camera blind spot data after 2 seconds of inactivity."""
    now_mono = time.monotonic()
    l_blindspot_time = info.get("l_blindspot_time", now_mono)
    r_blindspot_time = info.get("r_blindspot_time", now_mono)

    if (now_mono - l_blindspot_time) > 2.0:
      info["left_blind"] = False
    if (now_mono - r_blindspot_time) > 2.0:
      info["right_blind"] = False

    with lock:
      old_info = self._clients.get(ip, {})
      if old_info:
        self._clients[ip] = info

  def lidar_data_timeout(self, ip: str, info: dict) -> None:
    """Clear stale lidar distance data after 1 second and blind spot after 2 seconds."""
    now_mono = time.monotonic()

    lf_drel_time = info.get("lf_drel_time", now_mono)
    lb_drel_time = info.get("lb_drel_time", now_mono)
    rf_drel_time = info.get("rf_drel_time", now_mono)
    rb_drel_time = info.get("rb_drel_time", now_mono)
    lf_xrel_time = info.get("lf_xrel_time", now_mono)
    lb_xrel_time = info.get("lb_xrel_time", now_mono)
    rf_xrel_time = info.get("rf_xrel_time", now_mono)
    rb_xrel_time = info.get("rb_xrel_time", now_mono)

    if (now_mono - lf_drel_time) > 1.0:
      info["lf_drel"] = None
    if (now_mono - lb_drel_time) > 1.0:
      info["lb_drel"] = None
    if (now_mono - rf_drel_time) > 1.0:
      info["rf_drel"] = None
    if (now_mono - rb_drel_time) > 1.0:
      info["rb_drel"] = None
    if (now_mono - lf_xrel_time) > 1.0:
      info["lf_xrel"] = None
    if (now_mono - lb_xrel_time) > 1.0:
      info["lb_xrel"] = None
    if (now_mono - rf_xrel_time) > 1.0:
      info["rf_xrel"] = None
    if (now_mono - rb_xrel_time) > 1.0:
      info["rb_xrel"] = None

    lidar_lblind_time = info.get("lidar_lblind_time", now_mono)
    lidar_rblind_time = info.get("lidar_rblind_time", now_mono)

    if (now_mono - lidar_lblind_time) > 2.0:
      info["lidar_lblind"] = False
    if (now_mono - lidar_rblind_time) > 2.0:
      info["lidar_rblind"] = False

    with lock:
      old_info = self._clients.get(ip, {})
      if old_info:
        self._clients[ip] = info

  # ---- message construction --------------------------------------------- #

  def make_navi_message(self) -> str:
    """Build JSON navigation status message for UDP broadcast."""
    msg: dict = {}
    msg['ip'] = self._local_ip_address
    msg['port'] = self._listen_port
    msg['device'] = "op"
    msg['IsOnroad'] = True

    sd = self.shared_data

    if sd.car_state:
      if sd.v_cruise_kph is not None:
        msg['v_cruise_kph'] = sd.v_cruise_kph
      if sd.v_ego_kph is not None:
        msg['v_ego_kph'] = sd.v_ego_kph
      if sd.v_ego is not None:
        msg["vego"] = sd.v_ego
      if sd.a_ego is not None:
        msg["aego"] = self._f2(sd.a_ego)
      if sd.steer_angle is not None:
        msg["steer_angle"] = self._f1(sd.steer_angle)
      if sd.gas_press is not None:
        msg["gas_press"] = sd.gas_press
      if sd.break_press is not None:
        msg["break_press"] = sd.break_press
      if sd.engaged is not None:
        msg["engaged"] = sd.engaged
      if not self._disable_blind_spot:
        if sd.left_blindspot is not None:
          msg["left_blindspot"] = sd.left_blindspot
        if sd.right_blindspot is not None:
          msg["right_blindspot"] = sd.right_blindspot
      else:
        msg["left_blindspot"] = False
        msg["right_blindspot"] = False

    # Lidar speed data.
    if sd.lf_vrel is not None:
      msg["lf_vrel"] = int(sd.lf_vrel * 3.6)
    if sd.rf_vrel is not None:
      msg["rf_vrel"] = int(sd.rf_vrel * 3.6)
    if sd.lb_vrel is not None:
      msg["lb_vrel"] = int(sd.lb_vrel * 3.6)
    if sd.rb_vrel is not None:
      msg["rb_vrel"] = int(sd.rb_vrel * 3.6)

    # Blind spot signals.
    if sd.left_front_blind is not None:
      msg['l_front_blind'] = sd.left_front_blind
    if sd.right_front_blind is not None:
      msg['r_front_blind'] = sd.right_front_blind
    msg['lidar_lblind'] = self.left_blindspot()
    msg['lidar_rblind'] = self.right_blindspot()

    # Radar distance data.
    fields = ["lf_drel", "lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel"]
    all_lidar_ids = set()
    for f in fields:
      all_lidar_ids.update(getattr(sd, f).keys())
    for idx in sorted(all_lidar_ids):
      for field in fields:
        d = getattr(sd, field)
        if idx in d and d[idx] is not None:
          key = field if idx == 0 else f"{field}{idx}"
          msg[key] = d[idx]

    # Device presence flags.
    msg['lidar_l'] = sd.lidar_l
    msg['lidar_r'] = sd.lidar_r
    msg['camera_l'] = sd.camera_l
    msg['camera_r'] = sd.camera_r

    # Road context.
    if sd.roadcate is not None:
      msg['roadcate'] = sd.roadcate
    if sd.lat_a is not None:
      msg['lat_a'] = self._f2(sd.lat_a)
    if sd.max_curve is not None:
      msg['max_curve'] = self._f2(sd.max_curve)

    # Road blocked state.
    msg['blind_enable'] = (sd.lidar_l or sd.camera_l) and (sd.lidar_r or sd.camera_r)
    msg['op_blocked'] = sd.op_blocked
    msg['road_blocked'] = sd.road_blocked

    return json.dumps(msg)

  def make_lidar_message(self) -> str:
    """Build JSON lidar-specific status message for UDP broadcast."""
    msg: dict = {}
    msg['ip'] = self._local_ip_address
    msg['port'] = self._listen_port
    msg['device'] = "op"
    msg['IsOnroad'] = True

    sd = self.shared_data

    if sd.car_state:
      if sd.v_cruise_kph is not None:
        msg['v_cruise_kph'] = sd.v_cruise_kph
      if sd.v_ego_kph is not None:
        msg['v_ego_kph'] = sd.v_ego_kph

    # Cruise state.
    cruise_enable = False
    if sd.selfdrive_active is not None and sd.selfdrive_active:
      cruise_enable = True
    if sd.cruise_valid is not None:
      msg['active'] = sd.cruise_valid
    if cruise_enable:
      msg['active'] = True
    if not msg.get('engaged', False):
      msg['engaged'] = cruise_enable

    return json.dumps(msg)

  def make_blinker_message(self) -> str:
    """Build JSON blinker status message for UDP broadcast."""
    msg: dict = {}
    msg['ip'] = self._local_ip_address
    msg['port'] = self._listen_port
    msg['device'] = "op"
    msg['IsOnroad'] = True

    sd = self.shared_data

    if sd.car_state:
      if sd.v_cruise_kph is not None:
        msg['v_cruise_kph'] = sd.v_cruise_kph
      if sd.v_ego_kph is not None:
        msg['v_ego_kph'] = sd.v_ego_kph
      if sd.v_ego is not None:
        msg["vego"] = sd.v_ego
      if sd.gas_press is not None:
        msg["gas_press"] = sd.gas_press
      if sd.break_press is not None:
        msg["break_press"] = sd.break_press

    # Cruise state.
    cruise_enable = False
    if sd.selfdrive_active is not None and sd.selfdrive_active:
      cruise_enable = True
    if sd.cruise_valid is not None:
      msg['active'] = sd.cruise_valid
    if cruise_enable:
      msg['active'] = True
    if not msg.get('engaged', False):
      msg['engaged'] = cruise_enable

    return json.dumps(msg)

  def make_broadcast_message(self) -> str:
    """Build JSON broadcast announcement message for device discovery."""
    msg: dict = {}
    msg['ip'] = self._local_ip_address
    msg['port'] = self._listen_port
    msg['device'] = "op"
    return json.dumps(msg)

  # ---- network utilities ------------------------------------------------ #

  def navi_get_broadcast_address(self) -> str | None:
    """Get broadcast address for the primary network interface."""
    if PC:
      interfaces = ['wlan0', 'eth0', 'enp0s3', 'br0']
      for iface in interfaces:
        try:
          with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            ip = fcntl.ioctl(
              s.fileno(),
              0x8919,  # SIOCGIFBRDADDR
              struct.pack('256s', iface.encode('utf-8')[:15])
            )[20:24]
            return socket.inet_ntoa(ip)
        except Exception:
          continue
      return "255.255.255.255"
    else:
      iface = b'wlan0'
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        ip = fcntl.ioctl(
          s.fileno(),
          0x8919,
          struct.pack('256s', iface)
        )[20:24]
        return socket.inet_ntoa(ip)
    except (OSError, Exception):
      return None

  def navi_get_local_ip(self) -> str:
    """Get local IP address by connecting to an external host."""
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
      return "0.0.0.0"
