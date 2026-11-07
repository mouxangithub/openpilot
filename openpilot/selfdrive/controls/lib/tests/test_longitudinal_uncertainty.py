"""Pure-logic unit tests for the StarPilot uncertainty/panic-bypass port.

Only covers functions importable on dev machines (no capnp/messaging); the
full planner integration is exercised on device.
"""
import unittest
from types import SimpleNamespace


from openpilot.selfdrive.controls.lib.longitudinal_uncertainty import (
  UNCERT_MAG_TRIG,
  UNCERT_SLOPE_TRIG,
  UncertaintyTracker,
  compute_raw_uncertainty,
  is_urgent_lead_scenario,
  panic_window_flags,
  should_panic_bypass,
)

DT = 0.05  # DT_MDL


def make_meta(desire=None, brake=None):
  meta = SimpleNamespace()
  if desire is not None:
    meta.desirePrediction = desire
  if brake is not None:
    meta.disengagePredictions = SimpleNamespace(brakePressProbs=brake)
  return meta


class TestComputeRawUncertainty(unittest.TestCase):
  def test_none_meta_is_zero(self):
    self.assertEqual(compute_raw_uncertainty(None), 0.0)

  def test_uniform_desire_gives_max_entropy(self):
    # 4-way uniform -> normalized entropy 1.0, no brake risk
    raw = compute_raw_uncertainty(make_meta(desire=[1.0, 1.0, 1.0, 1.0]))
    self.assertAlmostEqual(raw, 1.0, places=6)

  def test_one_hot_desire_gives_zero_entropy(self):
    raw = compute_raw_uncertainty(make_meta(desire=[0.0, 1.0, 0.0, 0.0]))
    self.assertAlmostEqual(raw, 0.0, places=6)

  def test_all_zero_desire_guards_to_zero(self):
    raw = compute_raw_uncertainty(make_meta(desire=[0.0, 0.0]))
    self.assertAlmostEqual(raw, 0.0, places=6)

  def test_brake_risk_decayed_max(self):
    # Constant prob p over horizon: risk = max(p * exp(-lam*t)) = p (at t=0)
    p = 0.6
    raw = compute_raw_uncertainty(make_meta(desire=[0.0, 1.0], brake=[p] * 10))
    self.assertAlmostEqual(raw, p, places=6)

  def test_early_brake_peak_dominates_late(self):
    early = compute_raw_uncertainty(make_meta(desire=[1.0, 0.0], brake=[0.5, 0.0, 0.0, 0.0]))
    late = compute_raw_uncertainty(make_meta(desire=[1.0, 0.0], brake=[0.0, 0.0, 0.0, 0.5]))
    self.assertGreater(early, late)

  def test_tiny_blips_are_halved(self):
    below = [0.01] * 10  # max < clip threshold
    raw_halved = compute_raw_uncertainty(make_meta(desire=[1.0, 0.0], brake=below))
    raw_double = compute_raw_uncertainty(make_meta(desire=[1.0, 0.0], brake=[0.02] * 10))
    # halving the raw probs before decay must reduce the metric
    self.assertLess(raw_halved, raw_double)

  def test_combined_metric_adds(self):
    desire_entropy = 1.0
    brake_p = 0.4
    raw = compute_raw_uncertainty(make_meta(desire=[1.0, 1.0, 1.0, 1.0], brake=[brake_p] * 5))
    self.assertAlmostEqual(raw, desire_entropy + brake_p, places=6)


class TestUncertaintyTracker(unittest.TestCase):
  def test_converges_to_constant_input(self):
    tracker = UncertaintyTracker(DT)
    for i in range(600):
      u, ua, slope = tracker.update(1.0, i * DT)
    self.assertAlmostEqual(u, 1.0, delta=0.05)
    self.assertAlmostEqual(ua, 1.0, delta=0.05)
    self.assertLess(abs(slope), UNCERT_SLOPE_TRIG)

  def test_slope_positive_on_step(self):
    tracker = UncertaintyTracker(DT)
    tracker.update(0.0, 0.0)
    _, _, slope = tracker.update(1.0, DT)
    self.assertGreater(slope, UNCERT_SLOPE_TRIG)

  def test_accel_track_is_permissive_min(self):
    tracker = UncertaintyTracker(DT)
    # after a step down, the fast track cools down sooner
    for i in range(300):
      tracker.update(1.0, i * DT)
    u, ua, _ = tracker.update(0.0, 300 * DT)
    self.assertLessEqual(ua, u)

  def test_first_update_slope_is_zero(self):
    tracker = UncertaintyTracker(DT)
    _, _, slope = tracker.update(1.0, 0.0)
    self.assertEqual(slope, 0.0)


class TestPanicWindow(unittest.TestCase):
  def make_lead(self, d_rel=50.0, v_lead=20.0, present=True):
    return SimpleNamespace(present=present, status=present, dRel=d_rel, vLead=v_lead)

  def test_no_lead_never_panics(self):
    pw, cs, cf = panic_window_flags(None, 25.0, 40.0)
    self.assertFalse(pw)
    self.assertFalse(cf)
    pw, cs, cf = panic_window_flags(self.make_lead(present=False), 25.0, 40.0)
    self.assertFalse(pw)

  def test_close_window_bounds(self):
    v_ego = 25.0
    lead = self.make_lead(d_rel=38.0)
    scene_gap = 30.0
    pw, _, _ = panic_window_flags(lead, v_ego, scene_gap)
    self.assertTrue(pw)  # 38 <= 30 + 8.75
    lead_far = self.make_lead(d_rel=45.0)
    pw, _, _ = panic_window_flags(lead_far, v_ego, scene_gap)
    self.assertFalse(pw)  # 45 > 38.75

  def test_closing_fast_threshold(self):
    lead = self.make_lead(d_rel=30.0, v_lead=20.0)
    # v_ego 23 -> closing 3.0 >= max(2.0, 0.08*23=1.84)
    pw, cs, cf = panic_window_flags(lead, 23.0, 40.0)
    self.assertAlmostEqual(cs, 3.0)
    self.assertTrue(cf)
    # v_ego 21 -> closing 1.0 < 2.0
    pw, cs, cf = panic_window_flags(lead, 21.0, 40.0)
    self.assertAlmostEqual(cs, 1.0)
    self.assertFalse(cf)

  def test_panic_requires_window_and_fast(self):
    # magnitude alone without closing fast -> no bypass
    self.assertFalse(should_panic_bypass(0.9, 0.0, panic_close_window=True, closing_fast=False))
    self.assertFalse(should_panic_bypass(0.9, 0.0, panic_close_window=False, closing_fast=True))
    # slope trigger with both windows -> bypass
    self.assertTrue(should_panic_bypass(0.2, UNCERT_SLOPE_TRIG + 0.01, True, True))
    # magnitude trigger with both windows -> bypass
    self.assertTrue(should_panic_bypass(UNCERT_MAG_TRIG, 0.0, True, True))
    # below both triggers -> no bypass
    self.assertFalse(should_panic_bypass(0.3, 0.05, True, True))


class TestUrgentLeadScenario(unittest.TestCase):
  def test_closing_fast_close_range_is_urgent(self):
    lead = SimpleNamespace(present=True, dRel=20.0, vLead=10.0)
    # closing 5 m/s, ttc 4s < 7
    self.assertTrue(is_urgent_lead_scenario(lead, 15.0))

  def test_far_lead_not_urgent(self):
    lead = SimpleNamespace(present=True, dRel=140.0, vLead=10.0)
    self.assertFalse(is_urgent_lead_scenario(lead, 15.0))

  def test_slow_closing_not_urgent(self):
    lead = SimpleNamespace(present=True, dRel=30.0, vLead=14.9)
    self.assertFalse(is_urgent_lead_scenario(lead, 15.0))

  def test_none_lead(self):
    self.assertFalse(is_urgent_lead_scenario(None, 15.0))


if __name__ == "__main__":
  unittest.main()
