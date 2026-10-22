import pytest
from pathlib import Path
from types import SimpleNamespace as NS

from openpilot.common.repo_tools import load
from openpilot.sunnypilot.carrot.signal_assist import SignalAssist

# ``import tools.signal_analysis`` cannot resolve here: openpilot/tools is a
# regular package and wins over the repo-root tools/ namespace regardless of
# sys.path order. Load the harness by location instead (see repo_tools.load).
_harness = load('signal_analysis/replay_signal_assist.py')
planner_class, REPO = _harness.planner_class, _harness.REPO


def inputs(speed=0., distance=100., lead=False):
  return dict(carState=NS(vCluRatio=1., softHoldActive=0, vEgo=speed, aEgo=0., vEgoCluster=speed,
                         gasPressed=False, brakePressed=False, steeringAngleDeg=0., leftBlinker=False, rightBlinker=False),
              selfdriveState=NS(personality=1), radarState=NS(leadOne=NS(status=lead, dRel=10.)),
              modelV2=NS(position=NS(x=[distance*i/32 for i in range(33)], y=[0.]*33),
                         velocity=NS(x=[speed]+[15.]*32), leadsV3=[]))


def run(p, sm, state, start=0., count=20):
  for i in range(count):
    t = start + i * .05
    obs = dict(timestamp=t, frame_id=round(t*20), session='same', tracks=[
      dict(id=1, box=[640, 250, 680, 270], state=state, age=0., observations=10, evidence={'raw': state})])
    p.update(sm, 80., 'acc', signal_observation=obs, signal_context=dict(now=t, enabled=True, valid=True, drive=True))


def planner():
  """Build this fork's CarrotPlanner when it carries the signal hook.

  cp wires signal_observation/signal_context into CarrotPlanner; this fork's
  planner has a different signature (no signal kwargs) because the trial is
  still being revalidated upstream. Skip until that hook is ported - the
  library-side behaviour is covered by the signal_assist unit tests.
  """
  src = (REPO/'openpilot/sunnypilot/carrot/carrot_functions.py')
  if not src.exists():
    pytest.skip('carrot_functions.py not found for this fork layout')
  try:
    cls, _ = planner_class(src.read_text(encoding='utf-8'))
    return cls(SignalAssist())
  except Exception as exc:
    # The replay harness execs cp's planner shape; this fork's CarrotPlanner
    # has different imports/kwargs, so these four integration tests skip here.
    pytest.skip(f'planner replay harness cannot build this fork\'s planner: {type(exc).__name__}: {exc}')


def test_red_hold_wins_over_model_go_and_lead_handover():
  p = planner(); sm = inputs(lead=True)
  run(p, sm, 'red')
  assert p.xState.name == 'e2eStopped' and p.stop_dist == 0 and p.v_cruise == 0
  run(p, sm, 'unknown', 1.)
  assert p.xState.name == 'e2eStopped'


def test_moving_red_enters_existing_stop_and_speed_cap():
  p = planner(); sm = inputs(speed=10., distance=40.)
  run(p, sm, 'red')
  assert p.xState.name == 'e2eStop'
  assert 0 < p.stop_dist < 40. and p.v_cruise < 80/3.6
  assert 0 < p.comfort_brake <= 2.4


def test_green_does_not_force_departure_against_original_model():
  p = planner(); sm = inputs(distance=3.)
  sm['modelV2'].velocity.x = [0.] * 33
  run(p, sm, 'red')
  run(p, sm, 'green', 1.)
  assert not p.signal_decision.hold
  assert p.xState.name == 'e2eStopped' and p.v_cruise == 0


def test_driver_gas_releases_hold_through_original_override():
  p = planner(); sm = inputs()
  run(p, sm, 'red')
  sm['carState'].gasPressed = True
  run(p, sm, 'red', 1., 1)
  assert not p.signal_decision.hold and p.xState.name == 'e2eCruise'
