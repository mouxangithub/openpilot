import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from openpilot.common.pid import PIDController
from openpilot.sunnypilot.selfdrive.controls.lib.cruise_coasting import (
  BRAKE_RELEASE_JERK, CruiseCoastingPlan, coasting_percent, coasting_relief, no_coasting_lead,
)
# This existing fixture also supplies Windows-only Params/hardware import shims.
import openpilot.selfdrive.controls.lib.longcontrol as lc


@pytest.mark.parametrize('value, expected', [(0, 0), (5, 5), (10, 10), (30, 10), (-2, 0),
                                            (None, 0), ('bad', 0), (float('nan'), 0), (float('inf'), 0)])
def test_setting_bounds(value, expected):
  assert coasting_percent(value) == expected


def test_margin_has_continuous_lower_and_upper_edges():
  target = 100 / 3.6
  for percent in (1, 5, 10):
    width = target * percent / 100
    assert coasting_relief(target, target, percent) == 0
    assert coasting_relief(target + .3 * width, target, percent) == pytest.approx(1)
    assert coasting_relief(target + .8 * width, target, percent) == pytest.approx(.5)
    assert coasting_relief(target + width, target, percent) == pytest.approx(0, abs=1e-12)
    assert coasting_relief(target + 2 * width, target, percent) == 0
    for edge in (0., .1, .6, 1.):
      below = coasting_relief(target + (edge - 1e-6) * width, target, percent)
      above = coasting_relief(target + (edge + 1e-6) * width, target, percent)
      assert abs(above - below) < 1e-7


def test_plan_requires_stable_target_and_cap_clearance():
  plan = CruiseCoastingPlan()
  args = {'enabled': True, 'percent': 5, 'set_speed': 100., 'target': 100 / 3.6, 'external_limit': 250 / 3.6, 'dt': .05}
  assert plan.update(**args) == 0
  for _ in range(19):
    assert plan.update(**args) == 0
  assert plan.update(**args) == args['target']
  # Reference stays fixed despite speed-calibration noise; it cannot ratchet.
  assert plan.update(**{**args, 'target': args['target'] + .01}) == args['target']
  assert plan.update(**{**args, 'set_speed': 99.}) == 0
  for _ in range(21):
    result = plan.update(**args)
  assert result > 0
  # A cap within the band vetoes relief before it lowers the ordinary target.
  assert plan.update(**{**args, 'external_limit': 103 / 3.6}) == 0
  assert plan.update(**args) == 0
  for value in (0., float('nan')):
    assert plan.update(**{**args, 'target': value}) == 0
  assert plan.update(**{**args, 'percent': 0}) == 0


def inputs():
  cs = SimpleNamespace(vEgo=102 / 3.6, aEgo=.1, vCruise=100., vCluRatio=1.,
                       softHoldActive=0, brakePressed=False, gasPressed=False, carrotCruise=0,
                       standstill=False, cruiseState=SimpleNamespace(standstill=False))
  plan = SimpleNamespace(aTarget=-.2, vTargetNow=100 / 3.6, jTargetNow=0., shouldStop=False,
                         longitudinalPlanSource='cruise', fcw=False, cruiseTarget=100.,
                         cruiseCoastingTarget=100 / 3.6, cruiseCoastingPercent=5)
  radar = SimpleNamespace(**{key: SimpleNamespace(status=False) for key in ('leadOne', 'leadTwo', 'leadCutInRisk')})
  return cs, plan, radar


def test_live_speed_ratio_does_not_restart_entry_or_move_reference():
  plan = CruiseCoastingPlan()
  set_speed = 90.
  reference = set_speed / 3.6 * .968
  # Cluster quantization and ego-speed noise change the ratio even at a fixed
  # set speed. These changes exceed the old 0.02 m/s restart threshold.
  for frame in range(201):
    ratio = .968 + .006 * np.sin(frame * .9)
    result = plan.update(enabled=True, percent=10, set_speed=set_speed,
                         target=set_speed / 3.6 * ratio, external_limit=200 / 3.6 * ratio, dt=.05)
    assert result == (0 if frame < 20 else reference)
    assert plan.target == reference
  # With the reference frozen, actual overspeed enters the relief band.
  assert coasting_relief(reference * 1.03, result, 10) == pytest.approx(1)


@pytest.mark.parametrize('ratio', [.94, 1.02])
def test_external_caps_protect_frozen_and_current_speed_bands(ratio):
  plan = CruiseCoastingPlan()
  args = {'enabled': True, 'percent': 5, 'set_speed': 100., 'target': 100 / 3.6,
          'external_limit': 250 / 3.6, 'dt': .05}
  for _ in range(21):
    reference = plan.update(**args)
  current = args['target'] * ratio
  # Place the cap between the two ceilings: checking just one is insufficient.
  cap = (current + reference) / 2 * 1.05
  assert plan.update(**{**args, 'target': current, 'external_limit': cap}) == 0
  assert plan.target == 0


@pytest.mark.parametrize('change', ['set_speed', 'percent', 'veto'])
def test_real_changes_restart_entry_and_capture_a_new_reference(change):
  plan = CruiseCoastingPlan()
  args = {'enabled': True, 'percent': 5, 'set_speed': 100., 'target': 100 / 3.6,
          'external_limit': 250 / 3.6, 'dt': .05}
  for _ in range(21):
    assert plan.update(**args) >= 0
  assert plan.stable_time == 1
  args['target'] = 98 / 3.6
  if change == 'veto':
    assert plan.update(**{**args, 'enabled': False}) == 0
  elif change == 'set_speed':
    args['set_speed'] = 99.
  else:
    args['percent'] = 6
  for frame in range(21):
    assert plan.update(**args) == (0 if frame < 20 else args['target'])


# NOTE: the cp-longcontrol integration tests (control fixture, PID/no-windup/veto
# suites) are not portable: sp LongControl evolved (LongControlSP, CP-4 stopping
# accel clamp, no Hyundai PID constants). Pure CruiseCoastingPlan coverage above.
