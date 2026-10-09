"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Unit tests for CarrotLongitudinalSource.

These run without the cereal runtime: CarrotLongitudinalSource is exercised with
a mock planner and a dict-backed fake SubMaster so no compiled capnp is needed.
"""
import sys
import types
from unittest import TestCase
from types import SimpleNamespace
from unittest.mock import MagicMock

# Minimal module mocks so CarrotPlanner can be imported on a dev host without
# a compiled capnp runtime.
_common_pkg = types.ModuleType("openpilot.common")
_common_pkg.params = MagicMock()
_common_pkg.realtime = MagicMock(DT_MDL=0.05)
_common_pkg.swaglog = MagicMock(cloudlog=MagicMock())
sys.modules["openpilot.common"] = _common_pkg
sys.modules["openpilot.common.params"] = _common_pkg.params
sys.modules["openpilot.common.realtime"] = _common_pkg.realtime
sys.modules["openpilot.common.swaglog"] = _common_pkg.swaglog

_opendbc_pkg = types.ModuleType("opendbc")
_opendbc_car_pkg = types.ModuleType("opendbc.car")
_opendbc_car_common_pkg = types.ModuleType("opendbc.car.common")
_opendbc_conversions_mod = types.ModuleType("opendbc.car.common.conversions")
class _FakeConversions:
  KPH_TO_MS = 1.0 / 3.6
  MS_TO_KPH = 3.6
_opendbc_conversions_mod.Conversions = _FakeConversions
sys.modules["opendbc"] = _opendbc_pkg
sys.modules["opendbc.car"] = _opendbc_car_pkg
sys.modules["opendbc.car.common"] = _opendbc_car_common_pkg
sys.modules["opendbc.car.common.conversions"] = _opendbc_conversions_mod

from openpilot.sunnypilot.carrot.carrot_functions import XState
from openpilot.sunnypilot.selfdrive.controls.lib.carrot_longitudinal_source import CarrotLongitudinalSource


class FakeSM(dict):
  """Dict-backed SubMaster stand-in supporting ``sm[key]`` and ``logMonoTime``."""
  def __init__(self, data: dict):
    super().__init__(data)
    # Default every present service to a fresh timestamp (1 ms).
    self.logMonoTime = {k: 1_000_000 for k in data}


def _make_carrot(x_state: XState = XState.cruise, v_cruise: float = 30.0,
                 comfort_a: float = 0.0, stop_distance: float = 0.0,
                 active: bool = True, t_follow: float = 1.45,
                 jerk_factor: float = 0.7, comfort_brake: float = 2.5) -> MagicMock:
  carrot = MagicMock()
  carrot.x_state = x_state
  carrot.v_cruise = v_cruise
  carrot.comfort_a_target = comfort_a
  carrot.stop_distance = stop_distance
  carrot.active = active
  carrot.get_T_FOLLOW.return_value = t_follow
  carrot.jerk_factor = jerk_factor
  carrot.comfort_brake = comfort_brake
  return carrot


class TestCarrotLongitudinalSource(TestCase):
  def test_property_passthrough(self) -> None:
    carrot = _make_carrot(x_state=XState.e2eStop, v_cruise=12.5, comfort_a=-1.5,
                          stop_distance=18.0, active=True, t_follow=1.35,
                          jerk_factor=0.5, comfort_brake=2.4)
    src = CarrotLongitudinalSource(carrot=carrot)
    assert src.v_target == 12.5
    assert src.a_target == -1.5
    assert src.should_stop is True
    assert src.stop_dist == 18.0
    assert src.t_follow == 1.35
    assert src.jerk_factor == 0.5
    assert src.comfort_brake == 2.4
    assert src.stop_distance == 18.0

  def test_should_stop_false_when_cruising(self) -> None:
    carrot = _make_carrot(x_state=XState.cruise)
    src = CarrotLongitudinalSource(carrot=carrot)
    assert src.should_stop is False

  def test_active_false_when_planner_inactive(self) -> None:
    carrot = _make_carrot(active=False)
    src = CarrotLongitudinalSource(carrot=carrot)
    sm = FakeSM({"carrotManSP": SimpleNamespace(), "modelV2": SimpleNamespace()})
    src.update(sm, 100.0, "acc")
    # Fresh packet but planner has no real output -> inactive.
    assert src.active is False

  def test_active_true_when_fresh(self) -> None:
    carrot = _make_carrot(active=True)
    src = CarrotLongitudinalSource(carrot=carrot)
    sm = FakeSM({"carrotManSP": SimpleNamespace(), "modelV2": SimpleNamespace()})
    src.update(sm, 100.0, "acc")
    assert src.active is True

  def test_inactive_when_packet_stale(self) -> None:
    carrot = _make_carrot(active=True)
    src = CarrotLongitudinalSource(carrot=carrot)
    # carrotManSP timestamp is 5 s older than the reference -> beyond the 2 s timeout.
    sm = FakeSM({"carrotManSP": SimpleNamespace(), "modelV2": SimpleNamespace()})
    sm.logMonoTime = {"carrotManSP": 0, "modelV2": 5_000_000_000}
    src.update(sm, 100.0, "acc")
    assert src.active is False

  def test_inactive_when_packet_missing(self) -> None:
    carrot = _make_carrot(active=True)
    src = CarrotLongitudinalSource(carrot=carrot)
    # No carrotManSP at all.
    sm = FakeSM({"modelV2": SimpleNamespace()})
    src.update(sm, 100.0, "acc")
    assert src.active is False

  def test_timeout_param_respected(self) -> None:
    carrot = _make_carrot(active=True)
    src = CarrotLongitudinalSource(carrot=carrot)
    # 3 s old with a 5 s timeout -> still fresh.
    fake_params = MagicMock()
    fake_params.get_int = lambda key, default=2000: 5000
    src._params = fake_params
    sm = FakeSM({"carrotManSP": SimpleNamespace(), "modelV2": SimpleNamespace()})
    sm.logMonoTime = {"carrotManSP": 2_000_000_000, "modelV2": 5_000_000_000}
    src.update(sm, 100.0, "acc")
    assert src.active is True

  def test_longitudinal_outputs_passthrough(self) -> None:
    """CarrotPlanner dynamic outputs must be exposed by the adapter for the MPC."""
    carrot = _make_carrot()
    carrot.stop_distance_margin = 6.0
    carrot.traffic_stop_model_lead_offset = 2.0
    carrot.traffic_stop_distance_adjust = -1.5
    carrot.lane_change_active = True
    carrot.dynamic_t_follow_lc = 0.9
    plan = MagicMock(active=True)
    carrot.lane_change_gap = plan
    src = CarrotLongitudinalSource(carrot=carrot)

    assert src.stop_distance_margin == 6.0
    assert src.traffic_stop_model_lead_offset == 2.0
    assert src.traffic_stop_distance_adjust == -1.5
    assert src.lane_change_active is True
    assert src.dynamic_t_follow_lc == 0.9
    assert src.lane_change_gap is plan

  def test_inactive_source_suppresses_obstacle_outputs(self) -> None:
    """When the packet is stale/inactive, the planner must not consume outputs."""
    carrot = _make_carrot(active=False, comfort_brake=2.4)
    carrot.stop_distance_margin = 6.0
    carrot.lane_change_active = False
    src = CarrotLongitudinalSource(carrot=carrot)
    sm = FakeSM({"modelV2": SimpleNamespace()})  # no carrotManSP -> inactive
    src.update(sm, 100.0, "acc")
    assert src.active is False
    # The planner gates consumption on `active`; exposed values are unchanged but
    # are not fed into the MPC while inactive (covered by longitudinal_planner).
    assert src.comfort_brake == 2.4

