"""Tests for the lead-drop comfort relaxation.

The veto list is the safety boundary, so every veto gets a test and the
invariants (never below the raw target, state resets) get their own.
"""
import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.lead_drop_relaxation import (
  DECEL_V,
  LEAD_PERSIST_FRAMES,
  MIN_DISTANCE,
  MIN_HEADWAY,
  MIN_SPEED,
  OVERSPEED_BP,
  LeadDropRelaxation,
  interp_linear,
  lead_brake,
)

DT = 0.05  # slower than the real model rate, so one step moves further


def relaxed_step(mod: LeadDropRelaxation, raw: float, v_ego: float, **kw) -> float:
  defaults = {"lead_present": True, "lead_status": True,
              "d_rel": 120.0, "v_lead": raw, "a_lead_k": 0.0, "override_active": False}
  defaults.update(kw)
  return mod.relax(raw, v_ego, **defaults)


def prime_lead(mod: LeadDropRelaxation, raw: float, v_ego: float, **kw) -> None:
  """Run enough updates with a stable lead for the persistence gate."""
  for _ in range(LEAD_PERSIST_FRAMES + 1):
    relaxed_step(mod, raw, v_ego, **kw)


class TestInterpLinear(unittest.TestCase):
  def test_below_the_first_breakpoint_is_flat(self):
    self.assertEqual(interp_linear(-1.0, OVERSPEED_BP, DECEL_V), DECEL_V[0])

  def test_above_the_last_breakpoint_is_flat(self):
    self.assertEqual(interp_linear(100.0, OVERSPEED_BP, DECEL_V), DECEL_V[-1])

  def test_at_breakpoints_it_is_exact(self):
    for x, fp in zip(OVERSPEED_BP, DECEL_V, strict=True):
      self.assertEqual(interp_linear(x, OVERSPEED_BP, DECEL_V), fp)

  def test_between_breakpoints_it_is_linear(self):
    x0, x1 = OVERSPEED_BP[0], OVERSPEED_BP[1]
    self.assertAlmostEqual(interp_linear((x0 + x1) / 2, OVERSPEED_BP, DECEL_V),
                           (DECEL_V[0] + DECEL_V[1]) / 2)

  def test_at_a_breakpoint_midway_it_takes_that_value_exactly(self):
    self.assertEqual(interp_linear(OVERSPEED_BP[2], OVERSPEED_BP, DECEL_V), DECEL_V[2])

  def test_lead_brake_floors_positive_accel_at_zero(self):
    self.assertEqual(lead_brake(0.4), 0.0)
    self.assertEqual(lead_brake(-0.4), 0.4)


class TestEngagement(unittest.TestCase):
  def test_a_fresh_module_passes_the_raw_target_through(self):
    # No applied target yet: there is nothing to soften against.
    mod = LeadDropRelaxation(DT)
    self.assertEqual(relaxed_step(mod, 20.0, 30.0), 20.0)

  def test_the_lead_must_persist_before_relaxation_engages(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    # Now a sudden drop; the first relaxed answer must be above the raw one.
    out = relaxed_step(mod, 22.0, 33.0)
    self.assertGreater(out, 22.0)

  def test_a_flickering_lead_never_relaxes(self):
    mod = LeadDropRelaxation(DT)
    for i in range(LEAD_PERSIST_FRAMES * 3):
      present = (i % 4) != 3  # disappears every fourth frame
      relaxed_step(mod, 30.0, 33.0, lead_present=present, lead_status=present)
    out = relaxed_step(mod, 22.0, 33.0, lead_present=True)
    self.assertEqual(out, 22.0)

  def test_no_lead_means_no_relaxation(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    out = relaxed_step(mod, 22.0, 33.0, lead_present=False, lead_status=False)
    self.assertEqual(out, 22.0)

  def test_an_unstatused_lead_means_no_relaxation(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    out = relaxed_step(mod, 22.0, 33.0, lead_status=False)
    self.assertEqual(out, 22.0)


class TestVetoes(unittest.TestCase):
  def setUp(self):
    self.mod = LeadDropRelaxation(DT)
    prime_lead(self.mod, 30.0, 33.0)

  def test_target_rising_is_not_softened(self):
    self.assertEqual(relaxed_step(self.mod, 32.0, 33.0), 32.0)

  def test_target_equal_is_not_softened(self):
    self.assertEqual(relaxed_step(self.mod, 30.0, 33.0), 30.0)

  def test_below_the_minimum_speed_is_not_softened(self):
    self.assertEqual(relaxed_step(self.mod, 18.0, MIN_SPEED - 0.1), 18.0)

  def test_at_or_above_the_car_speed_is_not_softened(self):
    self.assertEqual(relaxed_step(self.mod, 32.98, 33.0), 32.98)

  def test_a_close_lead_is_not_softened(self):
    out = relaxed_step(self.mod, 22.0, 33.0, d_rel=MIN_DISTANCE - 1.0)
    self.assertEqual(out, 22.0)

  def test_a_close_headway_is_not_softened(self):
    out = relaxed_step(self.mod, 22.0, 40.0, d_rel=40.0 * MIN_HEADWAY - 1.0)
    self.assertEqual(out, 22.0)

  def test_a_lead_much_slower_than_the_new_limit_is_not_softened(self):
    out = relaxed_step(self.mod, 22.0, 33.0, v_lead=22.0 - 0.5)
    self.assertEqual(out, 22.0)

  def test_a_hard_braking_lead_is_not_softened(self):
    out = relaxed_step(self.mod, 22.0, 33.0, a_lead_k=-0.4)
    self.assertEqual(out, 22.0)

  def test_override_is_not_softened(self):
    out = relaxed_step(self.mod, 22.0, 33.0, override_active=True)
    self.assertEqual(out, 22.0)

  def test_a_nonpositive_raw_target_is_not_softened(self):
    self.assertEqual(relaxed_step(self.mod, 0.0, 33.0), 0.0)


class TestBehaviour(unittest.TestCase):
  def test_the_relaxed_target_never_drops_faster_than_the_comfort_rate(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    out = relaxed_step(mod, 22.0, 33.0)
    # 11 m/s of overspeed is past the last breakpoint: the firmest rate.
    self.assertAlmostEqual(out, 30.0 - 1.35 * DT, places=9)

  def test_the_relaxed_target_is_never_below_the_raw_one(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    # A huge drop: the comfort step still lands above the raw target.
    out = relaxed_step(mod, 10.0, 33.0)
    self.assertGreaterEqual(out, 10.0)

  def test_relaxation_converges_to_the_raw_target(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    for _ in range(400):
      out = relaxed_step(mod, 22.0, 33.0)
    self.assertAlmostEqual(out, 22.0, places=3)

  def test_the_applied_target_follows_the_raw_target_when_not_relaxing(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 20.0, 33.0)
    relaxed_step(mod, 30.0, 33.0)  # a rise: stored, not relaxed
    # A later drop relaxes against the new stored value, not the old one.
    out = relaxed_step(mod, 25.0, 33.0)
    # 8 m/s of overspeed is past the last breakpoint: the firmest rate.
    self.assertAlmostEqual(out, 30.0 - 1.35 * DT, places=9)

  def test_reset_clears_both_state_variables(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    mod.reset()
    self.assertFalse(mod.lead_trusted)
    self.assertEqual(relaxed_step(mod, 22.0, 33.0), 22.0)

  def test_a_nonpositive_target_clears_the_persisted_one(self):
    mod = LeadDropRelaxation(DT)
    prime_lead(mod, 30.0, 33.0)
    relaxed_step(mod, 0.0, 33.0)
    # After the raw target vanished, a drop has nothing to soften against.
    self.assertEqual(relaxed_step(mod, 22.0, 33.0), 22.0)


if __name__ == "__main__":
  unittest.main()
