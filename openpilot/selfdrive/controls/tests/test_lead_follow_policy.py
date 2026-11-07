#!/usr/bin/env python3
import unittest
from types import SimpleNamespace

from openpilot.selfdrive.controls.lib.lead_follow_policy import apply


def lead(*, d_rel=40.0, v_lead=20.0, a_lead=0.0, radar=False, model_prob=0.99, y_rel=0.0):
  return SimpleNamespace(
    status=True,
    dRel=d_rel,
    vLead=v_lead,
    aLeadK=a_lead,
    radar=radar,
    modelProb=model_prob,
    yRel=y_rel,
  )


def run(lead_one, *, lead_two=None, source="lead0", active=True, v_ego=20.0,
        previous=0.0, raw=0.0, post_departure=False, blocked=False, panic=False):
  return apply(
    lead_one,
    lead_two or SimpleNamespace(status=False),
    source=source,
    active=active,
    v_ego=v_ego,
    t_follow=1.45,
    previous_target=previous,
    raw_target=raw,
    tracking=active,
    post_departure=post_departure,
    blocked=blocked,
    panic_bypass=panic,
  )


class TestLeadFollowPolicy(unittest.TestCase):
  def test_follow_policy_never_reselects_or_fuses_leads(self):
    lead_one = lead(d_rel=80.0, v_lead=20.0)
    lead_two = lead(d_rel=35.0, v_lead=19.5)

    self.assertIs(run(lead_one, lead_two=lead_two, source="lead0").lead, lead_one)
    self.assertIs(run(lead_one, lead_two=lead_two, source="lead1").lead, lead_two)

    inactive = run(lead_one, lead_two=lead_two, source="lead1", active=False, raw=0.3)
    self.assertIsNone(inactive.lead)
    self.assertAlmostEqual(inactive.target, 0.3)

  def test_follow_policy_keeps_stop_and_panic_outputs_outside_comfort_path(self):
    for blocked in (True, False):
      result = run(lead(d_rel=8.0, v_lead=0.0), raw=-1.2, blocked=blocked, panic=not blocked)
      self.assertIsNone(result.lead)
      self.assertAlmostEqual(result.target, -1.2)

  def test_follow_policy_limits_small_post_lead_reversal(self):
    result = run(lead(d_rel=36.0, v_lead=20.2), v_ego=20.0, previous=-0.08, raw=0.45)
    self.assertLess(result.target, 0.45)
    self.assertLessEqual(result.target - (-0.08), 0.18)

  def test_follow_policy_deadbands_small_steady_sign_reversal(self):
    result = run(lead(d_rel=37.2, v_lead=24.0, radar=True), v_ego=24.0, previous=0.24, raw=-0.24)
    self.assertAlmostEqual(result.target, 0.0)

  def test_follow_policy_deadband_does_not_mask_closing_lead(self):
    result = run(lead(d_rel=37.2, v_lead=22.5, a_lead=-1.0, radar=True), v_ego=24.0, previous=0.24, raw=-0.24)
    self.assertLess(result.target, 0.0)

  def test_follow_policy_never_relaxes_material_braking(self):
    result = run(lead(d_rel=25.0, v_lead=18.0), v_ego=25.0, previous=0.30, raw=-1.2)
    self.assertAlmostEqual(result.target, -1.2)

  def test_follow_policy_leaves_low_speed_vision_departure_uncapped(self):
    # This is the range the old vision-only cap affected; below 4.5 m/s the
    # longitudinal planner still has its independent weak-lead safety cap.
    result = run(lead(d_rel=12.0, v_lead=6.0), v_ego=5.0, raw=1.4)
    self.assertIsNone(result.accel_cap)
    self.assertAlmostEqual(result.target, 1.4)

  def test_follow_policy_low_speed_vision_never_relaxes_braking(self):
    for v_ego in (0.0, 2.0, 4.5, 6.0, 7.9):
      result = run(
        lead(d_rel=8.0, v_lead=max(v_ego - 0.8, 0.0), a_lead=-0.8),
        v_ego=v_ego,
        previous=0.3,
        raw=-0.6,
      )
      self.assertLessEqual(result.target, -0.6)

  def test_follow_policy_bypasses_post_departure_handoff(self):
    result = run(lead(d_rel=46.0, v_lead=22.0), v_ego=20.0, previous=0.0, raw=0.6, post_departure=True)
    self.assertAlmostEqual(result.target, 0.6)
    self.assertIsNone(result.accel_cap)


if __name__ == "__main__":
  unittest.main()
