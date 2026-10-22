import unittest

from openpilot.selfdrive.controls.lib.weather_offsets import (
  WEATHER_STATES,
  WeatherOffsets,
  normalize_weather_state,
)


class TestNormalizeWeatherState(unittest.TestCase):
  def test_known_states(self):
    for state in WEATHER_STATES:
      self.assertEqual(normalize_weather_state(state), state)

  def test_aliases(self):
    self.assertEqual(normalize_weather_state("fog"), "low_visibility")
    self.assertEqual(normalize_weather_state("FOG"), "low_visibility")
    self.assertEqual(normalize_weather_state("Rain_Storm"), "rain_storm")
    self.assertEqual(normalize_weather_state("rain-storm"), "rain_storm")
    self.assertEqual(normalize_weather_state("sunny"), "clear")

  def test_unknown_falls_back_to_clear(self):
    self.assertEqual(normalize_weather_state("meteor shower"), "clear")
    self.assertEqual(normalize_weather_state(None), "clear")
    self.assertEqual(normalize_weather_state(42), "clear")


class TestWeatherOffsets(unittest.TestCase):
  def test_defaults_are_neutral(self):
    offsets = WeatherOffsets()
    self.assertEqual(offsets.state, "clear")
    self.assertFalse(offsets.is_adverse)
    self.assertAlmostEqual(offsets.increase_following_distance, 0.0)
    self.assertAlmostEqual(offsets.increase_stopped_distance, 0.0)
    self.assertAlmostEqual(offsets.reduce_acceleration, 0.0)
    self.assertAlmostEqual(offsets.reduce_lateral_acceleration, 0.0)

  def test_neutral_offsets_do_not_change_anything(self):
    offsets = WeatherOffsets("rain")
    self.assertAlmostEqual(offsets.apply_following(1.45), 1.45)
    self.assertAlmostEqual(offsets.apply_stopped_distance(4.0), 4.0)
    self.assertAlmostEqual(offsets.apply_acceleration(1.2), 1.2)
    self.assertAlmostEqual(offsets.apply_lateral_acceleration(1.8), 1.8)

  def test_following_is_additive(self):
    offsets = WeatherOffsets("rain", following=0.3)
    self.assertAlmostEqual(offsets.apply_following(1.45), 1.75)

  def test_stopped_distance_is_additive(self):
    offsets = WeatherOffsets("snow", stopped=2.0)
    self.assertAlmostEqual(offsets.apply_stopped_distance(4.0), 6.0)

  def test_acceleration_is_multiplicative(self):
    offsets = WeatherOffsets("rain", acceleration=0.25)
    self.assertAlmostEqual(offsets.apply_acceleration(2.0), 1.5)

  def test_lateral_acceleration_is_multiplicative(self):
    offsets = WeatherOffsets("rain", lateral=0.2)
    self.assertAlmostEqual(offsets.apply_lateral_acceleration(2.0), 1.6)

  def test_values_are_clamped(self):
    offsets = WeatherOffsets("rain", following=99.0, stopped=999.0, acceleration=5.0, lateral=-3.0)
    self.assertAlmostEqual(offsets.increase_following_distance, 3.0)
    self.assertAlmostEqual(offsets.increase_stopped_distance, 20.0)
    self.assertAlmostEqual(offsets.reduce_acceleration, 1.0)
    self.assertAlmostEqual(offsets.reduce_lateral_acceleration, 0.0)

  def test_non_finite_values_are_ignored(self):
    offsets = WeatherOffsets("rain", following=float("nan"), acceleration=float("inf"))
    self.assertAlmostEqual(offsets.increase_following_distance, 0.0)
    self.assertAlmostEqual(offsets.reduce_acceleration, 0.0)

  def test_garbage_values_are_ignored(self):
    offsets = WeatherOffsets("rain", following="abc", lateral=None)
    self.assertAlmostEqual(offsets.increase_following_distance, 0.0)
    self.assertAlmostEqual(offsets.reduce_lateral_acceleration, 0.0)

  def test_adverse_weather_is_flagged(self):
    self.assertTrue(WeatherOffsets("rain").is_adverse)
    self.assertTrue(WeatherOffsets("snow").is_adverse)
    self.assertFalse(WeatherOffsets("clear").is_adverse)

  def test_full_reduction_leaves_no_acceleration(self):
    offsets = WeatherOffsets("rain_storm", acceleration=1.0)
    self.assertAlmostEqual(offsets.apply_acceleration(2.0), 0.0)

  def test_as_dict_round_trip(self):
    offsets = WeatherOffsets("snow", following=0.2, stopped=1.0, acceleration=0.1, lateral=0.05)
    data = offsets.as_dict()
    self.assertEqual(data["state"], "snow")
    self.assertAlmostEqual(data["increase_following_distance"], 0.2)
    self.assertAlmostEqual(data["reduce_lateral_acceleration"], 0.05)


if __name__ == "__main__":
  unittest.main()
