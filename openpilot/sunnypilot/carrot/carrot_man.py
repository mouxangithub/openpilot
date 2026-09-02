#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import math
import socket
import threading

from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
import openpilot.cereal.messaging as messaging


DEFAULT_RATE = 10.  # Hz
UDP_BUFFER_SIZE = 4096
PACKET_TIMEOUT_SEC = 3.0

# Korean TMAP turn-type codes from the CarrotMan app -> (maneuverType, maneuverModifier, xTurnInfo).
# xTurnInfo semantics used by the sunnypilot UI/planner:
#   1=left turn, 2=right turn, 3=left lane change, 4=right lane change,
#   5=rotary, 6=tg, 7=arrive/uturn, 8=straight/arrive.
TURN_TYPE_MAPPING: dict[int, tuple[str, str, int]] = {
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

SDI_SPEED_CAMERA_TYPES = (0, 1, 2, 3, 4, 7, 8, 75, 76)

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
  if isinstance(value, (int, float)) and not math.isnan(value):
    return int(value)
  return default


def _safe_float(value, default: float = 0.0) -> float:
  if isinstance(value, (int, float)) and not math.isnan(value):
    return float(value)
  return default


def _safe_str(value, default: str = "") -> str:
  return default if value is None else str(value)


def _turn_info(turn_type: int) -> tuple[str, str, int]:
  return TURN_TYPE_MAPPING.get(turn_type, ("invalid", "", -1))


class CarrotManager:
  """Receive navigation/ADAS data from the CarrotMan phone app over UDP and
  publish ``carrotManSP`` + ``navInstructionCarrotSP``.

  The daemon also subscribes to the stock ``navInstruction`` and ``carState``
  sockets so it can fall back to the stock route guidance when the CarrotMan app
  is not streaming data.

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

  Unknown fields are ignored so the protocol remains forward-compatible.
  """

  def __init__(self):
    self.params = Params()
    self.sm = messaging.SubMaster(['deviceState', 'carState', 'navInstruction'])
    self.pm = messaging.PubMaster(['carrotManSP', 'navInstructionCarrotSP'])

    self._enabled = False
    self._port = 0

    self._sock: socket.socket | None = None
    self._lock = threading.Lock()
    self._last_packet_mono = 0.0
    self._last_seq: int | None = None
    self._remote_addr: str = ""

    # Raw state from the phone app.
    self._raw = {
      'nRoadLimitSpeed': 0,
      'nSdiType': -1,
      'nSdiSpeedLimit': 0,
      'nSdiDist': 0,
      'nSdiBlockType': -1,
      'nSdiBlockSpeed': 0,
      'nSdiBlockDist': 0,
      'nSdiPlusType': -1,
      'nSdiPlusSpeedLimit': 0,
      'nSdiPlusDist': 0,
      'nSdiPlusBlockType': -1,
      'nSdiPlusBlockSpeed': 0,
      'nSdiPlusBlockDist': 0,
      'nTBTDist': 0,
      'nTBTTurnType': -1,
      'szTBTMainText': "",
      'szNearDirName': "",
      'szFarDirName': "",
      'nTBTDistNext': 0,
      'nTBTTurnTypeNext': -1,
      'szTBTMainTextNext': "",
      'nGoPosDist': 0,
      'nGoPosTime': 0,
      'szPosRoadName': "",
      'vpPosPointLat': 0.0,
      'vpPosPointLon': 0.0,
      'nPosAngle': 0.0,
      'nPosSpeed': 0.0,
      'carrotCmdIndex': 0,
      'carrotCmd': "",
      'carrotArg': "",
      'roadcate': 0,
      'leftBlind': 0,
      'rightBlind': 0,
    }

    # Derived state published every tick.
    self._nav_type = "invalid"
    self._nav_modifier = ""
    self._x_turn_info = -1
    self._x_dist_to_turn = 0
    self._nav_type_next = "invalid"
    self._nav_modifier_next = ""
    self._x_turn_info_next = -1
    self._x_dist_to_turn_next = 0
    self._x_spd_type = -1
    self._x_spd_limit = 0
    self._x_spd_dist = 0
    self._v_turn_speed = 0
    self._desired_speed = 0
    self._desired_source = ""
    self._active_carrot = 0
    self._traffic_state = 0
    self._sz_sdi_descr = ""

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
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('0.0.0.0', port))
        self._sock.setblocking(False)
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

  def _parse_packet(self, data: bytes) -> dict | None:
    try:
      decoded = data.decode('utf-8')
      msg = json.loads(decoded)
      return msg if isinstance(msg, dict) else None
    except Exception:
      return None

  def _update_raw(self, msg: dict, recv_mono: float) -> None:
    seq = msg.get('carrotIndex')
    if isinstance(seq, (int, float)) and not math.isnan(seq):
      seq = int(seq)
      if self._last_seq is not None and 0 <= seq < self._last_seq:
        return
      self._last_seq = seq

    r = self._raw
    r['nRoadLimitSpeed'] = _safe_int(msg.get('nRoadLimitSpeed'), r['nRoadLimitSpeed'])
    r['nSdiType'] = _safe_int(msg.get('nSdiType'), r['nSdiType'])
    r['nSdiSpeedLimit'] = _safe_int(msg.get('nSdiSpeedLimit'), r['nSdiSpeedLimit'])
    r['nSdiDist'] = _safe_int(msg.get('nSdiDist'), r['nSdiDist'])
    r['nSdiBlockType'] = _safe_int(msg.get('nSdiBlockType'), r['nSdiBlockType'])
    r['nSdiBlockSpeed'] = _safe_int(msg.get('nSdiBlockSpeed'), r['nSdiBlockSpeed'])
    r['nSdiBlockDist'] = _safe_int(msg.get('nSdiBlockDist'), r['nSdiBlockDist'])
    r['nSdiPlusType'] = _safe_int(msg.get('nSdiPlusType'), r['nSdiPlusType'])
    r['nSdiPlusSpeedLimit'] = _safe_int(msg.get('nSdiPlusSpeedLimit'), r['nSdiPlusSpeedLimit'])
    r['nSdiPlusDist'] = _safe_int(msg.get('nSdiPlusDist'), r['nSdiPlusDist'])
    r['nSdiPlusBlockType'] = _safe_int(msg.get('nSdiPlusBlockType'), r['nSdiPlusBlockType'])
    r['nSdiPlusBlockSpeed'] = _safe_int(msg.get('nSdiPlusBlockSpeed'), r['nSdiPlusBlockSpeed'])
    r['nSdiPlusBlockDist'] = _safe_int(msg.get('nSdiPlusBlockDist'), r['nSdiPlusBlockDist'])
    r['nTBTDist'] = _safe_int(msg.get('nTBTDist'), r['nTBTDist'])
    r['nTBTTurnType'] = _safe_int(msg.get('nTBTTurnType'), r['nTBTTurnType'])
    r['szTBTMainText'] = _safe_str(msg.get('szTBTMainText'), r['szTBTMainText'])
    r['szNearDirName'] = _safe_str(msg.get('szNearDirName'), r['szNearDirName'])
    r['szFarDirName'] = _safe_str(msg.get('szFarDirName'), r['szFarDirName'])
    r['nTBTDistNext'] = _safe_int(msg.get('nTBTDistNext'), r['nTBTDistNext'])
    r['nTBTTurnTypeNext'] = _safe_int(msg.get('nTBTTurnTypeNext'), r['nTBTTurnTypeNext'])
    r['szTBTMainTextNext'] = _safe_str(msg.get('szTBTMainTextNext'), r['szTBTMainTextNext'])
    r['nGoPosDist'] = _safe_int(msg.get('nGoPosDist'), r['nGoPosDist'])
    r['nGoPosTime'] = _safe_int(msg.get('nGoPosTime'), r['nGoPosTime'])
    r['szPosRoadName'] = _safe_str(msg.get('szPosRoadName'), r['szPosRoadName'])
    if r['szPosRoadName'] == "null":
      r['szPosRoadName'] = ""
    r['vpPosPointLat'] = _safe_float(msg.get('vpPosPointLat'), r['vpPosPointLat'])
    r['vpPosPointLon'] = _safe_float(msg.get('vpPosPointLon'), r['vpPosPointLon'])
    r['nPosAngle'] = _safe_float(msg.get('nPosAngle'), r['nPosAngle'])
    r['nPosSpeed'] = _safe_float(msg.get('nPosSpeed'), r['nPosSpeed'])
    r['roadcate'] = _safe_int(msg.get('roadcate'), r['roadcate'])
    r['leftBlind'] = _safe_int(msg.get('leftBlind'), r['leftBlind'])
    r['rightBlind'] = _safe_int(msg.get('rightBlind'), r['rightBlind'])

    if 'carrotCmd' in msg:
      r['carrotCmdIndex'] = self._last_seq or r['carrotCmdIndex']
      r['carrotCmd'] = _safe_str(msg.get('carrotCmd'))
      r['carrotArg'] = _safe_str(msg.get('carrotArg'))
      cloudlog.info(f"carrot_man: remote cmd={r['carrotCmd']} arg={r['carrotArg']}")

    self._last_packet_mono = recv_mono

  def _derive_state(self) -> None:
    """Convert raw app fields into the derived CarrotManSP fields."""
    r = self._raw

    # TBT turn mapping.
    self._nav_type, self._nav_modifier, self._x_turn_info = _turn_info(r['nTBTTurnType'])
    self._nav_type_next, self._nav_modifier_next, self._x_turn_info_next = _turn_info(r['nTBTTurnTypeNext'])
    self._x_dist_to_turn = r['nTBTDist'] if self._x_turn_info > 0 else 0
    self._x_dist_to_turn_next = 0
    if self._x_turn_info_next > 0:
      self._x_dist_to_turn_next = r['nTBTDist'] + r['nTBTDistNext']

    # SDI -> xSpdType/xSpdLimit/xSpdDist.
    self._sz_sdi_descr = ""
    if r['nSdiType'] in SDI_SPEED_CAMERA_TYPES and r['nSdiSpeedLimit'] > 0:
      self._x_spd_limit = r['nSdiSpeedLimit']
      self._x_spd_dist = r['nSdiDist']
      self._x_spd_type = r['nSdiType']
      if r['nSdiBlockType'] in (2, 3):
        self._x_spd_dist = r['nSdiBlockDist']
        self._x_spd_type = 4
    elif (r['nSdiPlusType'] == 22 or r['nSdiType'] == 22) and r['roadcate'] > 1:
      # Speed bump on non-highway.
      self._x_spd_limit = 25
      self._x_spd_dist = r['nSdiPlusDist'] if r['nSdiPlusType'] == 22 else r['nSdiDist']
      self._x_spd_type = 22
    else:
      self._x_spd_limit = 0
      self._x_spd_type = -1
      self._x_spd_dist = 0

    if self._x_spd_type >= 0:
      self._sz_sdi_descr = f"sdi:{self._x_spd_type}"

    # Curve speed for upcoming turn.
    if self._x_turn_info > 0 and self._x_dist_to_turn > 0:
      table = TURN_SPEED_TABLE.get(self._x_turn_info, [])
      self._v_turn_speed = int(_interpolate_speed(self._x_dist_to_turn, table))
    else:
      self._v_turn_speed = 0

    # Desired speed: prefer active speed event, then turn speed, then road limit.
    v_ego_kph = 0.0
    if self.sm.alive['carState']:
      v_ego_kph = self.sm['carState'].vEgo * 3.6

    self._desired_speed = 0
    self._desired_source = ""
    if self._x_spd_type >= 0 and (self._x_spd_dist > 0 or self._x_spd_type in (100, 101)):
      self._desired_speed = self._x_spd_limit
      self._desired_source = "sdi"
    elif self._v_turn_speed > 0 and self._x_dist_to_turn < 300:
      self._desired_speed = self._v_turn_speed
      self._desired_source = "turn"
    elif r['nRoadLimitSpeed'] >= 30 and v_ego_kph > r['nRoadLimitSpeed'] + 5:
      self._desired_speed = r['nRoadLimitSpeed']
      self._desired_source = "limit"

    # activeCarrot mirrors the reference semantics:
    #   0 = inactive, 1 = enabled but no navi event, 2 = active event.
    self._active_carrot = 1 if self._enabled else 0
    if self._x_spd_type >= 0 or self._x_turn_info > 0 or r['nGoPosDist'] > 0:
      self._active_carrot = 2 if self._enabled else 0

    # trafficState is a placeholder; the reference derives it from signal data.
    self._traffic_state = 0

  def _maybe_expire_state(self, now_mono: float) -> None:
    if self._last_packet_mono == 0.0:
      return
    if now_mono - self._last_packet_mono > PACKET_TIMEOUT_SEC:
      self._reset_state()
      cloudlog.info("carrot_man: state expired due to packet timeout")

  def _reset_state(self) -> None:
    self._raw = {
      'nRoadLimitSpeed': 0,
      'nSdiType': -1,
      'nSdiSpeedLimit': 0,
      'nSdiDist': 0,
      'nSdiBlockType': -1,
      'nSdiBlockSpeed': 0,
      'nSdiBlockDist': 0,
      'nSdiPlusType': -1,
      'nSdiPlusSpeedLimit': 0,
      'nSdiPlusDist': 0,
      'nSdiPlusBlockType': -1,
      'nSdiPlusBlockSpeed': 0,
      'nSdiPlusBlockDist': 0,
      'nTBTDist': 0,
      'nTBTTurnType': -1,
      'szTBTMainText': "",
      'szNearDirName': "",
      'szFarDirName': "",
      'nTBTDistNext': 0,
      'nTBTTurnTypeNext': -1,
      'szTBTMainTextNext': "",
      'nGoPosDist': 0,
      'nGoPosTime': 0,
      'szPosRoadName': "",
      'vpPosPointLat': 0.0,
      'vpPosPointLon': 0.0,
      'nPosAngle': 0.0,
      'nPosSpeed': 0.0,
      'carrotCmdIndex': 0,
      'carrotCmd': "",
      'carrotArg': "",
      'roadcate': 0,
      'leftBlind': 0,
      'rightBlind': 0,
    }
    self._last_packet_mono = 0.0
    self._last_seq = None
    self._nav_type = "invalid"
    self._nav_modifier = ""
    self._x_turn_info = -1
    self._x_dist_to_turn = 0
    self._nav_type_next = "invalid"
    self._nav_modifier_next = ""
    self._x_turn_info_next = -1
    self._x_dist_to_turn_next = 0
    self._x_spd_type = -1
    self._x_spd_limit = 0
    self._x_spd_dist = 0
    self._v_turn_speed = 0
    self._desired_speed = 0
    self._desired_source = ""
    self._active_carrot = 0
    self._traffic_state = 0
    self._sz_sdi_descr = ""

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

  def _publish(self) -> None:
    r = self._raw

    carrot_msg = messaging.new_message('carrotManSP')
    carrot_msg.valid = True
    cm = carrot_msg.carrotManSP
    cm.activeCarrot = self._active_carrot
    cm.nRoadLimitSpeed = r['nRoadLimitSpeed']
    cm.remote = self._remote_addr
    cm.xSpdType = self._x_spd_type
    cm.xSpdLimit = self._x_spd_limit
    cm.xSpdDist = self._x_spd_dist
    cm.xSpdCountDown = 0
    cm.xTurnInfo = self._x_turn_info
    cm.xDistToTurn = self._x_dist_to_turn
    cm.xTurnCountDown = 0
    cm.atcType = ""
    cm.vTurnSpeed = self._v_turn_speed
    cm.szPosRoadName = r['szPosRoadName']
    cm.szTBTMainText = r['szTBTMainText']
    cm.desiredSpeed = self._desired_speed
    cm.desiredSource = self._desired_source
    cm.carrotCmdIndex = r['carrotCmdIndex']
    cm.carrotCmd = r['carrotCmd']
    cm.carrotArg = r['carrotArg']
    cm.xPosLat = r['vpPosPointLat']
    cm.xPosLon = r['vpPosPointLon']
    cm.xPosAngle = r['nPosAngle']
    cm.xPosSpeed = r['nPosSpeed']
    cm.trafficState = self._traffic_state
    cm.nGoPosDist = r['nGoPosDist']
    cm.nGoPosTime = r['nGoPosTime']
    cm.szSdiDescr = self._sz_sdi_descr
    cm.naviPaths = ""
    cm.leftSec = 0
    cm.xDistToTurnNav = self._x_dist_to_turn
    cm.xDistToTurnNavLast = self._x_dist_to_turn_next
    cm.xDistToTurnMax = self._x_dist_to_turn
    cm.xDistToTurnMaxCnt = 0
    cm.xLeftTurnSec = 0
    cm.roadCate = r['roadcate']
    cm.extBlinker = 0
    cm.extState = 0
    cm.leftBlind = r['leftBlind']
    cm.rightBlind = r['rightBlind']
    cm.trafficCountdown = 0
    cm.szGoalName = ""
    cm.szTBTMainTextNext = r['szTBTMainTextNext']
    cm.szNearDirName = r['szNearDirName']

    navi_msg = messaging.new_message('navInstructionCarrotSP')
    navi_msg.valid = True
    ni = navi_msg.navInstructionCarrotSP
    ni.maneuverPrimaryText = r['szTBTMainText']
    ni.maneuverSecondaryText = ""
    ni.maneuverDistance = float(self._x_dist_to_turn)
    ni.maneuverType = self._nav_type
    ni.maneuverModifier = self._nav_modifier
    ni.distanceRemaining = float(r['nGoPosDist'])
    ni.timeRemaining = float(r['nGoPosTime'])
    ni.timeRemainingTypical = float(r['nGoPosTime'])
    ni.speedLimit = float(r['nRoadLimitSpeed'] / 3.6) if r['nRoadLimitSpeed'] > 0 else 0.0

    # Build the allManeuvers list (current + next) when data is available.
    if self._x_turn_info > 0:
      m0 = ni.allManeuvers.add()
      m0.distance = float(self._x_dist_to_turn)
      m0.type = self._nav_type
      m0.modifier = self._nav_modifier
    if self._x_turn_info_next > 0:
      m1 = ni.allManeuvers.add()
      m1.distance = float(self._x_dist_to_turn_next)
      m1.type = self._nav_type_next
      m1.modifier = self._nav_modifier_next

    self.pm.send('carrotManSP', carrot_msg)
    self.pm.send('navInstructionCarrotSP', navi_msg)

  def _mono_now(self) -> float:
    import time as _time
    return _time.monotonic()

  def tick(self) -> None:
    self._enabled = self.params.get_bool("CarrotEnabled")
    self._port = self.params.get("CarrotManUdpPort", return_default=True) or 0

    self.sm.update(0)

    if not self._enabled or self._port <= 0:
      self._close_socket()
      return

    if not self._ensure_socket(self._port):
      return

    self._drain_packets()
    now = self._mono_now()
    self._maybe_expire_state(now)
    self._derive_state()
    self._publish()


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
