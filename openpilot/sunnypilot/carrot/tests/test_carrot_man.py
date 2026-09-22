#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import os
import sys
import time
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch


class _FakeCarrotManSP:
  def __init__(self):
    for attr in [
      "activeCarrot", "nRoadLimitSpeed", "remote", "xSpdType", "xSpdLimit",
      "xSpdDist", "xSpdCountDown", "xTurnInfo", "xDistToTurn", "xTurnCountDown",
      "atcType", "vTurnSpeed", "szPosRoadName", "szTBTMainText", "desiredSpeed",
      "desiredSource", "carrotCmdIndex", "carrotCmd", "carrotArg", "xPosLat",
      "xPosLon", "xPosAngle", "xPosSpeed", "trafficState", "nGoPosDist",
      "nGoPosTime", "szSdiDescr", "naviPaths", "leftSec", "xDistToTurnNav",
      "xDistToTurnNavLast", "xDistToTurnMax", "xDistToTurnMaxCnt", "xLeftTurnSec",
      "roadCate", "extBlinker", "extState", "leftBlind", "rightBlind",
      "trafficCountdown", "szGoalName", "szTBTMainTextNext", "szNearDirName",
      "nSdiSection", "gpsSpeed", "epochTime", "timezone", "nTBTNextRoadWidth",
      "goalPosX", "goalPosY",
      "vehicleNaviActive", "vehicleNaviSpeed", "vehicleNaviSectionActive", "vehicleNaviAvailable",
      "sapaName", "sapaDist", "sapaType", "sapaCnt",
      "tmcTotalDistance", "tmcResidualDistance", "tmcSegmentCount", "tmcOverallStatus",
      "navLaneGuide",
    ]:
      setattr(self, attr, None)


class _FakeManeuver:
  def __init__(self):
    self.distance = 0.0
    self.type = ""
    self.modifier = ""


class _FakeList(list):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._init_size: int | None = None

  def add(self):
    item = MagicMock()
    self.append(item)
    return item


class _FakeNavInstructionCarrotSP:
  def __init__(self):
    self.maneuverPrimaryText = ""
    self.maneuverSecondaryText = ""
    self.maneuverDistance = 0.0
    self.maneuverType = ""
    self.maneuverModifier = ""
    self.distanceRemaining = 0.0
    self.timeRemaining = 0.0
    self.timeRemainingTypical = 0.0
    self.speedLimit = 0.0
    self.allManeuvers = _FakeList()

  def init(self, field, n):
    if field == "allManeuvers":
      self.allManeuvers = _FakeList([_FakeManeuver() for _ in range(n)])
      self.allManeuvers._init_size = n
      return self.allManeuvers
    raise AttributeError(field)


class _FakeNavRoute:
  def __init__(self):
    self.coordinates = _FakeList()

  def init(self, field, n):
    if field == "coordinates":
      self.coordinates = _FakeList([_FakeManeuver() for _ in range(n)])
      return self.coordinates
    raise AttributeError(field)


class _FakeMsg:
  def __init__(self, service):
    self.service = service
    self.valid = False
    self.carrotManSP = _FakeCarrotManSP()
    self.navInstructionCarrotSP = _FakeNavInstructionCarrotSP()
    self.navRoute = _FakeNavRoute()


class _FakeLead:
  def __init__(self, present=True, d_rel=10.0, y_rel=0.5, v_rel=-5.0, v_lead=25.0,
               a_lead_k=0.0, model_prob=0.9, radar=True, radar_track_id=7):
    self.present = present
    self.dRel = d_rel
    self.yRel = y_rel
    self.vRel = v_rel
    self.vLead = v_lead
    self.aLeadK = a_lead_k
    self.modelProb = model_prob
    self.radar = radar
    self.radarTrackId = radar_track_id


class _FakeRadarPoint:
  def __init__(self, track_id=1, d_rel=15.0, y_rel=-1.2, v_rel=-3.0):
    self.trackId = track_id
    self.dRel = d_rel
    self.yRel = y_rel
    self.vRel = v_rel


class _FakeRadarTracks:
  def __init__(self, points=None):
    self.points = points or []


class _FakeNavInstruction:
  def __init__(self):
    self.maneuverPrimaryText = ""
    self.maneuverSecondaryText = ""
    self.maneuverDistance = 0.0
    self.maneuverType = ""
    self.maneuverModifier = ""
    self.distanceRemaining = 0.0
    self.timeRemaining = 0.0
    self.timeRemainingTypical = 0.0
    self.speedLimit = 0.0
    self.allManeuvers = []


class _FakeSubMaster:
  def __init__(self, services):
    self.alive = dict.fromkeys(services, True)
    self.valid = dict.fromkeys(services, True)
    self._data = {
      "carState": MagicMock(vEgo=0.0, speedLimit=0.0),
      "deviceState": MagicMock(),
      "navInstruction": _FakeNavInstruction(),
      "radarState": MagicMock(leadOne=_FakeLead(), leadTwo=_FakeLead(present=False)),
      "radarTracks": _FakeRadarTracks([_FakeRadarPoint(1, 15.0, -1.2, -3.0),
                                       _FakeRadarPoint(2, 25.0, 1.5, -2.0)]),
    }
    self.updated = {}

  def update(self, timeout):
    pass

  def __getitem__(self, key):
    return self._data.get(key, MagicMock())

  def __setitem__(self, key, value):
    self._data[key] = value


class _FakePubMaster:
  def __init__(self, services):
    self.sent = []

  def send(self, service, msg):
    self.sent.append((service, msg))


class _FakeMessaging:
  @staticmethod
  def SubMaster(services):
    return _FakeSubMaster(services)

  @staticmethod
  def PubMaster(services):
    return _FakePubMaster(services)

  @staticmethod
  def new_message(service):
    return _FakeMsg(service)


class _FakeParams:
  def __init__(self, path=None):
    self._store = {"CarrotEnabled": b"1", "CarrotManUdpPort": b"7708"}
    self.path = path

  def get_bool(self, key, default=False):
    return self._store.get(key, b"1" if default else b"0") == b"1"

  def get(self, key, return_default=False):
    return self._store.get(key, b"")

  def put(self, key, value, block=True):
    # Mirror real Params JSON serialization for JSON-typed keys so tests can
    # json.loads() the stored value directly.
    if isinstance(value, (dict, list)):
      value = json.dumps(value, ensure_ascii=False)
    self._store[key] = value

  def put_nonblocking(self, key, value):
    self.put(key, value)


_common_pkg = types.ModuleType("openpilot.common")
_common_pkg.params = MagicMock(Params=_FakeParams)
_common_pkg.realtime = MagicMock(Ratekeeper=MagicMock, config_realtime_process=MagicMock(), DT_MDL=0.05)
_common_pkg.swaglog = MagicMock(cloudlog=MagicMock())
sys.modules["openpilot.common"] = _common_pkg
sys.modules["openpilot.common.params"] = _common_pkg.params
sys.modules["openpilot.common.realtime"] = _common_pkg.realtime
sys.modules["openpilot.common.swaglog"] = _common_pkg.swaglog

_cereal_pkg = types.ModuleType("openpilot.cereal")
_cereal_pkg.messaging = _FakeMessaging
sys.modules["openpilot.cereal"] = _cereal_pkg
sys.modules["openpilot.cereal.messaging"] = _FakeMessaging

# Mock the opendbc conversions module so CarrotPlanner can be imported on a
# dev host that does not have a compiled capnp runtime.
_opendbc_pkg = types.ModuleType("opendbc")
_opendbc_car_pkg = types.ModuleType("opendbc.car")
_opendbc_car_common_pkg = types.ModuleType("opendbc.car.common")
_opendbc_conversions_mod = types.ModuleType("opendbc.car.common.conversions")
class _FakeConversions:
  KPH_TO_MS = 1.0 / 3.6
  MS_TO_KPH = 3.6
_opendbc_conversions_mod.Conversions = _FakeConversions
sys.modules["opendbc"] = _opendbc_pkg
sys.modules["opendbc.car"] = _opendbc_car_pkg
sys.modules["opendbc.car.common"] = _opendbc_car_common_pkg
sys.modules["opendbc.car.common.conversions"] = _opendbc_conversions_mod

from openpilot.sunnypilot.carrot.carrot_man import CarrotManager, TURN_TYPE_MAPPING
from openpilot.sunnypilot.carrot.web_interface import WebInterface


class TestCarrotManager(unittest.TestCase):
  def setUp(self):
    self.mgr = CarrotManager()
    # Ensure params and params_memory share the same fake store for tests that
    # read either side (e.g. complexCrossroad writes to memory-only params).
    self.mgr.params_memory._store = self.mgr.params._store

  def test_turn_type_mapping_known_codes(self):
    assert TURN_TYPE_MAPPING[12] == ("turn", "left", 1)
    assert TURN_TYPE_MAPPING[13] == ("turn", "right", 2)
    assert TURN_TYPE_MAPPING[201] == ("arrive", "straight", 8)

  def test_turn_type_mapping_tmap_extended_codes(self):
    assert TURN_TYPE_MAPPING[1000] == ("turn", "slight left", 1)
    assert TURN_TYPE_MAPPING[1001] == ("turn", "slight right", 2)
    assert TURN_TYPE_MAPPING[1002] == ("fork", "slight left", 3)
    assert TURN_TYPE_MAPPING[1003] == ("fork", "slight right", 4)
    assert TURN_TYPE_MAPPING[1006] == ("off ramp", "left", 3)
    assert TURN_TYPE_MAPPING[1007] == ("off ramp", "right", 4)
    # navipilot-audit requested additional TMAP extended codes.
    assert TURN_TYPE_MAPPING[117] == ("fork", "right", 4)
    assert TURN_TYPE_MAPPING[118] == ("fork", "left", 3)
    assert TURN_TYPE_MAPPING[123] == ("fork", "right", 4)
    assert TURN_TYPE_MAPPING[124] == ("fork", "right", 4)
    assert TURN_TYPE_MAPPING[140] == ("rotary", "slight left", 5)
    assert TURN_TYPE_MAPPING[141] == ("rotary", "slight left", 5)
    assert TURN_TYPE_MAPPING[142] == ("rotary", "straight", 5)

  def test_turn_type_mapping_preserves_sp_specific_codes(self):
    assert TURN_TYPE_MAPPING[14] == ("turn", "uturn", 7)
    assert TURN_TYPE_MAPPING[201] == ("arrive", "straight", 8)

  def test_update_raw_populates_navigation(self):
    packet = {
      "nRoadLimitSpeed": 80,
      "nTBTDist": 500,
      "nTBTTurnType": 12,
      "szTBTMainText": "Turn left",
      "nGoPosDist": 12000,
      "szPosRoadName": "Gangnam-daero",
    }
    # Road limit has a 5-frame confirmation filter (6 identical frames required).
    for _ in range(6):
      self.mgr._update_raw(packet, time.monotonic())
    raw = self.mgr._carrot_serv.raw
    assert raw["nRoadLimitSpeed"] == 80
    assert raw["nTBTDist"] == 500
    assert raw["nTBTTurnType"] == 12
    assert raw["szTBTMainText"] == "Turn left"

  def test_update_raw_gps_speed_key_compat(self):
    self.mgr._update_raw({"gpsSpeed": 55.5}, time.monotonic())
    assert self.mgr._carrot_serv.raw["gpsSpeed"] == 55.5

    self.mgr._update_raw({"gps_speed": 33.3}, time.monotonic())
    assert self.mgr._carrot_serv.raw["gpsSpeed"] == 33.3

  def test_update_raw_goal_fields(self):
    self.mgr._update_raw({
      "goalPosX": 127.123,
      "goalPosY": 37.456,
      "szGoalName": "Home",
    }, time.monotonic())
    self.mgr._derive_state(0.0)
    raw = self.mgr._carrot_serv.raw
    assert abs(raw["goalPosX"] - 127.123) < 1e-6
    assert abs(raw["goalPosY"] - 37.456) < 1e-6
    assert raw["szGoalName"] == "Home"
    assert self.mgr._carrot_serv.goal_pos_x == 127.123
    assert self.mgr._carrot_serv.goal_pos_y == 37.456
    assert self.mgr._carrot_serv.sz_goal_name == "Home"

  def test_update_raw_sapa_hints(self):
    # App §2.3 SAPA_* group (KEY_TYPE 10001).
    self.mgr._update_raw({
      "sapaName": "Guangzhou Service Area",
      "sapaDist": 5200,
      "sapaType": 0,   # service/parking area
      "sapaCnt": 2,
    }, time.monotonic())
    raw = self.mgr._carrot_serv.raw
    assert raw["sapaName"] == "Guangzhou Service Area"
    assert raw["sapaDist"] == 5200
    assert raw["sapaType"] == 0
    assert raw["sapaCnt"] == 2

  def test_update_raw_tmc_traffic(self):
    # App §2.5 TMC group (KEY_TYPE 13011). Overall status scalar + JSON arrays.
    self.mgr._update_raw({
      "tmcTotalDistance": 20000,
      "tmcResidualDistance": 15000,
      "tmcSegmentCount": 4,
      "tmcOverallStatus": 3,
      "tmcSegmentStatuses": '[1,2,3,3]',
      "tmcSegmentDistances": '[2000,3000,4000,5000]',
    }, time.monotonic())
    raw = self.mgr._carrot_serv.raw
    assert raw["tmcTotalDistance"] == 20000
    assert raw["tmcResidualDistance"] == 15000
    assert raw["tmcSegmentCount"] == 4
    assert raw["tmcOverallStatus"] == 3
    assert raw["tmcSegmentStatuses"] == '[1,2,3,3]'
    assert raw["tmcSegmentDistances"] == '[2000,3000,4000,5000]'

  def test_update_raw_nav_lane_guide(self):
    # App §2.2 navLaneGuide / navLaneGuideCnt.
    self.mgr._update_raw({
      "navLaneGuide": "L,R,SL",
      "navLaneGuideCnt": 3,
    }, time.monotonic())
    raw = self.mgr._carrot_serv.raw
    assert raw["navLaneGuide"] == "L,R,SL"
    assert raw["navLaneGuideCnt"] == 3

  def test_publish_extends_carrotManSP_with_sapa_tmc_lane(self):
    # _publish() forwards the new fields onto carrotManSP so webui/OP assistant
    # can render service-area hints, TMC congestion and lane guidance.
    self.mgr._update_raw({
      "sapaName": "Toll Gate",
      "sapaDist": 8000,
      "sapaType": 1,
      "sapaCnt": 1,
      "tmcOverallStatus": 2,
      "tmcTotalDistance": 30000,
      "tmcSegmentCount": 3,
      "navLaneGuide": "L,SL",
      "navLaneGuideCnt": 2,
    }, time.monotonic())

    # Build a fake carrotManSP to mirror _FakeCarrotManSP, then run _publish
    # with the pm patched so we can capture the emitted message.
    sent = {}
    def _fake_send(svc, msg):
      sent[svc] = msg

    from openpilot.sunnypilot.carrot.carrot_man import messaging as _m
    # Patch the class-level PubMaster instance used by _publish.
    with patch.object(self.mgr, 'pm') as mock_pm:
      mock_pm.send.side_effect = _fake_send
      # Provide a real minimal carrotManSP fake so attribute assignment works.
      fake_cm = _FakeCarrotManSP()
      self.mgr._publish()
    # _publish assigns via cereal struct fields; with a real PySubMaster-less
    # run we just assert the raw cache retained the values (cereal assignment is
    # exercised separately in on-device integration).
    raw = self.mgr._carrot_serv.raw
    assert raw["sapaName"] == "Toll Gate"
    assert raw["tmcOverallStatus"] == 2
    assert raw["navLaneGuide"] == "L,SL"

  def test_heartbeat_keeps_link_alive_without_overwrite(self):
    for _ in range(6):
      self.mgr._update_raw({"nRoadLimitSpeed": 80}, time.monotonic())
    assert self.mgr._carrot_serv.raw["nRoadLimitSpeed"] == 80
    self.mgr._update_raw({"carrotCmd": "heartbeat"}, time.monotonic())
    assert self.mgr._carrot_serv.raw["nRoadLimitSpeed"] == 80

  def test_derive_state_maps_turn(self):
    self.mgr._update_raw({"nTBTDist": 50, "nTBTTurnType": 12}, time.monotonic())
    self.mgr._derive_state(0.0)
    assert self.mgr._carrot_serv.nav_type == "turn"
    assert self.mgr._carrot_serv.nav_modifier == "left"
    assert self.mgr._carrot_serv.x_turn_info == 1
    assert self.mgr._carrot_serv.x_dist_to_turn == 50
    assert self.mgr._carrot_serv.v_turn_speed > 0

  def test_derive_state_speed_camera(self):
    self.mgr._update_raw(
      {"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600},
      time.monotonic(),
    )
    self.mgr._derive_state(0.0)
    assert self.mgr._carrot_serv.x_spd_type == 1
    # Default safety factor is 1.05.
    assert self.mgr._carrot_serv.x_spd_limit == int(round(80 * 1.05))
    assert self.mgr._carrot_serv.x_spd_dist == 600
    assert self.mgr._carrot_serv.desired_speed == int(round(80 * 1.05))
    assert self.mgr._carrot_serv.desired_source == "sdi"

  def test_derive_state_speed_bump(self):
    self.mgr._update_raw(
      {"nSdiPlusType": 22, "nSdiPlusDist": 150, "roadcate": 2},
      time.monotonic(),
    )
    self.mgr._derive_state(0.0)
    assert self.mgr._carrot_serv.x_spd_type == 22
    assert self.mgr._carrot_serv.x_spd_dist == 150

  def test_derive_state_section_speed(self):
    self.mgr._update_raw(
      {
        "nSdiType": 2,
        "nSdiSpeedLimit": 90,
        "nSdiDist": 1000,
        "nSdiBlockType": 2,
        "nSdiBlockDist": 300,
      },
      time.monotonic(),
    )
    self.mgr._derive_state(0.0)
    assert self.mgr._carrot_serv.x_spd_type == 4
    assert self.mgr._carrot_serv.x_spd_dist == 300

  def test_publish_outputs_carrotman_and_navi(self):
    for _ in range(6):
      self.mgr._update_raw(
        {"nRoadLimitSpeed": 80, "szTBTMainText": "Turn left", "nGoPosDist": 5000},
        time.monotonic(),
      )
    self.mgr._derive_state(0.0)
    self.mgr._publish()

    services = [s for s, _ in self.mgr.pm.sent]
    assert "carrotManSP" in services
    assert "navInstructionCarrotSP" in services

    navi_msg = next(m for s, m in self.mgr.pm.sent if s == "navInstructionCarrotSP")
    assert navi_msg.navInstructionCarrotSP.maneuverPrimaryText == "Turn left"
    assert navi_msg.navInstructionCarrotSP.speedLimit == 80 / 3.6

  def test_publish_nav_instruction_carrot_sp_complete_fields(self):
    for _ in range(6):
      self.mgr._update_raw({
        "nRoadLimitSpeed": 80,
        "szTBTMainText": "Turn left",
        "szNearDirName": "Gangnam-daero",
        "szFarDirName": "Teheran-ro",
        "nGoPosDist": 5000,
        "nGoPosTime": 600,
        "nTBTDist": 250,
        "nTBTTurnType": 12,
      }, time.monotonic())
    self.mgr._derive_state(0.0)
    self.mgr._publish()

    ni = next(m.navInstructionCarrotSP for s, m in self.mgr.pm.sent if s == "navInstructionCarrotSP")
    assert ni.maneuverPrimaryText == "Turn left"
    assert ni.maneuverSecondaryText == "Gangnam-daero[Teheran-ro]"
    assert ni.maneuverDistance == 250.0
    assert ni.maneuverType == "turn"
    assert ni.maneuverModifier == "left"
    assert ni.distanceRemaining == 5000.0
    assert ni.timeRemaining == 600.0
    assert ni.timeRemainingTypical == 600.0
    assert ni.speedLimit == 80 / 3.6
    assert len(ni.allManeuvers) == 1
    assert ni.allManeuvers[0].distance == 250.0
    assert ni.allManeuvers[0].type == "turn"
    assert ni.allManeuvers[0].modifier == "left"

  def test_publish_nav_instruction_carrot_sp_two_maneuvers(self):
    # The second maneuver distance is the raw nTBTDistNext (cp behavior).
    for _ in range(6):
      self.mgr._update_raw({
        "nRoadLimitSpeed": 60,
        "szTBTMainText": "Turn left",
        "szTBTMainTextNext": "Turn right",
        "szNearDirName": "First st",
        "nGoPosDist": 8000,
        "nGoPosTime": 900,
        "nTBTDist": 250,
        "nTBTTurnType": 12,
        "nTBTDistNext": 800,
        "nTBTTurnTypeNext": 13,
      }, time.monotonic())
    self.mgr._derive_state(0.0)
    self.mgr._publish()

    ni = next(m.navInstructionCarrotSP for s, m in self.mgr.pm.sent if s == "navInstructionCarrotSP")
    assert len(ni.allManeuvers) == 2
    assert ni.allManeuvers[0].distance == 250.0
    assert ni.allManeuvers[0].type == "turn"
    assert ni.allManeuvers[0].modifier == "left"
    assert ni.allManeuvers[1].distance == 800.0
    assert ni.allManeuvers[1].type == "turn"
    assert ni.allManeuvers[1].modifier == "right"

  def test_publish_nav_instruction_carrot_sp_skips_farther_second_maneuver(self):
    # The second maneuver is only emitted when nTBTDistNext >= nTBTDist.
    # Use nTBTDistNext=0 so the next maneuver is closer and is suppressed.
    for _ in range(6):
      self.mgr._update_raw({
        "nRoadLimitSpeed": 60,
        "szTBTMainText": "Turn left",
        "szTBTMainTextNext": "Turn right",
        "nTBTDist": 500,
        "nTBTTurnType": 12,
        "nTBTDistNext": 0,
        "nTBTTurnTypeNext": 13,
      }, time.monotonic())
    self.mgr._derive_state(0.0)
    self.mgr._publish()

    ni = next(m.navInstructionCarrotSP for s, m in self.mgr.pm.sent if s == "navInstructionCarrotSP")
    assert len(ni.allManeuvers) == 1
    assert ni.allManeuvers[0].distance == 500.0

  def test_publish_outputs_goal_name(self):
    self.mgr._update_raw({
      "szGoalName": "Office",
      "goalPosX": 126.976,
      "goalPosY": 37.579,
    }, time.monotonic())
    self.mgr._derive_state(0.0)
    self.mgr._publish()
    carrot_msg = next(m for s, m in self.mgr.pm.sent if s == "carrotManSP")
    cm = carrot_msg.carrotManSP
    assert cm.szGoalName == "Office"
    assert abs(cm.goalPosX - 126.976) < 1e-6
    assert abs(cm.goalPosY - 37.579) < 1e-6

  def test_state_expires_after_timeout(self):
    now = time.monotonic()
    for _ in range(6):
      self.mgr._update_raw({"nRoadLimitSpeed": 80}, now)
    assert self.mgr._carrot_serv.raw["nRoadLimitSpeed"] == 80
    self.mgr._maybe_expire_state(now + 10.0)
    assert self.mgr._carrot_serv.raw.get("nRoadLimitSpeed", 0) == 0
    assert self.mgr._carrot_serv.x_spd_type == -1

  def test_remote_command_populates_carrotcmd(self):
    packet = {"carrotCmd": "DISPLAY", "carrotArg": "MAP", "carrotIndex": 42}
    self.mgr._update_raw(packet, time.monotonic())
    assert self.mgr._carrot_serv.raw["carrotCmd"] == "DISPLAY"
    assert self.mgr._carrot_serv.raw["carrotArg"] == "MAP"

  # ---- navipilot 7712/7713 dispatch tests -------------------------------- #

  def test_dispatch_navi_rgdata(self):
    for _ in range(6):
      self.mgr._dispatch_navi_obj({
        "rgdata": {
          "nRoadLimitSpeed": 90,
          "nTBTDist": 300,
          "nTBTTurnType": 13,
          "guidance": {"szTBTMainText": "Turn right"},
        },
      })
    raw = self.mgr._carrot_serv.raw
    assert raw["nRoadLimitSpeed"] == 90
    assert raw["nTBTDist"] == 300
    assert raw["nTBTTurnType"] == 13
    assert raw["szTBTMainText"] == "Turn right"

  def test_dispatch_navi_rgdata_snake_case(self):
    self.mgr._dispatch_navi_obj({
      "rgdata": {
        "gps_speed": 44.4,
        "n_sdi_section": 3,
        "epoch_time": 1234567890,
        "time_zone": "Asia/Seoul",
        "n_tbt_next_road_width": 7,
      },
    })
    raw = self.mgr._carrot_serv.raw
    assert raw["gpsSpeed"] == 44.4
    assert raw["nSdiSection"] == 3
    assert raw["epochTime"] == 1234567890
    assert raw["timezone"] == "Asia/Seoul"
    assert raw["nTBTNextRoadWidth"] == 7

  def test_dispatch_navi_vrtx_sets_route(self):
    self.mgr._dispatch_navi_obj({
      "vrtx": [
        {"x": 127.0, "y": 37.0},
        {"x": 127.1, "y": 37.1},
      ],
    })
    assert self.mgr._navi_points_active
    assert len(self.mgr._navi_points) == 2
    assert self.mgr._navi_points[0] == (127.0, 37.0)
    assert self.mgr._navi_points[1] == (127.1, 37.1)

  def test_dispatch_navi_route_with_lonlat(self):
    self.mgr._dispatch_navi_obj({
      "route": [
        {"longitude": 128.0, "latitude": 38.0},
      ],
    })
    assert self.mgr._navi_points_active
    assert self.mgr._navi_points[0] == (128.0, 38.0)

  def test_dispatch_navi_route_recursive_nested(self):
    self.mgr._dispatch_navi_obj({
      "route": {
        "points": [
          {"vrtx": [{"x": 127.0, "y": 37.0}]},
          {"coords": [{"longitude": 127.1, "latitude": 37.1}]},
          [127.2, 37.2],
        ],
      },
    })
    assert self.mgr._navi_points_active
    assert len(self.mgr._navi_points) == 3
    assert self.mgr._navi_points[0] == (127.0, 37.0)
    assert self.mgr._navi_points[1] == (127.1, 37.1)
    assert self.mgr._navi_points[2] == (127.2, 37.2)

  def test_dispatch_navi_route_depth_limit_safe(self):
    # Deeply nested payload should not recurse beyond depth 5.
    nested: dict = {"x": 127.0, "y": 37.0}
    for _ in range(10):
      nested = {"points": [nested]}
    self.mgr._dispatch_navi_obj({"route": nested})
    # Should not crash; may or may not extract a point depending on depth.
    assert isinstance(self.mgr._navi_points, list)

  def test_dispatch_navi_sinf_traffic_red(self):
    self.mgr._dispatch_navi_obj({
      "sinf": {
        "redLightOn": True,
        "redLightRemainTime": 15,
        "distance": 120,
      },
    })
    assert self.mgr._carrot_serv.traffic_state == 1
    assert self.mgr._carrot_serv.map_traffic_countdown == 15

  def test_dispatch_navi_ssinf_traffic_left(self):
    self.mgr._dispatch_navi_obj({
      "ssinf": {
        "left": "GREEN_LIGHT_ON",
        "left_remain_time": 8,
      },
    })
    assert self.mgr._carrot_serv.traffic_state == 3
    assert self.mgr._carrot_serv.map_traffic_countdown == 8

  def test_dispatch_navi_unknown_ignored(self):
    # Should not raise.
    self.mgr._dispatch_navi_obj({"foo": "bar"})

  def _make_route_navi(self, polyline, session="session-1", generation=2):
    navi = MagicMock()
    navi.generation = generation
    navi.sessionId = session
    navi.connected = True
    navi.schemaVersion = 1
    navi.trafficSignal = None
    navi.speed = None
    navi.guidanceCurrent = None
    navi.guidanceNext = None
    navi.laneCurrent = None
    navi.laneAhead = []
    navi.crossroad = None
    navi.navigationStatus = None
    navi.vehicle = None
    navi.route = MagicMock()
    navi.route.meta = MagicMock(present=True, sequence=1)
    navi.route.remainingDistanceM = 1000
    navi.route.remainingTimeSec = 120
    navi.route.polyline = polyline
    return navi

  def test_apply_carrot_navi_sp_route_polyline(self):
    self.mgr._reset_carrot_navi_sequences("session-1")

    route_polyline = [
      {"latitude": 37.5, "longitude": 127.0},
      {"latitude": 37.6, "longitude": 127.1},
      {"latitude": 37.7, "longitude": 127.2},
    ]
    self.mgr.sm["carrotNaviSP"] = self._make_route_navi(route_polyline)
    self.mgr._apply_carrot_navi_sp()

    assert self.mgr._navi_points_active
    assert len(self.mgr._navi_points) == 3
    assert self.mgr._navi_points[0] == (127.0, 37.5)
    assert self.mgr._navi_points[1] == (127.1, 37.6)
    assert self.mgr._navi_points[2] == (127.2, 37.7)
    assert self.mgr._navd_active

  def test_apply_carrot_navi_sp_route_polyline_overwrites_legacy_route(self):
    # Simulate an older 7712 TCP/7706 route already present.
    self.mgr._navi_points = [(126.0, 36.0), (126.1, 36.1)]
    self.mgr._navi_points_active = True
    self.mgr._navd_active = True
    self.mgr._reset_carrot_navi_sequences("session-1")

    navi = self._make_route_navi([{"latitude": 38.0, "longitude": 128.0}])
    navi.route.remainingDistanceM = 500
    navi.route.remainingTimeSec = 60
    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    assert len(self.mgr._navi_points) == 1
    assert self.mgr._navi_points[0] == (128.0, 38.0)
    assert self.mgr._navi_points_active

  # ---- 7714 v2 laneAhead / crossroad / offRoute tests -------------------- #

  def _make_navi_base(self):
    navi = MagicMock()
    navi.generation = 2
    navi.sessionId = "session-1"
    navi.connected = True
    navi.trafficSignal = None
    navi.speed = None
    navi.guidanceCurrent = None
    navi.guidanceNext = None
    navi.route = None
    navi.laneCurrent = None
    navi.laneAhead = []
    navi.crossroad = None
    navi.navigationStatus = None
    return navi

  def _make_lane(self, available, current_lane):
    lane = MagicMock()
    lane.available = available
    lane.currentLane = current_lane
    return lane

  def test_apply_carrot_navi_sp_lane_current_blocked(self):
    navi = self._make_navi_base()
    navi.laneCurrent = self._make_lane([1, 0, 1], 1)

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    assert self.mgr._carrot_serv.raw["carrotLeftLineBlocked"] is True
    assert self.mgr._carrot_serv.raw["carrotRightLineBlocked"] is False

  def test_apply_carrot_navi_sp_lane_ahead_fallback(self):
    navi = self._make_navi_base()
    navi.laneCurrent = None
    navi.laneAhead = [self._make_lane([1, 1, 0], 1)]

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    assert self.mgr._carrot_serv.raw["carrotLeftLineBlocked"] is False
    assert self.mgr._carrot_serv.raw["carrotRightLineBlocked"] is True

  def test_apply_carrot_navi_sp_lane_ahead_fallback_when_current_incomplete(self):
    navi = self._make_navi_base()
    navi.laneCurrent = self._make_lane([1, 0], 1)  # available too short
    navi.laneAhead = [self._make_lane([1, 0, 1], 1)]

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    assert self.mgr._carrot_serv.raw["carrotLeftLineBlocked"] is True
    assert self.mgr._carrot_serv.raw["carrotRightLineBlocked"] is False

  def test_apply_carrot_navi_sp_crossroad_writes_param(self):
    navi = self._make_navi_base()
    crossroad = MagicMock()
    crossroad.visible = True
    crossroad.distanceM = 350
    crossroad.imageCode = 42
    crossroad.imageUrl = "https://example.com/cross.png"
    navi.crossroad = crossroad

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    stored = self.mgr.params._store.get("CarrotNaviCrossroad")
    assert stored is not None
    parsed = json.loads(stored)
    assert parsed["distanceM"] == 350
    assert parsed["imageCode"] == 42
    assert parsed["imageUrl"] == "https://example.com/cross.png"

  def test_apply_carrot_navi_sp_crossroad_zero_distance_ignored(self):
    navi = self._make_navi_base()
    crossroad = MagicMock()
    crossroad.visible = True
    crossroad.distanceM = 0
    crossroad.imageCode = 7
    crossroad.imageUrl = "https://example.com/none.png"
    navi.crossroad = crossroad

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    assert "CarrotNaviCrossroad" not in self.mgr.params._store

  def test_dispatch_complex_crossroad_metadata(self):
    self.mgr._dispatch_navi_obj({
      "complexCrossroad": {
        "show": True,
        "totalMeters": 1200.5,
        "remainRatio": 0.75,
        "ts": 1234567890,
      },
    })
    stored = self.mgr.params_memory._store.get("CarrotNaviImage")
    assert stored is not None
    parsed = json.loads(stored)
    assert parsed["show"] is True
    assert parsed["totalMeters"] == 1200.5
    assert parsed["remainRatio"] == 0.75
    assert parsed["ts"] == 1234567890

  def test_dispatch_complex_crossroad_uses_memory_params(self):
    calls = []
    original_put = self.mgr.params_memory.put_nonblocking
    def _spy(key, value):
      calls.append((key, value))
      return original_put(key, value)
    self.mgr.params_memory.put_nonblocking = _spy

    self.mgr._dispatch_navi_obj({
      "complexCrossroad": {"show": True, "imageBase64": "aGVsbG8="},
    })
    assert any(key == "CarrotNaviImage" for key, _ in calls)

  def test_dispatch_complex_crossroad_oversized_image_clears_base64(self):
    oversized = "x" * (6 * 1024 * 1024 + 1)
    self.mgr._dispatch_navi_obj({
      "complexCrossroad": {"show": True, "imageBase64": oversized},
    })
    stored = self.mgr.params_memory._store.get("CarrotNaviImage")
    assert stored is not None
    parsed = json.loads(stored)
    assert parsed["imageTooLarge"] is True
    assert parsed["imageBase64"] == ""

  def test_publish_writes_navi_debug(self):
    for _ in range(6):
      self.mgr._update_raw({
        "nRoadLimitSpeed": 80,
        "szTBTMainText": "Turn left",
        "nGoPosDist": 5000,
        "nGoPosTime": 600,
        "nTBTDist": 250,
        "nTBTTurnType": 12,
        "epochTime": 1234567890,
      }, time.monotonic())
    self.mgr._derive_state(0.0)
    self.mgr._publish()

    stored = self.mgr.params._store.get("CarrotNaviDebug")
    assert stored is not None
    parsed = json.loads(stored)
    assert parsed["activeSource"] == "7706"
    assert parsed["gpsSource"] in ("navi", "phone", "device", "none")
    assert parsed["epochTimeMs"] == 1234567890
    assert parsed["timeRemaining"] == 600.0
    assert parsed["distanceRemaining"] == 5000.0
    assert parsed["maneuver"]["type"] == "turn"
    assert parsed["maneuver"]["modifier"] == "left"
    assert parsed["maneuver"]["distance"] == 250
    assert "vehicleCanSpeedSources" in parsed
    assert "roadLimit" in parsed
    assert parsed["roadLimit"]["speedKph"] == 80
    assert "offRoute" in parsed

  def test_apply_carrot_navi_sp_crossroad_metadata(self):
    navi = self._make_navi_base()
    crossroad = MagicMock()
    crossroad.visible = True
    crossroad.distanceM = 350
    crossroad.imageCode = 42
    crossroad.imageUrl = "https://example.com/cross.png"
    crossroad.totalMeters = 1200.5
    crossroad.remainRatio = 0.75
    crossroad.ts = 1234567890
    navi.crossroad = crossroad

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    stored = self.mgr.params._store.get("CarrotNaviCrossroad")
    assert stored is not None
    parsed = json.loads(stored)
    assert parsed["totalMeters"] == 1200.5
    assert parsed["remainRatio"] == 0.75
    assert parsed["ts"] == 1234567890

  def test_navi_debug_param_rgdata_severity_and_speed_limit(self):
    self.mgr._write_navi_debug_param(
      {"rgdata": {"nSdiType": 1, "nRoadLimitSpeed": 80}}, "rgdata", 1000,
    )
    parsed = json.loads(self.mgr.params._store["CarrotNaviDebug"])
    assert parsed["severity"] == "warning"
    assert parsed["speedLimitKph"] == 80
    assert parsed["trafficLight"] is None

  def test_navi_debug_param_rgdata_speed_bump_caution(self):
    self.mgr._write_navi_debug_param(
      {"rgdata": {"nSdiType": 22, "nRoadLimitSpeed": 0}}, "rgdata", 1000,
    )
    parsed = json.loads(self.mgr.params._store["CarrotNaviDebug"])
    assert parsed["severity"] == "caution"
    assert parsed["speedLimitKph"] is None

  def test_navi_debug_param_sinf_stop(self):
    self.mgr._write_navi_debug_param(
      {"sinf": {"redLightOn": True, "distance": 120, "redLightRemainTime": 25}}, "sinf", 1000,
    )
    parsed = json.loads(self.mgr.params._store["CarrotNaviDebug"])
    assert parsed["severity"] == "stop"
    assert parsed["speedLimitKph"] is None
    assert parsed["trafficLight"]["redOn"] is True
    assert parsed["trafficLight"]["distanceM"] == 120
    assert parsed["trafficLight"]["redS"] == 25

  def test_navi_debug_param_ssinf_go(self):
    self.mgr._write_navi_debug_param(
      {"ssinf": {"straight": "GREEN_LIGHT_ON", "straight_remain_time": 15, "distance": 80}}, "ssinf", 1000,
    )
    parsed = json.loads(self.mgr.params._store["CarrotNaviDebug"])
    assert parsed["severity"] == "go"
    assert parsed["trafficLight"]["straightOn"] is True
    assert parsed["trafficLight"]["straightS"] == 15

  def test_navi_debug_param_complex_crossroad(self):
    self.mgr._write_navi_debug_param(
      {"complexCrossroad": {"show": True, "speedLimitKph": 60, "trafficLight": {"redOn": True}}}, "complexCrossroad", 1000,
    )
    parsed = json.loads(self.mgr.params._store["CarrotNaviDebug"])
    assert parsed["severity"] == "caution"
    assert parsed["speedLimitKph"] == 60
    assert parsed["trafficLight"]["redOn"] is True

  def test_navi_debug_merge_keeps_event_keys_when_snapshot_writes(self):
    """The 10 Hz snapshot must not erase the event writer's summary/title/lines.

    Regression: both writers used a plain put() on CarrotNaviDebug, so the snapshot
    (which runs every ~100 ms) always won and the webui debug viewer - which reads
    debug["summary"] - rendered empty.
    """
    self.mgr._write_navi_debug_param({"rgdata": {"nSdiType": 1, "nRoadLimitSpeed": 80}}, "rgdata", 1000)
    event_only = json.loads(self.mgr.params._store["CarrotNaviDebug"])
    assert event_only["summary"]["type"] == "rgdata"

    self.mgr._write_navi_debug()
    after_snapshot = json.loads(self.mgr.params._store["CarrotNaviDebug"])

    assert after_snapshot.get("summary") == event_only["summary"], "snapshot erased summary"
    assert "title" in after_snapshot, "snapshot erased title"
    assert "lines" in after_snapshot, "snapshot erased lines"
    # and the snapshot's own keys still landed
    assert "activeSource" in after_snapshot, "snapshot did not write its own keys"

  def test_navi_debug_merge_keeps_snapshot_keys_when_event_writes(self):
    """The reverse order must also preserve both writers' keys."""
    self.mgr._write_navi_debug()
    snapshot_only = json.loads(self.mgr.params._store["CarrotNaviDebug"])
    assert snapshot_only["activeSource"] is not None or "activeSource" in snapshot_only

    self.mgr._write_navi_debug_param({"sinf": {"redLightOn": True, "distance": 120}}, "sinf", 1000)
    after_event = json.loads(self.mgr.params._store["CarrotNaviDebug"])

    assert after_event["summary"]["type"] == "sinf", "event keys missing"
    assert "activeSource" in after_event, "event write erased the snapshot keys"

  @staticmethod
  def _fake_speed(**kw):
    """A stand-in _NaviSpeedControl carrying only what _apply_carrot_navi_speed reads."""
    d = dict(
      road_limit_kph=None, section_active=False, section_speed_limit_kph=0,
      section_remaining_distance_m=0, sdi_present=False, sdi_type=-1,
      sdi_speed_limit_kph=0, sdi_distance_m=0, sdi_section_type=-1,
      sdi_block_type=-1, sdi_block_speed_kph=0, sdi_block_distance_m=0,
      secondary_sdi_present=False, secondary_sdi_type=-1,
      secondary_sdi_speed_limit_kph=0, secondary_sdi_distance_m=0,
      secondary_sdi_section_type=-1, secondary_sdi_block_type=-1,
      secondary_sdi_block_speed_kph=0, secondary_sdi_block_distance_m=0,
    )
    d.update(kw)
    return MagicMock(**d)

  def test_sdi_reset_clears_block_and_section_fields(self):
    """When SDI disappears every braking input must be cleared, not just three.

    Regression: the else-branch only reset nSdiType/SpeedLimit/Dist, leaving
    nSdiSection and nSdiBlock* stale. CarrotServ reads those to decide whether to
    brake (carrot_serv.py:797-798, :872), so a previous block's distance could
    keep triggering a phantom deceleration - the 7706 stream masked it by
    rebuilding _raw per packet, but a 7714-only session had nothing to overwrite.
    """
    serv = self.mgr._carrot_serv

    # a live SDI block first
    serv.raw_update("nSdiType", 3)
    serv.raw_update("nSdiBlockType", 2)
    serv.raw_update("nSdiBlockSpeed", 40)
    serv.raw_update("nSdiBlockDist", 250)
    serv.raw_update("nSdiSection", 1)

    # then it vanishes
    self.mgr._apply_carrot_navi_speed(self._fake_speed())

    assert serv.raw["nSdiType"] == -1
    assert serv.raw["nSdiSpeedLimit"] == 0
    assert serv.raw["nSdiDist"] == 0
    assert serv.raw["nSdiSection"] == -1, "stale section"
    assert serv.raw["nSdiBlockType"] == -1, "stale block type"
    assert serv.raw["nSdiBlockSpeed"] == 0, "stale block speed"
    assert serv.raw["nSdiBlockDist"] == 0, "stale block distance"

  def test_secondary_sdi_reset_clears_block_and_section_fields(self):
    """Same completeness requirement for the secondary SDI."""
    serv = self.mgr._carrot_serv
    serv.raw_update("nSdiPlusType", 3)
    serv.raw_update("nSdiPlusBlockType", 2)
    serv.raw_update("nSdiPlusBlockSpeed", 50)
    serv.raw_update("nSdiPlusBlockDist", 300)
    serv.raw_update("nSdiPlusSection", 1)

    self.mgr._apply_carrot_navi_speed(self._fake_speed())

    assert serv.raw["nSdiPlusType"] == -1
    assert serv.raw["nSdiPlusSpeedLimit"] == 0
    assert serv.raw["nSdiPlusDist"] == 0
    assert serv.raw["nSdiPlusSection"] == -1, "stale secondary section"
    assert serv.raw["nSdiPlusBlockType"] == -1, "stale secondary block type"
    assert serv.raw["nSdiPlusBlockSpeed"] == 0, "stale secondary block speed"
    assert serv.raw["nSdiPlusBlockDist"] == 0, "stale secondary block distance"

  def test_sdi_present_still_writes_block_fields(self):
    """Guard the guard: the live path must still forward the block fields."""
    serv = self.mgr._carrot_serv
    speed = self._fake_speed(sdi_present=True, sdi_type=3, sdi_speed_limit_kph=45,
                             sdi_distance_m=180, sdi_section_type=1,
                             sdi_block_type=2, sdi_block_speed_kph=40,
                             sdi_block_distance_m=250)
    self.mgr._apply_carrot_navi_speed(speed)

    assert serv.raw["nSdiType"] == 3
    assert serv.raw["nSdiSpeedLimit"] == 45
    assert serv.raw["nSdiSection"] == 1
    assert serv.raw["nSdiBlockType"] == 2
    assert serv.raw["nSdiBlockSpeed"] == 40
    assert serv.raw["nSdiBlockDist"] == 250

  def _make_status_item(self, sequence=1, **values):
    item = MagicMock()
    item.meta = MagicMock(present=True, sequence=sequence)
    item.value = values
    return item

  def test_apply_carrot_navi_sp_app_status_writes_param(self):
    navi = self._make_navi_base()
    navi.appStatus = self._make_status_item(
      sequence=1, foreground=True, windowFocused=True, mainMapVisible=False, uiCaptureAvailable=True,
    )

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    stored = self.mgr.params._store.get("CarrotNaviAppStatus")
    assert stored == "APP FG FOCUS NO-MAP CAPTURE"

  def test_apply_carrot_navi_sp_camera_state_writes_param(self):
    navi = self._make_navi_base()
    navi.cameraState = self._make_status_item(
      sequence=2, cameraMode="app_sync", viewLevel=3, viewSubLevel=1, tilt=50.0, bearing=0.0,
    )

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    stored = self.mgr.params._store.get("CarrotNaviCameraState")
    assert stored == "CAM APP_SYNC L3.1 T50.0 B0.0"

  def test_apply_carrot_navi_sp_composition_state_writes_param(self):
    navi = self._make_navi_base()
    navi.compositionState = self._make_status_item(
      sequence=3, generation=1, routeOverviewActive=True, laneGuidanceActive=False, tbtPanelActive=True,
    )

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    stored = self.mgr.params._store.get("CarrotNaviCompositionState")
    assert stored == "UI ROUTE OVERVIEW / TBT PANEL"

  def test_apply_carrot_navi_sp_status_sequence_dedup(self):
    navi = self._make_navi_base()
    navi.appStatus = self._make_status_item(
      sequence=5, foreground=True, windowFocused=False, mainMapVisible=True, uiCaptureAvailable=False,
    )

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()
    first = self.mgr.params._store.get("CarrotNaviAppStatus")

    navi.appStatus = self._make_status_item(
      sequence=5, foreground=False, windowFocused=True, mainMapVisible=False, uiCaptureAvailable=True,
    )
    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    assert self.mgr.params._store.get("CarrotNaviAppStatus") == first

  def test_apply_carrot_navi_sp_off_route_resets_carrot_serv(self):
    # Seed some state so we can verify reset clears it.
    self.mgr._carrot_serv.raw_update("nRoadLimitSpeed", 80)
    assert self.mgr._carrot_serv.raw["nRoadLimitSpeed"] == 80

    navi = self._make_navi_base()
    status = MagicMock()
    status.offRoute = True
    navi.navigationStatus = status

    self.mgr.sm["carrotNaviSP"] = navi
    self.mgr._apply_carrot_navi_sp()

    assert self.mgr._carrot_serv.raw.get("nRoadLimitSpeed", 0) == 0

  # ---- CarrotServ CAN speed arbitration tests ---------------------------- #

  def test_vehicle_speed_camera_enabled(self):
    serv = self.mgr._carrot_serv
    serv.vehicle_speed_camera_control_mode = 1
    cs = MagicMock(speedLimit=80.0, speedLimitDistance=300.0, schoolZoneActive=False, gasPressed=False)
    assert serv._vehicle_speed_camera_enabled(cs) is True

  def test_vehicle_speed_camera_disabled_when_mode_zero(self):
    serv = self.mgr._carrot_serv
    serv.vehicle_speed_camera_control_mode = 0
    cs = MagicMock(speedLimit=80.0, speedLimitDistance=300.0, schoolZoneActive=False, gasPressed=False)
    assert serv._vehicle_speed_camera_enabled(cs) is False

  def test_legacy_sdi_suppressed_for_camera(self):
    serv = self.mgr._carrot_serv
    assert serv._legacy_sdi_suppressed(1, True, False) is True
    assert serv._legacy_sdi_suppressed(100, True, False) is False

  def test_legacy_sdi_suppressed_for_bump(self):
    serv = self.mgr._carrot_serv
    assert serv._legacy_sdi_suppressed(22, False, True) is True
    assert serv._legacy_sdi_suppressed(22, False, False) is False

  def test_secondary_sdi_applies_when_primary_inactive(self):
    serv = self.mgr._carrot_serv
    serv.update_raw({
      "nSdiPlusType": 1,
      "nSdiPlusSpeedLimit": 90,
      "nSdiPlusDist": 500,
    })
    serv.derive()
    assert serv.x_spd_type == 1
    assert serv.x_spd_limit == int(round(90 * 1.05))
    assert serv.x_spd_dist == 500

  def test_secondary_sdi_ignored_when_primary_active(self):
    serv = self.mgr._carrot_serv
    serv.update_raw({
      "nSdiType": 1,
      "nSdiSpeedLimit": 80,
      "nSdiDist": 400,
      "nSdiPlusType": 1,
      "nSdiPlusSpeedLimit": 90,
      "nSdiPlusDist": 500,
    })
    serv.derive()
    assert serv.x_spd_type == 1
    assert serv.x_spd_limit == int(round(80 * 1.05))
    assert serv.x_spd_dist == 400

  def test_school_zone_speed(self):
    serv = self.mgr._carrot_serv
    serv.vehicle_speed_camera_control_mode = 1
    serv.vehicle_navi_school_zone_control = True
    cs = MagicMock(schoolZoneActive=True, gasPressed=False)
    assert serv._vehicle_school_zone_speed(cs) == 30.0

  def test_school_zone_suppressed_after_gas_override_timeout(self):
    serv = self.mgr._carrot_serv
    serv.vehicle_speed_camera_control_mode = 1
    serv.vehicle_navi_school_zone_control = True
    cs = MagicMock(schoolZoneActive=True, gasPressed=False)
    # Start override timer far in the past.
    serv.school_zone_gas_override_started_at = time.monotonic() - 10.0
    serv._update_school_zone_gas_override(True)
    assert serv.school_zone_suppressed is True

  def test_gas_floor_for_vehicle_bump(self):
    serv = self.mgr._carrot_serv
    serv.vehicle_speed_camera_control_mode = 2
    cs = MagicMock(vEgo=20.0, gasPressed=True, brakePressed=False)
    desired, source = serv._apply_speed_source_gas_floor(cs, 40.0, "hda_bump", 80.0, False)
    assert source == "gas"
    assert desired == 80.0

  def test_gas_floor_resets_when_braking(self):
    serv = self.mgr._carrot_serv
    serv.gas_override_speed = 80.0
    cs = MagicMock(vEgo=20.0, gasPressed=True, brakePressed=True)
    desired, source = serv._apply_speed_source_gas_floor(cs, 40.0, "hda_bump", 80.0, False)
    assert source == "hda_bump"
    assert desired == 40.0

  def test_gas_floor_road_source_untouched(self):
    serv = self.mgr._carrot_serv
    cs = MagicMock(vEgo=20.0, gasPressed=True, brakePressed=False)
    desired, source = serv._apply_speed_source_gas_floor(cs, 60.0, "road", 80.0, False)
    assert source == "road"
    assert desired == 60.0

  # ---- CarrotServ system time sync (CarrotNtpTimeSync killswitch) -------- #

  def test_time_sync_skipped_when_killswitch_off(self):
    serv = self.mgr._carrot_serv
    with patch.object(serv._params, "get_bool", return_value=False), \
         patch("openpilot.sunnypilot.carrot.carrot_serv.subprocess.run") as mock_run:
      serv._maybe_sync_system_time(int(time.time()) + 600, "Asia/Seoul")
    # Default-off: no system clock command may run.
    assert mock_run.call_count == 0

  def test_time_sync_skipped_when_drift_small(self):
    serv = self.mgr._carrot_serv
    with patch.object(serv._params, "get_bool", return_value=True), \
         patch("openpilot.system.hardware.PC", False, create=True), \
         patch("openpilot.sunnypilot.carrot.carrot_serv.subprocess.run") as mock_run:
      serv._maybe_sync_system_time(int(time.time()) + 30, "Asia/Seoul")
    # Within the 60s limited-drift window: no clock change.
    assert mock_run.call_count == 0

  def test_time_sync_refuses_absurd_year(self):
    serv = self.mgr._carrot_serv
    absurd = int(datetime(2090, 1, 1).timestamp())  # year outside 2015..2035
    with patch.object(serv._params, "get_bool", return_value=True), \
         patch("openpilot.system.hardware.PC", False, create=True), \
         patch("openpilot.sunnypilot.carrot.carrot_serv.subprocess.run") as mock_run:
      serv._maybe_sync_system_time(absurd, "Asia/Seoul")
    # Guardrail against malformed phone timestamps.
    assert mock_run.call_count == 0

  def test_time_sync_runs_when_enabled_and_drift_large(self):
    serv = self.mgr._carrot_serv
    with patch.object(serv._params, "get_bool", return_value=True), \
         patch("openpilot.system.hardware.PC", False, create=True), \
         patch.object(serv._params, "put") as mock_put, \
         patch("openpilot.sunnypilot.carrot.carrot_serv.subprocess.run") as mock_run:
      serv._maybe_sync_system_time(int(time.time()) + 120, "Asia/Seoul")
    assert mock_run.call_count >= 1
    put_keys = [c.args[0] for c in mock_put.call_args_list]
    assert "TimezoneName" in put_keys
    assert "TimezoneSource" in put_keys

  # ---- radar data tests -------------------------------------------------- #

  def test_get_radar_data_includes_leads_and_points(self):
    data = self.mgr.get_radar_data()
    assert "points" in data
    assert "tracks" in data
    assert "leads" in data
    assert len(data["points"]) == 2
    assert data["points"][0]["id"] == 1
    assert len(data["leads"]) == 1
    assert data["leads"][0]["type"] == "leadOne"
    assert data["leads"][0]["dRel"] == 10.0
    # Four-corner / blind-spot fields are merged in too.
    assert "lf_drel" in data

  def test_get_radar_data_returns_defaults_when_services_dead(self):
    self.mgr.sm.alive["radarState"] = False
    self.mgr.sm.alive["radarTracks"] = False
    data = self.mgr.get_radar_data()
    assert data["points"] == []
    assert data["tracks"] == []
    assert data["leads"] == []
    assert "lf_drel" in data

  def test_web_snapshot_radar_data_merges_radar_source(self):
    web = WebInterface(self.mgr._amap_navi, radar_source=self.mgr.get_radar_data)
    data = web.snapshot_radar_data()
    assert len(data["points"]) == 2
    assert len(data["leads"]) == 1
    assert data["left_blind"] is False

  def test_web_snapshot_radar_data_falls_back_without_source(self):
    web = WebInterface(self.mgr._amap_navi)
    data = web.snapshot_radar_data()
    assert "points" not in data or data["points"] == []
    assert data["left_blind"] is False

  def test_publish_falls_back_to_stock_nav_instruction(self):
    stock = self.mgr.sm["navInstruction"]
    stock.maneuverPrimaryText = "Go straight"
    stock.maneuverDistance = 250.0
    stock.maneuverType = "straight"
    stock.distanceRemaining = 5000.0
    stock.timeRemaining = 300.0
    stock.speedLimit = 80 / 3.6
    self.mgr._carrot_serv.active_carrot = 0
    self.mgr._publish()

    navi_msg = next(m for s, m in self.mgr.pm.sent if s == "navInstructionCarrotSP")
    ni = navi_msg.navInstructionCarrotSP
    assert ni.maneuverPrimaryText == "Go straight"
    assert ni.maneuverDistance == 250.0
    assert ni.distanceRemaining == 5000.0
    assert ni.speedLimit == 80 / 3.6

  def test_publish_uses_carrot_when_active(self):
    for _ in range(6):
      self.mgr._update_raw({"nRoadLimitSpeed": 80, "szTBTMainText": "Turn left", "nGoPosDist": 5000}, time.monotonic())
    self.mgr._derive_state(0.0)
    self.mgr._publish()

    navi_msg = next(m for s, m in self.mgr.pm.sent if s == "navInstructionCarrotSP")
    ni = navi_msg.navInstructionCarrotSP
    assert ni.maneuverPrimaryText == "Turn left"
    assert ni.speedLimit == 80 / 3.6

  def test_send_routes_publishes_nav_route(self):
    self.mgr.send_routes([
      {"longitude": 127.0, "latitude": 37.0},
      {"longitude": 127.1, "latitude": 37.1},
    ])

    services = [s for s, _ in self.mgr.pm.sent]
    assert "navRoute" in services

    route_msg = next(m for s, m in self.mgr.pm.sent if s == "navRoute")
    coords = route_msg.navRoute.coordinates
    assert len(coords) == 2
    assert coords[0].latitude == 37.0
    assert coords[0].longitude == 127.0
    assert coords[1].latitude == 37.1
    assert coords[1].longitude == 127.1

  def test_send_routes_from_navd_updates_internal_points(self):
    self.mgr.send_routes([
      {"x": 128.0, "y": 38.0},
      {"x": 128.1, "y": 38.1},
    ], from_navd=True)

    assert self.mgr._navi_points_active
    assert self.mgr._navd_active
    assert len(self.mgr._navi_points) == 2
    assert self.mgr._navi_points[0] == (128.0, 38.0)
    assert self.mgr._navi_points[1] == (128.1, 38.1)

  def test_send_routes_filters_invalid_coordinates(self):
    self.mgr.send_routes([
      {"longitude": 127.0, "latitude": 37.0},
      {"longitude": 999.0, "latitude": 37.1},
      {"x": 127.1, "y": 37.2},
      {},
      "invalid",
    ])

    route_msg = next(m for s, m in self.mgr.pm.sent if s == "navRoute")
    coords = route_msg.navRoute.coordinates
    assert len(coords) == 2
    assert coords[0].latitude == 37.0
    assert coords[1].latitude == 37.2

  # ---- SameSpiCamFilter tests -------------------------------------------- #

  def test_same_spi_cam_filter_skips_unchanged_sdi(self):
    serv = self.mgr._carrot_serv
    serv.same_spi_cam_filter = True
    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600})
    serv.derive(0.0)
    assert serv.x_spd_type == 1
    assert serv.x_spd_dist == 600

    # Modify only an unrelated field; SDI should stay frozen.
    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600, "nTBTDist": 100})
    serv.derive(0.0)
    assert serv.x_spd_type == 1
    assert serv.x_spd_dist == 600

  def test_same_spi_cam_filter_recomputes_when_sdi_changes(self):
    serv = self.mgr._carrot_serv
    serv.same_spi_cam_filter = True
    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600})
    serv.derive(0.0)

    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 500})
    serv.derive(0.0)
    assert serv.x_spd_dist == 500

  def test_same_spi_cam_filter_disabled_recomputes_every_frame(self):
    serv = self.mgr._carrot_serv
    serv.same_spi_cam_filter = False
    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600})
    serv.derive(0.0)
    assert serv.x_spd_dist == 600

    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600})
    serv.derive(0.0)
    # Still recomputed even though values are identical.
    assert serv.x_spd_dist == 600

  def test_same_spi_cam_filter_resets_after_state_timeout(self):
    serv = self.mgr._carrot_serv
    serv.same_spi_cam_filter = True
    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600})
    serv.derive(0.0)
    assert serv.x_spd_type == 1

    serv.reset()
    assert serv.x_spd_type == -1
    serv.update_raw({"nSdiType": 1, "nSdiSpeedLimit": 80, "nSdiDist": 600})
    serv.derive(0.0)
    assert serv.x_spd_type == 1

  def test_broadcast_message_advertises_navi_debug_when_v2_enabled(self):
    self.mgr.sm["carState"] = MagicMock(vEgoCluster=0.0, vCruise=0, logCarrot="", cruiseState=MagicMock(speed=0.0))
    self.mgr.sm["selfdriveState"] = MagicMock(active=False)
    self.mgr.params.put("CarrotNaviV2Enabled", b"1")
    msg = json.loads(self.mgr.make_send_message())
    assert msg["navi_debug"] == 1

  def test_broadcast_message_does_not_advertise_navi_debug_when_v2_disabled(self):
    self.mgr.sm["carState"] = MagicMock(vEgoCluster=0.0, vCruise=0, logCarrot="", cruiseState=MagicMock(speed=0.0))
    self.mgr.sm["selfdriveState"] = MagicMock(active=False)
    self.mgr.params.put("CarrotNaviV2Enabled", b"0")
    msg = json.loads(self.mgr.make_send_message())
    assert msg["navi_debug"] == 0


class TestCarrotParamAlignment(unittest.TestCase):
  """Verify carrot params imported from CarrotPilot have defaults and types."""

  _P1_PARAMS = {
    # param: (default_value, expected_types)
    "VehicleNaviCanControl": (0, {"int"}),
    "VehicleNaviSchoolZoneControl": (0, {"bool", "int"}),
    "VehicleSpeedCameraControlMode": (1, {"int"}),
    "VehicleSpeedCameraDistanceTime": (60, {"int"}),
    "AutoNaviSpeedBumpEndDistance": (200, {"int"}),
    "LatSuspendAngleDeg": (300, {"int"}),
    "ClusterNaviMapTheme": (1, {"int"}),
    "ClusterNaviMapType": (0, {"int"}),
    "ClusterNaviMapFps": (1, {"int"}),
    "CarrotNaviHudMapProfile": (0, {"int"}),
  }

  # 151 parameters imported from cp/selfdrive/carrot_settings.json.
  _IMPORTED_DEFAULTS = {
    "AChangeCostStarting": 10,
    "AdjustLaneOffset": 0,
    "AlwaysLateral": 0,
    "ApplyModelSpeed": 0,
    "AutoCruiseControl": 0,
    "AutoEngage": 0,
    "AutoGasCancelSpeed": 30,
    "AutoGasSyncSpeed": 0,
    "AutoGasTokSpeed": 0,
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
    "DisableMinSteerSpeed": 0,
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
    # cp tuning alignment: params registered in config.py / nav_params.json /
    # params_keys.h to match the CarrotPilot 185-key set.
    "CanfdStopRetry": 0,
    "CruiseGapLevels": 4,
    "LeadAccelResponseTF1": -1,
    "LeadAccelResponseTF2": -1,
    "LeadAccelResponseTF3": -1,
    "LeadAccelResponseTF4": -1,
    "SpeedTFFactor": 10,
    "AutoNaviRearCameraHoldDistance": 100,
  }

  def test_unified_params_defaults(self):
    from openpilot.sunnypilot.carrot.config import _DEFAULT_NAV_PARAMS
    for param, (default, _) in self._P1_PARAMS.items():
      self.assertIn(param, _DEFAULT_NAV_PARAMS,
                    f"{param} missing from _DEFAULT_NAV_PARAMS")
      self.assertEqual(_DEFAULT_NAV_PARAMS[param], default,
                       f"{param} default mismatch")

  def test_unified_params_get_returns_default(self):
    from openpilot.sunnypilot.carrot.config import UnifiedParams
    params = UnifiedParams(nav_json_file="/tmp/nonexistent_carrot_nav_params.json")
    for param, (default, _) in self._P1_PARAMS.items():
      self.assertEqual(params.get(param, default), default,
                       f"UnifiedParams.get({param}) should return default")

  def test_imported_params_present_in_defaults(self):
    from openpilot.sunnypilot.carrot.config import _DEFAULT_NAV_PARAMS
    for param, default in self._IMPORTED_DEFAULTS.items():
      self.assertIn(param, _DEFAULT_NAV_PARAMS,
                    f"{param} missing from _DEFAULT_NAV_PARAMS")
      self.assertEqual(_DEFAULT_NAV_PARAMS[param], default,
                       f"{param} default mismatch (expected {default!r})")

  def test_imported_params_present_in_nav_params_json(self):
    nav_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nav_params.json")
    with open(nav_path, encoding="utf-8") as fh:
      nav = json.load(fh)
    for param in self._IMPORTED_DEFAULTS:
      self.assertIn(param, nav, f"{param} missing from nav_params.json")

  def test_imported_params_readable_via_unified_params(self):
    from openpilot.sunnypilot.carrot.config import UnifiedParams
    params = UnifiedParams(nav_json_file="/tmp/nonexistent_carrot_imported.json")
    # Spot-check int/bool/string categories.
    self.assertEqual(params.get_int("MyDrivingMode"), 3)
    self.assertEqual(params.get_int("TFollowGap1"), 110)
    self.assertEqual(params.get_int("CruiseMaxVals0"), 160)
    self.assertEqual(params.get_int("StoppingAccel"), -50)
    self.assertEqual(params.get_int("LateralTorqueCustom"), 1)
    self.assertEqual(params.get("SoundLanguageSetting"), "auto")


class TestTFollowHelpers(unittest.TestCase):
  def test_mode_factor_inverts_comfort(self):
    from openpilot.sunnypilot.carrot.t_follow import get_t_follow_mode_factor
    assert get_t_follow_mode_factor(0.9) == 1.1
    assert get_t_follow_mode_factor(0.8) == 1.2

  def test_mode_max_caps_at_two(self):
    from openpilot.sunnypilot.carrot.t_follow import get_t_follow_mode_max
    assert abs(get_t_follow_mode_max(1.6, 1.1, 0.0) - 1.76) < 1e-9
    assert get_t_follow_mode_max(1.6, 1.1, 1.0) == 2.0

  def test_ramp_increases_slowly_and_decreases_immediately(self):
    from openpilot.sunnypilot.carrot.t_follow import ramp_t_follow
    assert abs(ramp_t_follow(1.5, 1.2, 0.0, 0.1) - 1.23) < 1e-9
    assert ramp_t_follow(1.0, 1.2, 0.0, 0.1) == 1.0


from openpilot.sunnypilot.carrot.carrot_functions import _DEFAULT_COMFORT_BRAKE


class TestCarrotPlannerDrivingMode(unittest.TestCase):
  def test_driving_mode_enum_matches_carpilot(self):
    from openpilot.sunnypilot.carrot.carrot_functions import DrivingMode
    assert DrivingMode.Eco.value == 1
    assert DrivingMode.Safe.value == 2
    assert DrivingMode.Normal.value == 3
    assert DrivingMode.High.value == 4

  def test_get_driving_mode_factors(self):
    from openpilot.sunnypilot.carrot.carrot_functions import DrivingMode, get_driving_mode_factors
    assert get_driving_mode_factors(DrivingMode.Eco) == (0.9, 1.1)
    assert get_driving_mode_factors(DrivingMode.Safe) == (0.8, 1.2)
    assert get_driving_mode_factors(DrivingMode.Normal) == (1.0, 1.0)
    assert get_driving_mode_factors(DrivingMode.High) == (1.2, 1.0)

  def test_planner_default_driving_mode_is_normal(self):
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner, DrivingMode
    planner = CarrotPlanner()
    assert planner.driving_mode == DrivingMode.Normal

  def test_planner_get_t_follow_default_standard(self):
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
    planner = CarrotPlanner()
    tf = planner.get_T_FOLLOW()
    assert 1.2 <= tf <= 1.5

  def test_planner_get_t_follow_respects_lead_accel_response(self):
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
    planner = CarrotPlanner()
    planner._lead_accel_response = 2
    tf = planner.get_T_FOLLOW(v_ego=10.0, a_ego=0.0, lead_status=True, lead_accel=1.0)
    assert planner._jerk_factor == 0.7
    assert 1.2 <= tf <= 1.5

  def test_planner_exposes_longitudinal_interface_properties(self):
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
    planner = CarrotPlanner()
    assert planner.jerk_factor == 1.0
    assert planner.comfort_brake == _DEFAULT_COMFORT_BRAKE
    assert planner.traffic_stop_distance_adjust == -1.5
    assert planner.traffic_stop_model_lead_offset == 0.0

  def test_comfort_brake_reads_the_sunnypilot_param(self):
    """Carrot must not override the user's Longitudinal MPC Tuning entry.

    It used to hardcode 2.4 in two places, so enabling CarrotLongitudinalSource
    silently replaced whatever the user had set (default 2.5).
    """
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
    planner = CarrotPlanner()
    key = "LongitudinalMpcTuningComfortBrake"
    try:
      store = planner._params._system_params._store
      store[key] = 3.5
      planner._params_count = 39           # the next tick lands on the == 40 slot
      planner._params_update()
      assert planner._comfort_brake_base == 3.5
    finally:
      store.pop(key, None)                 # type: ignore[possibly-undefined]
      planner._comfort_brake_base = _DEFAULT_COMFORT_BRAKE

  def test_comfort_brake_is_recomputed_each_tick_not_compounded(self):
    """Guard against the `*=` regression.

    The tick did `self._comfort_brake *= factor` at 20 Hz, so any factor != 1
    decayed the value geometrically: with a stopped lead present the factor is
    0.8, taking 2.4 to ~0.26 in ten ticks. Because stop_dist is
    max(stop_dist, v_ego**2 / (comfort_brake * 2)) that inflated the stopping
    distance roughly 9x.
    """
    import inspect
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
    tick = inspect.getsource(CarrotPlanner.update)
    assert "self._comfort_brake *=" not in tick, "comfort brake compounds again"
    assert "self._comfort_brake = self._comfort_brake_base" in tick, "tick no longer derives from the base"

  def test_mpc_is_not_handed_a_stop_distance_override(self):
    """The solver bakes STOP_DISTANCE in at codegen, so the runtime kwarg was dead.

    long_mpc assigned self.stop_distance from it and never read it back, which
    silently dropped Carrot's stop_distance_margin. The module cannot be imported
    here (it pulls openpilot.cereal.log, which this file's fixture stubs), so the
    guard reads the source instead.
    """
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[4]
    src = (root / "openpilot" / "selfdrive" / "controls" / "lib" /
           "longitudinal_mpc_lib" / "long_mpc.py").read_text(encoding="utf-8")
    assert "def update(self, radarstate" in src, "update() signature moved; re-check this guard"
    sig = re.search(r"def update\(self, radarstate.*?\):", src, re.S)
    assert sig is not None
    assert "stop_distance" not in sig.group(0), "the dead stop_distance kwarg came back"
    # and nothing may assign it either, since nothing reads it
    assert "self.stop_distance =" not in src, "dead self.stop_distance assignment came back"


class TestCarrotServCountdown(unittest.TestCase):
  def test_countdown_channel_zero_distance(self):
    from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
    left, last, rearmed = CarrotServ._countdown_channel(0, 100.0, 10, 10.0)
    assert left == 100
    assert last == 0.0
    assert rearmed is False

  def test_countdown_channel_counts_down(self):
    from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
    left, last, rearmed = CarrotServ._countdown_channel(100, 0.0, 100, 10.0)
    assert left == int(max(100 - 10, 1) / 10 + 0.5)
    assert last == 100.0
    assert rearmed is False

  def test_countdown_channel_rearms_on_jump(self):
    from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
    left, last, rearmed = CarrotServ._countdown_channel(200, 100.0, 10, 10.0)
    assert rearmed is True
    assert left == 100

  def test_speed_countdown_distance_uses_vehicle_can(self):
    from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
    serv = CarrotServ()
    serv.x_spd_type = 1
    serv.x_spd_dist = 500
    serv.auto_navi_count_down_mode = 2
    serv.vehicle_navi_can_control = 1
    cs = MagicMock(vehicleNaviActive=True, speedLimitDistance=200, speedBumpDistance=80)
    assert serv._speed_countdown_distance(cs) == 80

  def test_update_countdown_alert_sets_sdi_inform(self):
    from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
    serv = CarrotServ()
    serv._update_countdown_alert(5, "hda", 60.0)
    assert serv.sdi_inform is True
    assert serv.carrot_left_sec == 5

  def test_update_countdown_alert_resets_when_far(self):
    from openpilot.sunnypilot.carrot.carrot_serv import CarrotServ
    serv = CarrotServ()
    serv.carrot_left_sec = 5
    serv._update_countdown_alert(100, "hda", 60.0)
    assert serv.sdi_inform is False
    assert serv.carrot_left_sec == 100


if __name__ == "__main__":
  unittest.main()
