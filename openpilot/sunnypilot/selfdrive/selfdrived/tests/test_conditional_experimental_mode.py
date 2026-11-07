"""
Copyright (c) 2026-, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Tests for the conditional experimental mode: trigger conditions, hysteresis, the manual
override muzzle and the standstill freeze. All condition inputs come through fake carState /
sm doubles; the params are dict-backed so writes are inspectable.
"""
import sys
import types

# common.params → swaglog → common.hardware → gpio imports fcntl at module load. It is only
# *used* from hardware functions CEM never calls, so on PC a bare module keeps the import
# chain alive. Must run before the CEM import below.
try:
  import fcntl  # noqa: F401
except ImportError:
  sys.modules.setdefault('fcntl', types.ModuleType('fcntl'))

# common.params loads libparams_c.so via ctypes at import time; no Windows build exists.
# The CEM only needs the Params *class symbol* for typing/defaults - tests inject FakeCEParams.
# Run single-file (pytest --noconftest): stubbing here would leak into a shared session.
try:
  from openpilot.common.params import Params  # noqa: F401
except (OSError, FileNotFoundError):
  _params_mod = types.ModuleType('openpilot.common.params')

  class _ParamsStub:
    def __init__(self, *args, **kwargs):
      raise RuntimeError("real Params is unavailable on PC; inject a fake in tests")

  _params_mod.Params = _ParamsStub
  sys.modules['openpilot.common.params'] = _params_mod

import pytest

from opendbc.car import structs
from openpilot.sunnypilot.selfdrive.car.tests.fakes import FakeParams
from openpilot.sunnypilot.selfdrive.selfdrived.conditional_experimental_mode import (
  CE_CURVES,
  CE_LEAD,
  CE_MANUAL,
  CE_OFF,
  CE_SIGNAL,
  MANUAL_HOLD_SECONDS,
  ConditionalExperimentalMode,
)

DT_CTRL = 0.01


class FakeCEParams(FakeParams):
  """FakeParams plus the int put CEM uses for CEStatus, and the registered defaults
  that real Params.get(key, return_default=True) would return."""

  DEFAULTS = {"CECurves": True, "CECurvesLead": True, "CELead": True, "CESignalSpeed": 0.0}

  def get(self, key, **kwargs):
    if key not in self.values and kwargs.get("return_default"):
      return self.DEFAULTS.get(key)
    return self.values.get(key)

  def put_int(self, key, value, **kwargs):
    self.values[key] = value


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


def car_state(v_ego=25.0, standstill=False, left_blinker=False, right_blinker=False):
  CS = car_state_msg()
  CS.vEgo = v_ego
  CS.standstill = standstill
  CS.leftBlinker = left_blinker
  CS.rightBlinker = right_blinker
  return CS


def car_state_msg():
  return structs.CarState.new_message()


def sm(desired_curvature=0.0, lead_status=False, lead_d_rel=100.0, lead_v_lead=30.0):
  class _Lead:
    pass

  lead = _Lead()
  lead.status = lead_status
  lead.dRel = lead_d_rel
  lead.vLead = lead_v_lead

  class _Radar:
    leadOne = lead

  class _Controls:
    desiredCurvature = desired_curvature

  class _SM:
    def __init__(self):
      self._data = {"controlsState": _Controls(), "radarState": _Radar()}

    def __getitem__(self, key):
      return self._data[key]

  return _SM()


def make_cem(**params):
  clock = FakeClock()
  params_obj = FakeCEParams(**{"ConditionalExperimental": True, **params})
  CP = structs.CarParams.new_message()
  CP.openpilotLongitudinalControl = True
  cem = ConditionalExperimentalMode(CP, params_obj, now_fn=clock)
  return cem, clock, params_obj


def frames(cem, n, CS, sm_obj):
  out = None
  for _ in range(n):
    out = cem.update(CS, sm_obj)
  return out


def test_curve_trigger_engages_experimental_mode():
  cem, _, params = make_cem()
  # 0.004 rad at 30 m/s is 3.6 m/s^2 lateral acceleration - demanding.
  sm_obj = sm(desired_curvature=0.004)
  CS = car_state(v_ego=30.0)
  # filter (tau 0.8 s) needs ~0.55 s to cross 0.5 from a sustained bool; run 2 s to be safe
  mode = frames(cem, 200, CS, sm_obj)
  assert mode is True
  assert params.values["ExperimentalMode"] is True
  assert params.values["CEStatus"] == CE_CURVES


def test_curve_clears_after_hysteresis():
  cem, clock, params = make_cem()
  sm_curve = sm(desired_curvature=0.004)
  CS = car_state(v_ego=30.0)
  frames(cem, 200, CS, sm_curve)
  assert params.values["ExperimentalMode"] is True

  # conditions vanish: the filter (tau 0.8 s) must decay below the threshold first, then
  # the 0.5 s guard + 0.25 s buffer keep the mode before it drops
  sm_open = sm(desired_curvature=0.0)
  frames(cem, 20, CS, sm_open)  # 0.2 s: filter still hot, guard active
  assert params.values["ExperimentalMode"] is True
  clock.t += 1.5
  frames(cem, 100, CS, sm_open)  # 1 s: filter decays through the threshold
  clock.t += 1.5
  frames(cem, 20, CS, sm_open)
  assert params.values["ExperimentalMode"] is False
  assert params.values["CEStatus"] == CE_OFF


def test_slow_lead_triggers_and_needs_closing_speed():
  cem, clock, params = make_cem()
  # 25 m/s ego, lead at 30 m ahead doing 21 m/s: closing 4 m/s, in range
  sm_obj = sm(lead_status=True, lead_d_rel=30.0, lead_v_lead=21.0)
  CS = car_state(v_ego=25.0)
  mode = frames(cem, 200, CS, sm_obj)
  assert mode is True
  assert params.values["CEStatus"] == CE_LEAD

  # lead speeds back up: filter decays and the mode drops once the hysteresis expires
  sm_fast_lead = sm(lead_status=True, lead_d_rel=60.0, lead_v_lead=25.0)
  clock.t = 10.0
  frames(cem, 30, CS, sm_fast_lead)  # filter decays but stays above the threshold: guard refreshes
  frames(cem, 30, CS, sm_fast_lead)  # filter now clearly below the threshold, buffer starts
  clock.t += 2.0  # let the guard hold and transition buffer expire
  mode = frames(cem, 5, CS, sm_fast_lead)
  assert mode is False


def test_signal_trigger_disabled_by_default():
  cem, _, params = make_cem()
  CS = car_state(v_ego=8.0, left_blinker=True)
  mode = frames(cem, 30, CS, sm())
  assert mode is False
  assert params.values["CEStatus"] == CE_OFF

  cem_sig, _, _ = make_cem(CESignalSpeed=10.0)
  mode = frames(cem_sig, 30, CS, sm())
  assert mode is True
  assert cem_sig._last_ce_status_written == CE_SIGNAL


def test_standstill_freezes_mode():
  cem, _, params = make_cem()
  sm_obj = sm(desired_curvature=0.004)
  CS = car_state(v_ego=30.0)
  frames(cem, 200, CS, sm_obj)
  assert params.values["ExperimentalMode"] is True

  # stop the car: no re-evaluation, mode stays pinned
  CS_stop = car_state(v_ego=0.0, standstill=True)
  frames(cem, 60, CS_stop, sm(desired_curvature=0.0))
  assert params.values["ExperimentalMode"] is True


def test_manual_switch_adopts_and_muzzles():
  cem, clock, params = make_cem()
  # start with conditions ON so the CEM owns the param
  sm_obj = sm(desired_curvature=0.004)
  CS = car_state(v_ego=30.0)
  frames(cem, 200, CS, sm_obj)
  assert params.values["ExperimentalMode"] is True

  # driver turns it off behind the CEM's back
  params.values["ExperimentalMode"] = False
  clock.t += 0.1
  frames(cem, 5, CS, sm_obj)
  assert cem.manual_override_active
  assert params.values["ExperimentalMode"] is False
  assert cem._last_ce_status_written == CE_MANUAL

  # during the muzzle the demanding curve must NOT switch the mode back
  clock.t += MANUAL_HOLD_SECONDS / 2
  frames(cem, 20, CS, sm_obj)
  assert params.values["ExperimentalMode"] is False

  # after the muzzle expires conditions own the mode again
  clock.t += MANUAL_HOLD_SECONDS
  mode = frames(cem, 60, CS, sm_obj)
  assert mode is True


def test_master_switch_off_is_inert():
  cem, _, params = make_cem(ConditionalExperimental=False)
  sm_obj = sm(desired_curvature=0.004)
  CS = car_state(v_ego=30.0)
  frames(cem, 200, CS, sm_obj)
  # no condition ever writes the param: the manual-only stock behaviour is untouched
  assert "ExperimentalMode" not in params.values or params.values["ExperimentalMode"] in (False, None)
  assert cem.experimental_mode is False


def test_curve_trigger_respects_following_lead_gate():
  cem, _, _ = make_cem(CECurvesLead=False)
  sm_obj = sm(desired_curvature=0.004, lead_status=True)
  CS = car_state(v_ego=30.0)
  mode = frames(cem, 200, CS, sm_obj)
  assert mode is False


def test_requires_longitudinal_control():
  params_obj = FakeCEParams(ConditionalExperimental=True)
  CP = structs.CarParams.new_message()
  CP.openpilotLongitudinalControl = False
  cem = ConditionalExperimentalMode(CP, params_obj)
  mode = frames(cem, 30, car_state(v_ego=30.0), sm(desired_curvature=0.004))
  assert mode is False
