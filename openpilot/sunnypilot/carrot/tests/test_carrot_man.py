#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
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

  def test_update_raw_populates_navigation(self):
    packet = {
      "nRoadLimitSpeed": 80,
      "nTBTDist": 500,
      "nTBTTurnType": 12,
      "szTBTMainText": "Turn left",
      "nGoPosDist": 12000,
      "szPosRoadName": "Gangnam-daero",
    }
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

  def test_heartbeat_keeps_link_alive_without_overwrite(self):
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
    assert self.mgr._carrot_serv.x_spd_limit == 80
    assert self.mgr._carrot_serv.x_spd_dist == 600
    assert self.mgr._carrot_serv.desired_speed == 80
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

  def test_state_expires_after_timeout(self):
    now = time.monotonic()
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
        "leftLightOn": True,
        "leftLightRemainTime": 8,
      },
    })
    assert self.mgr._carrot_serv.traffic_state == 3
    assert self.mgr._carrot_serv.map_traffic_countdown == 8

  def test_dispatch_navi_unknown_ignored(self):
    # Should not raise.
    self.mgr._dispatch_navi_obj({"foo": "bar"})


if __name__ == "__main__":
  unittest.main()
