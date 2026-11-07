"""Pure-logic unit tests for the StarPilot lane-centering port (PC-safe).

Builds a fake modelV2 namespace with lane lines / path position and covers
the gating chain, offset math, deadband and the smooth correction output.
"""
import unittest
from types import SimpleNamespace

import numpy as np

from openpilot.selfdrive.controls.lib.lane_centering import (
  LaneCenteringController,
  get_lane_centering_visual_direction,
  get_raw_lane_centering_correction,
)

X = np.arange(0.0, 50.0, 0.5)  # covers lookahead up to 35 m


def fake_model(left_y=-2.0, right_y=2.0, path_y=0.0, prob=0.9, std=0.1, path_std=0.05):
  left = SimpleNamespace(x=X.copy(), y=np.full_like(X, left_y))
  right = SimpleNamespace(x=X.copy(), y=np.full_like(X, right_y))
  return SimpleNamespace(
    laneLines=[SimpleNamespace(x=X.copy(), y=np.full_like(X, 0.0)), left, right],
    laneLineProbs=np.array([0.0, prob, prob]),
    laneLineStds=np.array([1.0, std, std]),
    position=SimpleNamespace(x=X.copy(), y=np.full_like(X, path_y), yStd=np.full_like(X, path_std)),
    meta=SimpleNamespace(laneChangeState=0),  # 0 == off
  )


class TestRawCorrection(unittest.TestCase):
  def test_centered_car_has_no_correction(self):
    valid, corr = get_raw_lane_centering_correction(fake_model(), 15.0, 0.0, 0.0)
    self.assertTrue(valid)
    self.assertAlmostEqual(corr, 0.0, places=9)

  def test_off_center_car_corrects_toward_center(self):
    # path at +0.5 m from center -> correction negative (pull back left)
    valid, corr = get_raw_lane_centering_correction(fake_model(path_y=0.5), 15.0, 0.0, 0.0)
    self.assertTrue(valid)
    self.assertLess(corr, 0.0)

  def test_deadband_suppresses_small_errors(self):
    valid, corr = get_raw_lane_centering_correction(fake_model(path_y=0.05), 15.0, 0.0, 0.0)
    self.assertTrue(valid)
    self.assertAlmostEqual(corr, 0.0, places=12)

  def test_offset_shifts_target(self):
    # car centered but driver offset 0.3 -> correction toward the offset
    valid_center, _ = get_raw_lane_centering_correction(fake_model(), 15.0, 0.0, 0.0)
    valid_off, corr_off = get_raw_lane_centering_correction(fake_model(), 15.0, 0.3, 0.0)
    self.assertTrue(valid_off)
    self.assertGreater(corr_off, 0.0)

  def test_low_lane_prob_rejected(self):
    valid, _ = get_raw_lane_centering_correction(fake_model(prob=0.4), 15.0, 0.0, 0.0)
    self.assertFalse(valid)

  def test_high_lane_std_rejected(self):
    valid, _ = get_raw_lane_centering_correction(fake_model(std=0.5), 15.0, 0.0, 0.0)
    self.assertFalse(valid)

  def test_unreasonable_lane_width_rejected(self):
    valid, _ = get_raw_lane_centering_correction(fake_model(left_y=-1.0, right_y=1.5), 15.0, 0.0, 0.0)
    self.assertFalse(valid)  # 2.5 m < min width

  def test_e2e_authority_attenuates_large_error(self):
    # path error 0.4 m: well above break-in start
    _, no_auth = get_raw_lane_centering_correction(fake_model(path_y=0.4), 15.0, 0.0, 0.0)
    _, full_auth = get_raw_lane_centering_correction(fake_model(path_y=0.4), 15.0, 0.0, 1.0)
    self.assertLess(abs(full_auth), abs(no_auth))

  def test_short_path_rejected(self):
    m = fake_model()
    m.position.x = np.array([0.0, 1.0])
    m.position.y = np.array([0.0, 0.0])
    valid, _ = get_raw_lane_centering_correction(m, 15.0, 0.0, 0.0)
    self.assertFalse(valid)


class TestController(unittest.TestCase):
  def make_controller(self):
    return LaneCenteringController()

  def test_disabled_resets_and_passes_through(self):
    c = self.make_controller()
    self.assertEqual(c.update(0.01, fake_model(), 15.0, enabled=False, offset=0.0,
                              e2e_authority=0.0, lat_active=True, model_valid=True), 0.01)
    self.assertEqual(c._correction, 0.0)

  def test_inactive_lateral_resets(self):
    c = self.make_controller()
    self.assertEqual(c.update(0.01, fake_model(), 15.0, enabled=True, offset=0.0,
                              e2e_authority=0.0, lat_active=False, model_valid=True), 0.01)

  def test_lane_change_resets(self):
    c = self.make_controller()
    c.update(0.01, fake_model(path_y=0.4), 15.0, True, 0.0, 0.0, True, True)
    self.assertNotEqual(c._correction, 0.0)
    out = c.update(0.01, fake_model(path_y=0.4), 15.0, True, 0.0, 0.0, True, True,
                   lane_change_active=True)
    self.assertEqual(c._correction, 0.0)
    self.assertAlmostEqual(out, 0.01)

  def test_signal_pause_holds_correction_decay(self):
    c = self.make_controller()
    for _ in range(50):
      c.update(0.01, fake_model(path_y=0.4), 15.0, True, 0.0, 0.0, True, True)
    held = c._correction
    c.update(0.01, fake_model(path_y=0.4), 15.0, True, 0.0, 0.0, True, True,
             pause_on_signal=True, turn_signal_active=True)
    # correction decays smoothly, not reset instantly
    self.assertGreater(abs(c._correction), 0.0)
    self.assertLess(abs(c._correction), abs(held))

  def test_correction_smoothed_and_bounded(self):
    c = self.make_controller()
    for _ in range(200):
      out = c.update(0.01, fake_model(path_y=0.3), 15.0, True, 0.0, 0.0, True, True)
    self.assertNotEqual(out, 0.01)
    # total correction magnitude bounded by MAX_RAW_CORRECTION * MAX_GAIN
    self.assertLessEqual(abs(c._correction), 0.004 * 0.30 + 1e-9)

  def test_driver_override_resets(self):
    c = self.make_controller()
    c.update(0.01, fake_model(path_y=0.4), 15.0, True, 0.0, 0.0, True, True)
    c.update(0.01, fake_model(path_y=0.4), 15.0, True, 0.0, 0.0, True, True, driver_override=True)
    self.assertEqual(c._correction, 0.0)

  def test_invalid_model_finite_guard(self):
    c = self.make_controller()
    out = c.update(float("nan"), fake_model(), 15.0, True, 0.0, 0.0, True, True)
    self.assertTrue(np.isnan(out))


class TestVisualDirection(unittest.TestCase):
  def test_direction_matches_correction_sign(self):
    # path at +0.4 -> correction negative -> left (-1)
    self.assertEqual(get_lane_centering_visual_direction(fake_model(path_y=0.4), 15.0, 0.0, 0.0,
                                                         True, True), -1)
    # path at -0.4 -> correction positive -> right (+1)
    self.assertEqual(get_lane_centering_visual_direction(fake_model(path_y=-0.4), 15.0, 0.0, 0.0,
                                                         True, True), 1)

  def test_disabled_is_zero(self):
    self.assertEqual(get_lane_centering_visual_direction(fake_model(path_y=0.4), 15.0, 0.0, 0.0,
                                                         False, True), 0)


if __name__ == "__main__":
  unittest.main()
