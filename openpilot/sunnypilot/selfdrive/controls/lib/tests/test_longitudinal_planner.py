"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
S3 / E2 regression test for the speed-limit unification.

After unification, ``LongitudinalPlannerSP`` must NOT inject a competing speed
*target* keyed by ``LongitudinalPlanSource.carrot``. Carrot's longitudinal
adapter still feeds t-follow / lane-change / traffic-stop data to the MPC when
active, but the road-speed-limit target is owned solely by Speed Limit Assist
(SLA). With ``CarrotLongitudinalSourceEnabled`` set, ``carrot`` must never
appear in ``planner.targets``.
"""
from unittest.mock import MagicMock

from openpilot.common.test import OpenpilotTestCase
from openpilot.cereal import custom
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlannerSP

LongitudinalPlanSource = custom.LongitudinalPlanSP.LongitudinalPlanSource


class _StubSource:
  def __init__(self, v_target: float = 0.0, a_target: float = 0.0) -> None:
    self.output_v_target = v_target
    self.output_a_target = a_target

  def update(self, *args, **kwargs) -> None:
    pass


class TestCarrotTargetUnification(OpenpilotTestCase):
  def _make_planner(self):
    planner = LongitudinalPlannerSP(MagicMock(), MagicMock(), MagicMock())
    # Stub the heavy collaborators so the test depends only on the planner's
    # target-arbitration logic, not on SLA/SCC/dec internals or a live stream.
    planner.scc = _StubSource(v_target=100.0, a_target=0.0)
    planner.sla = _StubSource(v_target=10.0, a_target=0.0)  # lowest -> wins
    planner.resolver = MagicMock()
    planner.resolver.speed_limit = 10.0
    planner.resolver.speed_limit_final_last = 10.0
    planner.resolver.speed_limit_valid = True
    planner.resolver.speed_limit_last_valid = True
    planner.resolver.distance = 0.0
    planner.dec = MagicMock()
    planner.dec.mode.return_value = "acc"
    planner.dec.active.return_value = False
    planner.carrot_source = MagicMock()
    planner.carrot_source.active = False
    planner._carrot_enabled = True  # simulate CarrotLongitudinalSourceEnabled
    return planner

  def _sm(self):
    car_state = MagicMock()
    car_state.vCruiseCluster = 30.0
    car_control = MagicMock()
    car_control.enabled = True
    car_control.cruiseControl.override = False
    sm = MagicMock()
    sm.__getitem__.side_effect = lambda k: {"carState": car_state, "carControl": car_control}[k]
    return sm

  def test_no_carrot_target_injected(self) -> None:
    planner = self._make_planner()
    sm = self._sm()
    planner.update_targets(sm, v_ego=10.0, a_ego=0.0, v_cruise=30.0)
    # The competing carrot speed target is gone.
    assert LongitudinalPlanSource.carrot not in planner.targets
    # SLA (lowest stubbed v_target) is the sole speed-limit executor.
    assert planner.source == LongitudinalPlanSource.speedLimitAssist

  def test_carrot_target_absent_even_with_source_active(self) -> None:
    # Even if the Carrot adapter reports active (t-follow / traffic-stop data),
    # it must still not reintroduce a speed target — it only supplies MPC
    # shaping data via the carrot_* fields.
    planner = self._make_planner()
    planner.carrot_source.active = True
    sm = self._sm()
    planner.update_targets(sm, v_ego=10.0, a_ego=0.0, v_cruise=30.0)
    assert LongitudinalPlanSource.carrot not in planner.targets
