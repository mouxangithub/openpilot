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
from types import SimpleNamespace
from unittest.mock import MagicMock

from openpilot.common.test import OpenpilotTestCase

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
                 active: bool = True) -> MagicMock:
  carrot = MagicMock()
  carrot.x_state = x_state
  carrot.v_cruise = v_cruise
  carrot.comfort_a_target = comfort_a
  carrot.stop_distance = stop_distance
  carrot.active = active
  return carrot


class TestCarrotLongitudinalSource(OpenpilotTestCase):
  def test_property_passthrough(self) -> None:
    carrot = _make_carrot(x_state=XState.e2eStop, v_cruise=12.5, comfort_a=-1.5,
                          stop_distance=18.0, active=True)
    src = CarrotLongitudinalSource(carrot=carrot)
    assert src.v_target == 12.5
    assert src.a_target == -1.5
    assert src.should_stop is True
    assert src.stop_dist == 18.0

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

  def test_timeout_param_respected(self, mocker) -> None:
    carrot = _make_carrot(active=True)
    src = CarrotLongitudinalSource(carrot=carrot)
    # 3 s old with a 5 s timeout -> still fresh.
    src._params = mocker.MagicMock()
    src._params.get_int = lambda key, default=2000: 5000
    sm = FakeSM({"carrotManSP": SimpleNamespace(), "modelV2": SimpleNamespace()})
    sm.logMonoTime = {"carrotManSP": 2_000_000_000, "modelV2": 5_000_000_000}
    src.update(sm, 100.0, "acc")
    assert src.active is True
