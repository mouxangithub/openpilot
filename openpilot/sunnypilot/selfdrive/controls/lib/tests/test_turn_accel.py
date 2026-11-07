"""Turn acceleration limiting (ported from carrot): positive accel is capped by
the combined lateral+longitudinal budget over the upcoming path. Braking and
jerk stay owned by the longitudinal planner."""
import unittest

import numpy as np

from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.selfdrive.controls.lib.turn_accel import (
  get_future_curvature, limit_accel_in_turns,
)


class _Model:
  def __init__(self, yaw_rate=0.0, velocity=15.0, straight=True):
    n = ModelConstants.IDX_N
    self.orientationRate = type('O', (), {'z': [yaw_rate] * n})()
    self.velocity = type('V', (), {'x': [velocity] * n})()
    if straight:
      self.position = type('P', (), {'x': list(np.linspace(0, 60, n)),
                                     'y': [0.0] * n, 'z': [0.0] * n})()
    else:
      self.position = type('P', (), {'x': list(np.linspace(0, 60, n)),
                                     'y': list(np.linspace(0, 30, n)), 'z': [0.0] * n})()


class TestGetFutureCurvature(unittest.TestCase):
  def test_bad_shape_falls_back(self):
    m = type('M', (), {'orientationRate': type('O', (), {'z': [0.0]})(),
                       'velocity': type('V', (), {'x': [0.0]})()})()
    self.assertEqual(get_future_curvature(m, 0.123), 0.123)

  def test_straight_is_near_zero(self):
    self.assertAlmostEqual(get_future_curvature(_Model(yaw_rate=0.0), 9.9), 0.0, places=6)


class TestLimitAccelInTurns(unittest.TestCase):
  def test_straight_leaves_accel_untouched(self):
    a = limit_accel_in_turns(20.0, 0.0, [0.0, 1.5], 3.0)
    self.assertEqual(a, [0.0, 1.5])

  def test_sharp_curve_forbids_positive_accel(self):
    a = limit_accel_in_turns(20.0, 0.5, [0.0, 1.5], 3.0)
    self.assertLessEqual(a[1], 0.0)

  def test_low_speed_is_untouched(self):
    a = limit_accel_in_turns(0.05, 0.5, [0.0, 1.5], 3.0)
    self.assertEqual(a, [0.0, 1.5])

  def test_no_positive_target_is_untouched(self):
    a = limit_accel_in_turns(20.0, 0.5, [0.0, 0.0], 3.0)
    self.assertEqual(a, [0.0, 0.0])

  def test_never_raises_cap(self):
    a = limit_accel_in_turns(15.0, 0.03, [0.0, 2.0], 3.0, model_msg=_Model())
    self.assertLessEqual(a[1], 2.0)


if __name__ == "__main__":
  unittest.main()
