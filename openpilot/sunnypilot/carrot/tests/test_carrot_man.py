#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import sys
import time
import types
import unittest
from unittest.mock import MagicMock


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
    ]:
      setattr(self, attr, None)


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


class _FakeList(list):
  def add(self):
    item = MagicMock()
    self.append(item)
    return item


class _FakeMsg:
  def __init__(self, service):
    self.service = service
    self.valid = False
    self.carrotManSP = _FakeCarrotManSP()
    self.navInstructionCarrotSP = _FakeNavInstructionCarrotSP()


class _FakeSubMaster:
  def __init__(self, services):
    self.alive = dict.fromkeys(services, True)
    self._data = {
      "carState": MagicMock(vEgo=0.0, speedLimit=0.0),
      "deviceState": MagicMock(),
      "navInstruction": MagicMock(),
    }

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
  def __init__(self):
    self._store = {"CarrotEnabled": b"1", "CarrotManUdpPort": b"7708"}

  def get_bool(self, key, default=False):
    return self._store.get(key, b"1" if default else b"0") == b"1"

  def get(self, key, return_default=False):
    return self._store.get(key, b"")

  def put(self, key, value):
    self._store[key] = value


_common_pkg = types.ModuleType("openpilot.common")
_common_pkg.params = MagicMock(Params=_FakeParams)
_common_pkg.realtime = MagicMock(Ratekeeper=MagicMock, config_realtime_process=MagicMock())
_common_pkg.swaglog = MagicMock(cloudlog=MagicMock())
sys.modules["openpilot.common"] = _common_pkg
sys.modules["openpilot.common.params"] = _common_pkg.params
sys.modules["openpilot.common.realtime"] = _common_pkg.realtime
sys.modules["openpilot.common.swaglog"] = _common_pkg.swaglog

_cereal_pkg = types.ModuleType("openpilot.cereal")
_cereal_pkg.messaging = _FakeMessaging
sys.modules["openpilot.cereal"] = _cereal_pkg
sys.modules["openpilot.cereal.messaging"] = _FakeMessaging

from openpilot.sunnypilot.carrot.carrot_man import CarrotManager, TURN_TYPE_MAPPING


class TestCarrotManager(unittest.TestCase):
  def setUp(self):
    self.mgr = CarrotManager()

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
    stored = self.mgr.params._store.get("CarrotNaviImage")
    assert stored is not None
    parsed = json.loads(stored)
    assert parsed["show"] is True
    assert parsed["totalMeters"] == 1200.5
    assert parsed["remainRatio"] == 0.75
    assert parsed["ts"] == 1234567890

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


if __name__ == "__main__":
  unittest.main()
