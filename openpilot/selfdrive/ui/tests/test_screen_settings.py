"""Unit tests for the ST-8 screen brightness settings (pure value computation).

Covers level/offset parsing, the offset application and the final brightness
calculation, plus default equivalence: with no params set, the computed value
is exactly the stock input value.
"""
import unittest

from openpilot.selfdrive.ui.screen_settings import (
  KEY_SCREEN_BRIGHTNESS_OFFROAD,
  KEY_SCREEN_BRIGHTNESS_OFFROAD_OFFSET,
  KEY_SCREEN_BRIGHTNESS_ONROAD,
  KEY_SCREEN_BRIGHTNESS_ONROAD_OFFSET,
  OFFSET_MAX,
  OFFSET_MIN,
  apply_offset,
  calculate_screen_brightness,
  parse_level,
  parse_offset,
  read_screen_brightness,
)


class DictParams:
  """Dict-backed params returning bytes like the real Params (or raising on unknown keys)."""

  def __init__(self, values=None, raise_unknown=True):
    self.values = dict(values or {})
    self.raise_unknown = raise_unknown

  def get(self, key, **kwargs):
    if key in self.values:
      return self.values[key]
    if self.raise_unknown:
      raise KeyError(key)
    return None


class TestParseLevel(unittest.TestCase):
  def test_valid_values(self):
    self.assertEqual(parse_level(b"55", None), 55)
    self.assertEqual(parse_level(b"0", None), 0)
    self.assertEqual(parse_level(b"100", None), 100)

  def test_float_input_is_rounded(self):
    self.assertEqual(parse_level(55.4, None), 55)
    self.assertEqual(parse_level(55.6, None), 56)

  def test_unset_returns_default(self):
    self.assertIsNone(parse_level(None, None))
    self.assertIsNone(parse_level(b"", None))
    self.assertEqual(parse_level(None, 50), 50)

  def test_garbage_returns_default(self):
    self.assertIsNone(parse_level(b"abc", None))
    self.assertIsNone(parse_level(float("nan"), None))
    self.assertIsNone(parse_level(float("inf"), None))

  def test_out_of_range_returns_default(self):
    self.assertIsNone(parse_level(b"101", None))
    self.assertIsNone(parse_level(b"-1", None))
    self.assertIsNone(parse_level(255, None))


class TestParseOffset(unittest.TestCase):
  def test_valid_values(self):
    self.assertEqual(parse_offset(b"10"), 10.0)
    self.assertEqual(parse_offset(b"-15.5"), -15.5)

  def test_clamped(self):
    self.assertEqual(parse_offset(b"99"), OFFSET_MAX)
    self.assertEqual(parse_offset(b"-99"), OFFSET_MIN)

  def test_unset_or_garbage_returns_default(self):
    self.assertEqual(parse_offset(None), 0.0)
    self.assertEqual(parse_offset(b"junk"), 0.0)
    self.assertEqual(parse_offset(float("nan")), 0.0)
    self.assertEqual(parse_offset(None, 5.0), 5.0)


class TestApplyOffset(unittest.TestCase):
  def test_zero_offset_is_identity(self):
    self.assertEqual(apply_offset(65.0, 0.0), 65.0)

  def test_positive_and_negative(self):
    self.assertEqual(apply_offset(50.0, 20.0), 60.0)
    self.assertEqual(apply_offset(50.0, -20.0), 40.0)

  def test_result_clamped(self):
    self.assertEqual(apply_offset(90.0, 30.0), 100.0)
    self.assertEqual(apply_offset(20.0, -30.0), 14.0)
    self.assertEqual(apply_offset(10.0, -30.0), 7.0)


class TestCalculateScreenBrightness(unittest.TestCase):
  def test_default_equivalence(self):
    # No prefs: output equals the stock value (offroad default and auto onroad).
    self.assertEqual(calculate_screen_brightness(65, None, 0.0), 65)
    self.assertEqual(calculate_screen_brightness(42.3, None, 0.0), 42)

  def test_manual_overrides_auto_and_ignores_offset(self):
    self.assertEqual(calculate_screen_brightness(80.0, 30, 15.0), 30)

  def test_offset_scales_auto(self):
    self.assertEqual(calculate_screen_brightness(50.0, None, 20.0), 60)

  def test_result_clamped(self):
    self.assertEqual(calculate_screen_brightness(95.0, None, 30.0), 100)
    self.assertEqual(calculate_screen_brightness(10.0, None, -30.0), 7)

  def test_not_awake_is_zero(self):
    self.assertEqual(calculate_screen_brightness(65, None, 0.0, awake=False), 0)
    self.assertEqual(calculate_screen_brightness(65, 50, 0.0, awake=False), 0)


class TestReadScreenBrightness(unittest.TestCase):
  def test_unset_keys_give_unset_defaults(self):
    onroad, onroad_offset, offroad, offroad_offset = read_screen_brightness(DictParams({}))
    self.assertIsNone(onroad)
    self.assertEqual(onroad_offset, 0.0)
    self.assertIsNone(offroad)
    self.assertEqual(offroad_offset, 0.0)

  def test_set_keys_are_parsed(self):
    params = DictParams({
      KEY_SCREEN_BRIGHTNESS_ONROAD: b"70",
      KEY_SCREEN_BRIGHTNESS_ONROAD_OFFSET: b"-10",
      KEY_SCREEN_BRIGHTNESS_OFFROAD: b"55",
      KEY_SCREEN_BRIGHTNESS_OFFROAD_OFFSET: b"15",
    })
    onroad, onroad_offset, offroad, offroad_offset = read_screen_brightness(params)
    self.assertEqual((onroad, onroad_offset, offroad, offroad_offset), (70, -10.0, 55, 15.0))

  def test_invalid_values_fall_back(self):
    params = DictParams({
      KEY_SCREEN_BRIGHTNESS_ONROAD: b"999",
      KEY_SCREEN_BRIGHTNESS_ONROAD_OFFSET: b"junk",
    })
    onroad, onroad_offset, offroad, offroad_offset = read_screen_brightness(params)
    self.assertIsNone(onroad)
    self.assertEqual(onroad_offset, 0.0)
    self.assertIsNone(offroad)
    self.assertEqual(offroad_offset, 0.0)


if __name__ == "__main__":
  unittest.main()
