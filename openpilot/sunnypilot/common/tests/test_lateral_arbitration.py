import unittest

from openpilot.sunnypilot.common.lateral_arbitration import (
  LateralArbitrationState,
  differs_from_stock,
  resolve_torque_control_params,
  resolve_use_custom,
  resolve_vehicle_model_params,
)


class TestDiffersFromStock(unittest.TestCase):
  def test_identical_values_are_not_an_edit(self):
    self.assertFalse(differs_from_stock(1.0, 1.0))

  def test_small_float_noise_is_not_an_edit(self):
    # Slider drags produce values like 0.34800000000000003; comparing those
    # raw would always count as an edit and permanently kill the learning.
    self.assertFalse(differs_from_stock(0.34800000000000003, 0.348))
    self.assertFalse(differs_from_stock(1.2500000000000002, 1.25))

  def test_real_difference_is_an_edit(self):
    self.assertTrue(differs_from_stock(0.5, 0.3))
    self.assertTrue(differs_from_stock(1.25, 1.45))

  def test_boundary_is_rounded_to_two_decimals(self):
    # 0.004 rounds to 0.00, so it is not an edit.
    self.assertFalse(differs_from_stock(0.004, 0.0))
    # 0.006 rounds to 0.01, so it is an edit.
    self.assertTrue(differs_from_stock(0.006, 0.0))

  def test_non_finite_is_never_an_edit(self):
    self.assertFalse(differs_from_stock(float("nan"), 0.3))
    self.assertFalse(differs_from_stock(float("inf"), 0.3))
    self.assertFalse(differs_from_stock(float("-inf"), 0.3))

  def test_non_numeric_is_never_an_edit(self):
    self.assertFalse(differs_from_stock(None, 0.3))
    self.assertFalse(differs_from_stock("x", 0.3))


class TestResolveUseCustom(unittest.TestCase):
  def test_edited_value_uses_user(self):
    self.assertTrue(resolve_use_custom(0.5, 0.3, is_torque_car=True,
                                        force_auto_tune=False, force_auto_tune_off=False))

  def test_unedited_value_keeps_learning(self):
    self.assertFalse(resolve_use_custom(0.3, 0.3, is_torque_car=True,
                                         force_auto_tune=False, force_auto_tune_off=False))

  def test_force_auto_tune_suppresses_user_edit(self):
    # ForceAutoTune means "trust the learner", so an edited value must lose.
    self.assertFalse(resolve_use_custom(0.5, 0.3, is_torque_car=True,
                                         force_auto_tune=True, force_auto_tune_off=False))

  def test_force_auto_tune_off_wins_over_everything(self):
    # The operator precedence in the StarPilot original makes this True
    # regardless of whether the value was edited.
    self.assertTrue(resolve_use_custom(0.3, 0.3, is_torque_car=True,
                                        force_auto_tune=False, force_auto_tune_off=True))
    self.assertTrue(resolve_use_custom(0.5, 0.3, is_torque_car=True,
                                        force_auto_tune=True, force_auto_tune_off=True))

  def test_non_torque_car_cannot_lock_friction(self):
    # Friction and latAccelFactor only exist for torque cars.
    self.assertFalse(resolve_use_custom(0.5, 0.3, is_torque_car=False,
                                         force_auto_tune=False, force_auto_tune_off=False))

  def test_steer_ratio_does_not_require_a_torque_car(self):
    # The steering ratio is learned for every car, not just torque ones.
    self.assertTrue(resolve_use_custom(16.8, 15.0, is_torque_car=False,
                                        force_auto_tune=False, force_auto_tune_off=False,
                                        require_torque_car=False))


class TestResolveVehicleModelParams(unittest.TestCase):
  def test_learned_values_by_default(self):
    state = LateralArbitrationState()
    sr, stiffness = resolve_vehicle_model_params(16.5, 1.2, state)
    self.assertAlmostEqual(sr, 16.5)
    self.assertAlmostEqual(stiffness, 1.2)

  def test_user_ratio_wins_when_edited(self):
    state = LateralArbitrationState(use_custom_steer_ratio=True, user_steer_ratio=15.5)
    sr, stiffness = resolve_vehicle_model_params(16.5, 1.2, state)
    self.assertAlmostEqual(sr, 15.5)
    # The stiffness always comes from the learner.
    self.assertAlmostEqual(stiffness, 1.2)

  def test_force_auto_tune_off_pins_stiffness_to_one(self):
    state = LateralArbitrationState(force_auto_tune_off=True, user_steer_ratio=15.5)
    sr, stiffness = resolve_vehicle_model_params(16.5, 1.2, state)
    self.assertAlmostEqual(sr, 15.5)
    self.assertAlmostEqual(stiffness, 1.0)

  def test_user_ratio_is_not_rescaled(self):
    # The caller applies the live ratio rate to the learned value only. A
    # user-set ratio is absolute, so it must come back untouched.
    state = LateralArbitrationState(use_custom_steer_ratio=True, user_steer_ratio=16.8)
    sr, _ = resolve_vehicle_model_params(16.5, 1.2, state)
    self.assertAlmostEqual(sr, 16.8)


class TestResolveTorqueControlParams(unittest.TestCase):
  STOCK = (1.5, 0.1, 0.3)
  LEARNED = (1.8, 0.15, 0.45)

  def test_learned_values_when_live_and_not_edited(self):
    state = LateralArbitrationState()
    result = resolve_torque_control_params(*self.STOCK, *self.LEARNED, state, use_live_params=True)
    self.assertAlmostEqual(result[0], 1.8)
    self.assertAlmostEqual(result[1], 0.15)
    self.assertAlmostEqual(result[2], 0.45)

  def test_stock_values_when_live_params_unavailable(self):
    state = LateralArbitrationState()
    result = resolve_torque_control_params(*self.STOCK, *self.LEARNED, state, use_live_params=False)
    self.assertAlmostEqual(result[0], 1.5)
    self.assertAlmostEqual(result[1], 0.1)
    self.assertAlmostEqual(result[2], 0.3)

  def test_user_friction_wins_when_edited(self):
    state = LateralArbitrationState(use_custom_friction=True, user_friction=0.25)
    result = resolve_torque_control_params(*self.STOCK, *self.LEARNED, state, use_live_params=True)
    self.assertAlmostEqual(result[2], 0.25)
    # The other two still follow the learner.
    self.assertAlmostEqual(result[0], 1.8)

  def test_user_lat_accel_wins_when_edited(self):
    state = LateralArbitrationState(use_custom_lat_accel_factor=True, user_lat_accel_factor=1.2)
    result = resolve_torque_control_params(*self.STOCK, *self.LEARNED, state, use_live_params=True)
    self.assertAlmostEqual(result[0], 1.2)
    # The offset is tied to the factor: when the user takes over the factor the
    # offset reverts to the factory value with it, because the learned offset
    # was measured against the learned factor.
    self.assertAlmostEqual(result[1], 0.1)

  def test_user_value_applies_even_without_live_params(self):
    # A user-set friction is an explicit instruction; it must survive even
    # when the learner is not running.
    state = LateralArbitrationState(use_custom_friction=True, user_friction=0.25)
    result = resolve_torque_control_params(*self.STOCK, *self.LEARNED, state, use_live_params=False)
    self.assertAlmostEqual(result[2], 0.25)


if __name__ == "__main__":
  unittest.main()
