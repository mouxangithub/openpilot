"""Deterministic replay regression for the red pre-deceleration chain.

Fixture-driven (navipilot traffic_control pattern): a recorded-style timeline
of shadow observations replays through SignalStopPrepare and PrepareArbitrator
and the full decision trajectory is locked, so controller/arbitrator refactors
cannot silently change when the cap engages, holds or releases.
"""
import json
import math
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from openpilot.sunnypilot.carrot.signal_stop_prepare import (
  PREPARE_ESCALATED_ACCEL, PrepareArbitrator, SignalStopPrepare,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'signal_prepare_replay.json'

TRACK = {'id': 1, 'box': [600, 300, 660, 330], 'state': 'red', 'age': 0, 'observations': 5,
         'evidence': {'raw': 'red', 'source': 'detected', 'quality': 1., 'red_score': 1., 'green_score': 0.}}


def observation(session, frame_id, stamp):
  return {'version': 1, 'stream': 'road', 'size': [1344, 760], 'session': session,
          'frame_id': frame_id, 'timestamp': stamp, 'tracks': [dict(TRACK)]}


def replay():
  """Yield (frame, decision, engaged, cap_target) over the fixture timeline."""
  data = json.loads(FIXTURE.read_text())
  prepare = SignalStopPrepare()
  arbitrator = PrepareArbitrator()
  radar = NS(leadOne=NS(status=False, dRel=100.), leadTwo=NS(status=False, dRel=100.))
  last_observation = None
  next_frame = 1
  for frame in data['frames']:
    kind = frame['kind']
    if kind == 'red':
      last_observation = observation(data['session'], next_frame, frame['t'])
      next_frame += 1
    gas = bool(frame.get('gas', False))
    decision = prepare.update(
      frame['t'], last_observation,
      enabled=True, valid=True, drive=True, speed=data['speed_mps'],
      gas=gas, brake=False, lead=False, turning=False, model_stopping=False,
      entry_allowed=True, geometry=lambda box: tuple(data['distance_range']))
    engaged, cap_target, _ = arbitrator.engage(
      frame['t'], decision, actuate=True, radar_state=radar,
      cs=NS(gasPressed=gas, brakePressed=False, vEgo=data['speed_mps'], aEgo=0.),
      a_ego=0., actuator_delay=0.18)
    yield frame, decision, engaged, cap_target


class TestSignalPrepareReplay(unittest.TestCase):
  def test_decision_trajectory_matches_fixture(self):
    for frame, decision, _, _ in replay():
      with self.subTest(t=frame['t'], kind=frame['kind']):
        self.assertEqual(decision.active, frame['expect_active'], frame)
        self.assertEqual(decision.reason, frame['expect_reason'], frame)

  def test_arbitrator_cap_trajectory_matches_fixture(self):
    expected = json.loads(FIXTURE.read_text())['arbitrator']['expect']
    for frame, _, engaged, _ in replay():
      if frame['t'] in expected:
        with self.subTest(t=frame['t']):
          self.assertEqual(engaged, expected[str(frame['t'])], frame)

  def test_chain_stays_cap_only(self):
    """Across the whole timeline the chain only ever produces a bounded,
    advisory deceleration cap - never a stop request, a departure grant or an
    unbounded braking target."""
    for frame, decision, engaged, cap_target in replay():
      with self.subTest(t=frame['t']):
        self.assertIn(getattr(decision, 'reason', ''), (
          'confirming', 'red_prepare', 'awaiting_fresh', 'ineligible', 'stale',
          'capture_gap', 'new_session'))
        if engaged:
          self.assertTrue(math.isfinite(cap_target))
          self.assertIn(cap_target, (SignalStopPrepare.TARGET_ACCEL, PREPARE_ESCALATED_ACCEL))
          self.assertLess(cap_target, 0.)  # braking only, and bounded


if __name__ == '__main__':
  unittest.main()
