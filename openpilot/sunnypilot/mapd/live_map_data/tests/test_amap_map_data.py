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
  AMAP_DRIVING_SHOW_FIELDS,
  AMAP_FATAL_INFOCODES,
  AMAP_THROTTLE_INFOCODES,
  CURVE_MAX_SPEED_KPH,
  AmapMapData,
  _as_float,
  _as_int,
  _as_text,
  _extract_steps,
  _kph_to_ms,
  _min_curve_speed_kph,
  _out_of_china,
  _parse_polyline,
  _step_distance_m,
  _step_speed_kph,
  wgs84_to_gcj02,
)

_MOD = "openpilot.sunnypilot.mapd.live_map_data.amap_map_data"


def _provider(key: str | None = "KEY", **flags) -> AmapMapData:
  """An AmapMapData with a position and a key, and every feature flag explicit."""
  p = AmapMapData()
  p._last_position = (39.9, 116.4)
  p._last_bearing = 0.0
  p.params.get = MagicMock(return_value=key)
  p.params.get_bool = MagicMock(side_effect=lambda name, *a: bool(flags.get(name, False)))
  p._api_key = key
  p._curve_speed_enabled = flags.get("AmapCurveSpeedEnabled", False)
  p._traffic_light_hint_enabled = flags.get("AmapTrafficLightHintEnabled", False)
  return p


class TestWgs84ToGcj02(unittest.TestCase):
  def test_beijing_conversion(self):
    # Tiananmen square WGS-84 -> GCJ-02.
    #
    # The expected longitude used to be 116.416357, which is ~232 m east of what the
    # algorithm produces. Two independent implementations agree on 116.413637 (this
    # module's function, and a from-scratch reference), and the latitude was equally
    # off. The conversion itself only ever offsets a WGS-84 point by roughly +0.0014
    # deg lat / +0.0062 deg lng here, which is the well-known Tiananmen GCJ-02 shift.
    lat, lng = wgs84_to_gcj02(39.904211, 116.407395)
    self.assertAlmostEqual(lat, 39.905614, places=5)
    self.assertAlmostEqual(lng, 116.413637, places=5)

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


class TestAmapFieldCoercion(unittest.TestCase):
  """Amap returns numbers as strings and uses [] for absent values.

  A bare float() raises on [], and bool is an int subclass, so each of these needs
  explicit handling - otherwise one odd field takes the whole parser down.
  """

  def test_as_float_from_string(self):
    self.assertEqual(_as_float("80"), 80.0)

  def test_as_float_from_number(self):
    self.assertEqual(_as_float(80), 80.0)

  def test_as_float_empty_string(self):
    self.assertEqual(_as_float(""), 0.0)

  def test_as_float_empty_list(self):
    self.assertEqual(_as_float([]), 0.0)

  def test_as_float_rejects_bool(self):
    # True is not 1.0 here - it would silently become a speed.
    self.assertEqual(_as_float(True), 0.0)

  def test_as_float_uses_default(self):
    self.assertEqual(_as_float(None, -1.0), -1.0)

  def test_as_int(self):
    self.assertEqual(_as_int("3"), 3)

  def test_as_int_default(self):
    self.assertEqual(_as_int(None, -1), -1)

  def test_as_text_empty_list(self):
    self.assertEqual(_as_text([]), "")

  def test_as_text_passthrough(self):
    self.assertEqual(_as_text("长安街"), "长安街")

  def test_as_text_joins_multi_value(self):
    self.assertEqual(_as_text(["a", "b"]), "a;b")


class TestAmapMapDataHelpers(unittest.TestCase):
  def test_offset_position_north(self):
    # Converting the result back to metres is the robust check: it does not depend on
    # which Earth radius the implementation happens to use.
    #
    # This previously asserted lat == 1.0 for a 111320 m offset, which is wrong - that
    # would need R = 6378166 m, while _offset_position uses R = 6371000 m, so 111320 m
    # north is 1.001125 deg. Two assertions, both rounding artefacts, not a code fault.
    provider = AmapMapData()
    lat, lng = provider._offset_position(0.0, 0.0, 111320.0, 0.0)
    self.assertAlmostEqual(lat, 1.001125, places=5)
    self.assertAlmostEqual(lng, 0.0, places=6)

  def test_offset_position_round_trips_through_metres(self):
    import math
    provider = AmapMapData()
    for metres in (50.0, 500.0, 2000.0):
      for bearing in (0.0, 90.0, 180.0, 270.0):
        lat, lng = provider._offset_position(39.9, 116.4, metres, bearing)
        # Spherical distance from the original point must equal the requested offset.
        p1, p2 = math.radians(39.9), math.radians(lat)
        dlng = math.radians(lng - 116.4)
        cos_d = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dlng)
        back = 6371000.0 * math.acos(max(-1.0, min(1.0, cos_d)))
        self.assertAlmostEqual(back, metres, delta=max(0.5, metres * 0.001),
                               msg=f"{metres} m at {bearing} deg came back as {back:.2f} m")

  def test_parse_speed_int(self):
    self.assertEqual(AmapMapData._parse_speed(80), 80.0)

  def test_parse_speed_string(self):
    self.assertEqual(AmapMapData._parse_speed("60"), 60.0)

  def test_parse_speed_invalid(self):
    self.assertEqual(AmapMapData._parse_speed("fast"), 0.0)

  def test_should_refresh_without_position(self):
    provider = AmapMapData()
    self.assertFalse(provider._should_refresh())

  def test_should_refresh_without_key(self):
    self.assertFalse(_provider(key=None)._should_refresh())


class TestAmapMapDataApiParsing(unittest.TestCase):
  def test_update_road_name(self):
    # The documented shape is addressComponent.streetNumber.street.
    provider = _provider()
    result = {
      "status": "1",
      "infocode": "10000",
      "regeocode": {
        "addressComponent": {
          "streetNumber": {"street": "长安街"},
        },
      },
    }
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=result):
      provider._update_road_name("KEY", "116.400000,39.900000")
    self.assertEqual(provider._road_name, "长安街")

  def test_update_road_name_legacy_street_object(self):
    # Older payloads carried addressComponent.street as an object with a name.
    provider = _provider()
    result = {
      "status": "1",
      "regeocode": {"addressComponent": {"street": {"name": "阜通东大街"}}},
    }
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=result):
      provider._update_road_name("KEY", "116.400000,39.900000")
    self.assertEqual(provider._road_name, "阜通东大街")

  def test_update_road_name_falls_back_to_township(self):
    provider = _provider()
    result = {
      "status": "1",
      "regeocode": {"addressComponent": {"streetNumber": [], "street": [], "township": "燕园街道"}},
    }
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=result):
      provider._update_road_name("KEY", "116.400000,39.900000")
    self.assertEqual(provider._road_name, "燕园街道")

  def test_regeo_uses_the_documented_default_radius(self):
    # radius is documented 0-3000 with a default of 1000; 100 was needlessly narrow.
    provider = _provider()
    seen = {}

    def capture(url):
      seen["url"] = url
      return {"status": "1", "regeocode": {"addressComponent": {"streetNumber": {"street": "x"}}}}

    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", side_effect=capture):
      provider._update_road_name("KEY", "116.400000,39.900000")
    self.assertIn("radius=1000", seen["url"])
    self.assertIn("extensions=all", seen["url"])

  def test_update_speed_limits(self):
    provider = _provider()
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

  def test_missing_speed_does_not_invent_a_limit(self):
    # A step without `speed` must leave the limit at zero: not raise, not guess.
    provider = _provider()
    result = {"status": "1", "route": {"paths": [{"steps": [{"step_distance": "100", "road_name": "长安街"}]}]}}
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=result):
      provider._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(provider._speed_limit, 0.0)

  def test_malformed_payloads_do_not_raise(self):
    payloads = [
      {"status": "1", "regeocode": "oops"},
      {"status": "1", "regeocode": {}},
      {"status": "1", "route": {"paths": "oops"}},
      {"status": "1", "route": {"paths": [{"steps": "oops"}]}},
      {"status": "1", "route": {"paths": [{"steps": ["oops"]}]}},
      {"status": "1", "route": {"paths": []}},
      {"status": "1", "route": {"paths": [{"steps": [{"distance": "1", "polyline": ";;,;"}]}]}},
    ]
    for payload in payloads:
      provider = _provider(AmapCurveSpeedEnabled=True, AmapTrafficLightHintEnabled=True)
      with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=payload):
        provider._update_road_name("KEY", "116.400000,39.900000")
        provider._update_speed_limits("KEY", "116.400000,39.900000")


class TestAmapTrafficLightHint(unittest.TestCase):
  def _route(self, count="3"):
    return {
      "status": "1",
      "route": {"paths": [{"traffic_lights": count, "steps": [{"distance": "100", "speed": "80"}]}]},
    }

  def test_count_is_read_when_enabled(self):
    provider = _provider(AmapTrafficLightHintEnabled=True)
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=self._route()):
      provider._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(provider._traffic_light_count, 3)
    self.assertEqual(provider.get_traffic_light_count(), 3)

  def test_count_stays_unknown_when_disabled(self):
    provider = _provider(AmapTrafficLightHintEnabled=False)
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=self._route()):
      provider._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(provider._traffic_light_count, -1)
    self.assertEqual(provider.get_traffic_light_count(), -1)

  def test_absent_count_is_unknown(self):
    provider = _provider(AmapTrafficLightHintEnabled=True)
    payload = {"status": "1", "route": {"paths": [{"steps": [{"distance": "100", "speed": "80"}]}]}}
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=payload):
      provider._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(provider._traffic_light_count, -1)


class TestAmapCurveSpeed(unittest.TestCase):
  def test_parse_polyline(self):
    self.assertEqual(_parse_polyline("116.0,39.0;116.001,39.001"),
                     [(39.0, 116.0), (39.001, 116.001)])

  def test_parse_polyline_empty(self):
    self.assertEqual(_parse_polyline(""), [])

  def test_parse_polyline_skips_malformed_chunks(self):
    self.assertEqual(_parse_polyline("116.0;116.001,39.001"), [(39.001, 116.001)])

  def test_straight_road_is_unconstrained(self):
    straight = [(39.9 + i * 0.0009, 116.4) for i in range(10)]
    self.assertEqual(_min_curve_speed_kph(straight, 500.0), CURVE_MAX_SPEED_KPH)

  def test_tight_curve_slows_down(self):
    import math
    tight = []
    for deg in range(0, 90, 3):
      rad = math.radians(deg)
      tight.append((39.9 + 30.0 * math.cos(rad) / 111132.92,
                    116.4 + 30.0 * math.sin(rad) / 85300.0))
    kph = _min_curve_speed_kph(tight, 500.0)
    self.assertLess(kph, 40.0)
    self.assertGreaterEqual(kph, 20.0)  # never below the floor

  def test_curve_speed_is_opt_in(self):
    poly = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in
                    [(39.9000, 116.4000), (39.9015, 116.4000), (39.9030, 116.4000), (39.9045, 116.4000)])
    payload = {"status": "1",
               "route": {"paths": [{"steps": [{"distance": "500", "speed": "80", "polyline": poly}]}]}}

    off = _provider(AmapCurveSpeedEnabled=False)
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=payload):
      off._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(off._curve_speed_limit, 0.0)
    self.assertEqual(off.get_curve_speed_limit(), 0.0)

    on = _provider(AmapCurveSpeedEnabled=True)
    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", return_value=payload):
      on._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(on._curve_speed_limit, CURVE_MAX_SPEED_KPH)


class TestAmapErrorHandling(unittest.TestCase):
  """Amap reports failures as HTTP 200 with status=0 plus an infocode.

  The previous code only checked `status != "1"` and returned, so an invalid key and an
  exhausted quota were indistinguishable, nothing was logged, and the doomed request was
  re-issued at the full refresh rate for the whole drive.
  """

  def _fail(self, infocode, info):
    return {"status": "0", "info": info, "infocode": infocode}

  def test_invalid_key_is_recorded_with_a_reason(self):
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=self._fail("10001", "INVALID_USER_KEY")):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertIn("invalid or expired", p._last_error)
    self.assertEqual(p._last_info_code, "10001")

  def test_invalid_key_backs_off_and_stops_refreshing(self):
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=self._fail("10001", "INVALID_USER_KEY")):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertGreater(p._backoff_until, 0.0)
    self.assertFalse(p._should_refresh(), "a fatal error must stop the retry loop")

  def test_failure_does_not_advance_the_refresh_clock(self):
    # Otherwise a permanently failing call is re-issued at the full refresh rate.
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=self._fail("10001", "INVALID_USER_KEY")):
      p._update_from_api()
    self.assertEqual(p._last_update_mono, 0.0)
    self.assertIsNone(p._last_refresh_position)

  def test_quota_error_is_reported(self):
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=self._fail("10003", "DAILY_QUERY_OVER_LIMIT")):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertIn("daily quota", p._last_error.lower())

  def test_no_roads_nearby_is_not_a_hard_error(self):
    # A legitimate "no data for this position" answer must not trigger a backoff.
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=self._fail("20801", "NO_ROADS_NEARBY")):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(p._backoff_until, 0.0)

  def test_success_clears_the_error(self):
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=self._fail("10001", "INVALID_USER_KEY")):
      p._update_road_name("KEY", "116.400000,39.900000")
    with patch(f"{_MOD}._http_get_json",
               return_value={"status": "1",
                             "regeocode": {"addressComponent": {"streetNumber": {"street": "x"}}}}):
      p._update_road_name("KEY", "116.400000,39.900000")
    self.assertEqual(p._last_error, "")
    self.assertEqual(p._consecutive_failures, 0)

  def test_http_failure_is_recorded(self):
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=None):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertNotEqual(p._last_error, "")

  def test_diagnostics_shape(self):
    p = _provider()
    with patch(f"{_MOD}._http_get_json", return_value=self._fail("10001", "INVALID_USER_KEY")):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    d = p.get_diagnostics()
    self.assertEqual(d["infocode"], "10001")
    self.assertEqual(d["error"], p._last_error)
    self.assertGreaterEqual(d["backoff_s"], 0.0)

  def test_fatal_and_throttle_sets_are_disjoint(self):
    self.assertFalse(AMAP_FATAL_INFOCODES & AMAP_THROTTLE_INFOCODES)



class TestAmapV5Shape(unittest.TestCase):
  """The driving call targets 路径规划2.0 (`/v5/direction/driving`).

  v5 renames the field groups (v3's `extensions` becomes `show_fields`, `distance`
  becomes `step_distance`, `road` becomes `road_name`) and nests `route.paths` one
  level differently, so the parser has to accept either generation. These tests pin
  that down without asserting which fields Amap actually returns - the request is
  made against the documented v5 endpoint, and the response is read either way.
  """

  def test_extract_steps_accepts_a_list(self):
    self.assertEqual(_extract_steps({"steps": [{"a": 1}, {"b": 2}]}), [{"a": 1}, {"b": 2}])

  def test_extract_steps_accepts_a_single_object(self):
    self.assertEqual(_extract_steps({"steps": {"a": 1}}), [{"a": 1}])

  def test_extract_steps_ignores_non_dict_entries(self):
    self.assertEqual(_extract_steps({"steps": [{"a": 1}, "junk", None]}), [{"a": 1}])

  def test_extract_steps_missing(self):
    self.assertEqual(_extract_steps({}), [])

  def test_step_speed_reads_v3_name(self):
    self.assertEqual(_step_speed_kph({"speed": "80"}), 80.0)

  def test_step_speed_reads_limit_speed_aliases(self):
    # Amap documents road speed as `limitSpeed` on its navigation SDK; if a Web
    # response ever carries it under that spelling, it must be picked up.
    self.assertEqual(_step_speed_kph({"limit_speed": "60"}), 60.0)
    self.assertEqual(_step_speed_kph({"speed_limit": "50"}), 50.0)

  def test_step_speed_absent(self):
    self.assertEqual(_step_speed_kph({"instruction": "go"}), 0.0)

  def test_step_distance_reads_both_generations(self):
    self.assertEqual(_step_distance_m({"distance": "100"}), 100.0)
    self.assertEqual(_step_distance_m({"step_distance": "250"}), 250.0)

  def test_step_distance_absent(self):
    self.assertEqual(_step_distance_m({}), 0.0)

  def test_v5_request_uses_show_fields_not_extensions(self):
    provider = _provider()
    seen = {}

    def capture(url):
      seen["url"] = url
      return {"status": "1", "route": {"paths": [{"steps": [{"step_distance": "100"}]}]}}

    with patch("openpilot.sunnypilot.mapd.live_map_data.amap_map_data._http_get_json", side_effect=capture):
      provider._update_speed_limits("KEY", "116.400000,39.900000")

    url = seen["url"]
    self.assertIn("/v5/direction/driving", url)
    self.assertIn("show_fields=", url)
    self.assertNotIn("extensions=", url)
    for group in AMAP_DRIVING_SHOW_FIELDS.split(","):
      self.assertIn(group, url)

  def test_v5_step_distance_is_used_for_the_ahead_distance(self):
    provider = _provider()
    payload = {"status": "1", "route": {"paths": [{
      "steps": [
        {"step_distance": "100", "speed": "80"},
        {"step_distance": "200", "speed": "60"},
      ],
    }]}}
    with patch(f"{_MOD}._http_get_json", return_value=payload):
      provider._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertAlmostEqual(provider._speed_limit, 80.0 / 3.6, places=6)
    self.assertAlmostEqual(provider._next_speed_limit, 60.0 / 3.6, places=6)
    self.assertEqual(provider._next_speed_limit_distance, 200.0)

  def test_paths_delivered_as_a_single_object(self):
    provider = _provider()
    payload = {"status": "1", "route": {"paths": {"steps": [{"step_distance": "10", "speed": "70"}]}}}
    with patch(f"{_MOD}._http_get_json", return_value=payload):
      provider._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertAlmostEqual(provider._speed_limit, 70.0 / 3.6, places=6)

  def test_limits_ever_seen_counts_only_real_limits(self):
    # The counter is the one number that shows whether the speed path produces
    # anything, since Amap documents no road-speed field on either version.
    p = _provider()
    self.assertEqual(p.get_diagnostics()["limits_ever_seen"], 0)

    with patch(f"{_MOD}._http_get_json",
               return_value={"status": "1", "route": {"paths": [{"steps": [{"step_distance": "10"}]}]}}):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(p.get_diagnostics()["limits_ever_seen"], 0, "no speed field -> no count")

    with patch(f"{_MOD}._http_get_json",
               return_value={"status": "1", "route": {"paths": [{"steps": [{"step_distance": "10", "speed": "80"}]}]}}):
      p._update_speed_limits("KEY", "116.400000,39.900000")
    self.assertEqual(p.get_diagnostics()["limits_ever_seen"], 1)


if __name__ == "__main__":
  unittest.main()

