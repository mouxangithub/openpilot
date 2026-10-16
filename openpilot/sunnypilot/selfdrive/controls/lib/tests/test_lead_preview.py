"""Lead-deceleration preview (ported from carrot): a bounded early-deceleration
preview of the MPC plan when the radar lead brakes. Preview only ever lowers
the target; the lead-accel-response MPC cost path is ported but unwired
(sp's long_mpc does not take cost factors yet)."""
import unittest
from unittest.mock import MagicMock

from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_preview import (
  apply_preview_target, clip_preview_offset, get_lead_preview_request,
  lead_accel_response_allowed, rate_limit_preview,
)


class TestPreviewRequest(unittest.TestCase):
  def test_no_lead_is_inactive(self):
    r = get_lead_preview_request(3, lead_status=False, a_lead=-2.0, a_ego=0.0)
    self.assertFalse(r.active)
    self.assertEqual(r.offset_s, 0.0)

  def test_braking_lead_requests_preview(self):
    r = get_lead_preview_request(3, lead_status=True, a_lead=-2.0, a_ego=0.0)
    self.assertTrue(r.active)
    self.assertGreater(r.offset_s, 0.0)
    self.assertLess(r.lead_accel_signal, 0.0)

  def test_accelerating_lead_requests_nothing(self):
    r = get_lead_preview_request(3, lead_status=True, a_lead=1.0, a_ego=0.0)
    self.assertTrue(r.active)
    self.assertEqual(r.offset_s, 0.0)

  def test_offset_is_capped(self):
    r = get_lead_preview_request(3, lead_status=True, a_lead=-9.0, a_ego=0.0)
    self.assertLessEqual(r.offset_s, 1.5)

  def test_non_finite_is_inactive(self):
    r = get_lead_preview_request(3, lead_status=True, a_lead=float('nan'), a_ego=0.0)
    self.assertFalse(r.active)


class TestRateLimitAndClip(unittest.TestCase):
  def test_attack_faster_than_release(self):
    cur = 0.0
    for _ in range(3):
      cur = rate_limit_preview(1.0, cur)
    up = cur
    for _ in range(3):
      cur = rate_limit_preview(0.0, cur)
    self.assertGreater(up, 0.0)
    self.assertGreaterEqual(1.0 - cur, up)  # released at least as far as it rose in same count

  def test_clip_bounds_offset(self):
    self.assertLessEqual(clip_preview_offset(0.1, 5.0), 2.5)
    self.assertGreaterEqual(clip_preview_offset(0.1, -5.0), -0.05)


class TestApplyPreviewTarget(unittest.TestCase):
  def test_never_raises_target(self):
    for base in (-1.0, 0.0, 0.5, 2.0):
      for preview in (-2.0, 0.0, 1.0):
        out = apply_preview_target(base, preview, 3)
        self.assertLessEqual(out, base, (base, preview))

  def test_bounded_decel_floor(self):
    # base>0 branch: bounded by the mode's prebrake floor (Normal=-0.03),
    # so an extreme preview cannot command a hard brake.
    out = apply_preview_target(0.5, -5.0, 3)
    self.assertAlmostEqual(out, -0.03, places=6)


class TestLeadAccelResponsePure(unittest.TestCase):
  """Pure policy check for the ported-but-unwired cost-factor path."""

  def test_receding_lead_not_allowed(self):
    self.assertFalse(lead_accel_response_allowed(3, v_rel=-1.0, gap_margin=5.0,
                                                 lead_accel_signal=1.0, a_lead=1.0))

  def test_no_gap_margin_not_allowed(self):
    self.assertFalse(lead_accel_response_allowed(3, v_rel=0.5, gap_margin=0.0,
                                                 lead_accel_signal=1.0, a_lead=1.0))


class TestPlannerGate(unittest.TestCase):
  def _planner(self, enabled: bool):
    from opendbc.car import structs
    from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlannerSP
    cp = structs.CarParams(brand="mazda", openpilotLongitudinalControl=True, longitudinalActuatorDelay=0.36)
    planner = LongitudinalPlannerSP(cp, structs.CarParamsSP(), MagicMock())
    planner._lead_preview_enabled = enabled
    planner.dec.active = lambda: False
    return planner

  def _sm(self, lead_present=True, braking=True):
    import openpilot.cereal.messaging as messaging
    cs = messaging.new_message('carState').carState
    cs.vEgo = 15.0
    cs.aEgo = 0.0
    radar = messaging.new_message('radarState').radarState
    lead = radar.leadOne
    lead.present = lead_present
    lead.radar = lead_present
    lead.radarTrackId = 7 if lead_present else -1
    lead.aLeadK = -2.0 if braking else 0.5
    return {'carState': cs, 'radarState': radar}

  def test_disabled_is_identity(self):
    p = self._planner(False)
    sm = self._sm()
    self.assertEqual(p.apply_lead_preview(sm, 0.5, 0.4, False, 15.0), (0.5, 0.4))

  def test_enabled_braking_lead_only_lowers(self):
    p = self._planner(True)
    sm = self._sm()
    action_t, a = p.apply_lead_preview(sm, 0.5, 0.4, False, 15.0)
    self.assertGreaterEqual(action_t, 0.5)
    self.assertLessEqual(a, 0.4)

  def test_enabled_no_lead_keeps_target(self):
    p = self._planner(True)
    sm = self._sm(lead_present=False)
    action_t, a = p.apply_lead_preview(sm, 0.5, 0.4, False, 15.0)
    self.assertEqual(action_t, 0.5)
    self.assertEqual(a, 0.4)

  def test_gas_blocks_preview(self):
    p = self._planner(True)
    sm = self._sm()
    sm['carState'].gasPressed = True
    action_t, a = p.apply_lead_preview(sm, 0.5, 0.4, False, 15.0)
    self.assertEqual(action_t, 0.5)
    self.assertEqual(a, 0.4)

  def test_malformed_sm_is_safe(self):
    p = self._planner(True)
    out = p.apply_lead_preview({}, 0.5, 0.4, False, 15.0)
    self.assertEqual(out, (0.5, 0.4))


if __name__ == "__main__":
  unittest.main()
