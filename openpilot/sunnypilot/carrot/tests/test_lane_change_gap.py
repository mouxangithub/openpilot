#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Unit tests for the sunnypilot lane-change gap tracker.

Covers ``GapLead.read``, ``LaneChangeGapPlan.credit`` and
``LaneChangeGapTracker.update`` directly, plus the
``CarrotPlanner._update_lane_change_gap`` wiring. Everything is mocked so no
cereal runtime / zmq / SubMaster is required.
"""
import math
import unittest
from types import SimpleNamespace
from typing import Any

import numpy as np

from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner
from openpilot.sunnypilot.carrot.config import UnifiedParams
from openpilot.sunnypilot.carrot.radar_motion.lane_change_gap import (
  CHECK_TIMES,
  GapLead,
  LaneChangeGapPlan,
  LaneChangeGapTracker,
)


# --------------------------------------------------------------------------- #
# Builders                                                                    #
# --------------------------------------------------------------------------- #


class _FakeLead:
  """Minimal stand-in for a cereal radar lead (radarState.leadOne/Two)."""

  def __init__(self, *, radarTrackId: int = 0, dRel: float = 30.0, yRel: float = 0.0,
               vRel: float = 0.0, vLead: float = 15.0, aLeadK: float = 0.0,
               status: bool = True, radar: bool = True) -> None:
    self.radarTrackId = radarTrackId
    self.dRel = dRel
    self.yRel = yRel
    self.vRel = vRel
    self.vLead = vLead
    self.aLeadK = aLeadK
    self.status = status
    self.radar = radar


class _FakeAngle:
  def __init__(self, z: float = 0.0, valid: bool = True) -> None:
    self.z = z
    self.valid = valid


class _FakePose:
  def __init__(self, *, z: float = 0.0, valid: bool = True,
               inputs_ok: bool = True, sensors_ok: bool = True) -> None:
    self.angularVelocityDevice = _FakeAngle(z=z, valid=valid)
    self.inputsOK = inputs_ok
    self.sensorsOK = sensors_ok


class _FakeMeta:
  def __init__(self, lane_change_state: int = 0, desire_state: tuple[float, ...] = (0.0,) * 6) -> None:
    self.laneChangeState = lane_change_state
    self.desireState = list(desire_state)


class _FakePosition:
  def __init__(self, t: tuple, x: tuple, y: tuple) -> None:
    self.t = t
    self.x = x
    self.y = y


class _FakeModel:
  def __init__(self, meta: _FakeMeta, position: _FakePosition) -> None:
    self.meta = meta
    self.position = position
    self.velocity = SimpleNamespace(x=tuple(15.0 for _ in position.t))


class _FakeSM:
  """A SubMaster-shaped object that supports ``sm[key]`` indexing."""

  def __init__(self, *, left_blinker: bool = False, right_blinker: bool = False,
               v_ego: float = 15.0, left_blindspot: bool = False, right_blindspot: bool = False,
               lane_change_state: int = 0, lead_one: Any = None, lead_two: Any = None,
               pose: _FakePose | None = None, valid: bool = True, alive: bool = True,
               now_ns: int = 1_000_000_000) -> None:
    self._now_ns = now_ns
    car_state = SimpleNamespace(
      leftBlinker=left_blinker, rightBlinker=right_blinker, vEgo=v_ego,
      leftBlindspot=left_blindspot, rightBlindspot=right_blindspot,
      aEgo=0.0, gasPressed=False, brakePressed=False, steeringAngleDeg=0.0,
      vEgoCluster=v_ego, softHoldActive=0,
    )
    # A straight, well-formed model path (increasing t, monotonic x/y) so the
    # path validation branch in the tracker is satisfiable.
    t = tuple(float(i) * 0.1 for i in range(40))
    x = tuple(0.0 for _ in t)
    y = tuple(float(i) * 0.2 for i in t)  # straight line to the right
    model = _FakeModel(_FakeMeta(lane_change_state), _FakePosition(t, x, y))
    radar = SimpleNamespace(
      leadOne=lead_one if lead_one is not None else _FakeLead(),
      leadTwo=lead_two if lead_two is not None else _FakeLead(status=False, radar=False),
    )
    self._data = {
      "carState": car_state,
      "modelV2": model,
      "radarState": radar,
      "livePose": pose if pose is not None else _FakePose(),
    }
    self.logMonoTime = {
      "modelV2": now_ns,
      "radarState": now_ns,
      "livePose": now_ns,
    }
    self.valid = {k: valid for k in self._data}
    self.alive = {k: alive for k in self._data}

  def __getitem__(self, key: str) -> Any:
    return self._data[key]


# --------------------------------------------------------------------------- #
# GapLead.read                                                                #
# --------------------------------------------------------------------------- #


class TestGapLeadRead(unittest.TestCase):
  def test_none_returns_none(self) -> None:
    assert GapLead.read(None) is None

  def test_status_false_returns_none(self) -> None:
    assert GapLead.read(_FakeLead(status=False)) is None

  def test_radar_false_returns_none(self) -> None:
    assert GapLead.read(_FakeLead(radar=False)) is None

  def test_negative_track_id_returns_none(self) -> None:
    assert GapLead.read(_FakeLead(radarTrackId=-1)) is None

  def test_valid_lead_is_read(self) -> None:
    lead = GapLead.read(_FakeLead(radarTrackId=7, dRel=25.0, yRel=-1.0,
                                  vRel=2.0, vLead=18.0, aLeadK=-0.3))
    assert lead is not None
    assert lead.radarTrackId == 7
    assert lead.dRel == 25.0

  def test_out_of_range_drel_returns_none(self) -> None:
    assert GapLead.read(_FakeLead(dRel=200.0)) is None
    assert GapLead.read(_FakeLead(dRel=-50.0)) is None

  def test_out_of_range_yrel_returns_none(self) -> None:
    assert GapLead.read(_FakeLead(yRel=15.0)) is None

  def test_nan_fields_returns_none(self) -> None:
    lead = _FakeLead()
    lead.dRel = float("nan")
    assert GapLead.read(lead) is None


# --------------------------------------------------------------------------- #
# LaneChangeGapPlan.credit                                                   #
# --------------------------------------------------------------------------- #


class TestLaneChangeGapPlanCredit(unittest.TestCase):
  def _valid_lead(self, **kw) -> _FakeLead:
    return _FakeLead(vLead=18.0, aLeadK=0.0, status=True, radar=True, **kw)

  def test_inactive_returns_zeros(self) -> None:
    plan = LaneChangeGapPlan(active=False)
    out = plan.credit(self._valid_lead(), np.linspace(0, 3, 61), 15.0, 1.0, 1.5, 6.0, 0.9)
    assert np.all(out == 0.0)

  def test_returns_zeros_when_primary_mismatch(self) -> None:
    plan = LaneChangeGapPlan(active=True, primary_id=99, confidence=1.0, clearance_s=0.5,
                             targets=(GapLead.read(self._valid_lead(radarTrackId=8, dRel=20.0)),))
    out = plan.credit(self._valid_lead(radarTrackId=7), np.linspace(0, 3, 61), 15.0, 1.0, 1.5, 6.0, 0.9)
    assert np.all(out == 0.0)

  def test_credit_shape_and_nonneg(self) -> None:
    primary = self._valid_lead(radarTrackId=7, dRel=20.0, yRel=3.0)  # lateral offset in the destination lane
    target = self._valid_lead(radarTrackId=8, dRel=15.0, yRel=-3.0)
    plan = LaneChangeGapPlan(
      active=True, primary_id=7, confidence=1.0, clearance_s=0.5,
      targets=(GapLead.read(target),),
    )
    horizons = np.linspace(0.0, 3.0, 61)
    out = plan.credit(primary, horizons, 15.0, 1.0, 1.5, 6.0, 0.9)
    assert out.shape == horizons.shape
    assert out.dtype == horizons.dtype
    # When the model says the gap is clear, credit is non-negative everywhere.
    assert np.all(out >= 0.0)


# --------------------------------------------------------------------------- #
# LaneChangeGapTracker.update                                                 #
# --------------------------------------------------------------------------- #


class TestLaneChangeGapTrackerUpdate(unittest.TestCase):
  def test_direction_zero_is_inactive(self) -> None:
    tracker = LaneChangeGapTracker()
    plan = tracker.update(now=1.0, direction=0, v_ego=15.0, yaw_rate=0.0,
                           path_t=(0.0, 1.0), path_x=(0.0, 0.0), path_y=(0.0, 0.0),
                           primary=_FakeLead(), secondary=None)
    assert plan.active is False
    assert plan.reason == "inactive"

  def test_invalid_now_resets(self) -> None:
    tracker = LaneChangeGapTracker()
    plan = tracker.update(now=float("nan"), direction=-1, v_ego=15.0, yaw_rate=0.0,
                           path_t=(0.0, 1.0), path_x=(0.0, 0.0), path_y=(0.0, 0.0),
                           primary=_FakeLead(), secondary=None, valid=False)
    assert plan.reason == "invalid-input"
    assert tracker.direction == 0

  def test_high_yaw_rate_is_pose_or_speed(self) -> None:
    tracker = LaneChangeGapTracker()
    plan = tracker.update(now=1.0, direction=-1, v_ego=15.0, yaw_rate=0.2,
                           path_t=(0.0, 1.0), path_x=(0.0, 0.0), path_y=(0.0, 0.0),
                           primary=_FakeLead(), secondary=None)
    assert plan.reason == "pose-or-speed"

  def test_selection_changed_returns_inactive(self) -> None:
    tracker = LaneChangeGapTracker()
    # First update establishes the entry selection.
    tracker.update(now=1.0, direction=-1, v_ego=15.0, yaw_rate=0.0,
                   path_t=(0.0, 1.0), path_x=(0.0, 0.0), path_y=(0.0, 0.0),
                   primary=_FakeLead(radarTrackId=1), secondary=None)
    # Second update keeps direction but the primary id flips -> selection changed.
    plan = tracker.update(now=1.05, direction=-1, v_ego=15.0, yaw_rate=0.0,
                          path_t=(0.0, 1.0), path_x=(0.0, 0.0), path_y=(0.0, 0.0),
                          primary=_FakeLead(radarTrackId=2), secondary=None)
    assert plan.reason in ("selected-leads-changed", "primary-changed")

  def test_left_and_right_directions_are_active(self) -> None:
    tracker = LaneChangeGapTracker()
    for direction in (-1, 1):
      plan = tracker.update(now=1.0, direction=direction, v_ego=15.0, yaw_rate=0.0,
                             path_t=(0.0, 1.0), path_x=(0.0, 0.0), path_y=(0.0, 0.0),
                             primary=_FakeLead(), secondary=None, valid=False)
      assert plan.active is True


# --------------------------------------------------------------------------- #
# CarrotPlanner wiring                                                        #
# --------------------------------------------------------------------------- #


class TestCarrotPlannerLaneChangeGap(unittest.TestCase):
  def _planner(self) -> CarrotPlanner:
    return CarrotPlanner(UnifiedParams())

  def test_no_blinker_is_inactive(self) -> None:
    planner = self._planner()
    sm = _FakeSM(left_blinker=False, right_blinker=False, lane_change_state=0)
    planner._update_lane_change_gap(sm)
    assert planner.lane_change_active is False
    assert planner.lane_change_gap.active is False
    assert planner.lane_change_gap.reason == "inactive"

  def test_active_but_invalid_sets_invalid_input(self) -> None:
    planner = self._planner()
    planner.lane_change_active = True  # normally set by _update_model_desire
    sm = _FakeSM(left_blinker=True, right_blinker=False, lane_change_state=1, valid=False)
    planner._update_lane_change_gap(sm)
    assert planner.lane_change_active is True
    assert planner.lane_change_gap.active is True
    assert planner.lane_change_gap.reason == "invalid-input"

  def test_desire_wiring_in_model_desire(self) -> None:
    # _update_model_desire must set lane_change_active from laneChangeState and
    # still run the gap tracker without raising.
    planner = self._planner()
    sm = _FakeSM(left_blinker=True, right_blinker=False, lane_change_state=1)
    planner._update_model_desire(sm)
    assert planner.lane_change_active is True
    # A finishing state also counts as active.
    planner2 = self._planner()
    sm2 = _FakeSM(left_blinker=True, right_blinker=False, lane_change_state=2)
    planner2._update_model_desire(sm2)
    assert planner2.lane_change_active is True

  def test_update_runs_end_to_end(self) -> None:
    planner = self._planner()
    sm = _FakeSM(left_blinker=True, right_blinker=False, lane_change_state=1,
                 v_ego=15.0, lead_one=_FakeLead(radarTrackId=1, dRel=20.0, vLead=18.0))
    # The public update() must not raise and must leave the planner consistent.
    planner.update(sm, v_cruise_kph=60.0, mode="acc")
    assert planner.lane_change_active is True
    assert isinstance(planner.lane_change_gap, LaneChangeGapPlan)
    assert hasattr(planner, "_lane_change_tracker")
    assert isinstance(planner._lane_change_tracker, LaneChangeGapTracker)


if __name__ == "__main__":
  unittest.main()
