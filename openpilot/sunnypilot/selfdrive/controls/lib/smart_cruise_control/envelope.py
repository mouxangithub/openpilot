"""
Copyright (c) 2021-, Haibin Wen, sunnypilot and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""Distance-envelope control half for the vision curve-speed controller.

Ported from StarPilot ``curve_speed_controller.py::update_target`` /
``_correct_far_field`` and ``starpilot_utilities.py::extract_curve_profile``.

Where the stock path condenses the model's predicted plan into a single 97th
percentile curvature, this walks every plan point: each point yields a curve
speed ``sqrt(lat_accel / k)`` and an approach speed
``sqrt(v_point^2 + 2 * decel * distance)``; the binding (minimum) approach
speed is the raw target. The model's known under-read of distant curvature is
compensated by the far-field gain, and the target is rate-limited both ways so
it can never step.

Pure numpy over primitives; the lateral-acceleration ceiling is injected as a
callable so the caller keeps ownership of learning/weather/factor scaling.
"""

import numpy as np

from openpilot.common.constants import CV

# plan extraction (StarPilot extract_curve_profile)
PROFILE_MIN_SPEED = 3.0          # m/s; below this the model's curvature is noise
PROFILE_MAX_CURVATURE = 0.1      # 1/m; sane ceiling on plan curvature

# envelope constants (StarPilot CSC_*)
CSC_MIN_SPEED = 25.0 * CV.MPH_TO_MS        # floor on curve point speeds
CSC_MAX_LATERAL_ACCEL = 4.0                # hard ceiling, 1/m scaling
CSC_APPROACH_DECEL = 0.3                   # m/s^2 assumed available on approach
CSC_TARGET_UP_RATE = 3.0                   # m/s per s while releasing
CSC_TARGET_DOWN_RATE = 2.5                 # m/s per s while tightening
CSC_EGO_HEADROOM = 2.0                     # seed never below v_ego + this
CSC_FARFIELD_MIN_CURVATURE = 0.004         # 1/m; "firm" reading threshold
CSC_FARFIELD_MIN_DISTANCE = 30.0           # m; only correct far-enough points
CSC_FARFIELD_GAIN = 1.23                   # undo the model's distance under-read


def extract_curve_profile(model_v2) -> tuple[np.ndarray, np.ndarray]:
  """Per-point curvature (1/m) and distance (m) along the predicted plan."""
  try:
    orientation_rate = np.abs(np.asarray(model_v2.orientationRate.z, dtype=float))
    velocity = np.asarray(model_v2.velocity.x, dtype=float)
    distances = np.asarray(model_v2.position.x, dtype=float)
  except (AttributeError, TypeError, ValueError):
    return np.array([]), np.array([])

  if not (len(orientation_rate) == len(velocity) == len(distances)):
    return np.array([]), np.array([])
  if not (np.all(np.isfinite(orientation_rate)) and
          np.all(np.isfinite(velocity)) and
          np.all(np.isfinite(distances))):
    return np.array([]), np.array([])

  curvatures = orientation_rate / np.clip(velocity, PROFILE_MIN_SPEED, None)
  curvatures = np.where(velocity < PROFILE_MIN_SPEED, 0.0, np.minimum(curvatures, PROFILE_MAX_CURVATURE))
  return curvatures, distances


def correct_far_field(curvatures: np.ndarray, distances: np.ndarray) -> np.ndarray:
  """Undo the model's known under-read of distant curvature, where firm."""
  firm = (curvatures >= CSC_FARFIELD_MIN_CURVATURE) & (distances >= CSC_FARFIELD_MIN_DISTANCE)
  return np.minimum(np.where(firm, curvatures * CSC_FARFIELD_GAIN, curvatures), PROFILE_MAX_CURVATURE)


class EnvelopeController:
  """Rate-limited curve-speed target from the per-point distance envelope."""

  def __init__(self, dt: float):
    self._dt = float(dt)
    self._target: float | None = None
    self._seed_pending = True
    self.binding_distance = 0.0

  def reset(self) -> None:
    self._target = None
    self._seed_pending = True
    self.binding_distance = 0.0

  def compute(self, v_ego: float, v_cruise: float,
              curvatures: np.ndarray, distances: np.ndarray,
              lat_accel_fn) -> float | None:
    """Raw envelope target for this frame, or None when the plan is empty.

    ``lat_accel_fn`` maps a curvature (1/m) to the lateral-acceleration
    ceiling in m/s^2 (learning + factor scale + weather applied by caller).
    """
    if len(curvatures) == 0:
      self.binding_distance = 0.0
      return None

    ks = correct_far_field(np.abs(np.asarray(curvatures, dtype=float)), np.asarray(distances, dtype=float))
    lat_accel = np.array([float(lat_accel_fn(float(k))) for k in ks])
    curvature_floor = np.maximum(ks, 1e-4)
    point_speeds = np.sqrt(lat_accel / curvature_floor)
    point_speeds = np.minimum(
      np.maximum(point_speeds, CSC_MIN_SPEED),
      np.sqrt(CSC_MAX_LATERAL_ACCEL / curvature_floor),
    )
    allowed_speeds = np.sqrt(point_speeds ** 2 + 2.0 * CSC_APPROACH_DECEL * np.maximum(distances, 0.0))
    binding_index = int(np.argmin(allowed_speeds))
    raw_target = min(float(allowed_speeds[binding_index]), float(v_cruise))
    self.binding_distance = float(distances[binding_index]) if raw_target < v_cruise else 0.0

    if self._seed_pending or self._target is None:
      # Seed with something the car can already do, so the first frames of a
      # fresh engagement do not demand an instant brake.
      self._target = min(float(v_cruise), max(raw_target, v_ego + CSC_EGO_HEADROOM))
      self._seed_pending = False

    self._target = float(np.clip(raw_target,
                                 self._target - CSC_TARGET_DOWN_RATE * self._dt,
                                 self._target + CSC_TARGET_UP_RATE * self._dt))
    return self._target
