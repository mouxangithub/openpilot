"""Reads the arbitration state for the lateral parameter learners from Params.

StarPilot keeps this in a ~1700-line `starpilot_variables` aggregator. Only the
slice the arbitration actually needs is reproduced here, so the module stays
small enough to audit.

The tricky part is the steering ratio. StarPilot's `SteerRatio` parameter
holds the ratio directly (~16.8). This fork's `SteerRatio` is also a plain
float, but the knob the UI exposes is `CustomSR`, an integer that is scaled by
0.1 inside `resolve_vehicle_model_steer_ratio`. Two different conventions for
the same concept, so the stock-value comparison below is done against the
*scaled* custom value, and the user ratio is taken from whichever knob the
user actually moved.
"""
import math

from openpilot.sunnypilot.common.lateral_arbitration import (
  LateralArbitrationState,
  resolve_use_custom,
)
from openpilot.sunnypilot.common.param_read import read_bool
from openpilot.sunnypilot.common.param_read import read_float

# The Params type is only needed for the annotation, and importing it would
# pull the swaglog -> zmq chain onto every PC host that wants to unit test
# this module. The functions below therefore take an untyped `params`.

# The UI's CustomSR knob is an integer scaled by 0.1 (see
# resolve_vehicle_model_steer_ratio). 168 therefore means 16.8.
CUSTOM_SR_SCALE = 0.1

# CustomSR values at or below this are treated as "not set". The scaling
# means CustomSR=10 -> 1.0, which resolve_vehicle_model_steer_ratio itself
# rejects (it requires > 1.0), so the two thresholds agree.
CUSTOM_SR_MIN_VALID = 1.0


def _read_float(params, key: str, default: float) -> float:
  return read_float(params, key, default)


def _read_bool(params, key: str) -> bool:
  return read_bool(params, key)


def read_lateral_arbitration_state(params, *, stock_steer_ratio: float,
                                   stock_friction: float, stock_lat_accel_factor: float,
                                   is_torque_car: bool) -> LateralArbitrationState:
  """Build the arbitration state from Params plus the factory values.

  `stock_*` come from CarParams and represent what the car ships with; they
  are what the "did the user edit it?" comparison is made against.
  """
  force_auto_tune = _read_bool(params, "ForceAutoTune")
  force_auto_tune_off = _read_bool(params, "ForceAutoTuneOff")

  # CustomSR is an integer knob scaled by 0.1; SteerRatio is a plain float.
  # Whichever one the user moved wins, so that a device configured through
  # either UI is honoured. When both are set, CustomSR takes precedence
  # because it is the knob this fork's UI actually exposes.
  custom_sr_raw = _read_float(params, "CustomSR", 0.0)
  custom_sr = custom_sr_raw * CUSTOM_SR_SCALE
  steer_ratio_param = _read_float(params, "SteerRatio", 0.0)

  custom_sr_set = math.isfinite(custom_sr) and custom_sr > CUSTOM_SR_MIN_VALID
  steer_ratio_param_set = steer_ratio_param > 0.0

  if custom_sr_set:
    user_steer_ratio = custom_sr
    steer_ratio_is_user_set = True
  elif steer_ratio_param_set:
    user_steer_ratio = steer_ratio_param
    steer_ratio_is_user_set = True
  else:
    user_steer_ratio = float(stock_steer_ratio)
    steer_ratio_is_user_set = False

  # The knobs below all default to 0.0, which is the "not set" marker rather
  # than a value the user chose: a zero friction or a zero lateral-accel
  # factor is not a physically meaningful setting.
  #
  # The effective user value falls back to the factory value when the knob is
  # untouched, and the "did the user edit it?" test is only meaningful for a
  # knob that carries a number. ForceAutoTuneOff is the exception: it locks
  # the parameter to the factory value explicitly, so it applies either way.
  friction_raw = _read_float(params, "SteerFriction", 0.0)
  lat_accel_factor_raw = _read_float(params, "SteerLatAccel", 0.0)

  friction_set = friction_raw > 0.0
  lat_accel_factor_set = lat_accel_factor_raw > 0.0

  friction = friction_raw if friction_set else float(stock_friction)
  lat_accel_factor = lat_accel_factor_raw if lat_accel_factor_set else float(stock_lat_accel_factor)

  # The steering ratio is judged by whether the user moved the knob at all,
  # not by comparing against the factory value: a user who deliberately sets
  # the ratio to the factory number has still expressed an intent, and
  # comparing the two would silently hand control back to the learner.
  # ForceAutoTune still suppresses it - that switch exists precisely to
  # hand the parameter back to the learner - while ForceAutoTuneOff locks it
  # to the factory ratio even when no knob was touched.
  use_custom_steer_ratio = (steer_ratio_is_user_set or force_auto_tune_off) and not force_auto_tune

  use_custom_lat_accel_factor = (lat_accel_factor_set or force_auto_tune_off) and resolve_use_custom(
    lat_accel_factor, stock_lat_accel_factor,
    is_torque_car=is_torque_car, force_auto_tune=force_auto_tune,
    force_auto_tune_off=force_auto_tune_off)

  use_custom_friction = (friction_set or force_auto_tune_off) and resolve_use_custom(
    friction, stock_friction,
    is_torque_car=is_torque_car, force_auto_tune=force_auto_tune,
    force_auto_tune_off=force_auto_tune_off)

  return LateralArbitrationState(
    force_auto_tune=force_auto_tune,
    force_auto_tune_off=force_auto_tune_off,
    use_custom_steer_ratio=use_custom_steer_ratio,
    use_custom_steer_actuator_delay=not _read_bool(params, "UseAutoSteerDelay"),
    use_custom_lat_accel_factor=use_custom_lat_accel_factor,
    use_custom_friction=use_custom_friction,
    steer_ratio_is_user_set=steer_ratio_is_user_set,
    user_steer_ratio=user_steer_ratio,
    user_lat_accel_factor=lat_accel_factor,
    user_friction=friction,
  )
