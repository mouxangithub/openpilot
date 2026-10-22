"""Pure-logic unit tests for the StarPilot longcontrol stop-release port.

Covers the sustained-release tracker and the negative-target creep guards.
The state-machine wiring is exercised by test_longcontrol.py on device.
"""
import unittest

from openpilot.selfdrive.controls.lib.longcontrol_stop_release import (
  NEGATIVE_TARGET_CREEP_GUARD_SPEED,
  STOPPING_RELEASE_HYSTERESIS,
  STOPPING_RELEASE_MIN_ACCEL,
  STOPPING_RELEASE_STRONG_ACCEL,
  StopReleaseTracker,
  cap_positive_output_on_negative_target,
  trim_positive_overshoot_integrator,
)


class TestStopReleaseTracker(unittest.TestCase):
  def setUp(self):
    self.tracker = StopReleaseTracker()

  def test_not_stopping_is_always_ready(self):
    self.assertTrue(self.tracker.ready(False, v_ego=0.0, a_target=0.0,
                                       should_stop=True, brake_pressed=False, cruise_standstill=True))

  def test_stop_or_brake_resets_counter(self):
    # build up 34 frames (one below threshold at 35)
    for _ in range(34):
      ready = self.tracker.ready(True, 0.0, STOPPING_RELEASE_MIN_ACCEL + 0.01,
                                 False, False, True)
    self.assertFalse(ready)
    # brake pressed resets
    self.assertFalse(self.tracker.ready(True, 0.0, 0.5, False, True, True))
    self.assertFalse(self.tracker.ready(True, 0.0, 0.5, True, False, True))

  def test_sustained_request_releases(self):
    ready = False
    for _ in range(int(round(STOPPING_RELEASE_HYSTERESIS / 0.01))):
      ready = self.tracker.ready(True, 0.0, STOPPING_RELEASE_MIN_ACCEL + 0.01,
                                 False, False, True)
    self.assertTrue(ready)

  def test_single_request_insufficient(self):
    self.assertFalse(self.tracker.ready(True, 0.0, STOPPING_RELEASE_MIN_ACCEL + 0.01,
                                        False, False, True))

  def test_fast_speed_releases_immediately(self):
    self.assertTrue(self.tracker.ready(True, 0.6, 0.0, False, False, True))

  def test_lead_release_immediate(self):
    self.assertTrue(self.tracker.ready(True, 0.0, STOPPING_RELEASE_MIN_ACCEL + 0.01,
                                       False, False, True, has_lead=True))

  def test_strong_accel_releases_unless_standstill(self):
    self.assertTrue(self.tracker.ready(True, 0.0, STOPPING_RELEASE_STRONG_ACCEL,
                                       False, False, False))
    # fresh tracker: with standstill latched, strong accel alone must not
    # release (falls through to the sustained-request counter)
    self.tracker = StopReleaseTracker()
    self.assertFalse(self.tracker.ready(True, 0.0, STOPPING_RELEASE_STRONG_ACCEL,
                                        False, False, True))

  def test_counter_saturates(self):
    for _ in range(100):
      self.tracker.ready(True, 0.0, STOPPING_RELEASE_MIN_ACCEL + 0.01, False, False, True)
    self.assertEqual(self.tracker.stop_release_counter, self.tracker.max_frames)

  def test_weak_negative_target_resets(self):
    self.tracker.ready(True, 0.0, STOPPING_RELEASE_MIN_ACCEL + 0.01, False, False, True)
    self.tracker.ready(True, 0.0, 0.0, False, False, True)
    self.assertEqual(self.tracker.stop_release_counter, 0)


class TestTrimPositiveOvershootIntegrator(unittest.TestCase):
  def test_negative_integrator_untouched(self):
    self.assertEqual(trim_positive_overshoot_integrator(-0.1, -1.0, -1.0, 5.0), -0.1)

  def test_mild_decel_target_untouched(self):
    self.assertEqual(trim_positive_overshoot_integrator(0.2, -0.04, -1.0, 5.0), 0.2)

  def test_creep_scene_untouched(self):
    # low speed with a gentle (>-0.40) decel target is exempt
    self.assertEqual(trim_positive_overshoot_integrator(
      0.2, -0.30, -1.0, NEGATIVE_TARGET_CREEP_GUARD_SPEED - 0.1), 0.2)

  def test_real_decel_bleeds_integrator(self):
    bled = trim_positive_overshoot_integrator(0.4, -1.0, -1.2, 5.0)
    self.assertGreater(bled, 0.0)
    self.assertLess(bled, 0.4)
    # larger error bleeds more
    bled_more = trim_positive_overshoot_integrator(0.4, -1.0, -1.6, 5.0)
    self.assertLess(bled_more, bled)

  def test_zero_error_untouched(self):
    self.assertEqual(trim_positive_overshoot_integrator(0.4, -1.0, -0.2, 5.0), 0.4)


class TestCapPositiveOutput(unittest.TestCase):
  def test_nonpositive_output_untouched(self):
    self.assertEqual(cap_positive_output_on_negative_target(-0.5, -1.0, -1.0, 5.0), -0.5)

  def test_mild_decel_target_untouched(self):
    self.assertEqual(cap_positive_output_on_negative_target(0.3, -0.05, -1.0, 5.0), 0.3)

  def test_creep_scene_untouched(self):
    self.assertEqual(cap_positive_output_on_negative_target(
      0.3, -0.30, -1.0, NEGATIVE_TARGET_CREEP_GUARD_SPEED - 0.1), 0.3)

  def test_real_decel_caps_to_zero(self):
    self.assertEqual(cap_positive_output_on_negative_target(0.3, -1.0, -1.2, 5.0), 0.0)

  def test_medium_decel_caps_partially(self):
    capped = cap_positive_output_on_negative_target(0.3, -0.7, -1.2, 5.0)
    self.assertLessEqual(capped, 0.0)

  def test_small_error_untouched(self):
    self.assertEqual(cap_positive_output_on_negative_target(0.3, -1.0, -0.3, 5.0), 0.3)


if __name__ == "__main__":
  unittest.main()
