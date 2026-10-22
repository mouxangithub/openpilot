#!/usr/bin/env python3
"""Stopping-release hysteresis and negative-target creep guard (StarPilot port).

- StopReleaseTracker: sustained planner release requests (0.35 s hysteresis)
  allow LongControl to leave the stopping state even when a stock ACC
  platform keeps cruiseState.standstill latched until positive drive torque.
- Creep guards: when the planner has crossed into real decel, bleed stale
  positive integrator charge and cap positive output so the command can cross
  back through zero instead of carrying throttle. Low-speed creep scenes
  (tiny decel targets near standstill) are explicitly exempted.

Pure logic only -- no Params, no swaglog, safe to import on a PC host.
"""
import numpy as np

# StarPilot verbatim constants
STOPPING_RELEASE_HYSTERESIS = 0.35  # s of sustained release request
STOPPING_RELEASE_MIN_ACCEL = 0.15
STOPPING_RELEASE_STRONG_ACCEL = 0.45
NEGATIVE_TARGET_CREEP_GUARD_SPEED = 0.35
NEGATIVE_TARGET_CREEP_GUARD_DECEL = 0.40

# Upstream V_EGO_STARTING default; this fork has no toggle system.
V_EGO_STARTING = 0.5

# Control-loop period. Kept local (same value as common.realtime.DT_CTRL) so
# the module stays free of the realtime->utils->zstandard chain on PC hosts.
DT_CTRL = 0.01


class StopReleaseTracker:
  """Sustained-release counter deciding allow_stopping_release.

  Mirrors StarPilot's _stop_release_ready with the vehicle/toggle hooks
  parameterized out (no Corolla stopped-lead hold, fixed V_EGO_STARTING).
  """

  def __init__(self, dt_ctrl=DT_CTRL):
    self.stop_release_counter = 0
    self.max_frames = int(round(STOPPING_RELEASE_HYSTERESIS / dt_ctrl))

  def ready(self, is_stopping, v_ego, a_target, should_stop, brake_pressed,
            cruise_standstill, has_lead=False) -> bool:
    if not is_stopping:
      self.stop_release_counter = 0
      return True

    if should_stop or brake_pressed:
      self.stop_release_counter = 0
      return False

    if v_ego > V_EGO_STARTING:
      self.stop_release_counter = self.max_frames
      return True

    if has_lead and a_target > STOPPING_RELEASE_MIN_ACCEL:
      self.stop_release_counter = self.max_frames
      return True

    if a_target >= STOPPING_RELEASE_STRONG_ACCEL and not cruise_standstill:
      self.stop_release_counter = self.max_frames
      return True

    if a_target > STOPPING_RELEASE_MIN_ACCEL:
      self.stop_release_counter = min(self.stop_release_counter + 1, self.max_frames)
    else:
      self.stop_release_counter = 0

    return self.stop_release_counter >= self.max_frames


def trim_positive_overshoot_integrator(pid_i, a_target, error, v_ego):
  """Bleed stale positive integrator once the planner asks for real decel."""
  if pid_i <= 0.0:
    return pid_i
  if a_target >= -0.05 or error >= -0.25:
    return pid_i
  if v_ego <= NEGATIVE_TARGET_CREEP_GUARD_SPEED and a_target > -NEGATIVE_TARGET_CREEP_GUARD_DECEL:
    return pid_i

  bleed = float(np.interp(abs(error), [0.25, 0.75, 1.5], [0.55, 0.25, 0.0]))
  return pid_i * bleed


def cap_positive_output_on_negative_target(output_accel, a_target, error, v_ego):
  """Don't keep feeding positive drive torque when the planner asks for decel."""
  if output_accel <= 0.0:
    return output_accel
  if a_target >= -0.10 or error >= -0.35:
    return output_accel
  if v_ego <= NEGATIVE_TARGET_CREEP_GUARD_SPEED and a_target > -NEGATIVE_TARGET_CREEP_GUARD_DECEL:
    return output_accel

  positive_cap = float(np.interp(a_target, [-1.5, -0.6, -0.1], [0.0, 0.0, 0.05]))
  return min(output_accel, positive_cap)
