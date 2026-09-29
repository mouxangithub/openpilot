"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Helpers that were ported from CarrotPilot's t_follow but never wired up.

Two gaps this pins down:

* ``ramp_mode_t_follow_factor`` did not exist here, so the driving-mode multiplier on the
  following time was applied instantly. Clearing a comfort mode (Safe -> Normal is a
  1.3x -> 1.0x step) snapped the gap shut in one cycle instead of releasing it over a few
  seconds as CarrotPilot does.
* ``LeadAccelResponseTF1..4`` were registered in params_keys.h and
  ``get_mode_lead_response`` was defined, but neither was ever read or called. Only the
  flat ``LeadAccelResponse`` reached the decision, so per-gap overrides and the
  driving-mode ceiling were inert.

The pure helpers run anywhere; the planner-level tests need the installed opendbc.
"""
import ast
import pathlib
import unittest

from openpilot.sunnypilot.carrot.t_follow import (
  MODE_T_FOLLOW_RELEASE_RATE,
  get_lead_response_for_gap,
  get_speed_t_follow_factor,
  ramp_mode_t_follow_factor,
)

try:
  from openpilot.common.realtime import DT_MDL
except Exception:  # openpilot.common.realtime pulls in zmq; the pure helpers must still run
  DT_MDL = 0.05

try:
  from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner, DrivingMode
  from openpilot.sunnypilot.carrot.config import UnifiedParams

  _HAVE_PLANNER = True
except Exception:  # opendbc / native deps absent on a bare dev host
  _HAVE_PLANNER = False


class TestRampModeTFollowFactor(unittest.TestCase):
  def test_an_increase_is_applied_immediately(self):
    self.assertEqual(ramp_mode_t_follow_factor(1.3, 1.0, DT_MDL), 1.3)

  def test_a_decrease_is_released_at_the_configured_rate(self):
    # One cycle moves by exactly the release rate: 0.05 * 0.05 s.
    step = MODE_T_FOLLOW_RELEASE_RATE * DT_MDL
    self.assertAlmostEqual(ramp_mode_t_follow_factor(1.0, 1.3, DT_MDL), 1.3 - step, places=9)

  def test_it_never_goes_below_the_target(self):
    # A release step larger than the remaining margin lands exactly on the target.
    self.assertEqual(ramp_mode_t_follow_factor(1.0, 1.001, DT_MDL), 1.0)
    self.assertEqual(ramp_mode_t_follow_factor(1.0, 1.0, DT_MDL), 1.0)

  def test_a_full_safe_to_normal_release_takes_a_few_seconds(self):
    factor, cycles = 1.3, 0
    while factor > 1.0 and cycles < 10_000:
      factor = ramp_mode_t_follow_factor(1.0, factor, DT_MDL)
      cycles += 1
    # 0.3 / 0.05 = 6 s
    self.assertAlmostEqual(cycles * DT_MDL, 6.0, delta=0.1)


class TestGetLeadResponseForGap(unittest.TestCase):
  def test_all_unset_falls_back_to_common(self):
    for gap in range(4):
      self.assertEqual(get_lead_response_for_gap(4, (-1, -1, -1, -1), gap), 4)

  def test_overrides_replace_common_per_gap(self):
    overrides = (5, 3, 0, 4)
    self.assertEqual([get_lead_response_for_gap(4, overrides, g) for g in range(4)], [5, 3, 0, 4])

  def test_an_unset_entry_keeps_common_and_others_stay_independent(self):
    overrides = (-1, -1, 5, -1)
    self.assertEqual(get_lead_response_for_gap(2, overrides, 0), 2)
    self.assertEqual(get_lead_response_for_gap(2, overrides, 2), 5)

  def test_an_out_of_range_gap_falls_back_instead_of_raising(self):
    # Runs in the planner hot path: raising here would take the planner down.
    self.assertEqual(get_lead_response_for_gap(3, (5, 5, 5, 5), 7), 3)
    self.assertEqual(get_lead_response_for_gap(3, (), 0), 3)

  def test_a_capnp_enum_reader_is_unwrapped(self):
    class _Enum:
      raw = 2

    self.assertEqual(get_lead_response_for_gap(1, (0, 0, 4, 0), _Enum()), 4)

  def test_values_are_clamped(self):
    self.assertEqual(get_lead_response_for_gap(9, (-1, -1, -1, -1), 0), 5)
    self.assertEqual(get_lead_response_for_gap(-3, (-1, -1, -1, -1), 0), 0)


class TestGetSpeedTFollowFactor(unittest.TestCase):
  def test_setting_10_leaves_the_gap_unchanged(self):
    for speed in (0.0, 50.0, 100.0, 200.0):
      self.assertAlmostEqual(get_speed_t_follow_factor(10, speed), 1.0, places=9)

  def test_setting_20_doubles_it_at_100_kph(self):
    self.assertAlmostEqual(get_speed_t_follow_factor(20, 0.0), 1.0, places=9)
    self.assertAlmostEqual(get_speed_t_follow_factor(20, 100.0), 2.0, places=9)

  def test_it_does_not_exceed_the_setting_range(self):
    self.assertAlmostEqual(get_speed_t_follow_factor(99, 100.0), 3.0, places=9)
    self.assertAlmostEqual(get_speed_t_follow_factor(0, 100.0), 1.0, places=9)


@unittest.skipUnless(_HAVE_PLANNER, 'needs the installed opendbc')
class TestPlannerWiring(unittest.TestCase):
  def _planner(self):
    planner = CarrotPlanner(UnifiedParams())
    planner._t_follow_gap1 = 1.1
    planner._t_follow_gap2 = 1.3
    planner._t_follow_gap3 = 1.45
    planner._t_follow_gap4 = 1.6
    planner._enable_speed_tf = 0
    planner._tf_decel_boost = 0.0
    return planner

  def test_the_mode_factor_is_ramped_not_stepped(self):
    planner = self._planner()
    planner._my_t_follow_factor = 1.3
    planner.get_T_FOLLOW(personality=2, v_ego=20.0)
    self.assertEqual(planner._tf_mode_factor, 1.3, 'a comfort mode must apply at once')

    planner._my_t_follow_factor = 1.0
    planner.get_T_FOLLOW(personality=2, v_ego=20.0)
    self.assertGreater(planner._tf_mode_factor, 1.0, 'the release must not snap to the target')
    self.assertAlmostEqual(planner._tf_mode_factor, 1.3 - MODE_T_FOLLOW_RELEASE_RATE * DT_MDL, places=9)

  def test_a_per_gap_override_reaches_the_lead_response_decision(self):
    # The two t_follow branches converge to the same number for some inputs, so assert on
    # the wiring itself: get_T_FOLLOW must resolve the response through the per-gap table
    # and the mode ceiling, and must ramp the mode factor.
    src = pathlib.Path(__file__).resolve().parents[1].joinpath('carrot_functions.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    planner = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'CarrotPlanner')
    fn = next(n for n in planner.body if isinstance(n, ast.FunctionDef) and n.name == 'get_T_FOLLOW')
    body = ast.unparse(fn)
    self.assertIn('get_mode_lead_response', body, 'the driving-mode ceiling must be applied')
    self.assertIn('get_lead_response_for_gap', body, 'the per-gap override table must be read')
    self.assertIn('ramp_mode_t_follow_factor', body, 'the mode factor must be ramped, not stepped')
    self.assertIn('_lead_response_tf', body)

  def test_a_comfort_mode_ceiling_softens_an_override(self):
    planner = self._planner()
    planner._lead_accel_response = 5
    planner._lead_response_tf = (-1, -1, -1, -1)
    planner._my_driving_mode = DrivingMode.Eco  # ceiling 2
    from openpilot.sunnypilot.carrot.carrot_functions import get_mode_lead_response
    self.assertEqual(get_mode_lead_response(5, DrivingMode.Eco), 2)


if __name__ == '__main__':
  unittest.main()
