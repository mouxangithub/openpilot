"""Pure-logic unit tests for the StarPilot stop/depart policy port.

Only covers functions importable on dev machines (no capnp/messaging); the
full planner integration is exercised on device.
"""
import unittest
from types import SimpleNamespace

from openpilot.selfdrive.controls.lib.lead_stop_depart_policy import (
  RADAR_STANDSTILL_GAP_SETTLE_ACCEL,
  STANDSTILL_LEAD_CREEP_RELEASE_MIN_ACCEL,
  STANDSTILL_LEAD_DEPART_MIN_ACCEL,
  STANDSTILL_STOPPED_LEAD_GUARD_MAX_BRAKE,
  STANDSTILL_STOPPED_LEAD_GUARD_MIN_BRAKE,
  VISION_CLOSE_STOP_HOLD_MAX_BRAKE,
  VISION_CLOSE_STOP_HOLD_MIN_BRAKE,
  VISION_LEAD_APPROACH_MAX_DECEL,
  VISION_LEAD_APPROACH_MIN_DECEL,
  VISION_LOW_SPEED_STOP_BUFFER_BRAKE_GAIN,
  VISION_LOW_SPEED_STOP_BUFFER_MIN_BRAKE,
  LeadStopDepartPolicy,
  StopDepartContext,
  _lead_present,
)


def make_lead(radar=False, d_rel=30.0, v_lead=20.0, a_lead=0.0, prob=0.99, y_rel=0.0, present=True):
  return SimpleNamespace(present=present, status=present, radar=radar, dRel=d_rel, vLead=v_lead,
                         aLeadK=a_lead, modelProb=prob, yRel=y_rel)


def make_policy(v_ego=0.0):
  cp = SimpleNamespace(longitudinalActuatorDelay=0.15, carFingerprint="TOYOTA_WILDLANDER_PHEV", brand="toyota")
  return LeadStopDepartPolicy(cp, dt=0.05)


def make_ctx(policy, lead_one=None, lead_two=None, v_ego=0.0, a_target=0.0, should_stop=False,
             standstill=False, tracking=True, active=True, t_follow=1.8, model_desired_accel=0.0,
             model_should_stop=False):
  return StopDepartContext(
    CP=policy.CP, dt=policy.dt, lead_one=lead_one, lead_two=lead_two,
    v_ego=v_ego, standstill=standstill, brake_pressed=False, gas_pressed=False,
    long_control_stopping=False, active=active, tracking=tracking, t_follow=t_follow,
    a_target=a_target, should_stop=should_stop, output_accel_min=-1.2,
    model_desired_accel=model_desired_accel, model_should_stop=model_should_stop,
    model_data=None,
  )


class TestLeadPresence(unittest.TestCase):
  def test_reads_sp_present_flag(self):
    self.assertTrue(_lead_present(SimpleNamespace(present=True)))
    self.assertFalse(_lead_present(SimpleNamespace(present=False)))

  def test_reads_starpilot_status_flag(self):
    self.assertTrue(_lead_present(SimpleNamespace(status=True)))
    self.assertFalse(_lead_present(SimpleNamespace(status=False)))

  def test_none_lead_is_absent(self):
    self.assertFalse(_lead_present(None))


class TestVisionApproachCap(unittest.TestCase):
  def test_none_for_radar_lead(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=10.0, v_lead=5.0, a_lead=-1.0)
    self.assertIsNone(policy.get_vision_lead_approach_cap(lead, 20.0, -1.2, 1.8))

  def test_none_before_trigger_window(self):
    policy = make_policy()
    # far above the tight-follow window: t_follow*v + buffer = 1.8*20+2 = 38m
    lead = make_lead(d_rel=90.0, v_lead=15.0, prob=0.99)
    self.assertIsNone(policy.get_vision_lead_approach_cap(lead, 20.0, -1.2, 1.8))

  def test_cap_in_expected_range_at_tight_follow(self):
    policy = make_policy()
    lead = make_lead(d_rel=20.0, v_lead=8.0, prob=0.99)
    cap = policy.get_vision_lead_approach_cap(lead, 10.0, -2.0, 1.8)
    self.assertIsNotNone(cap)
    self.assertLessEqual(cap, -VISION_LEAD_APPROACH_MIN_DECEL + 1e-9)
    self.assertGreaterEqual(cap, -VISION_LEAD_APPROACH_MAX_DECEL - 1e-9)

  def test_low_model_prob_is_ignored(self):
    policy = make_policy()
    lead = make_lead(d_rel=30.0, v_lead=10.0, prob=0.5)
    self.assertIsNone(policy.get_vision_lead_approach_cap(lead, 20.0, -1.2, 1.8))


class TestLowSpeedStopBuffer(unittest.TestCase):
  def test_entry_context_floors_brake(self):
    policy = make_policy()
    lead = make_lead(d_rel=6.0, v_lead=0.5, prob=0.95)
    cap, active = policy.get_vision_low_speed_stop_buffer_cap(lead, 3.0, -2.0)
    self.assertTrue(active)
    self.assertIsNotNone(cap)
    self.assertAlmostEqual(cap, -(VISION_LOW_SPEED_STOP_BUFFER_MIN_BRAKE + VISION_LOW_SPEED_STOP_BUFFER_BRAKE_GAIN * 3.0))

  def test_brake_floor_scales_with_speed(self):
    policy = make_policy()
    lead = make_lead(d_rel=4.0, v_lead=0.5, prob=0.95)
    slow, _ = policy.get_vision_low_speed_stop_buffer_cap(lead, 1.0, -2.0)
    fast, _ = policy.get_vision_low_speed_stop_buffer_cap(lead, 5.0, -2.0)
    self.assertIsNotNone(slow)
    self.assertIsNotNone(fast)
    self.assertLess(fast, slow)

  def test_no_latch_for_radar_lead(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=6.0, v_lead=0.5)
    cap, active = policy.get_vision_low_speed_stop_buffer_cap(lead, 3.0, -1.2)
    self.assertIsNone(cap)
    self.assertFalse(active)


class TestStandstillStoppedLeadGuard(unittest.TestCase):
  def test_floor_clamped_between_bounds(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=6.0, v_lead=0.2, prob=1.0)
    cap = policy.get_standstill_stopped_lead_guard_cap(lead, 0.0, -1.2, 5.5, False, False)
    self.assertIsNotNone(cap)
    self.assertGreaterEqual(cap, -STANDSTILL_STOPPED_LEAD_GUARD_MAX_BRAKE - 1e-9)
    self.assertLessEqual(cap, -STANDSTILL_STOPPED_LEAD_GUARD_MIN_BRAKE + 1e-9)

  def test_released_when_depart_ready(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=6.0, v_lead=0.2, prob=1.0)
    self.assertIsNone(policy.get_standstill_stopped_lead_guard_cap(lead, 0.0, -1.2, 5.5, True, False))

  def test_ignores_far_lead(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=40.0, v_lead=0.2, prob=1.0)
    self.assertIsNone(policy.get_standstill_stopped_lead_guard_cap(lead, 0.0, -1.2, 5.5, False, False))


class TestDepartDetection(unittest.TestCase):
  def test_confident_depart_window(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=4.5, v_lead=0.8, a_lead=0.3)
    self.assertTrue(policy.is_confident_lead_depart(lead, 0.0))
    # outside the gap window
    lead_far = make_lead(radar=True, d_rel=8.0, v_lead=0.8, a_lead=0.3)
    self.assertFalse(policy.is_confident_lead_depart(lead_far, 0.0))
    # too slow lead
    lead_slow = make_lead(radar=True, d_rel=4.5, v_lead=0.1, a_lead=0.3)
    self.assertFalse(policy.is_confident_lead_depart(lead_slow, 0.0))

  def test_slow_creep_depart_uses_stock_thresholds_without_tune(self):
    policy = make_policy()
    nudge_gap = 5.5
    lead = make_lead(radar=True, d_rel=nudge_gap + 0.2, v_lead=0.3, a_lead=0.1, prob=1.0)
    self.assertTrue(policy.is_slow_creep_lead_depart(lead, 0.0, nudge_gap))
    lead_weak = make_lead(radar=True, d_rel=nudge_gap + 0.2, v_lead=0.3, a_lead=0.05, prob=1.0)
    self.assertFalse(policy.is_slow_creep_lead_depart(lead_weak, 0.0, nudge_gap))

  def test_apply_releases_depart_after_confirm(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=4.5, v_lead=0.8, a_lead=0.4, prob=1.0)

    # first frames build the confident-depart confirm timer
    for _ in range(8):  # 8 * 0.05 = 0.40s >= 0.35s confirm time
      result = policy.apply(make_ctx(policy, lead_one=lead, v_ego=0.0, a_target=0.0,
                                     should_stop=True, standstill=True, tracking=False))
    self.assertGreaterEqual(result.a_target, STANDSTILL_LEAD_DEPART_MIN_ACCEL)
    self.assertFalse(result.should_stop)

  def test_apply_creep_release_uses_lower_min_accel(self):
    policy = make_policy()
    # creep: slow lead, high prob, just past the nudge gap; not confident-depart
    lead = make_lead(radar=True, d_rel=6.0, v_lead=0.4, a_lead=0.12, prob=1.0)
    for _ in range(8):  # 0.40s >= 0.30s creep confirm
      result = policy.apply(make_ctx(policy, lead_one=lead, v_ego=0.0, a_target=0.0,
                                     should_stop=True, standstill=True, tracking=False))
    # The creep release (0.18) may be trimmed further by the low-speed weak-lead
    # cap (StarPilot ordering); the observable contract is: stop released,
    # positive launch accel, capped at the creep minimum.
    self.assertFalse(result.should_stop)
    self.assertGreater(result.a_target, 0.0)
    self.assertLessEqual(result.a_target, STANDSTILL_LEAD_CREEP_RELEASE_MIN_ACCEL + 1e-9)

  def test_apply_passthrough_without_leads(self):
    policy = make_policy()
    result = policy.apply(make_ctx(policy, lead_one=None, lead_two=None, v_ego=15.0,
                                   a_target=-0.4, should_stop=False, tracking=False))
    self.assertEqual(result.a_target, -0.4)
    self.assertFalse(result.should_stop)


class TestGapSettle(unittest.TestCase):
  def test_candidate_requires_radar_or_vision_flag(self):
    policy = make_policy()
    vision_lead = make_lead(radar=False, d_rel=6.8, v_lead=0.0, prob=0.995)
    self.assertFalse(policy.is_radar_standstill_gap_settle_candidate(vision_lead, 0.0, 5.5))
    self.assertTrue(policy.is_radar_standstill_gap_settle_candidate(vision_lead, 0.0, 5.5, allow_vision=True))

  def test_confirmed_settle_returns_settle_accel(self):
    policy = make_policy()
    lead = make_lead(radar=True, d_rel=6.8, v_lead=0.0, prob=1.0)
    ctx = make_ctx(policy, lead_one=lead, v_ego=0.0, a_target=0.0, should_stop=True,
                   standstill=True, tracking=False)
    self.assertFalse(policy.update_radar_standstill_gap_settle(ctx, 5.5))
    for _ in range(11):  # 11 * 0.05 >= 0.50s confirm
      active = policy.update_radar_standstill_gap_settle(ctx, 5.5)
    self.assertTrue(active)
    result = policy.apply(make_ctx(policy, lead_one=lead, v_ego=0.0, a_target=0.0,
                                   should_stop=True, standstill=True, tracking=False))
    # Settle requests 0.18; the low-speed weak-lead cap may trim it (StarPilot
    # ordering). The contract: stop released with positive accel.
    self.assertFalse(result.should_stop)
    self.assertGreater(result.a_target, 0.0)
    self.assertLessEqual(result.a_target, RADAR_STANDSTILL_GAP_SETTLE_ACCEL + 1e-9)


class TestDynamicTFollow(unittest.TestCase):
  def test_only_increases_and_rate_limited(self):
    policy = make_policy()
    lead = make_lead(d_rel=25.0, v_lead=12.0, prob=0.99)
    tf = policy.get_dynamic_t_follow(1.8, lead, 20.0)
    self.assertGreaterEqual(tf, 1.8)
    self.assertLessEqual(tf, 1.8 + 1.0 * 0.05 + 1e-9)  # rate up * dt

  def test_no_lead_keeps_base(self):
    policy = make_policy()
    self.assertEqual(policy.get_dynamic_t_follow(1.8, None, 20.0), 1.8)


class TestCloseStopHoldCaps(unittest.TestCase):
  def test_stop_hold_floor_range(self):
    policy = make_policy()
    lead = make_lead(d_rel=2.5, v_lead=0.2, prob=0.99)
    cap = policy.get_vision_close_stop_hold_cap(lead, 0.5, -1.2, True)
    self.assertIsNotNone(cap)
    self.assertGreaterEqual(cap, -VISION_CLOSE_STOP_HOLD_MAX_BRAKE - 1e-9)
    self.assertLessEqual(cap, -VISION_CLOSE_STOP_HOLD_MIN_BRAKE + 1e-9)

  def test_release_hold_requires_no_stop(self):
    policy = make_policy()
    lead = make_lead(d_rel=3.0, v_lead=1.0, prob=0.99)
    self.assertIsNone(policy.get_vision_close_release_hold_cap(lead, 0.5, -1.2, True))

  def test_final_guard_applies_when_stopped_lead_close(self):
    policy = make_policy()
    lead = make_lead(d_rel=2.0, v_lead=0.1, prob=0.99)
    self.assertIsNotNone(policy.get_vision_close_final_guard_cap(lead, 0.3, -1.2))


class TestInsideGapClosingCap(unittest.TestCase):
  def test_none_below_speed_gate(self):
    policy = make_policy()
    lead = make_lead(d_rel=20.0, v_lead=2.0)
    self.assertIsNone(policy.get_inside_gap_closing_lead_accel_cap(lead, 5.0, -1.2, 1.8))

  def test_cap_when_far_inside_desired_gap(self):
    policy = make_policy()
    lead = make_lead(d_rel=15.0, v_lead=10.0)
    cap = policy.get_inside_gap_closing_lead_accel_cap(lead, 20.0, -1.2, 1.8)
    self.assertIsNotNone(cap)
    self.assertGreaterEqual(cap, -0.65 - 1e-9)


if __name__ == "__main__":
  unittest.main()
