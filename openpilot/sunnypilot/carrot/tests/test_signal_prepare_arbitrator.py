"""PrepareArbitrator + radar corroboration + stop envelope (navipilot patterns).

The arbitrator owns decision-to-actuation machinery for the pre-deceleration
cap: evidence-loss grace, driver-override cooldown, radar cross-confirmation
and the closed-form stop envelope. Cap-only: nothing here can command a stop
or a departure.
"""
import math
import unittest
from types import SimpleNamespace as NS

from openpilot.sunnypilot.carrot.signal_stop_prepare import (
  PREPARE_ESCALATED_ACCEL, PREPARE_JERK_LIMIT, PrepareAccel, PrepareArbitrator,
  SignalStopPrepare, prepare_radar_corroboration, required_stop_distance,
)


def _radar(one=None, two=None):
  def lead(status, d_rel):
    return NS(present=status, dRel=d_rel)
  return NS(leadOne=lead(True, one) if one is not None else NS(present=False, dRel=100.),
            leadTwo=lead(True, two) if two is not None else NS(present=False, dRel=100.))


def _cs(gas=False, brake=False, v_ego=12., a_ego=0.):
  return NS(gasPressed=gas, brakePressed=brake, vEgo=v_ego, aEgo=a_ego)


class TestRequiredStopDistance(unittest.TestCase):
  def test_zero_speed_stops_in_place(self):
    self.assertEqual(required_stop_distance(0., 0., 0.18, 2.4, 0.8), 0.0)

  def test_delay_and_ramp_and_braking_components(self):
    # constant-deceleration shortcut: distance = v^2 / (2*B) when already at -B
    self.assertAlmostEqual(required_stop_distance(10., -2.4, 0.0, 2.4, 0.8), 100. / 4.8, places=6)
    # positive measured acceleration is retained, never clipped to -B
    self.assertGreater(required_stop_distance(10., 1.0, 0.0, 2.4, 0.8),
                       required_stop_distance(10., 0.0, 0.0, 2.4, 0.8))
    # actuator delay always adds distance
    self.assertGreater(required_stop_distance(10., 0., 0.2, 2.4, 0.8),
                       required_stop_distance(10., 0., 0.0, 2.4, 0.8))
    # gentler jerk stretches the envelope
    self.assertGreater(required_stop_distance(10., 0., 0.0, 2.4, 0.4),
                       required_stop_distance(10., 0., 0.0, 2.4, PREPARE_JERK_LIMIT))

  def test_nonfinite_is_infinite(self):
    self.assertEqual(required_stop_distance(float('nan'), 0., 0.18, 2.4, 0.8), math.inf)


class TestRadarCorroboration(unittest.TestCase):
  def test_clear_when_no_lead_overlaps(self):
    self.assertEqual(prepare_radar_corroboration(_radar(), (60., 65.)), (True, 'clear'))

  def test_lead_inside_range_blocks_escalation(self):
    self.assertEqual(prepare_radar_corroboration(_radar(one=62.), (60., 65.)), (False, 'lead_overlap_ambiguous'))
    self.assertEqual(prepare_radar_corroboration(_radar(two=68.), (60., 65.)), (False, 'lead_overlap_ambiguous'))

  def test_lead_beyond_range_is_ignored(self):
    self.assertEqual(prepare_radar_corroboration(_radar(one=90.), (60., 65.)), (True, 'clear'))

  def test_night_candidates_and_bad_radar_never_escalate(self):
    self.assertEqual(prepare_radar_corroboration(_radar(), None), (False, 'no_distance_bounds'))
    self.assertEqual(prepare_radar_corroboration(None, (60., 65.)), (False, 'radar_invalid'))
    self.assertEqual(prepare_radar_corroboration(_radar(), (float('nan'), 65.)), (False, 'no_distance_bounds'))


class TestPrepareArbitrator(unittest.TestCase):
  def setUp(self):
    self.arb = PrepareArbitrator()

  def _decision(self, active=False, reason='confirming', distance_range=(60., 65.)):
    return NS(active=active, reason=reason, distance_range=distance_range)

  def test_gated_without_decision_mode_or_permission(self):
    cs = _cs()
    self.assertEqual(self.arb.engage(1.0, None, True, _radar(), cs, 0., 0.18), (False, SignalStopPrepare.TARGET_ACCEL, 'gated'))
    self.assertEqual(self.arb.engage(1.0, self._decision(True), False, _radar(), cs, 0., 0.18)[0], False)

  def test_driver_input_starts_cooldown(self):
    self.assertEqual(self.arb.engage(1.0, self._decision(True), True, _radar(), _cs(gas=True), 0., 0.18)[0], False)
    # within 0.75 s of the override the cap stays off even with a fresh decision
    self.assertEqual(self.arb.engage(1.5, self._decision(True), True, _radar(), _cs(), 0., 0.18)[0], False)
    self.assertEqual(self.arb.engage(1.8, self._decision(True), True, _radar(), _cs(), 0., 0.18)[0], True)

  def test_reset_reasons_release_immediately(self):
    self.arb.engage(1.0, self._decision(True), True, _radar(), _cs(), 0., 0.18)
    self.assertEqual(self.arb.engage(1.1, self._decision(False, 'no_red'), True, _radar(), _cs(), 0., 0.18)[0], False)

  def test_evidence_loss_grace_holds_the_cap(self):
    self.arb.engage(1.0, self._decision(True), True, _radar(), _cs(), 0., 0.18)
    active, target, reason = self.arb.engage(3.0, self._decision(False, 'awaiting_fresh'), True, _radar(), _cs(), 0., 0.18)
    self.assertTrue(active)
    self.assertEqual(target, SignalStopPrepare.TARGET_ACCEL)
    # beyond the grace window the cap releases
    self.assertEqual(self.arb.engage(4.5, self._decision(False, 'awaiting_fresh'), True, _radar(), _cs(), 0., 0.18)[0], False)

  def test_grace_only_covers_dropout_reasons(self):
    self.arb.engage(1.0, self._decision(True), True, _radar(), _cs(), 0., 0.18)
    # a confirming (never-confirmed) decision during the window is not a dropout
    self.assertEqual(self.arb.engage(1.1, self._decision(False, 'confirming'), True, _radar(), _cs(), 0., 0.18)[0], False)

  def test_envelope_escalation_only_when_radar_clear(self):
    # ~14 m/s: the gentle envelope (~63 m) exceeds the 60 m near bound but the
    # bounded stronger cap still fits inside the far bound -> escalate.
    cs = _cs(v_ego=14.)
    active, target, reason = self.arb.engage(1.0, self._decision(True), True, _radar(), cs, 0., 0.18)
    self.assertTrue(active)
    self.assertEqual(target, PREPARE_ESCALATED_ACCEL)
    self.assertEqual(reason, 'envelope_escalation')
    # a lead overlapping the housing range keeps the gentle cap
    self.arb.reset()
    active, target, _ = self.arb.engage(1.0, self._decision(True), True, _radar(one=62.), cs, 0., 0.18)
    self.assertTrue(active)
    self.assertEqual(target, SignalStopPrepare.TARGET_ACCEL)

  def test_envelope_beyond_far_bound_keeps_gentle_cap(self):
    # unreachable even at the far bound: no escalation (gentle cap still helps)
    cs = _cs(v_ego=25.)
    active, target, reason = self.arb.engage(1.0, self._decision(True), True, _radar(), cs, 0., 0.18)
    self.assertTrue(active)
    self.assertEqual(target, SignalStopPrepare.TARGET_ACCEL)
    self.assertEqual(reason, 'clear')

  def test_night_decision_never_escalates(self):
    active, target, _ = self.arb.engage(1.0, self._decision(True, distance_range=None), True, _radar(), _cs(v_ego=30.), 0., 0.18)
    self.assertTrue(active)
    self.assertEqual(target, SignalStopPrepare.TARGET_ACCEL)


class TestPrepareAccelTarget(unittest.TestCase):
  def test_default_floor_is_respected(self):
    cap = PrepareAccel()
    out = cap.apply(0.0, -0.2, 0.05, True, target_accel=0.0)
    self.assertLessEqual(out, 0.0)  # a weak explicit target still caps
    self.assertGreaterEqual(cap.cap, SignalStopPrepare.TARGET_ACCEL - 1e-9)  # never weaker than the default floor
    self.assertLessEqual(cap.cap, -0.2 + 1e-9)  # and it starts from the stronger of previous/floor

  def test_escalated_floor_is_respected(self):
    cap = PrepareAccel()
    out = 0.0
    for _ in range(120):
      out = cap.apply(0.0, out, 0.05, True, target_accel=PREPARE_ESCALATED_ACCEL)
    self.assertAlmostEqual(out, PREPARE_ESCALATED_ACCEL, places=9)
    self.assertAlmostEqual(cap.cap, PREPARE_ESCALATED_ACCEL, places=9)
    self.assertEqual(cap.apply(0.0, out, 0.05, False), 0.0)  # inactive resets
    self.assertIsNone(cap.cap)

  def test_escalated_target_never_jumps_from_previous(self):
    cap = PrepareAccel()
    out = cap.apply(0.0, 0.0, 0.05, True, target_accel=PREPARE_ESCALATED_ACCEL)
    self.assertGreater(out, PREPARE_ESCALATED_ACCEL)  # ramped, not a step
    self.assertLess(out, 0.0 + 1e-9)


if __name__ == '__main__':
  unittest.main()
