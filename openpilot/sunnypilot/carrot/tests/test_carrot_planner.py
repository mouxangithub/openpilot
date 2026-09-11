"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Unit tests for the carrot planner control changes (Phase 1):

  * ``TrafficState.left`` equals 3 (left-turn green semantics).
  * Multi-frame confirmation of the vision traffic-light state.
  * ``comfort_a_target`` comfortable-brake computation.
  * ``active`` reflects carrot connectivity.

These exercise ``CarrotPlanner`` internals directly so no cereal runtime and no
full SubMaster are required.
"""
import numpy as np
from openpilot.common.test import OpenpilotTestCase

from openpilot.sunnypilot.carrot.carrot_functions import (
  CarrotPlanner, TrafficState, XState,
)
from openpilot.sunnypilot.carrot.config import UnifiedParams


def _make_planner() -> CarrotPlanner:
  return CarrotPlanner(UnifiedParams())


def _check_stopping(planner: CarrotPlanner, *, stop: bool, v_ego: float = 10.0) -> None:
  """Drive ``_check_model_stopping`` with a controlled stop/non-stop frame."""
  v_model = np.array([4.0] * 33, dtype=float)
  if stop:
    # Near, slow end-of-path => stop_sign True at 36 km/h.
    v_model[-1] = 1.0
    model_x_last = 10.0
  else:
    v_model[-1] = 20.0
    model_x_last = 300.0
  planner._check_model_stopping(
    v_cruise_set=0.0, v_model=v_model, v_ego=v_ego, a_ego=0.0,
    model_x_last=model_x_last, model_y=v_model, d_rel=50.0,
  )


class TestTrafficStateEnum(OpenpilotTestCase):
  def test_left_value_is_three(self) -> None:
    assert TrafficState.left.value == 3
    assert TrafficState.off.value == 0
    assert TrafficState.red.value == 1
    assert TrafficState.green.value == 2


class TestMultiFrameConfirmation(OpenpilotTestCase):
  def test_red_requires_confirmation(self) -> None:
    planner = _make_planner()
    # A single stop frame must NOT flip the state.
    _check_stopping(planner, stop=True)
    assert planner._traffic_state == TrafficState.off
    # Five sustained frames confirm red.
    for _ in range(4):
      _check_stopping(planner, stop=True)
    assert planner._traffic_state == TrafficState.red

  def test_red_expires_when_lost(self) -> None:
    planner = _make_planner()
    for _ in range(5):
      _check_stopping(planner, stop=True)
    assert planner._traffic_state == TrafficState.red
    # Losing the signal for 5 frames returns to off (hysteresis).
    for _ in range(5):
      _check_stopping(planner, stop=False)
    assert planner._traffic_state == TrafficState.off

  def test_green_requires_longer_confirmation(self) -> None:
    planner = _make_planner()
    # Build a green frame: fast end-of-path velocity => start_sign True.
    v_model = np.array([4.0] * 33, dtype=float)
    v_model[-1] = 8.0
    for _ in range(7):  # one short of the 8-frame green threshold
      planner._check_model_stopping(0.0, v_model, 10.0, 0.0, 300.0, v_model, 50.0)
    assert planner._traffic_state == TrafficState.off
    planner._check_model_stopping(0.0, v_model, 10.0, 0.0, 300.0, v_model, 50.0)
    assert planner._traffic_state == TrafficState.green


class TestComfortATarget(OpenpilotTestCase):
  def test_zero_when_not_stopping(self) -> None:
    planner = _make_planner()
    planner._x_state = XState.cruise
    planner._v_ego = 20.0
    planner._stop_dist = 0.0
    assert planner.comfort_a_target == 0.0

  def test_negative_when_stopping(self) -> None:
    planner = _make_planner()
    planner._x_state = XState.e2eStop
    planner._v_ego = 10.0
    planner._stop_dist = 20.0
    planner._comfort_brake = 2.4
    # a = -v^2 / (2*d) = -100/40 = -2.5, capped at comfort_brake 2.4.
    assert planner.comfort_a_target == -2.4

  def test_capped_when_comfort_brake_lower(self) -> None:
    planner = _make_planner()
    planner._x_state = XState.e2eStopped
    planner._v_ego = 5.0
    planner._stop_dist = 100.0
    planner._comfort_brake = 0.5
    # a = -25/200 = -0.125, capped at 0.5 -> -0.125 (smaller magnitude wins).
    assert abs(planner.comfort_a_target - (-0.125)) < 1e-6


class TestActiveProperty(OpenpilotTestCase):
  def test_active_reflects_connectivity(self) -> None:
    planner = _make_planner()
    planner._active_carrot = 0
    assert planner.active is False
    planner._active_carrot = 2
    assert planner.active is True
