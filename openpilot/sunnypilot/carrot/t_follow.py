"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Following-time ramp helpers for the carrot driving-mode system.

Ported from CarrotPilot. These helpers convert a configured following-time gap
into a mode-scaled, rate-limited target that the planner exposes to the
longitudinal MPC via ``CarrotPlanner.get_T_FOLLOW``.
"""

T_FOLLOW_RISE_RATE = 0.30  # seconds of time gap per second
T_FOLLOW_DECEL_RISE_RATE = 0.60
T_FOLLOW_DECEL_EXTRA_THRESHOLD = 0.02


def get_t_follow_mode_factor(accel_comfort_factor: float) -> float:
  """Invert a comfort-mode reduction into the intended following-time increase."""
  return float(2.0 - accel_comfort_factor)


def get_t_follow_mode_max(configured_max: float, mode_factor: float, decel_extra: float) -> float:
  """Let a comfort mode increase the configured gap while preserving the global cap."""
  return float(min(2.0, configured_max * max(1.0, mode_factor) + max(0.0, decel_extra)))


def get_speed_t_follow_factor(setting: int, speed_kph: float) -> float:
  """10 means unchanged; 20 means twice the selected TF at 100 km/h."""
  factor_at_100 = min(30, max(10, setting)) * 0.1
  return 1.0 + (factor_at_100 - 1.0) * max(0.0, speed_kph) / 100.0


def get_lead_response_for_gap(common: int, overrides, gap_index: int) -> int:
  """Per-gap override of the lead acceleration response, falling back to ``common``.

  ``overrides[index] < 0`` means "not set here, use ``common``". ``gap_index`` is the
  driver's selected following gap; it may be a capnp enum reader, hence the ``.raw``.
  An index outside the table falls back to ``common`` rather than raising - this runs in
  the planner's hot path, where an IndexError would take the planner down.
  """
  gap_index = int(getattr(gap_index, 'raw', gap_index))
  if not 0 <= gap_index < len(overrides):
    return int(min(5, max(0, common)))
  value = overrides[gap_index]
  return int(min(5, max(0, common if value < 0 else value)))


MODE_T_FOLLOW_RELEASE_RATE = 0.05  # mode multiplier per second (Safe -> Normal in 4 s)


def ramp_mode_t_follow_factor(target: float, current: float, dt: float) -> float:
  """Release only the mode margin slowly; explicit driver gap changes still apply.

  Without this the gap snaps back the instant the driving mode clears (Safe -> Normal
  is a 1.3x -> 1.0x step on the following time), which the driver feels as the car
  suddenly closing up. Increases are applied immediately - only the release is ramped.
  """
  return float(max(target, current - MODE_T_FOLLOW_RELEASE_RATE * dt))


def ramp_t_follow(target: float, current: float, decel_extra: float, dt: float) -> float:
  """Apply increases progressively while keeping gap reductions immediate."""
  if target <= current:
    return float(target)

  rise_rate = T_FOLLOW_DECEL_RISE_RATE if decel_extra > T_FOLLOW_DECEL_EXTRA_THRESHOLD else T_FOLLOW_RISE_RATE
  return float(min(target, current + rise_rate * dt))
