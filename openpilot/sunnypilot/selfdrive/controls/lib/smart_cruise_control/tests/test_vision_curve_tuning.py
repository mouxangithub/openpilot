#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""SmartCruiseControlVision curve tuning, fed by carrot's curve parameters.

Why these knobs moved here: carrot exposes AutoCurveSpeedFactor,
AutoCurveSpeedAggressiveness and their highway variants in BOTH UIs, and before this
wiring they did nothing for the car - the value only reached `desiredSpeed`, which is
display-only (see the note in carrot_functions.py, plus the assertions in
test_carrot_planner.py and test_speed_limit_resolver.py). Meanwhile the controller that
actually slows for curves had no tunables at all: every threshold was a module constant.
carrot now supplies setpoints to that controller instead of owning a second
curve-deceleration path.

The safety argument for the whole change is one property:

  **At carrot's neutral values (every factor 100) the tuned setpoints equal the module
  constants exactly, so an untouched device behaves precisely as before.**

test_neutral_is_identical_to_the_constants pins that down. The rest covers the
direction of each knob, the plain/highway variant selection, and that a nonsense value
cannot ask for an unsafe amount of lateral acceleration.

Note: this uses unittest.TestCase rather than OpenpilotTestCase on purpose - the latter
imports common.hardware -> gpio -> fcntl, which is Linux-only, so a bare TestCase keeps
this runnable on a dev PC as well as on the device.
"""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.vision_controller import (
  _A_LAT_REG_MAX,
  _A_LAT_REG_MAX_MAX,
  _A_LAT_REG_MAX_MIN,
  _ABORT_ENTERING_PRED_LAT_ACC_TH,
  _CURVE_TH_SCALE_MAX,
  _CURVE_TH_SCALE_MIN,
  _ENTERING_PRED_LAT_ACC_TH,
  _FINISH_LAT_ACC_TH,
  _HIGHWAY_SPEED_KPH,
  _LEAVING_LAT_ACC_TH,
  _TH,
  _TURNING_LAT_ACC_TH,
  _URGENT_PRED_LAT_ACC_TH,
  SmartCruiseControlVision,
  VisionState,
)


NEUTRAL = {
  "AutoCurveSpeedFactor": 100.0,
  "AutoCurveSpeedFactorH": 100.0,
  "AutoCurveSpeedAggressiveness": 100.0,
  "AutoCurveSpeedAggressivenessH": 100.0,
}

PLAIN_SPEED = 15.0   # 54 kph -> normal-road variant
HIGHWAY_SPEED = 25.0  # 90 kph -> highway variant


def _params(values: dict[str, float] | None = None, enabled: bool = True):
  """A Params stand-in returning the given curve values, 100 (neutral) by default."""
  merged = dict(NEUTRAL)
  merged.update(values or {})

  class _P:
    def get_bool(self, name, *a, **k):
      return enabled if name == "SmartCruiseControlVision" else False

    def get_float(self, name, *a, **k):
      return merged.get(name, 100.0)

  return _P()


def _vision(v_ego: float = PLAIN_SPEED, values: dict[str, float] | None = None,
            enabled: bool = True) -> SmartCruiseControlVision:
  """A controller at the given speed, with tuning loaded as update() would do."""
  with patch("openpilot.common.params.Params", return_value=_params(values, enabled)):
    c = SmartCruiseControlVision()
  c.v_ego = v_ego
  c._load_curve_tuning()
  return c


class TestCurveTuningNeutral(unittest.TestCase):
  """Neutral carrot values must reproduce the pre-existing behaviour exactly."""

  def test_neutral_is_identical_to_the_constants(self):
    c = _vision()
    self.assertEqual(c.tuned_a_lat_reg_max, _A_LAT_REG_MAX)
    self.assertEqual(c.tuned_curve_th_scale, 1.0)

  def test_th_helper_is_identity_at_scale_one(self):
    for nominal in (_ENTERING_PRED_LAT_ACC_TH, _TURNING_LAT_ACC_TH, _URGENT_PRED_LAT_ACC_TH,
                    _LEAVING_LAT_ACC_TH, _FINISH_LAT_ACC_TH, _ABORT_ENTERING_PRED_LAT_ACC_TH):
      self.assertEqual(_TH(1.0, nominal), nominal)

  def test_v_target_matches_the_constant_derived_value(self):
    """The number that reaches the planner is unchanged at neutral."""
    rate_z = np.array([0.02] * 33)
    vel_x = np.array([25.0] * 33)
    sm = SimpleNamespace(modelV2=SimpleNamespace(
      orientationRate=SimpleNamespace(z=rate_z), velocity=SimpleNamespace(x=vel_x)),
      controlsState=SimpleNamespace(curvature=0.01))

    c = _vision(v_ego=25.0)
    c.long_enabled = True
    c._update_calculations(sm)

    max_pred_curvature = float(np.percentile(rate_z / vel_x, 97))
    expected = min(float((_A_LAT_REG_MAX / max_pred_curvature) ** 0.5), 255.0)
    self.assertAlmostEqual(c.v_target, expected, places=6)


class TestCurveSpeedFactor(unittest.TestCase):
  """AutoCurveSpeedFactor scales the lateral-acceleration ceiling."""

  def test_higher_factor_allows_more_lateral_acc(self):
    neutral = _vision(values={"AutoCurveSpeedFactor": 100.0, "AutoCurveSpeedFactorH": 100.0})
    loose = _vision(values={"AutoCurveSpeedFactor": 200.0, "AutoCurveSpeedFactorH": 200.0})
    self.assertGreater(loose.tuned_a_lat_reg_max, neutral.tuned_a_lat_reg_max)

  def test_lower_factor_is_more_cautious(self):
    tight = _vision(values={"AutoCurveSpeedFactor": 50.0, "AutoCurveSpeedFactorH": 50.0})
    self.assertAlmostEqual(tight.tuned_a_lat_reg_max, _A_LAT_REG_MAX * 0.5, places=6)

  def test_a_full_scale_factor_is_clamped(self):
    """200% would ask for 4.0 m/s^2; the clamp keeps it at the documented ceiling."""
    c = _vision(values={"AutoCurveSpeedFactor": 200.0, "AutoCurveSpeedFactorH": 200.0})
    self.assertEqual(c.tuned_a_lat_reg_max, _A_LAT_REG_MAX_MAX)

  def test_an_absurd_factor_is_clamped(self):
    c = _vision(values={"AutoCurveSpeedFactor": 100000.0, "AutoCurveSpeedFactorH": 100000.0})
    self.assertEqual(c.tuned_a_lat_reg_max, _A_LAT_REG_MAX_MAX)

  def test_v_target_scales_with_the_square_root_of_the_ceiling(self):
    """v = sqrt(a_lat / curvature), so the speed scales as the square root."""
    rate_z = np.array([0.02] * 33)
    vel_x = np.array([25.0] * 33)
    sm = SimpleNamespace(modelV2=SimpleNamespace(
      orientationRate=SimpleNamespace(z=rate_z), velocity=SimpleNamespace(x=vel_x)),
      controlsState=SimpleNamespace(curvature=0.01))

    neutral = _vision(v_ego=PLAIN_SPEED)
    neutral.long_enabled = True
    neutral._update_calculations(sm)

    loose = _vision(v_ego=PLAIN_SPEED, values={"AutoCurveSpeedFactor": 200.0,
                                              "AutoCurveSpeedFactorH": 200.0})
    loose.long_enabled = True
    loose._update_calculations(sm)

    expected_ratio = math.sqrt(_A_LAT_REG_MAX_MAX / _A_LAT_REG_MAX)
    self.assertAlmostEqual(loose.v_target / neutral.v_target, expected_ratio, places=2)

  def test_zero_factor_is_treated_as_neutral(self):
    """An unset/unreadable param reads back as 0; it must not mean 'no lateral acc'."""
    c = _vision(values={"AutoCurveSpeedFactor": 0.0, "AutoCurveSpeedFactorH": 0.0})
    self.assertEqual(c.tuned_a_lat_reg_max, _A_LAT_REG_MAX)


class TestCurveAggressiveness(unittest.TestCase):
  """AutoCurveSpeedAggressiveness scales the thresholds that arm the turn cycle."""

  def test_aggressiveness_is_inverted(self):
    """A smaller threshold reacts to gentler curves, i.e. more aggressive."""
    high = _vision(values={"AutoCurveSpeedAggressiveness": 200.0,
                           "AutoCurveSpeedAggressivenessH": 200.0})
    low = _vision(values={"AutoCurveSpeedAggressiveness": 50.0,
                          "AutoCurveSpeedAggressivenessH": 50.0})
    self.assertLess(high.tuned_curve_th_scale, 1.0)
    self.assertGreater(low.tuned_curve_th_scale, 1.0)
    self.assertLess(_TH(high.tuned_curve_th_scale, _ENTERING_PRED_LAT_ACC_TH),
                    _TH(low.tuned_curve_th_scale, _ENTERING_PRED_LAT_ACC_TH))

  def test_scales_are_clamped(self):
    huge = _vision(values={"AutoCurveSpeedAggressiveness": 10000.0,
                           "AutoCurveSpeedAggressivenessH": 10000.0})
    self.assertEqual(huge.tuned_curve_th_scale, _CURVE_TH_SCALE_MIN)
    tiny = _vision(values={"AutoCurveSpeedAggressiveness": 1.0,
                           "AutoCurveSpeedAggressivenessH": 1.0})
    self.assertLessEqual(tiny.tuned_curve_th_scale, _CURVE_TH_SCALE_MAX)

  def test_zero_aggressiveness_is_treated_as_neutral(self):
    c = _vision(values={"AutoCurveSpeedAggressiveness": 0.0,
                        "AutoCurveSpeedAggressivenessH": 0.0})
    self.assertEqual(c.tuned_curve_th_scale, 1.0)


class TestVariantSelection(unittest.TestCase):
  """The H (highway) parameters apply at or above _HIGHWAY_SPEED_KPH."""

  def test_plain_variant_below_the_crossover(self):
    c = _vision(v_ego=PLAIN_SPEED, values={"AutoCurveSpeedFactor": 150.0,
                                           "AutoCurveSpeedFactorH": 60.0})
    self.assertAlmostEqual(c.tuned_a_lat_reg_max, _A_LAT_REG_MAX * 1.5, places=6)

  def test_highway_variant_at_or_above_the_crossover(self):
    c = _vision(v_ego=HIGHWAY_SPEED, values={"AutoCurveSpeedFactor": 150.0,
                                             "AutoCurveSpeedFactorH": 60.0})
    self.assertAlmostEqual(c.tuned_a_lat_reg_max, _A_LAT_REG_MAX * 0.6, places=6)

  def test_crossover_is_where_the_h_variant_starts(self):
    just_below = _vision(v_ego=(_HIGHWAY_SPEED_KPH - 1) / 3.6,
                         values={"AutoCurveSpeedFactor": 150.0, "AutoCurveSpeedFactorH": 60.0})
    just_at = _vision(v_ego=_HIGHWAY_SPEED_KPH / 3.6,
                      values={"AutoCurveSpeedFactor": 150.0, "AutoCurveSpeedFactorH": 60.0})
    self.assertAlmostEqual(just_below.tuned_a_lat_reg_max, _A_LAT_REG_MAX * 1.5, places=6)
    self.assertAlmostEqual(just_at.tuned_a_lat_reg_max, _A_LAT_REG_MAX * 0.6, places=6)


class TestMasterSwitchStillGates(unittest.TestCase):
  """carrot's parameters must never become an execution path of their own."""

  def test_disabled_controller_emits_nothing(self):
    c = _vision(v_ego=HIGHWAY_SPEED, enabled=False)
    c.long_enabled = True
    c.long_override = False
    enabled, active = c._update_state_machine()
    self.assertEqual(c.state, VisionState.disabled)
    self.assertFalse(enabled)
    self.assertFalse(active)
    self.assertEqual(c.get_v_target_from_control(), 255.0)

  def test_tuning_is_neutral_when_params_are_unreadable(self):
    """A Params that throws must not take down longitudinal control."""
    class _Boom:
      def get_bool(self, *a, **k):
        raise RuntimeError("params unavailable")

      def get_float(self, *a, **k):
        raise RuntimeError("params unavailable")

    with patch("openpilot.common.params.Params", return_value=_Boom()):
      c = SmartCruiseControlVision()
    c.v_ego = HIGHWAY_SPEED
    c._load_curve_tuning()
    self.assertEqual(c.tuned_a_lat_reg_max, _A_LAT_REG_MAX)
    self.assertEqual(c.tuned_curve_th_scale, 1.0)


class TestBoundsAreSane(unittest.TestCase):
  def test_ceiling_bounds_are_ordered(self):
    self.assertLess(_A_LAT_REG_MAX_MIN, _A_LAT_REG_MAX)
    self.assertLess(_A_LAT_REG_MAX, _A_LAT_REG_MAX_MAX)

  def test_neutral_scale_lies_inside_the_scale_bounds(self):
    self.assertLessEqual(_CURVE_TH_SCALE_MIN, 1.0)
    self.assertGreaterEqual(_CURVE_TH_SCALE_MAX, 1.0)


if __name__ == "__main__":
  unittest.main()
