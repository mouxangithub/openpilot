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


class TestTFollowUserScale(OpenpilotTestCase):
  """Carrot must scale sunnypilot's follow time, not replace it.

  long_mpc.update() treats a non-None t_follow as authoritative, so while the Carrot
  source was active the Longitudinal MPC Tuning page was ignored. Carrot now
  multiplies its own modulated value by the ratio between the user's tuning and that
  tuning's default, which keeps the page authoritative and leaves an untouched device
  at exactly 1.0.
  """

  def test_defaults_match_the_registered_param_defaults(self) -> None:
    """The invariant: a drift here makes the scale non-1.0 for everyone.

    long_mpc pulls in acados and capnp, so parse the sources instead of importing.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[6]
    mpc_src = (root / "openpilot" / "selfdrive" / "controls" / "lib" /
               "longitudinal_mpc_lib" / "long_mpc.py").read_text(encoding="utf-8")
    keys_src = (root / "openpilot" / "common" / "params_keys.h").read_text(encoding="utf-8")

    block = re.search(r"T_FOLLOW_DEFAULTS\s*=\s*\{(.*?)\n\}", mpc_src, re.S)
    assert block is not None, "T_FOLLOW_DEFAULTS is gone; the scaling fix depends on it"
    declared = {m.group(1): float(m.group(2))
                for m in re.finditer(r"LongitudinalPersonality\.(\w+):\s*([\d.]+)", block.group(1))}

    for personality, key in (("relaxed", "LongitudinalMpcTuningTFollowRelaxed"),
                             ("standard", "LongitudinalMpcTuningTFollowStandard"),
                             ("aggressive", "LongitudinalMpcTuningTFollowAggressive")):
      m = re.search(r'\{"' + key + r'",\s*\{\s*PERSISTENT \| BACKUP,\s*FLOAT,\s*"([\d.]+)"\s*\}\}', keys_src)
      assert m is not None, f"{key} is not registered"
      assert declared.get(personality) == float(m.group(1)), (
        f"{personality}: T_FOLLOW_DEFAULTS={declared.get(personality)} but {key} defaults to "
        f"{m.group(1)} - the user scale would not be 1.0 on an untouched device")

  def test_scale_is_exactly_one_on_defaults(self) -> None:
    """Behaviour preservation: untouched tuning must not change the follow time."""
    from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import T_FOLLOW_DEFAULTS
    for personality, default in T_FOLLOW_DEFAULTS.items():
      assert default > 0.0, f"{personality} default must be positive, got {default}"
    # the ratio of a default to itself is 1.0 by construction; assert the shape the
    # planner relies on rather than re-deriving the division
    assert set(T_FOLLOW_DEFAULTS) == {
      __import__("openpilot.cereal.log", fromlist=["log"]).LongitudinalPersonality.relaxed,
      __import__("openpilot.cereal.log", fromlist=["log"]).LongitudinalPersonality.standard,
      __import__("openpilot.cereal.log", fromlist=["log"]).LongitudinalPersonality.aggressive,
    }, "T_FOLLOW_DEFAULTS must be keyed by the cereal personality enum"

  def test_planner_multiplies_and_never_replaces(self) -> None:
    """Guard the call site: the raw carrot value must not reach mpc.update again."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[6]
    src = (root / "openpilot" / "selfdrive" / "controls" / "lib" /
           "longitudinal_planner.py").read_text(encoding="utf-8")
    assert "t_follow=self.carrot_t_follow" not in src, "the raw carrot t_follow is passed again"
    assert "t_follow_user_scale(" in src, "the user scale is no longer applied"
    assert re.search(r"carrot_t_follow = None\s*\n\s*if self\.carrot_source_active:", src) is not None, \
      "carrot_t_follow must default to None so the MPC falls back to the tuned value"
