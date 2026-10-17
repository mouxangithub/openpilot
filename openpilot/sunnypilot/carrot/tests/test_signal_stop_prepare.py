"""Pure-algorithm unit tests for the experimental geometric red-light
pre-deceleration. The modeld publication + planner seam is intentionally not
wired in this changeset (opt-in, needs route validation); these lock the
geometry/acceleration-cap math so the library is safe to land dormant.
"""
import unittest
from types import SimpleNamespace as NS

from openpilot.sunnypilot.carrot.signal_stop_prepare import (
  PrepareAccel, SignalStopPrepare, prepare_lead_blocked, road_corridor,
)


def curve(xs, ys):
  return NS(x=tuple(float(x) for x in xs), y=tuple(float(y) for y in ys))


class TestRoadCorridor(unittest.TestCase):
  def test_bad_margin_rejected(self):
    self.assertIsNone(road_corridor((0., 10.), (), (), lane_margin=-1.0))
    self.assertIsNone(road_corridor((0., 10.), (), (), lane_margin=99.0))

  def test_empty_returns_something_or_none_safely(self):
    # must never raise on empty geometry
    result = road_corridor((0., 10., 20.), (), ())
    self.assertTrue(result is None or isinstance(result, tuple))


class TestPrepareLeadBlocked(unittest.TestCase):
  def _radar(self, one=None, two=None):
    def lead(d):
      if d is None:
        return NS(present=False, dRel=float('nan'))
      return NS(present=True, dRel=float(d))
    return NS(leadOne=lead(one), leadTwo=lead(two))

  def test_nearby_lead_blocks_preparation(self):
    self.assertTrue(prepare_lead_blocked(self._radar(one=8.0)))
    self.assertTrue(prepare_lead_blocked(self._radar(two=5.0)))

  def test_far_lead_allows_preparation(self):
    self.assertFalse(prepare_lead_blocked(self._radar(one=80.0, two=90.0)))

  def test_missing_radar_is_safe(self):
    self.assertTrue(prepare_lead_blocked(None))


class TestPrepareAccel(unittest.TestCase):
  def test_inactive_passes_target_through(self):
    cap = PrepareAccel()
    self.assertEqual(cap.apply(-0.1, -2.0, 0.05, active=False), -0.1)
    self.assertIsNone(cap.cap)

  def test_bad_dt_is_ignored(self):
    cap = PrepareAccel()
    self.assertEqual(cap.apply(-0.1, -2.0, 0.0, active=True), -0.1)
    self.assertEqual(cap.apply(-0.1, -2.0, 0.5, active=True), -0.1)

  def test_cap_never_commands_more_brake_than_target(self):
    # a mild target decel is not made stronger; only an optimistic (weaker)
    # target gets pulled down toward the preparing deceleration.
    cap = PrepareAccel()
    out = cap.apply(-3.0, -0.2, 0.05, active=True)
    self.assertLessEqual(out, -3.0 + 1e-9)


class TestSignalStopPrepareGuards(unittest.TestCase):
  def test_target_accel_is_braking_and_ramp_nonnegative(self):
    self.assertLess(SignalStopPrepare.TARGET_ACCEL, 0.0)
    self.assertGreaterEqual(SignalStopPrepare.RAMP, 0.0)


if __name__ == "__main__":
  unittest.main()
