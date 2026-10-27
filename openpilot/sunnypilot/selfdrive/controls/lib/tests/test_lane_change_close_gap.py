import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.lane_change_close_gap import (
  DIRECTION_LEFT, DIRECTION_RIGHT, LC_STATE_FINISHING, LC_STATE_PRE, LC_STATE_STARTING,
  LaneChangeCloseGap)

LC_STATE_OFF = 0  # cereal LaneChangeState.off


def make_gap(enabled=True, requested=0.6, dt=0.05):
  return LaneChangeCloseGap(enabled=enabled, requested_seconds=requested, dt=dt)


class TestLaneChangeCloseGap(unittest.TestCase):
  def test_disabled_returns_base_and_resets(self):
    gap = make_gap(enabled=False)
    gap.update(True, 25.0, False, LC_STATE_FINISHING, DIRECTION_LEFT, False, False, False, 0.0, 2.2)
    self.assertEqual(2.4, gap.update(True, 25.0, False, LC_STATE_FINISHING, DIRECTION_LEFT, False, False, False, 0.0, 2.4))
    self.assertIsNone(gap._ramp)

  def test_off_state_returns_base(self):
    gap = make_gap()
    self.assertEqual(2.0, gap.update(True, 25.0, False, LC_STATE_OFF, DIRECTION_LEFT, False, False, False, 0.0, 2.0))

  def test_never_lengthens(self):
    # requested clamps to 1.0; with a base of 0.5 the absolute cap must keep 0.5
    gap = make_gap(requested=3.5)
    t = gap.update(True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, False, 0.0, 0.5)
    self.assertAlmostEqual(0.5, t, places=9)

  def test_ramps_toward_absolute_target(self):
    gap = make_gap(requested=0.6, dt=0.05)
    t = 2.0
    for _ in range(200):  # 10 s: ramp-in (0.6/s) fully converges
      t = gap.update(True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, False, 0.0, t)
    self.assertAlmostEqual(0.6, t, places=6)

  def test_ramp_snaps_back_fast_on_state_off(self):
    gap = make_gap(requested=0.6, dt=0.05)
    t = 2.0
    for _ in range(200):
      t = gap.update(True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, False, 0.0, t)
    self.assertAlmostEqual(0.6, t, places=6)
    # Signal off: 4.0 s/s ramp out (0.2 s per frame) recovers the base quickly.
    for _ in range(10):
      t = gap.update(True, 25.0, False, LC_STATE_OFF, DIRECTION_LEFT, False, False, False, 0.0, 2.0)
    self.assertEqual(2.0, t)

  def test_blindspot_veto_on_change_side(self):
    gap = make_gap(requested=0.6, dt=0.05)
    left = gap.update(True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, True, False, False, 0.0, 2.0)
    self.assertEqual(2.0, left)
    right = make_gap(requested=0.6, dt=0.05).update(
      True, 25.0, False, LC_STATE_STARTING, DIRECTION_RIGHT, False, True, False, 0.0, 2.0)
    self.assertEqual(2.0, right)
    # Blindspot on the *other* side does not veto.
    ok = make_gap(requested=0.6, dt=0.05).update(
      True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, True, False, 0.0, 2.0)
    self.assertLess(ok, 2.0)

  def test_standstill_and_low_speed_veto(self):
    gap = make_gap()
    self.assertEqual(2.0, gap.update(True, 0.0, True, LC_STATE_STARTING, DIRECTION_LEFT, False, False, False, 0.0, 2.0))
    self.assertEqual(2.0, gap.update(True, 5.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, False, 0.0, 2.0))

  def test_braking_lead_aborts(self):
    gap = make_gap()
    self.assertEqual(2.0, gap.update(True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, True, -0.9, 2.0))
    # Gentle lead decel does not abort.
    self.assertLess(gap.update(True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, True, -0.3, 2.0), 2.0)

  def test_not_long_enabled_resets(self):
    gap = make_gap()
    gap.update(True, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, False, 0.0, 2.0)
    self.assertEqual(1.5, gap.update(False, 25.0, False, LC_STATE_STARTING, DIRECTION_LEFT, False, False, False, 0.0, 1.5))
    self.assertIsNone(gap._ramp)

  def test_requested_clamped_to_range(self):
    self.assertEqual(0.25, make_gap(requested=0.1)._requested)
    self.assertEqual(1.0, make_gap(requested=9.9)._requested)


if __name__ == "__main__":
  unittest.main()
