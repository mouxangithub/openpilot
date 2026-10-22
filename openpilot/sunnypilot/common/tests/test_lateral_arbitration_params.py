import unittest

from openpilot.sunnypilot.common.lateral_arbitration_params import read_lateral_arbitration_state

STOCK_STEER_RATIO = 16.8
STOCK_FRICTION = 0.3
STOCK_LAT_ACCEL = 1.5


class UnknownKeyName(Exception):
  """Mirrors openpilot.common.params.UnknownKeyName without importing it.

  Importing the real class would pull the swaglog -> hardware -> cereal chain
  onto the PC test host.
  """


class FakeParams:
  """A Params stand-in that mirrors the real method signatures exactly.

  The signatures matter: an earlier version of this test used a loose
  ``get_float(key, return_default=False)`` stand-in, which happily accepted
  a keyword the real ``Params.get_float`` rejects. The production code then
  shipped a call that raised TypeError on the device while the test stayed
  green. Signatures are therefore copied verbatim from common/params.py.
  """

  def __init__(self, values: dict, *, missing: tuple = ()):
    self.values = values
    self.missing = set(missing)

  def _check(self, key: str) -> None:
    if key in self.missing:
      raise UnknownKeyName(key)

  def get(self, key: str, block: bool = False, return_default: bool = False):
    self._check(key)
    if key in self.values:
      return self.values[key]
    return None

  def get_bool(self, key: str, block: bool = False) -> bool:
    self._check(key)
    return bool(self.values.get(key, False))

  def get_int(self, key: str, default: int = 0) -> int:
    self._check(key)
    try:
      return int(self.get(key))
    except (TypeError, ValueError):
      return default

  def get_float(self, key: str, default: float = 0.0) -> float:
    self._check(key)
    try:
      return float(self.get(key))
    except (TypeError, ValueError):
      return default

  def get_str(self, key: str, default: str = "") -> str:
    self._check(key)
    value = self.get(key)
    return default if value is None else str(value)


def make_params(values: dict, *, missing: tuple = ()) -> FakeParams:
  """A Params stand-in that returns the given values and False for bools."""
  return FakeParams(values, missing=missing)


class TestReadLateralArbitrationState(unittest.TestCase):
  def read(self, values: dict, is_torque_car: bool = True, missing: tuple = ()):
    return read_lateral_arbitration_state(
      make_params(values, missing=missing),
      stock_steer_ratio=STOCK_STEER_RATIO,
      stock_friction=STOCK_FRICTION,
      stock_lat_accel_factor=STOCK_LAT_ACCEL,
      is_torque_car=is_torque_car,
    )

  def test_defaults_keep_the_learning_path(self):
    state = self.read({})
    self.assertFalse(state.use_custom_steer_ratio)
    self.assertFalse(state.use_custom_friction)
    self.assertFalse(state.use_custom_lat_accel_factor)
    self.assertFalse(state.force_auto_tune)
    self.assertFalse(state.force_auto_tune_off)

  def test_custom_sr_is_scaled_by_one_tenth(self):
    # The UI knob is an integer: 168 means a 16.8 ratio.
    state = self.read({"CustomSR": 168})
    self.assertTrue(state.use_custom_steer_ratio)
    self.assertAlmostEqual(state.user_steer_ratio, 16.8)

  def test_custom_sr_below_the_threshold_is_ignored(self):
    # 10 -> 1.0 after scaling, which resolve_vehicle_model_steer_ratio also
    # rejects, so it must not count as a user choice.
    state = self.read({"CustomSR": 10})
    self.assertFalse(state.use_custom_steer_ratio)
    self.assertAlmostEqual(state.user_steer_ratio, STOCK_STEER_RATIO)

  def test_steer_ratio_param_is_absolute(self):
    state = self.read({"SteerRatio": 15.5})
    self.assertTrue(state.use_custom_steer_ratio)
    self.assertAlmostEqual(state.user_steer_ratio, 15.5)

  def test_custom_sr_wins_over_the_steer_ratio_param(self):
    state = self.read({"CustomSR": 168, "SteerRatio": 15.5})
    self.assertAlmostEqual(state.user_steer_ratio, 16.8)

  def test_friction_edit_locks_the_learned_value(self):
    state = self.read({"SteerFriction": 0.45})
    self.assertTrue(state.use_custom_friction)
    self.assertAlmostEqual(state.user_friction, 0.45)

  def test_friction_at_the_stock_value_keeps_the_learned_value(self):
    state = self.read({"SteerFriction": STOCK_FRICTION})
    self.assertFalse(state.use_custom_friction)

  def test_force_auto_tune_off_locks_everything(self):
    state = self.read({"ForceAutoTuneOff": True})
    self.assertTrue(state.use_custom_friction)
    self.assertTrue(state.use_custom_lat_accel_factor)
    self.assertTrue(state.use_custom_steer_ratio)

  def test_force_auto_tune_suppresses_user_edits(self):
    state = self.read({"ForceAutoTune": True, "SteerFriction": 0.45})
    self.assertFalse(state.use_custom_friction)

  def test_non_torque_car_cannot_lock_friction(self):
    state = self.read({"SteerFriction": 0.45}, is_torque_car=False)
    self.assertFalse(state.use_custom_friction)

  def test_steer_ratio_can_be_locked_on_a_non_torque_car(self):
    state = self.read({"CustomSR": 168}, is_torque_car=False)
    self.assertTrue(state.use_custom_steer_ratio)

  def test_auto_steer_delay_toggle_is_reported(self):
    state = self.read({"UseAutoSteerDelay": False})
    self.assertTrue(state.use_custom_steer_actuator_delay)
    state = self.read({"UseAutoSteerDelay": True})
    self.assertFalse(state.use_custom_steer_actuator_delay)


if __name__ == "__main__":
  unittest.main()
