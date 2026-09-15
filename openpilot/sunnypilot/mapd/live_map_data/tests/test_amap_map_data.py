#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


_common_pkg = types.ModuleType("openpilot.common")
_common_pkg.params = MagicMock(Params=MagicMock)
_common_pkg.realtime = MagicMock()
_common_pkg.swaglog = MagicMock(cloudlog=MagicMock())
_common_pkg.constants = types.ModuleType("openpilot.common.constants")
_common_pkg.constants.CV = types.ModuleType("CV")
_common_pkg.constants.CV.KPH_TO_MS = 1.0 / 3.6
sys.modules["openpilot.common"] = _common_pkg
sys.modules["openpilot.common.params"] = _common_pkg.params
sys.modules["openpilot.common.realtime"] = _common_pkg.realtime
sys.modules["openpilot.common.swaglog"] = _common_pkg.swaglog
sys.modules["openpilot.common.constants"] = _common_pkg.constants

_cereal_pkg = types.ModuleType("openpilot.cereal")
_cereal_pkg.messaging = MagicMock()
_cereal_pkg.log = types.ModuleType("openpilot.cereal.log")
_cereal_pkg.log.LiveLocationKalman = MagicMock()
_cereal_pkg.log.LiveLocationKalman.Status = MagicMock(valid=0)
sys.modules["openpilot.cereal"] = _cereal_pkg
sys.modules["openpilot.cereal.messaging"] = _cereal_pkg.messaging
sys.modules["openpilot.cereal.log"] = _cereal_pkg.log

from openpilot.sunnypilot.mapd.live_map_data.amap_map_data import (
  AmapMapData,
  _kph_to_ms,
  _out_of_china,
  wgs84_to_gcj02,
)


class TestWgs84ToGcj02(unittest.TestCase):
  def test_beijing_conversion(self):
    # Tiananmen square WGS-84 -> GCJ-02 (known public test vector).
    lat, lng = wgs84_to_gcj02(39.904211, 116.407395)
    self.assertAlmostEqual(lat, 39.905489, places=5)
    self.assertAlmostEqual(lng, 116.416357, places=5)

  def test_out_of_china_unchanged(self):
    lat, lng = wgs84_to_gcj02(40.7128, -74.0060)  # New York
    self.assertEqual(lat, 40.7128)
    self.assertEqual(lng, -74.0060)


class TestKphToMs(unittest.TestCase):
  def test_conversion(self):
    self.assertAlmostEqual(_kph_to_ms(36.0), 10.0, places=6)


class TestOutOfChina(unittest.TestCase):
  def test_china_inside(self):
    self.assertFalse(_out_of_china(39.9, 116.4))

  def test_china_outside(self):
    self.assertTrue(_out_of_china(35.0, 70.0))


class TestAmapMapDataHelpers(unittest.TestCase):
  def test_offset_position_north(self):
    provider = AmapMapData()
    lat, lng = provider._offset_position(0.0, 0.0, 111320.0, 0.0)
    self.assertAlmostEqual(lat, 1.0, places=3)
    self.assertAlmostEqual(lng, 0.0, places=3)

  def test_parse_speed_int(self):
    self.assertEqual(AmapMapData._parse_speed(80), 80.0)

  def test_parse_speed_string(self):
    self.assertEqual(AmapMapData._parse_speed("60"), 60.0)

  def test_parse_speed_invalid(self):
    self.assertEqual(AmapMapData._parse_speed("fast"), 0.0)

  def test_should_refresh_without_position(self):
    provider = AmapMapData()
    self.assertFalse(provider._should_refresh())


class TestAmapMapDataApiParsing(unittest.TestCase):
  def test_update_road_name(self):
    provider = AmapMapData()
    provider._last_position = (39.9, 116.4)
    result = {
      "status": "1",
      "regeocode": {
        "addressComponent": {
          "street": {"name": "长安街"},
        },
      },
    }
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=result):
      provider._update_road_name("KEY", "116.400000,39.900000")
    self.assertEqual(provider._road_name, "长安街")

  def test_update_speed_limits(self):
    provider = AmapMapData()
    provider._last_position = (39.9, 116.4)
    provider._last_bearing = 0.0
    result = {
      "status": "1",
      "route": {
        "paths": [
          {
            "steps": [
              {"distance": "100", "speed": "80"},
              {"distance": "200", "speed": "60"},
            ],
          },
        ],
      },
    }
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=result):
      provider._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertAlmostEqual(provider._speed_limit, 80.0 / 3.6, places=6)
    self.assertAlmostEqual(provider._next_speed_limit, 60.0 / 3.6, places=6)
    self.assertEqual(provider._next_speed_limit_distance, 200.0)


if __name__ == "__main__":
  unittest.main()
