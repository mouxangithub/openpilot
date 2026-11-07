from __future__ import annotations
"""StopProfileGenerator: closed-form delayed, jerk-limited stop envelope.

Ported from sunnypilot's selfdrive/traffic_control/stop_profile.py (MIT
License, Copyright (c) 2021-, Haibin Wen, sunnypilot, and contributors) so the
CarrotPlanner traffic-light stop point can be enveloped with a smooth braking
profile (CarrotTrafficStopProfileEnabled). Pure numpy/math, no openpilot
imports, unit-testable without a compiled capnp runtime.
"""

import math

import numpy as np


class StopProfileGenerator:
  def __init__(self, comfort_brake: float = 2.4, jerk_limit: float = 0.8,
               release_jerk_limit: float = 0.5, actuator_delay: float = 0.2,
               planner_dt: float = 0.05) -> None:
    self.comfort_brake = comfort_brake
    self.jerk_limit = jerk_limit
    self.release_jerk_limit = release_jerk_limit
    self.actuator_delay = actuator_delay
    self.planner_dt = planner_dt
    self.previous_accel: float | None = None

  def reset(self) -> None:
    self.previous_accel = None

  @staticmethod
  def required_stop_distance(*, v_ego: float, a_ego: float,
                             actuator_delay: float, max_brake: float,
                             jerk_limit: float, dt: float = 0.05) -> float:
    """Closed-form delayed, jerk-limited stop envelope."""
    del dt  # Kept for call-site compatibility with older tests/tools.
    velocity = float(v_ego)
    acceleration = float(a_ego)
    delay = float(actuator_delay)
    brake = float(max_brake)
    jerk = float(jerk_limit)
    if not all(math.isfinite(value) for value in (velocity, acceleration, delay, brake, jerk)):
      return math.inf

    velocity = max(velocity, 0.0)
    brake = max(brake, 0.1)
    jerk = max(jerk, 0.1)
    # Do not assume that a positive measured acceleration is bounded by the
    # available braking magnitude. Retain it so the predicted stopping
    # distance cannot be understated; only cap already-strong braking at -B.
    acceleration = max(acceleration, -brake)
    delay = max(delay, 0.0)
    if velocity <= 0.0:
      return 0.0

    # The vehicle may stop during the actuator-delay interval when it is
    # already decelerating strongly.
    delay_time = min(delay, velocity / -acceleration) if acceleration < 0.0 else delay
    distance = max(0.0, velocity * delay_time + 0.5 * acceleration * delay_time ** 2)
    velocity = max(0.0, velocity + acceleration * delay_time)
    if velocity <= 0.0:
      return distance

    # Ramp acceleration from a0 to -brake with constant negative jerk. If the
    # velocity reaches zero first, use that positive root instead.
    ramp_to_brake = max(0.0, (acceleration + brake) / jerk)
    stop_in_ramp = (acceleration + math.sqrt(acceleration ** 2 + 2.0 * jerk * velocity)) / jerk
    ramp_time = min(ramp_to_brake, stop_in_ramp)
    distance += max(0.0, (
      velocity * ramp_time
      + 0.5 * acceleration * ramp_time ** 2
      - jerk * ramp_time ** 3 / 6.0
    ))
    velocity = max(0.0, velocity + acceleration * ramp_time - 0.5 * jerk * ramp_time ** 2)

    # Any remaining velocity is removed at constant maximum braking.
    return distance + velocity ** 2 / (2.0 * brake)

  @staticmethod
  def _dt(times: np.ndarray, index: int) -> float:
    return max(float(times[index] - times[index - 1]), 1e-3)

  def _next_cycle_accel(self, times: np.ndarray, accels: np.ndarray) -> float:
    return float(np.interp(self.planner_dt, times, accels))

  def build_stop(self, *, v_ego: float, a_ego: float, remaining_distance: float,
                 times: np.ndarray, hold: bool = False,
                 comfort_brake: float | None = None, jerk_limit: float | None = None,
                 decel_margin: float = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    speeds = np.zeros(len(times), dtype=float)
    accels = np.zeros(len(times), dtype=float)
    jerks = np.zeros(max(len(times) - 1, 0), dtype=float)
    if len(times) == 0:
      return speeds, accels, jerks

    speeds[0] = max(0.0, v_ego)
    if v_ego <= 0.01:
      self.previous_accel = 0.0
      return speeds, accels, jerks

    stop_brake = self.comfort_brake if comfort_brake is None else max(float(comfort_brake), 0.1)
    stop_jerk = self.jerk_limit if jerk_limit is None else max(float(jerk_limit), 0.1)
    stop_margin = max(float(decel_margin), 1.0)
    current_a = float(np.clip(a_ego if self.previous_accel is None else self.previous_accel,
                              -stop_brake, 0.0))
    accels[0] = current_a
    remaining = 0.0 if hold else max(remaining_distance, 0.0)
    for i in range(1, len(times)):
      dt = self._dt(times, i)
      effective_distance = max(remaining - speeds[i - 1] * self.actuator_delay, 0.5)
      target_a = -stop_margin * speeds[i - 1] ** 2 / (2.0 * effective_distance)
      target_a = float(np.clip(target_a, -stop_brake, 0.0))
      delta_a = float(np.clip(target_a - current_a, -stop_jerk * dt, stop_jerk * dt))
      current_a += delta_a
      next_v = max(0.0, speeds[i - 1] + current_a * dt)
      travelled = max(0.0, (speeds[i - 1] + next_v) * 0.5 * dt)
      remaining = max(0.0, remaining - travelled)
      speeds[i] = next_v
      accels[i] = current_a if next_v > 0.0 else 0.0
      jerks[i - 1] = delta_a / dt

    self.previous_accel = self._next_cycle_accel(times, accels)
    return speeds, accels, jerks

  def build_release(self, *, v_ego: float, base_accel: float,
                    times: np.ndarray, preserve_positive_accel: bool = False,
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    speeds = np.zeros(len(times), dtype=float)
    accels = np.zeros(len(times), dtype=float)
    jerks = np.zeros(max(len(times) - 1, 0), dtype=float)
    if len(times) == 0:
      return speeds, accels, jerks

    speeds[0] = max(0.0, v_ego)
    current_a = self.previous_accel or 0.0
    if not preserve_positive_accel:
      current_a = min(0.0, current_a)
    accels[0] = current_a
    for i in range(1, len(times)):
      dt = self._dt(times, i)
      target_a = max(current_a, base_accel)
      delta_a = float(np.clip(target_a - current_a,
                              -self.release_jerk_limit * dt, self.release_jerk_limit * dt))
      current_a += delta_a
      speeds[i] = max(0.0, speeds[i - 1] + current_a * dt)
      accels[i] = current_a
      jerks[i - 1] = delta_a / dt
    self.previous_accel = self._next_cycle_accel(times, accels)
    return speeds, accels, jerks
