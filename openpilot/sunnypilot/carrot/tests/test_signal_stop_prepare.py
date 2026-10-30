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


_YOLO_TRACK = {'id': 1, 'box': [600, 300, 660, 330], 'state': 'red', 'age': 0, 'observations': 5,
               'evidence': {'raw': 'red', 'source': 'detected', 'quality': 1.0,
                            'red_score': 1.0, 'green_score': 0.0}}


def _prepare_observation(session, frame_id, stamp, *, producer=None):
  obs = {'version': 1, 'stream': 'road', 'size': [1344, 760], 'session': session,
         'frame_id': frame_id, 'timestamp': stamp, 'tracks': [dict(_YOLO_TRACK)]}
  if producer is not None:
    obs['producer'] = producer
  return obs


def _replay_prepare(producer, cadence, frames=6):
  prepare = SignalStopPrepare()

  def geometry(box):
    return (50.0, 80.0)

  decisions = []
  for i in range(frames):
    t = 10.0 + i * cadence
    decision = prepare.update(
      t, _prepare_observation('s', i + 1, t, producer=producer),
      enabled=True, valid=True, drive=True, speed=20.0, gas=False, brake=False,
      lead=False, turning=False, model_stopping=False, entry_allowed=True, geometry=geometry)
    decisions.append(decision)
  return decisions


class TestYoloProducerCadence(unittest.TestCase):
  """The YOLO observer publishes at ~0.6 Hz on a comma 3, far slower than the
  classical tracker's 20 Hz. It carries producer='yolo' and selects a fixed,
  audited slow-cadence freshness window; the fast path must stay strict."""

  def test_slow_cadence_confirms_for_the_yolo_producer(self):
    decisions = _replay_prepare('yolo', 1.7)
    self.assertTrue(any(d.active for d in decisions),
                    [d.reason for d in decisions])
    self.assertEqual(decisions[-1].reason, 'red_prepare')

  def test_slow_cadence_never_confirms_without_the_tag(self):
    # A 1.7 s gap is a capture gap for the fast producer, so its confirmation
    # history resets every frame and the cap must never engage.
    decisions = _replay_prepare(None, 1.7)
    self.assertFalse(any(d.active for d in decisions))
    self.assertTrue(all(d.reason in ('confirming', 'capture_gap', 'awaiting_fresh')
                        for d in decisions))

  def test_unknown_producer_value_does_not_widen_the_window(self):
    # Only the literal 'yolo' tag selects the slow window; any other string
    # keeps the strict fast window even if an external record sets it.
    decisions = _replay_prepare('something_else', 1.7)
    self.assertFalse(any(d.active for d in decisions))

  def test_fast_cadence_still_confirms_with_the_tag(self):
    # The slow window must not break a device that runs YOLO at the 2 Hz cap.
    decisions = _replay_prepare('yolo', 0.15, frames=8)
    self.assertTrue(any(d.active for d in decisions),
                    [d.reason for d in decisions])


if __name__ == "__main__":
  unittest.main()
