import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.vision_limit import (
  LARGE_REFERENCE_SPEED_DELTA,
  LARGE_SET_SPEED_MIN_SUPPORT,
  SUPPORT_SPEED_TOLERANCE,
  has_support,
  is_low_limit_filtered,
  merge_lower_limit,
  needs_support,
  normalize_vision_limit,
  resolve_vision_limit,
)

MPH = 0.44704


class TestNormalizeVisionLimit(unittest.TestCase):
  def test_valid_limit(self):
    self.assertAlmostEqual(normalize_vision_limit(22.0), 22.0)

  def test_zero_and_negative_are_dropped(self):
    self.assertAlmostEqual(normalize_vision_limit(0.0), 0.0)
    self.assertAlmostEqual(normalize_vision_limit(-5.0), 0.0)

  def test_garbage_is_dropped(self):
    self.assertAlmostEqual(normalize_vision_limit(None), 0.0)
    self.assertAlmostEqual(normalize_vision_limit("abc"), 0.0)
    self.assertAlmostEqual(normalize_vision_limit(float("nan")), 0.0)
    self.assertAlmostEqual(normalize_vision_limit(float("inf")), 0.0)


class TestLowLimitFilter(unittest.TestCase):
  def test_filter_is_off_by_default(self):
    self.assertFalse(is_low_limit_filtered(1.0, False, 5.0))

  def test_below_threshold_is_filtered(self):
    self.assertTrue(is_low_limit_filtered(4.0, True, 5.0))
    self.assertTrue(is_low_limit_filtered(5.0, True, 5.0))

  def test_above_threshold_is_kept(self):
    self.assertFalse(is_low_limit_filtered(6.0, True, 5.0))

  def test_zero_limit_is_not_filtered(self):
    # A zero limit means "no reading", not "a very low limit".
    self.assertFalse(is_low_limit_filtered(0.0, True, 5.0))

  def test_negative_threshold_is_tolerated(self):
    self.assertFalse(is_low_limit_filtered(1.0, True, -3.0))


class TestNeedsSupport(unittest.TestCase):
  def test_small_deviation_does_not_need_support(self):
    self.assertFalse(needs_support(20.0, 20.0 + 1.0, False))

  def test_large_deviation_needs_support(self):
    self.assertTrue(needs_support(10.0, 40.0, False))

  def test_standstill_does_not_need_support(self):
    self.assertFalse(needs_support(10.0, 40.0, True))

  def test_no_reference_speed_does_not_need_support(self):
    self.assertFalse(needs_support(10.0, 0.0, False))


class TestHasSupport(unittest.TestCase):
  def test_enough_count_and_matching_speed(self):
    self.assertTrue(has_support(LARGE_SET_SPEED_MIN_SUPPORT, 20.0, 20.0))

  def test_too_few_readings(self):
    self.assertFalse(has_support(LARGE_SET_SPEED_MIN_SUPPORT - 1, 20.0, 20.0))

  def test_speed_disagrees(self):
    self.assertFalse(has_support(5, 20.0 + SUPPORT_SPEED_TOLERANCE + 0.1, 20.0))

  def test_speed_within_tolerance(self):
    self.assertTrue(has_support(5, 20.0 + SUPPORT_SPEED_TOLERANCE * 0.5, 20.0))

  def test_garbage_support(self):
    self.assertFalse(has_support(None, 20.0, 20.0))
    self.assertFalse(has_support(5, None, 20.0))
    self.assertFalse(has_support(5, float("nan"), 20.0))


class TestResolveVisionLimit(unittest.TestCase):
  def test_no_reading(self):
    self.assertAlmostEqual(resolve_vision_limit(0.0, 20.0, False), 0.0)

  def test_plausible_limit_is_accepted(self):
    self.assertAlmostEqual(resolve_vision_limit(20.0, 21.0, False), 20.0)

  def test_large_deviation_without_support_is_rejected(self):
    self.assertAlmostEqual(resolve_vision_limit(10.0, 40.0, False), 0.0)

  def test_large_deviation_with_support_is_accepted(self):
    result = resolve_vision_limit(10.0, 40.0, False, support_count=3, support_speed=10.0)
    self.assertAlmostEqual(result, 10.0)

  def test_large_deviation_at_standstill_is_accepted(self):
    self.assertAlmostEqual(resolve_vision_limit(10.0, 40.0, True), 10.0)

  def test_low_limit_is_filtered(self):
    result = resolve_vision_limit(3.0, 20.0, False, low_limit_filter=True, low_limit_threshold=5.0)
    self.assertAlmostEqual(result, 0.0)

  def test_the_delta_threshold_is_thirty_mph(self):
    self.assertAlmostEqual(LARGE_REFERENCE_SPEED_DELTA, 30 * MPH)


class TestMergeLowerLimit(unittest.TestCase):
  def test_candidate_lowers_the_current(self):
    self.assertAlmostEqual(merge_lower_limit(25.0, 20.0), 20.0)

  def test_candidate_does_not_raise_the_current(self):
    self.assertAlmostEqual(merge_lower_limit(20.0, 25.0), 20.0)

  def test_candidate_fills_an_empty_current(self):
    self.assertAlmostEqual(merge_lower_limit(0.0, 20.0), 20.0)

  def test_invalid_candidate_leaves_the_current(self):
    self.assertAlmostEqual(merge_lower_limit(20.0, 0.0), 20.0)
    self.assertAlmostEqual(merge_lower_limit(20.0, -1.0), 20.0)


if __name__ == "__main__":
  unittest.main()
