"""Stopped-red memory must not survive into the driving phase.

Both auxiliary signal guards latch a stop at rest and are bypassed per cycle by
lead following. Their internal memory used to stay armed, so losing the lead at
road speed re-applied a red-light veto. Evidence for the failure mode is a
recorded drive: planner target -4.4967 m/s^2 and measured -3.6156 m/s^2 at
76.5 km/h with no fresh signal tracks in the preceding 6.45 s.

These tests lock the retirement scope (stop/creep, up to 5 km/h), the preserved
independent paths (fresh moving red, explicit driver stop, low-speed lead loss)
and the final output gate.
"""
import unittest

from openpilot.sunnypilot.carrot.signal_assist import SignalAssist, departed_signal_stop
from openpilot.sunnypilot.carrot.signal_start_guard import SignalStartGuard

try:
  from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner, XState
  HAVE_CARROT = True
except ImportError:  # local host without the opendbc checkout
  CarrotPlanner = XState = None
  HAVE_CARROT = False

CREEP = 5 / 3.6  # m/s, the stop/creep boundary


def assist_observation(t, state='red', ident=1, session='worker1', box=(640, 250, 680, 270)):
  return {'timestamp': t, 'frame_id': round(t * 20), 'session': session,
          'tracks': [{'id': ident, 'box': box, 'state': state, 'age': 0.,
                      'observations': 10, 'evidence': {'raw': state}}]}


def assist_step(a, t, o=None, **kw):
  context = {'enabled': True, 'valid': True, 'drive': True, 'gas': False, 'speed': 0.,
             'model_distance': 3., 'model_y': 0., 'comfort_brake': 2.4, 'lead': False,
             'entry_allowed': True}
  context.update(kw)
  return a.update(t, o, **context)


def latch_assist_red(a, start=0.):
  result = None
  for i in range(12):
    t = start + i * .05
    result = assist_step(a, t, assist_observation(t))
  return result


def guard_observation(t, raw='red', ident=1, session='worker1', box=(640, 250, 680, 270)):
  return {'timestamp': t, 'frame_id': round(t * 5), 'session': session,
          'tracks': [{'id': ident, 'box': list(box), 'raw': raw, 'seen_red': raw == 'red'}]}


def latch_guard_red(g, start=0.):
  result = None
  for i in range(3):
    t = start + i * .2
    result = g.update(t, guard_observation(t), enabled=True, valid=True, drive=True,
                      gas=False, speed=0., departure=False)
  return result


class TestDepartureBoundary(unittest.TestCase):
  def test_boundary_is_five_km_h(self):
    self.assertFalse(departed_signal_stop(0.))
    self.assertFalse(departed_signal_stop(CREEP - .01))
    self.assertTrue(departed_signal_stop(CREEP + .01))
    self.assertTrue(departed_signal_stop(-10.))  # reverse motion also departs
    self.assertFalse(departed_signal_stop(float('nan')))
    self.assertFalse(departed_signal_stop(float('inf')))


class TestSignalAssistDeparture(unittest.TestCase):
  def test_stopped_hold_retires_when_rolling(self):
    a = SignalAssist()
    self.assertTrue(latch_assist_red(a).hold)
    d = assist_step(a, 1.0, assist_observation(1.0), speed=10.)
    self.assertFalse(d.hold)  # was True before the fix: a stop at road speed
    self.assertEqual(d.reason, 'departed_stop')
    self.assertFalse(d.red_sign)

  def test_creep_speed_keeps_the_hold(self):
    a = SignalAssist()
    latch_assist_red(a)
    self.assertTrue(assist_step(a, 1.0, assist_observation(1.0), speed=CREEP - .1).hold)

  def test_lead_loss_after_departure_cannot_reapply(self):
    a = SignalAssist()
    latch_assist_red(a)
    # Lead following bypasses the veto per cycle; the latch survives at creep.
    self.assertTrue(assist_step(a, 1.0, assist_observation(1.0), speed=.5, lead=True).hold)
    # Lead disappears while rolling: the latch must already be retired.
    d = assist_step(a, 2.0, None, speed=20., lead=False)
    self.assertFalse(d.hold)
    self.assertEqual(d.reason, 'departed_stop')

  def test_fresh_moving_red_still_commits_after_departure(self):
    a = SignalAssist()
    latch_assist_red(a)
    assist_step(a, 1.0, assist_observation(1.0), speed=10.)
    # A new red ahead with a usable model distance keeps its own path; it needs
    # the usual reconfirmation, so feed the full streak again.
    d = None
    for i in range(12):
      t = 1.05 + i * .05
      d = assist_step(a, t, assist_observation(t), speed=10., model_distance=30.)
    self.assertTrue(d.red_sign)  # committed, surfaced as red_sign
    self.assertEqual(d.reason, 'confirmed_red_with_model_distance')
    self.assertFalse(d.hold)  # hold is rest-only; the commitment is separate

  def test_return_to_rest_needs_a_new_confirmation(self):
    a = SignalAssist()
    latch_assist_red(a)
    assist_step(a, 1.0, assist_observation(1.0), speed=10.)
    # Back at rest with a single red frame: the old memory must not revive.
    self.assertFalse(assist_step(a, 2.0, assist_observation(2.0), speed=0.).hold)
    self.assertTrue(latch_assist_red(a, 2.05).hold)


class TestStartGuardDeparture(unittest.TestCase):
  def test_latched_hold_retires_above_creep(self):
    g = SignalStartGuard()
    self.assertTrue(latch_guard_red(g).hold)
    d = g.update(1.0, guard_observation(1.0), enabled=True, valid=True, drive=True,
                 gas=False, speed=10., departure=True)
    self.assertFalse(d.hold)
    self.assertEqual(d.reason, 'departed_stop')
    self.assertFalse(d.green_confirmed)

  def test_creep_speed_keeps_the_hold(self):
    g = SignalStartGuard()
    latch_guard_red(g)
    d = g.update(1.0, guard_observation(1.0), enabled=True, valid=True, drive=True,
                 gas=False, speed=CREEP - .1, departure=True)
    self.assertTrue(d.hold)

  def test_clock_rollback_cannot_reapply_a_hold_at_speed(self):
    g = SignalStartGuard()
    latch_guard_red(g)
    # now < last_now used to return the retained hold unchanged.
    d = g.update(.2, guard_observation(.2), enabled=True, valid=True, drive=True,
                 gas=False, speed=10., departure=True)
    self.assertFalse(d.hold)
    self.assertEqual(d.reason, 'departed_stop')

  def test_invalid_context_at_speed_still_retires(self):
    g = SignalStartGuard()
    latch_guard_red(g)
    d = g.update(1.0, None, enabled=True, valid=False, drive=True,
                 gas=False, speed=10., departure=True)
    self.assertFalse(d.hold)
    self.assertEqual(d.reason, 'departed_stop')

  def test_restart_at_rest_needs_a_new_confirmation(self):
    g = SignalStartGuard()
    latch_guard_red(g)
    g.update(1.0, None, enabled=True, valid=True, drive=True,
             gas=False, speed=10., departure=True)
    self.assertFalse(g.update(2.0, guard_observation(2.0), enabled=True, valid=True, drive=True,
                              gas=False, speed=0., departure=True).hold)
    self.assertTrue(latch_guard_red(g, 2.2).hold)


@unittest.skipUnless(HAVE_CARROT, 'carrot_functions needs the opendbc checkout')
class TestOwnedSignalStopRetirement(unittest.TestCase):
  """The guards inject e2eStopped; retiring the latch must take it with them."""

  def planner(self, *, x_state, owned=False, guard_hold=False, assist_hold=False,
              user_stop=-1., stay_stop=False):
    p = object.__new__(CarrotPlanner)
    p._x_state = x_state
    p._signal_stop_owned = owned
    p.start_guard = type('G', (), {'hold': guard_hold})()
    p._signal_assist = type('A', (), {'hold': assist_hold})()
    p._user_stop_distance = user_stop
    p._carrot_stay_stop = stay_stop
    p._actual_stop_distance = 0.
    p._stopping_count = 10.
    return p

  def test_owned_stop_is_retired_above_creep(self):
    p = self.planner(x_state=XState.e2eStopped, owned=True)
    p._retire_departed_signal_stop(10.)
    self.assertEqual(p._x_state, XState.e2eCruise)
    self.assertFalse(p._signal_stop_owned)
    self.assertEqual(p._stopping_count, 0.)

  def test_owned_stop_survives_creep(self):
    p = self.planner(x_state=XState.e2eStopped, owned=True)
    p._retire_departed_signal_stop(CREEP - .1)
    self.assertEqual(p._x_state, XState.e2eStopped)
    self.assertTrue(p._signal_stop_owned)

  def test_guard_latch_alone_can_retire_the_injected_stop(self):
    p = self.planner(x_state=XState.e2eStopped, guard_hold=True)
    p._retire_departed_signal_stop(10.)
    self.assertEqual(p._x_state, XState.e2eCruise)

  def test_assist_latch_alone_can_retire_the_injected_stop(self):
    p = self.planner(x_state=XState.e2eStopped, assist_hold=True)
    p._retire_departed_signal_stop(10.)
    self.assertEqual(p._x_state, XState.e2eCruise)

  def test_explicit_user_stop_keeps_ownership(self):
    p = self.planner(x_state=XState.e2eStopped, owned=True, user_stop=5.)
    p._retire_departed_signal_stop(10.)
    self.assertEqual(p._x_state, XState.e2eStopped)

  def test_stay_stop_keeps_ownership(self):
    p = self.planner(x_state=XState.e2eStopped, owned=True, stay_stop=True)
    p._retire_departed_signal_stop(10.)
    self.assertEqual(p._x_state, XState.e2eStopped)

  def test_ownership_clears_once_the_state_machine_leaves_the_stop(self):
    p = self.planner(x_state=XState.e2eCruise, owned=True)
    p._retire_departed_signal_stop(10.)
    self.assertFalse(p._signal_stop_owned)

  def test_no_credit_without_a_latch_or_ownership(self):
    p = self.planner(x_state=XState.e2eStopped)
    p._retire_departed_signal_stop(10.)
    self.assertEqual(p._x_state, XState.e2eStopped)

  def test_disabled_guards_cannot_strand_a_stop(self):
    p = self.planner(x_state=XState.e2eStopped, owned=True)
    p.start_guard = None
    p._signal_assist = None
    p._retire_departed_signal_stop(10.)
    self.assertEqual(p._x_state, XState.e2eCruise)

  def test_reverse_motion_also_retires(self):
    p = self.planner(x_state=XState.e2eStopped, owned=True)
    p._retire_departed_signal_stop(-1.5)
    self.assertEqual(p._x_state, XState.e2eCruise)

  def test_nan_speed_is_not_evidence_of_departure(self):
    p = self.planner(x_state=XState.e2eStopped, owned=True)
    p._retire_departed_signal_stop(float('nan'))
    self.assertEqual(p._x_state, XState.e2eStopped)


if __name__ == '__main__':
  unittest.main()
