"""Where the weather state comes from, and how long an answer stays good.

The offsets in `selfdrive.controls.lib.weather_offsets` were ported first and
the network lookup was not, so `WeatherState` had no writer and the feature
did nothing unless somebody typed a param by hand. This module is that writer
minus the side effects: everything here decides, nothing here writes, so the
whole schedule can be replayed at any clock speed.

The last test compares the WMO table against StarPilot's two-step translation
(WMO -> OpenWeatherMap id -> category range). That is what makes this a port
rather than a reinterpretation of the weather.
"""
import unittest

from openpilot.selfdrive.controls.lib.weather_offsets import state_from_wmo_code
from openpilot.sunnypilot.carrot.server.services.weather import auto_detect_enabled
from openpilot.sunnypilot.carrot.weather import (
  DEFAULT_INTERVAL_S, DEFAULT_RETRY_INTERVAL_S, OPEN_METEO_URL, Reading, WeatherPoller,
  build_url, fetch_open_meteo, haversine_km, parse_reading, position_from_raw, usable_position,
)

# StarPilot: starpilot/controls/lib/weather_checker.py, both tables verbatim.
STARPILOT_WMO_TO_OWM = {
  0: 800, 1: 801, 2: 802, 3: 803, 45: 741, 48: 741,
  51: 300, 53: 301, 55: 302, 56: 311, 57: 312,
  61: 500, 63: 501, 65: 502, 66: 511, 67: 511,
  71: 600, 73: 601, 75: 602, 77: 600,
  80: 520, 81: 521, 82: 522, 85: 620, 86: 621,
  95: 200, 96: 201, 99: 202,
}
STARPILOT_CATEGORIES = (
  ("rain", ((300, 321), (500, 504))),
  ("rain_storm", ((200, 232), (511, 511), (520, 531))),
  ("snow", ((600, 622),)),
  ("low_visibility", ((701, 762),)),
  ("clear", ((800, 800),)),
)


def _starpilot_state(wmo_code):
  """What StarPilot's classifier concludes, in StarPilot's own order."""
  owm_id = STARPILOT_WMO_TO_OWM.get(wmo_code, 800)
  for suffix, ranges in STARPILOT_CATEGORIES:
    if any(start <= owm_id <= end for start, end in ranges):
      return suffix
  return "clear"


class TestStateFromWmoCode(unittest.TestCase):
  def test_every_code_starpilot_knows_agrees_with_starpilot(self):
    for code in sorted(STARPILOT_WMO_TO_OWM):
      self.assertEqual(_starpilot_state(code), state_from_wmo_code(code), f"WMO {code}")

  def test_an_unmapped_code_is_clear(self):
    """StarPilot defaults an unknown code to OWM 800, which is clear."""
    for code in (4, 44, 100, 999):
      self.assertEqual(_starpilot_state(code), state_from_wmo_code(code), f"WMO {code}")

  def test_the_shower_codes_are_storms_not_rain(self):
    """80-82 are rain showers, but StarPilot files them under rain_storm."""
    for code in (80, 81, 82, 95, 99):
      self.assertEqual("rain_storm", state_from_wmo_code(code), f"WMO {code}")

  def test_a_cloudy_sky_is_clear(self):
    """Only OWM 800 is clear in StarPilot; 801-803 fall through to the default."""
    for code in (0, 1, 2, 3):
      self.assertEqual("clear", state_from_wmo_code(code), f"WMO {code}")

  def test_malformed_codes_are_clear(self):
    for bad in (None, "61", 61.0, True, [], {}):
      self.assertEqual("clear", state_from_wmo_code(bad), repr(bad))


class TestUsablePosition(unittest.TestCase):
  def test_a_real_fix_passes_through_as_floats(self):
    self.assertEqual((37.5, 127.0), usable_position(37.5, 127.0))
    self.assertEqual((37.0, 127.0), usable_position(37, 127))

  def test_the_null_island_is_refused(self):
    self.assertIsNone(usable_position(0.0, 0.0))

  def test_out_of_range_is_refused(self):
    self.assertIsNone(usable_position(91.0, 0.0))
    self.assertIsNone(usable_position(0.0, 181.0))

  def test_non_finite_is_refused(self):
    self.assertIsNone(usable_position(float("nan"), 127.0))
    self.assertIsNone(usable_position(37.5, float("inf")))
    self.assertIsNone(usable_position(None, 127.0))


class TestHaversine(unittest.TestCase):
  def test_a_known_distance(self):
    """Seoul to Busan is about 325 km."""
    self.assertAlmostEqual(325.0, haversine_km(37.5665, 126.9780, 35.1796, 129.0756), delta=2.0)

  def test_the_same_point_is_zero(self):
    self.assertAlmostEqual(0.0, haversine_km(37.5, 127.0, 37.5, 127.0), places=6)


class TestPositionFromRaw(unittest.TestCase):
  """`LastGPSPosition` is a JSON string, but the store may hand back bytes."""

  def test_the_normal_shape(self):
    self.assertEqual((37.5, 127.0), position_from_raw('{"latitude": 37.5, "longitude": 127.0}'))

  def test_bytes_are_decoded(self):
    self.assertEqual((37.5, 127.0), position_from_raw(b'{"latitude": 37.5, "longitude": 127.0}'))

  def test_an_already_decoded_dict_is_accepted(self):
    self.assertEqual((37.5, 127.0), position_from_raw({"latitude": 37.5, "longitude": 127.0}))

  def test_extra_keys_are_ignored(self):
    """mapd also writes a bearing; it is not this module's business."""
    raw = '{"latitude": 37.5, "longitude": 127.0, "bearing": 91.5}'
    self.assertEqual((37.5, 127.0), position_from_raw(raw))

  def test_no_fix_yet(self):
    for empty in ("", "{}", b"", None, "null", "[]", 3, []):
      self.assertIsNone(position_from_raw(empty), repr(empty))

  def test_unparseable_is_not_an_error(self):
    for bad in ("{", "not json", b"\xff\xfe"):
      self.assertIsNone(position_from_raw(bad), repr(bad))

  def test_a_null_island_fix_is_refused(self):
    self.assertIsNone(position_from_raw('{"latitude": 0.0, "longitude": 0.0}'))


class TestAutoDetectEnabled(unittest.TestCase):
  """The gate that decides whether this process may make a request at all."""

  class _Params:
    """Just enough Params for these two reads.

    Signatures are copied from the real class rather than loosened: `get_bool`
    takes one positional key, `get` takes the `return_default` keyword. A
    generous fake would have accepted the bug this is guarding against.
    """

    def __init__(self, values, defaults=None):
      self._values = values
      self._defaults = defaults or {}

    def get_bool(self, key):
      return self._values.get(key, False)

    def get(self, key, return_default=False):
      if key in self._values:
        return self._values[key]
      return self._defaults.get(key) if return_default else None

  def _enabled(self, values=None, defaults=None):
    return auto_detect_enabled(self._Params(values or {}, defaults))

  def test_off_when_the_feature_is_off(self):
    """Auto-detect being on is not enough - the whole feature has a switch too."""
    self.assertFalse(self._enabled({"WeatherAutoDetect": True}))

  def test_on_when_both_are_on(self):
    values = {"WeatherOffsetsEnabled": True, "WeatherAutoDetect": True}
    self.assertTrue(self._enabled(values))

  def test_off_when_auto_detect_is_switched_off(self):
    values = {"WeatherOffsetsEnabled": True, "WeatherAutoDetect": False}
    self.assertFalse(self._enabled(values))

  def test_auto_detect_defaults_on_when_it_was_never_written(self):
    """`get_bool` is `get(key) == "1"` - an unwritten key reads False.

    Auto-detect ships on, so the registered default has to be consulted;
    otherwise the feature is off until somebody opens the settings page and
    toggles it twice, which is exactly the failure this whole change is about.
    """
    self.assertTrue(self._enabled({"WeatherOffsetsEnabled": True}, {"WeatherAutoDetect": "1"}))

  def test_an_unregistered_key_means_off(self):
    """A device whose params_c.so predates this feature must not call out."""
    class _Unregistered(self._Params):
      def get_bool(self, key):
        raise type("UnknownKeyName", (Exception,), {})(key)

      def get(self, key, return_default=False):
        raise type("UnknownKeyName", (Exception,), {})(key)

    self.assertFalse(auto_detect_enabled(_Unregistered({})))


class TestBuildUrl(unittest.TestCase):
  def test_it_points_at_open_meteo_and_asks_only_for_the_code(self):
    url = build_url(37.5, 127.0)
    self.assertTrue(url.startswith(f"{OPEN_METEO_URL}?"))
    self.assertIn("current=weather_code", url)
    self.assertIn("latitude=37.5000", url)
    self.assertIn("longitude=127.0000", url)
    self.assertIn("timezone=UTC", url)


class TestParseReading(unittest.TestCase):
  def test_a_normal_payload(self):
    reading = parse_reading({"current": {"weather_code": 61}}, 37.5, 127.0, 1000.0)
    self.assertIsInstance(reading, Reading)
    self.assertEqual(("rain", 61, 37.5, 127.0, 1000.0),
                     (reading.state, reading.code, reading.latitude, reading.longitude, reading.at))

  def test_a_payload_without_current_is_not_a_reading(self):
    for bad in ({}, {"hourly": {}}, {"current": None}, {"current": []}, None, [], "x"):
      self.assertIsNone(parse_reading(bad, 37.5, 127.0, 1000.0), repr(bad))

  def test_a_current_block_without_a_code_is_not_a_reading(self):
    for bad in ({"current": {}}, {"current": {"weather_code": None}},
                {"current": {"weather_code": "61"}}, {"current": {"weather_code": True}}):
      self.assertIsNone(parse_reading(bad, 37.5, 127.0, 1000.0), repr(bad))


class TestFetchOpenMeteo(unittest.TestCase):
  def test_the_opener_result_is_returned(self):
    seen = {}

    def opener(url, timeout):
      seen["url"], seen["timeout"] = url, timeout
      return {"current": {"weather_code": 71}}

    self.assertEqual({"current": {"weather_code": 71}}, fetch_open_meteo(37.5, 127.0, opener=opener))
    self.assertTrue(seen["url"].startswith(OPEN_METEO_URL))
    self.assertEqual(10.0, seen["timeout"])

  def test_a_raising_opener_is_swallowed(self):
    """A background thread whose only job is a param must never propagate."""
    def opener(url, timeout):
      raise OSError("network is unreachable")

    self.assertIsNone(fetch_open_meteo(37.5, 127.0, opener=opener))

  def test_a_non_dict_opener_result_is_ignored(self):
    for bad in (None, [], "{}", 3):
      self.assertIsNone(fetch_open_meteo(37.5, 127.0, opener=lambda u, t, b=bad: b), repr(bad))


class TestWeatherPoller(unittest.TestCase):
  """`tick` answers one question: should the caller persist a new state?"""

  def _poller(self, answers, **kwargs):
    """A poller whose network is a scripted list of payloads (None = failure)."""
    self.calls = []

    def fetch(latitude, longitude):
      self.calls.append((latitude, longitude))
      if not answers:
        raise AssertionError("fetch called more often than the script allows")
      return answers.pop(0)

    return WeatherPoller(fetch=fetch, **kwargs)

  def test_no_position_means_no_request(self):
    poller = self._poller([])
    self.assertIsNone(poller.tick(1000.0, 0.0, 0.0))
    self.assertIsNone(poller.tick(1000.0, None, None))
    self.assertEqual([], self.calls)
    self.assertEqual("clear", poller.state)

  def test_the_first_answer_is_news(self):
    poller = self._poller([{"current": {"weather_code": 61}}])
    reading = poller.tick(1000.0, 37.5, 127.0)
    self.assertIsNotNone(reading)
    self.assertEqual("rain", reading.state)
    self.assertEqual("rain", poller.state)
    self.assertEqual([(37.5, 127.0)], self.calls)

  def test_the_same_weather_again_is_not_news(self):
    """Persisting an unchanged state every 15 minutes would be disk churn."""
    poller = self._poller([{"current": {"weather_code": 61}}, {"current": {"weather_code": 63}}])

    self.assertIsNotNone(poller.tick(1000.0, 37.5, 127.0))
    self.assertIsNone(poller.tick(1000.0 + DEFAULT_INTERVAL_S, 37.5, 127.0))
    self.assertEqual(2, len(self.calls))

  def test_a_change_of_weather_is_news(self):
    poller = self._poller([{"current": {"weather_code": 61}}, {"current": {"weather_code": 71}}])

    poller.tick(1000.0, 37.5, 127.0)
    reading = poller.tick(1000.0 + DEFAULT_INTERVAL_S, 37.5, 127.0)
    self.assertIsNotNone(reading)
    self.assertEqual("snow", reading.state)

  def test_nothing_is_asked_before_the_interval_elapses(self):
    poller = self._poller([{"current": {"weather_code": 61}}])

    poller.tick(1000.0, 37.5, 127.0)
    self.assertIsNone(poller.tick(1000.0 + DEFAULT_INTERVAL_S - 1.0, 37.5, 127.0))
    self.assertEqual(1, len(self.calls))

  def test_a_long_drive_asks_again_early(self):
    """The cached answer is about the old place, so the timer does not hold."""
    poller = self._poller([{"current": {"weather_code": 61}}, {"current": {"weather_code": 71}}])

    poller.tick(1000.0, 37.5, 127.0)
    self.assertIsNone(poller.tick(1000.0 + 60.0, 37.6, 127.0))
    reading = poller.tick(1000.0 + 60.0, 38.5, 127.0)
    self.assertIsNotNone(reading)
    self.assertEqual("snow", reading.state)
    self.assertEqual(2, len(self.calls))

  def test_a_failed_request_is_retried_after_a_minute_not_a_quarter_hour(self):
    poller = self._poller([None, {"current": {"weather_code": 61}}])

    self.assertIsNone(poller.tick(1000.0, 37.5, 127.0))
    self.assertIsNone(poller.tick(1000.0 + DEFAULT_RETRY_INTERVAL_S - 1.0, 37.5, 127.0))
    self.assertEqual(1, len(self.calls))
    self.assertIsNotNone(poller.tick(1000.0 + DEFAULT_RETRY_INTERVAL_S, 37.5, 127.0))

  def test_a_failed_request_keeps_the_previous_state(self):
    """Losing the network is not a reason to declare the weather clear."""
    poller = self._poller([{"current": {"weather_code": 61}}, None])

    poller.tick(1000.0, 37.5, 127.0)
    self.assertIsNone(poller.tick(1000.0 + DEFAULT_INTERVAL_S, 37.5, 127.0))
    self.assertEqual("rain", poller.state)

  def test_a_broken_payload_counts_as_a_failure(self):
    poller = self._poller([{"current": {}}, {"current": {"weather_code": 61}}])

    self.assertIsNone(poller.tick(1000.0, 37.5, 127.0))
    self.assertIsNone(poller.tick(1000.0 + DEFAULT_RETRY_INTERVAL_S - 1.0, 37.5, 127.0))
    self.assertIsNotNone(poller.tick(1000.0 + DEFAULT_RETRY_INTERVAL_S, 37.5, 127.0))

  def test_a_custom_interval_is_honoured(self):
    poller = self._poller([{"current": {"weather_code": 61}}], interval_s=30.0)

    poller.tick(1000.0, 37.5, 127.0)
    self.assertIsNone(poller.tick(1000.0 + 29.0, 37.5, 127.0))
    self.assertEqual(1, len(self.calls))


if __name__ == "__main__":
  unittest.main()
