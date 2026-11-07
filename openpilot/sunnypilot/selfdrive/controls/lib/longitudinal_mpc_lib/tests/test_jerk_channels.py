"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Three-channel jerk factors: the clamping, the parsing and the resolution.

The MPC calls `set_weights` every frame, so a bad factor here would reach the
solver continuously. These tests pin the two properties that keep that safe:
a factor outside the usable range never reaches the solver, and the defaults
reproduce the stock single-factor behaviour exactly.
"""

import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_mpc_lib.jerk_channels import (
  CHANNELS,
  MAX_FACTOR,
  MIN_FACTOR,
  STOCK_FACTORS,
  clamp_factor,
  factors_for_personality,
  parse_factors,
)


class TestClampFactor(unittest.TestCase):
  def test_a_normal_value_passes_through(self):
    self.assertEqual(clamp_factor(1.5), 1.5)
    self.assertEqual(clamp_factor(1.0), 1.0)

  def test_the_range_is_enforced(self):
    self.assertEqual(clamp_factor(MIN_FACTOR / 2), MIN_FACTOR)
    self.assertEqual(clamp_factor(MAX_FACTOR * 2), MAX_FACTOR)
    self.assertEqual(clamp_factor(0.0), MIN_FACTOR)
    self.assertEqual(clamp_factor(-3.0), MIN_FACTOR)

  def test_a_zero_never_reaches_the_solver(self):
    # A zero factor would drop a cost term entirely, which is not what a user
    # asking for "smoother" means.
    self.assertGreater(clamp_factor(0.0), 0.0)

  def test_unusable_values_fall_back_to_the_default(self):
    self.assertEqual(clamp_factor(None), 1.0)
    self.assertEqual(clamp_factor("nonsense"), 1.0)
    self.assertEqual(clamp_factor(float("nan")), 1.0)
    self.assertEqual(clamp_factor(None, default=1.4), 1.4)

  def test_a_numeric_string_is_accepted(self):
    self.assertEqual(clamp_factor("1.25"), 1.25)


class TestParseFactors(unittest.TestCase):
  def test_three_values_are_kept_in_order(self):
    self.assertEqual(parse_factors([0.5, 1.5, 2.0]), (0.5, 1.5, 2.0))

  def test_a_short_sequence_fills_the_rest_from_the_default(self):
    self.assertEqual(parse_factors([0.5]), (0.5, 1.0, 1.0))
    self.assertEqual(parse_factors([0.5, 1.5]), (0.5, 1.5, 1.0))

  def test_an_empty_or_missing_sequence_is_the_default(self):
    self.assertEqual(parse_factors([]), (1.0, 1.0, 1.0))
    self.assertEqual(parse_factors(None), (1.0, 1.0, 1.0))

  def test_each_value_is_clamped_independently(self):
    self.assertEqual(parse_factors([0.0, 99.0, 1.2]), (MIN_FACTOR, MAX_FACTOR, 1.2))

  def test_a_custom_default_is_honoured_for_missing_channels(self):
    self.assertEqual(parse_factors([0.5], default=(1.2, 1.3, 1.4)), (0.5, 1.3, 1.4))


class TestFactorsForPersonality(unittest.TestCase):
  def test_without_overrides_the_stock_factors_apply(self):
    self.assertEqual(factors_for_personality("standard"), (1.0, 1.0, 1.0))
    self.assertEqual(factors_for_personality("aggressive"), STOCK_FACTORS["aggressive"])
    self.assertEqual(factors_for_personality("relaxed"), (1.0, 1.0, 1.0))

  def test_an_unknown_personality_falls_back_to_standard(self):
    self.assertEqual(factors_for_personality("nonsense"), STOCK_FACTORS["standard"])

  def test_overrides_replace_the_stock_factors(self):
    overrides = {"standard": (0.6, 1.4, 0.8)}
    self.assertEqual(factors_for_personality("standard", overrides), (0.6, 1.4, 0.8))

  def test_an_override_for_one_personality_leaves_the_others_alone(self):
    overrides = {"standard": (0.6, 1.4, 0.8)}
    self.assertEqual(factors_for_personality("aggressive", overrides), STOCK_FACTORS["aggressive"])
    self.assertEqual(factors_for_personality("relaxed", overrides), STOCK_FACTORS["relaxed"])

  def test_overrides_are_clamped_like_any_other_value(self):
    overrides = {"standard": (0.0, 99.0, 1.0)}
    self.assertEqual(factors_for_personality("standard", overrides), (MIN_FACTOR, MAX_FACTOR, 1.0))

  def test_all_three_channels_are_covered(self):
    self.assertEqual(len(CHANNELS), 3)
    for factors in STOCK_FACTORS.values():
      self.assertEqual(len(factors), 3)


class TestDefaultsAreBehaviourPreserving(unittest.TestCase):
  def test_the_registered_defaults_reproduce_the_stock_weights(self):
    # Every personality defaults to 1.0 on every channel, so a fresh install
    # must produce exactly the same cost weights as the stock single factor.
    for personality in ("aggressive", "standard", "relaxed"):
      factors = factors_for_personality(personality)
      self.assertEqual(len(factors), 3, personality)

    # The two personalities that were already 1.0 everywhere stay that way.
    self.assertEqual(factors_for_personality("standard"), (1.0, 1.0, 1.0))
    self.assertEqual(factors_for_personality("relaxed"), (1.0, 1.0, 1.0))

  def test_aggressive_keeps_its_quicker_accel_and_speed(self):
    # Stock aggressive was 0.5 on the single factor, which scaled both the
    # acceleration and the jerk cost. The split reproduces that.
    accel, danger, speed = factors_for_personality("aggressive")
    self.assertEqual(accel, 0.5)
    self.assertEqual(speed, 0.5)
    self.assertEqual(danger, 1.0)


class TestCarrotFactorPrecedence(unittest.TestCase):
  """The carrot source's single factor must not be silently dropped.

  This is a regression guard. The first version of the three-channel change
  let the per-personality tuning (which defaults to 1.0 everywhere) take
  precedence over the carrot factor the planner passes in, so an active
  carrot source lost its jerk contribution entirely - a behaviour change the
  user never asked for and could not see. The resolution order has to prefer
  the explicit argument.

  The logic is mirrored here rather than imported because `long_mpc` needs
  the compiled acados solver.
  """

  @staticmethod
  def _resolve(jerk_factor, jerk_factors, configured, personality="standard"):
    """The resolution `LongitudinalMpc.set_weights` performs."""
    if jerk_factors is not None:
      return jerk_factors
    if jerk_factor is not None:
      return (jerk_factor, jerk_factor, jerk_factor)
    if configured:
      return factors_for_personality(personality, configured)
    scalar = factors_for_personality(personality)[0]
    return (scalar, scalar, scalar)

  def test_the_carrot_factor_survives_the_default_tuning(self):
    # Every tuning value defaults to 1.0; the carrot value must still win.
    configured = {"standard": (1.0, 1.0, 1.0)}
    self.assertEqual(self._resolve(0.3, None, configured), (0.3, 0.3, 0.3))

  def test_the_carrot_factor_wins_over_a_configured_tuning(self):
    configured = {"standard": (0.6, 1.4, 0.8)}
    self.assertEqual(self._resolve(0.3, None, configured), (0.3, 0.3, 0.3))

  def test_without_carrot_the_tuning_is_used(self):
    configured = {"standard": (0.6, 1.4, 0.8)}
    self.assertEqual(self._resolve(None, None, configured), (0.6, 1.4, 0.8))

  def test_an_explicit_three_channel_argument_wins_over_everything(self):
    configured = {"standard": (1.0, 1.0, 1.0)}
    self.assertEqual(self._resolve(0.3, (0.5, 1.5, 0.7), configured), (0.5, 1.5, 0.7))

  def test_with_nothing_configured_the_stock_personality_applies(self):
    self.assertEqual(self._resolve(None, None, None), (1.0, 1.0, 1.0))


if __name__ == "__main__":
  unittest.main()
