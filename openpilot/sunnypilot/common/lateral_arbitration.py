"""Arbitration between learned vehicle parameters and user-set values.

StarPilot's paramsd/torqued learn a steering ratio, a stiffness factor, a
lateral-acceleration factor and a friction coefficient online. The learning
only wins when the user has not touched the corresponding knob; a user value
that differs from the factory value locks that parameter out of the learning
path. Two explicit overrides sit on top of that:

  * ForceAutoTune     - force the learned values, ignore user edits.
  * ForceAutoTuneOff  - force the user values, disable the learning entirely.

The interesting part is the "did the user touch it?" test. Comparing floats
exactly would make a 0.004 nudge count as an intentional override, so the
comparison rounds to two decimals - the same tolerance StarPilot uses.

This module is pure logic with no openpilot imports, so it can be unit tested
on a PC host. The caller supplies the values; nothing here reads Params.
"""
from dataclasses import dataclass

# Rounding used when comparing a user value against the factory value. Two
# decimals is deliberately coarse: a user dragging a slider produces values
# like 0.34800000000000003, and comparing those raw would always count as an
# edit and permanently disable the learning.
COMPARISON_DECIMALS = 2


@dataclass(frozen=True)
class LateralArbitrationState:
  """Resolved arbitration inputs for the lateral parameter learners.

  stock_* are the factory (CarParams) values; user_* are what the user has
  set. custom_* are the pre-computed "did the user edit this?" flags.
  """

  force_auto_tune: bool = False
  force_auto_tune_off: bool = False

  use_custom_steer_ratio: bool = False
  use_custom_steer_actuator_delay: bool = False
  use_custom_lat_accel_factor: bool = False
  use_custom_friction: bool = False

  # True when user_steer_ratio holds a ratio the user actually chose, as
  # opposed to the factory value that is only there as a fallback. A user
  # ratio is absolute and must not be scaled again by the live ratio rate.
  steer_ratio_is_user_set: bool = False

  user_steer_ratio: float = 0.0
  user_lat_accel_factor: float = 0.0
  user_friction: float = 0.0


def differs_from_stock(user_value: float, stock_value: float) -> bool:
  """True when the user value differs from the factory value.

  Rounded to two decimals so float noise from slider drags does not count as
  an edit. A non-finite user value never counts as an edit: an unset knob
  must not silently disable the learning.
  """
  try:
    user_value = float(user_value)
    stock_value = float(stock_value)
  except (TypeError, ValueError):
    return False

  if not (isfinite(user_value) and isfinite(stock_value)):
    return False

  return round(user_value, COMPARISON_DECIMALS) != round(stock_value, COMPARISON_DECIMALS)


def isfinite(value: float) -> bool:
  """Local isfinite so this module stays import-free."""
  try:
    value = float(value)
  except (TypeError, ValueError):
    return False
  return value == value and value not in (float("inf"), float("-inf"))


def resolve_use_custom(user_value: float, stock_value: float, *, is_torque_car: bool,
                       force_auto_tune: bool, force_auto_tune_off: bool,
                       require_torque_car: bool = True) -> bool:
  """Decide whether the user value wins over the learned one.

  Mirrors StarPilot's expression exactly, including its operator precedence:
  `A and B and not C or D` parses as `(A and B and (not C)) or D`. ForceAutoTuneOff
  therefore wins unconditionally, while ForceAutoTune suppresses the whole
  "user edited it" path even if the user did edit the value.

  Adding parentheses here would change the semantics, so they are deliberately
  absent - the boolean result is identical, but the intent is documented.
  """
  edited = differs_from_stock(user_value, stock_value)
  applicable = is_torque_car if require_torque_car else True
  return bool((edited and applicable and not force_auto_tune) or force_auto_tune_off)


def resolve_vehicle_model_params(learned_steer_ratio: float, learned_stiffness: float,
                                  state: LateralArbitrationState) -> tuple[float, float]:
  """Pick the steering ratio and stiffness factor the vehicle model should use.

  `learned_steer_ratio` must already carry whatever live scaling the caller
  applies; a user-set ratio bypasses that scaling entirely, because it is an
  absolute value the user typed in.

  ForceAutoTuneOff returns the user's ratio and pins the stiffness to 1.0:
  the stiffness is only meaningful alongside a learned ratio, and StarPilot
  treats it as untrustworthy the moment the user takes over the ratio.

  Otherwise the ratio is the user's when they edited it and the learned value
  when they did not; the stiffness always comes from the learner.
  """
  if state.force_auto_tune_off:
    return float(state.user_steer_ratio), 1.0

  if state.use_custom_steer_ratio:
    return float(state.user_steer_ratio), float(learned_stiffness)

  return float(learned_steer_ratio), float(learned_stiffness)


def resolve_torque_control_params(stock_lat_accel_factor: float, stock_lat_accel_offset: float,
                                  stock_friction: float, learned_lat_accel_factor: float,
                                  learned_lat_accel_offset: float, learned_friction: float,
                                  state: LateralArbitrationState, use_live_params: bool) -> tuple[float, float, float]:
  """Pick the lateral-acceleration factor, its offset and the friction coefficient.

  Two independent arbitrations run here, one per user-adjustable knob:

    * lat_accel_factor - user value wins when they edited it.
    * friction         - user value wins when they edited it.

  The offset has no user knob of its own, but it is still tied to the factor:
  when the user takes over the factor, the offset reverts to the factory
  value with it. That mirrors StarPilot exactly - the offset corrects a roll
  compensation bias that was measured against the learned factor, so mixing a
  user factor with a learned offset would be inconsistent.

  `use_live_params` is the caller's gate for whether the learned values are
  trustworthy at all (an unsupported car, or a failed learner run). When it is
  false the factory values are returned regardless of the arbitration state.
  """
  lat_accel_factor = float(stock_lat_accel_factor)
  lat_accel_offset = float(stock_lat_accel_offset)
  friction = float(stock_friction)

  if use_live_params:
    if not state.use_custom_lat_accel_factor:
      lat_accel_factor = float(learned_lat_accel_factor)
      lat_accel_offset = float(learned_lat_accel_offset)
    if not state.use_custom_friction:
      friction = float(learned_friction)

  if state.use_custom_lat_accel_factor:
    lat_accel_factor = float(state.user_lat_accel_factor)
  if state.use_custom_friction:
    friction = float(state.user_friction)

  return lat_accel_factor, lat_accel_offset, friction
