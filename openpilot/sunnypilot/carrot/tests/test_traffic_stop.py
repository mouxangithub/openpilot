#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock

import numpy as np


# Minimal import shims so this module is runnable on a dev host without a
# compiled capnp runtime (mirrors the mocks in test_carrot_man.py). When the
# combined test run already installed these fakes, setdefault keeps them.
if "opendbc.car.common.conversions" not in sys.modules:
  _opendbc = sys.modules.setdefault("opendbc", types.ModuleType("opendbc"))
  _opendbc_car = sys.modules.setdefault("opendbc.car", types.ModuleType("opendbc.car"))
  _opendbc_car_common = sys.modules.setdefault("opendbc.car.common", types.ModuleType("opendbc.car.common"))
  _conv = types.ModuleType("opendbc.car.common.conversions")
  class _Conversions:
    KPH_TO_MS = 1.0 / 3.6
    MS_TO_KPH = 3.6
  _conv.Conversions = _Conversions
  sys.modules["opendbc.car.common.conversions"] = _conv

if "openpilot.common.realtime" not in sys.modules:
  _rt = types.ModuleType("openpilot.common.realtime")
  _rt.DT_MDL = 0.05
  sys.modules["openpilot.common.realtime"] = _rt


from openpilot.sunnypilot.carrot.traffic_stop import (
  MODEL_LEAD_STOP_CONFIRM_FRAMES,
  MODEL_LEAD_STOP_OFFSET_M,
  TrafficStopModelLeadMatcher,
  get_traffic_stop_distance_adjust,
  get_traffic_stop_obstacle_distance,
  is_traffic_stop_entry_allowed,
)


class TestTrafficStopModelLeadMatcher(unittest.TestCase):
  def _valid_kwargs(self, **overrides):
    kw = dict(
      stop_active=True,
      allow_confirmation=True,
      active_lead=False,
      stop_distance=10.0,
      lead_probability=0.99,
      lead_distance=12.0,        # ~2 m behind the stop point (12 - 10)
      lead_velocity=0.0,
      lead_x_std=0.5,
      lead_y_std=0.1,
      lead_v_std=0.1,
    )
    kw.update(overrides)
    return kw

  def test_initial_state_returns_zero(self):
    m = TrafficStopModelLeadMatcher()
    assert m.update(**self._valid_kwargs()) == 0.0

  def test_not_stop_active_resets_and_returns_zero(self):
    m = TrafficStopModelLeadMatcher()
    m.update(**self._valid_kwargs())
    assert m.update(stop_active=False, allow_confirmation=True, active_lead=False,
                    stop_distance=10.0, lead_probability=0.99, lead_distance=12.0,
                    lead_velocity=0.0, lead_x_std=0.5, lead_y_std=0.1, lead_v_std=0.1) == 0.0

  def test_active_lead_resets_and_returns_zero(self):
    m = TrafficStopModelLeadMatcher()
    m.update(**self._valid_kwargs())
    assert m.update(**self._valid_kwargs(active_lead=True)) == 0.0

  def test_confirmation_disabled_clears_pending(self):
    m = TrafficStopModelLeadMatcher()
    m.update(**self._valid_kwargs(allow_confirmation=False)) == 0.0
    # A later valid frame must still start from scratch (pending was cleared).
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES - 1):
      m.update(**self._valid_kwargs())
    assert m.update(**self._valid_kwargs(allow_confirmation=False)) == 0.0

  def test_non_finite_inputs_return_zero(self):
    m = TrafficStopModelLeadMatcher()
    assert m.update(**self._valid_kwargs(lead_probability=np.nan)) == 0.0
    assert m.update(**self._valid_kwargs(lead_distance=np.inf)) == 0.0
    assert m.update(**self._valid_kwargs(stop_distance=np.nan)) == 0.0

  def test_requires_confirm_frames_then_locks_offset(self):
    m = TrafficStopModelLeadMatcher()
    for i in range(MODEL_LEAD_STOP_CONFIRM_FRAMES - 1):
      assert m.update(**self._valid_kwargs()) == 0.0
    # Final confirming frame returns the offset and locks it in.
    assert m.update(**self._valid_kwargs()) == MODEL_LEAD_STOP_OFFSET_M

  def test_confirmed_offset_persists_while_stopping(self):
    m = TrafficStopModelLeadMatcher()
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES):
      m.update(**self._valid_kwargs())
    # Stays confirmed across many more valid stopping frames.
    for _ in range(20):
      assert m.update(**self._valid_kwargs()) == MODEL_LEAD_STOP_OFFSET_M

  def test_confirmed_offset_released_when_not_stopping(self):
    m = TrafficStopModelLeadMatcher()
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES):
      m.update(**self._valid_kwargs())
    assert m.update(**self._valid_kwargs(stop_active=False)) == 0.0

  def test_invalid_frame_resets_match_count(self):
    m = TrafficStopModelLeadMatcher()
    # Three good frames, then one bad, then need a full run again.
    for _ in range(3):
      m.update(**self._valid_kwargs())
    m.update(**self._valid_kwargs(lead_probability=0.5))  # probability below min
    # A full confirm window of valid frames is required again after the reset.
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES - 1):
      assert m.update(**self._valid_kwargs()) == 0.0
    # One more valid frame reaches the confirm threshold.
    assert m.update(**self._valid_kwargs()) == MODEL_LEAD_STOP_OFFSET_M

  def test_low_probability_is_invalid(self):
    m = TrafficStopModelLeadMatcher()
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES):
      m.update(**self._valid_kwargs(lead_probability=0.5))
    assert m.update(**self._valid_kwargs(lead_probability=0.5)) == 0.0

  def test_gap_out_of_range_is_invalid(self):
    m = TrafficStopModelLeadMatcher()
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES):
      m.update(**self._valid_kwargs(lead_distance=20.0))  # gap 10 m > max
    assert m.update(**self._valid_kwargs(lead_distance=20.0)) == 0.0

  def test_reset_clears_confirmed_state(self):
    m = TrafficStopModelLeadMatcher()
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES):
      m.update(**self._valid_kwargs())
    m.reset()
    assert m.update(**self._valid_kwargs()) == 0.0


class TestTrafficStopHelpers(unittest.TestCase):
  def test_distance_adjust_prefers_model_lead_offset(self):
    assert get_traffic_stop_distance_adjust(-1.5, 0.0, 2.0) == 2.0
    assert get_traffic_stop_distance_adjust(-1.5, 30.0, 2.0) == 2.0

  def test_distance_adjust_uses_configured_when_moving(self):
    assert get_traffic_stop_distance_adjust(-1.5, 5.0, 0.0) == -1.5
    assert get_traffic_stop_distance_adjust(-1.5, 5.0, np.nan) == -1.5

  def test_distance_adjust_uses_default_when_stopped(self):
    assert get_traffic_stop_distance_adjust(-1.5, 0.0, 0.0) == -2.0
    assert get_traffic_stop_distance_adjust(-1.5, 0.05, np.nan) == -2.0

  def test_obstacle_distance_passthrough(self):
    # Signal obstacle beyond the cruise obstacle is returned as-is.
    assert get_traffic_stop_obstacle_distance(20.0, 10.0, 0.0) == 20.0
    assert get_traffic_stop_obstacle_distance(0.0, 0.0, 0.0) == 0.0

  def test_obstacle_distance_release_interp(self):
    # Signal obstacle between release and cruise is progressively revealed.
    out = get_traffic_stop_obstacle_distance(60.0, 100.0, 0.0, release_distance=50.0)
    # Released value is strictly between the signal and cruise obstacles.
    assert 60.0 < out < 100.0
    release = float(np.interp(60.0, [50.0, 100.0], [1.0, 0.0]))
    assert abs(out - (100.0 + release * (60.0 - 100.0))) < 1e-9

  def test_obstacle_distance_below_release_is_signal(self):
    assert get_traffic_stop_obstacle_distance(20.0, 100.0, 0.0, release_distance=50.0) == 20.0

  def test_entry_allowed_steering(self):
    assert is_traffic_stop_entry_allowed(0.0) is True
    assert is_traffic_stop_entry_allowed(49.0) is True
    assert is_traffic_stop_entry_allowed(50.0) is False
    assert is_traffic_stop_entry_allowed(-50.0) is False
    assert is_traffic_stop_entry_allowed(90.0) is False


class TestCarrotPlannerTrafficStopWiring(unittest.TestCase):
  """End-to-end check that CarrotPlanner drives the matcher from a model lead."""

  def _make_fake_sm(self, v_ego=1.0, lead_prob=0.99, lead_x=13.52, lead_v=0.0,
                    lead_x_std=0.5, lead_y_std=0.1, lead_v_std=0.1, radar_lead=False):
    car_state = MagicMock()
    car_state.vEgo = float(v_ego)
    car_state.aEgo = 0.0
    car_state.gasPressed = False
    car_state.brakePressed = False
    car_state.leftBlinker = False
    car_state.steeringAngleDeg = 0.0

    lead_one = MagicMock()
    lead_one.status = bool(radar_lead)
    lead_one.vLead = 0.0
    lead_one.aLeadK = 0.0
    lead_one.dRel = 0.0

    model = MagicMock()
    model.meta.laneChangeState = 0
    model.meta.desireState = [0, 0, 0, 0, 0, 0]
    model.position.x = [10.0] * 33
    model.position.y = [0.0] * 33
    model.velocity.x = [0.0] * 33
    model.orientationRate.z = [0.0] * 33
    lead = MagicMock()
    lead.prob = lead_prob
    lead.x = (lead_x,)
    lead.v = (lead_v,)
    lead.xStd = (lead_x_std,)
    lead.yStd = (lead_y_std,)
    lead.vStd = (lead_v_std,)
    model.leadsV3 = [lead]

    sm = _FakeSM({
      "carState": car_state,
      "radarState": MagicMock(leadOne=lead_one),
      "modelV2": model,
    })
    return sm

  def test_planner_exposes_matcher_and_default_zero_offset(self):
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
    planner = CarrotPlanner()
    assert isinstance(planner._traffic_stop_model_lead_matcher, TrafficStopModelLeadMatcher)
    assert planner.traffic_stop_model_lead_offset == 0.0

  def test_planner_matches_model_lead_after_confirm_frames(self):
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner, TrafficState, XState
    planner = CarrotPlanner()
    # Force the planner into a confirmed stopping state behind a red light.
    planner._traffic_state = TrafficState.red
    planner._x_state = XState.e2eStopped

    sm = self._make_fake_sm()
    # Before the confirm window elapses the offset stays zero.
    planner.update(sm, v_cruise_kph=30.0)
    assert planner.traffic_stop_model_lead_offset == 0.0

    # Feed enough additional valid stopping frames to confirm the match.
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES):
      planner.update(sm, v_cruise_kph=30.0)
    assert planner.traffic_stop_model_lead_offset == MODEL_LEAD_STOP_OFFSET_M

  def test_planner_no_match_with_radar_lead_present(self):
    from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner, TrafficState, XState
    planner = CarrotPlanner()
    planner._traffic_state = TrafficState.red
    planner._x_state = XState.e2eStopped
    sm = self._make_fake_sm(radar_lead=True)
    for _ in range(MODEL_LEAD_STOP_CONFIRM_FRAMES + 2):
      planner.update(sm, v_cruise_kph=30.0)
    assert planner.traffic_stop_model_lead_offset == 0.0


class _FakeSM:
  """Tiny SubMaster stand-in exposing attribute-style .valid/.alive gates."""

  def __init__(self, data):
    self._data = data
    self.valid = {k: True for k in data}
    self.alive = {k: True for k in data}
    self.logMonoTime = {"modelV2": 0, "radarState": 0, "livePose": 0, "carState": 0}

  def __getitem__(self, key):
    return self._data[key]


if __name__ == "__main__":
  unittest.main()
