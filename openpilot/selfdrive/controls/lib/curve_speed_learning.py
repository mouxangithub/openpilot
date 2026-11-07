#!/usr/bin/env python3
"""Curvature-speed self-learning (StarPilot curve_speed_controller port).

Learns a comfort lateral-acceleration curve over road curvature from the
driver's own manual driving, blended against a fixed prior:

- Samples |lateral acceleration| into log-spaced curvature buckets while the
  driver (not openpilot) owns speed, the car has settled into a curve, and
  there is no lead tracking or blinker.
- Each bucket averages with a capped effective count; the comfort curve is a
  Bayesian-style blend of the samples with the prior (confidence =
  count / (count + CSC_PRIOR_COUNT)), monotonised with a weighted isotonic
  fit so comfort never falls as curves tighten.
- Override watch: when the driver accelerates through a curve faster than
  the learned comfort, a weighted pseudo-sample raises the learned value.
  Braking in a curve nudges it down.

Pure logic only; persistence is injected via put/load hooks so this stays
importable and unit-testable on a PC host.
"""
import math

import numpy as np

# StarPilot verbatim constants
CSC_COUNT_CAP = 600
CSC_PRIOR_COUNT = 100
CSC_LAT_ACCEL_MIN = 1.2
CSC_LAT_ACCEL_MAX = 3.2
CSC_NUDGE = 0.15
CSC_NUDGE_WEIGHT = 20
CSC_OVERRIDE_WATCH_TIME = 6.0
CSC_TRAINING_SETTLE_TIME = 2.0
CSC_COMFORT_MARGIN = 1.0

CRUISING_SPEED = 5.0  # m/s, StarPilot starpilot_variables
DEFAULT_LATERAL_ACCELERATION = 2.0  # m/s^2, typical lateral accel in curves
# Persistence cadence while actively sampling: model horizon length (10 s).
PLANNER_TIME = 10.0

MIN_CURVATURE = 0.0005
MAX_CURVATURE = 0.02
CURVATURE_BUCKETS = 24
ROUNDING_PRECISION = 6
CURVATURE_GRID = MIN_CURVATURE * np.power(MAX_CURVATURE / MIN_CURVATURE,
                                          np.arange(CURVATURE_BUCKETS) / (CURVATURE_BUCKETS - 1))
CURVATURE_GRID = np.round(CURVATURE_GRID, ROUNDING_PRECISION)

PRIOR_CURVATURE_BP = [0.001, 0.003, 0.01, 0.03, 0.1]
PRIOR_LAT_ACCEL_V = [1.5, 1.8, 2.2, 2.6, 2.9]


def bucket_curvature(road_curvature: float) -> str:
  """Nearest log-grid bucket key for a road curvature (StarPilot verbatim)."""
  clipped_curvature = float(np.clip(abs(road_curvature), MIN_CURVATURE, MAX_CURVATURE))
  bucket_index = int(np.argmin(np.abs(np.log(CURVATURE_GRID) - np.log(clipped_curvature))))
  return str(round(float(CURVATURE_GRID[bucket_index]), ROUNDING_PRECISION))


def normalize_curvature_data(curvature_data) -> dict:
  """Merge arbitrary persisted data into valid bucket entries (verbatim)."""
  if not isinstance(curvature_data, dict):
    return {}

  normalized: dict[str, dict] = {}
  for key, value in curvature_data.items():
    if not isinstance(value, dict):
      continue

    try:
      raw_curvature = abs(float(key))
      average = float(value["average"])
      count = int(value["count"])
    except (KeyError, TypeError, ValueError):
      continue

    if count <= 0 or not math.isfinite(raw_curvature) or not math.isfinite(average):
      continue

    bucket = bucket_curvature(raw_curvature)
    if bucket in normalized:
      existing = normalized[bucket]
      total_count = existing["count"] + count
      normalized[bucket] = {
        "average": ((existing["average"] * existing["count"]) + (average * count)) / total_count,
        "count": total_count,
      }
    else:
      normalized[bucket] = {
        "average": average,
        "count": count,
      }

  return normalized


def weighted_isotonic(values, weights):
  """Weighted non-decreasing fit (pool adjacent violators).

  Keeps comfort from falling as curves tighten, without letting a sparse
  bucket overrule a well-sampled neighbour the way a running maximum would.
  """
  block_values: list[float] = []
  block_weights: list[float] = []
  block_sizes: list[int] = []

  for value, weight in zip(values, weights, strict=True):
    block_values.append(float(value))
    block_weights.append(float(weight))
    block_sizes.append(1)

    while len(block_values) > 1 and block_values[-2] > block_values[-1]:
      merged_weight = block_weights[-2] + block_weights[-1]
      merged_value = ((block_values[-2] * block_weights[-2]) + (block_values[-1] * block_weights[-1])) / merged_weight
      block_values.pop()
      block_weights.pop()
      merged_size = block_sizes.pop()
      block_values[-1] = merged_value
      block_weights[-1] = merged_weight
      block_sizes[-1] += merged_size

  fitted = np.empty(len(values))
  index = 0
  for value, size in zip(block_values, block_sizes, strict=True):
    fitted[index:index + size] = value
    index += size
  return fitted


class CurvatureLearning:
  def __init__(self, dt=0.05):
    self.dt = float(dt)
    self.curvature_data: dict[str, dict] = {}
    self.lateral_acceleration = DEFAULT_LATERAL_ACCELERATION
    self._curve_k = CURVATURE_GRID
    self._curve_a = np.full(len(CURVATURE_GRID), DEFAULT_LATERAL_ACCELERATION)

    self.training_quiet_timer = 0.0
    self.training_timer = 0.0
    self.persistence_timer = 0.0
    self.data_dirty = False
    self.enable_training = False
    self.nudge_applied = False
    self._long_active_prev = False
    self.override_watch_key = None
    self.override_watch_peak = 0.0
    self.override_watch_timer = 0.0

    self.rebuild()

    # persistence hooks (inject device Params access; none on PC hosts)
    self.load_fn = None    # callable() -> dict | None
    self.put_fn = None     # callable(dict) -> None

  # ---- persistence ----

  def load(self):
    if self.load_fn is None:
      return
    data = self.load_fn()
    if isinstance(data, dict) and data:
      normalized = normalize_curvature_data(data)
      if normalized:
        self.curvature_data = normalized
        self.rebuild()
        self.data_dirty = False

  def flush(self):
    if not self.data_dirty:
      return
    if self.put_fn is not None:
      # keys are already normalized bucket strings
      self.put_fn(dict(self.curvature_data))
    self.data_dirty = False
    self.persistence_timer = 0.0

  # ---- learning ----

  def log_data(self, v_ego, tracking_lead, manual_speed_control, driving_in_curve,
               blinker, lateral_acceleration, road_curvature):
    """Per-frame sampler. Mirrors StarPilot CurveSpeedController.log_data."""
    self.training_quiet_timer = max(self.training_quiet_timer - self.dt, 0.0)

    eligible = (
      v_ego > CRUISING_SPEED and
      not tracking_lead and
      manual_speed_control and
      self.training_quiet_timer <= 0.0
    )
    self.enable_training = False

    if not eligible:
      self.flush()
      self.training_timer = max(self.training_timer - self.dt, 0.0)
      self.persistence_timer = 0.0
      return

    self.training_timer += self.dt
    if self.data_dirty:
      self.persistence_timer += self.dt

    in_curve = (
      self.training_timer >= CSC_TRAINING_SETTLE_TIME and
      driving_in_curve and
      not blinker
    )
    if in_curve:
      lat_accel = abs(lateral_acceleration)
      key = bucket_curvature(abs(road_curvature))

      if key in self.curvature_data:
        data = self.curvature_data[key]
        effective_count = min(data["count"], CSC_COUNT_CAP)
        self.curvature_data[key] = {
          "average": ((data["average"] * effective_count) + lat_accel) / (effective_count + 1),
          "count": data["count"] + 1,
        }
      else:
        self.curvature_data[key] = {"average": lat_accel, "count": 1}

      self.data_dirty = True
      self.rebuild()
      self.enable_training = True

      if self.persistence_timer >= PLANNER_TIME:
        self.flush()
    elif self.data_dirty:
      self.flush()

  def handle_override_watch(self, overriding_or_in_curve, lateral_acceleration, road_curvature):
    """Track the driver's peak lateral accel while they push through a curve.

    overriding_or_in_curve: True while the override scene is still active
    (user override or still driving in curve), False once it has settled.
    """
    if self.override_watch_key is None:
      return

    lat_accel = abs(lateral_acceleration)
    if lat_accel > self.override_watch_peak:
      self.override_watch_peak = lat_accel
      self.override_watch_key = bucket_curvature(abs(road_curvature))

    self.override_watch_timer -= self.dt
    if self.override_watch_timer > 0.0 and overriding_or_in_curve:
      return

    key = self.override_watch_key
    self.override_watch_key = None
    if key is not None:
      self.record_pseudo_sample(key, max(self.override_watch_peak,
                                         self.learned_lat_accel(float(key)) + CSC_NUDGE))

  def start_override_watch(self, road_curvature, lateral_acceleration):
    self.override_watch_key = bucket_curvature(abs(road_curvature))
    self.override_watch_peak = abs(lateral_acceleration)
    self.override_watch_timer = CSC_OVERRIDE_WATCH_TIME

  def apply_brake_nudge(self, road_curvature):
    """Driver braked in a curve: lower the learned comfort by one nudge."""
    self.record_pseudo_sample(bucket_curvature(abs(road_curvature)),
                              self.learned_lat_accel(abs(road_curvature)) - CSC_NUDGE)

  def record_pseudo_sample(self, key, sample):
    sample = float(np.clip(sample, CSC_LAT_ACCEL_MIN, CSC_LAT_ACCEL_MAX))

    data = self.curvature_data.get(key, {"average": sample, "count": 0})
    effective_count = min(data["count"], CSC_COUNT_CAP)
    total = effective_count + CSC_NUDGE_WEIGHT
    self.curvature_data[key] = {
      "average": ((data["average"] * effective_count) + (sample * CSC_NUDGE_WEIGHT)) / total,
      "count": data["count"] + CSC_NUDGE_WEIGHT,
    }

    self.rebuild()
    self.data_dirty = True
    self.flush()

  def rebuild(self):
    grid_k = np.asarray(CURVATURE_GRID, dtype=np.float64)
    prior = np.interp(grid_k, PRIOR_CURVATURE_BP, PRIOR_LAT_ACCEL_V)

    blended = prior.copy()
    counts = np.zeros(len(grid_k))
    for i, key in enumerate(grid_k):
      bucket_key = str(round(float(key), ROUNDING_PRECISION))
      data = self.curvature_data.get(bucket_key)
      if data:
        confidence = data["count"] / (data["count"] + CSC_PRIOR_COUNT)
        blended[i] = confidence * data["average"] + (1.0 - confidence) * prior[i]
        counts[i] = data["count"]

    blended = np.clip(blended, CSC_LAT_ACCEL_MIN, CSC_LAT_ACCEL_MAX)
    blended = weighted_isotonic(blended, counts + CSC_PRIOR_COUNT)

    self._curve_k = grid_k
    self._curve_a = blended

    if counts.sum() > 0:
      self.lateral_acceleration = float(np.average(blended, weights=counts))
    else:
      self.lateral_acceleration = DEFAULT_LATERAL_ACCELERATION

  def learned_lat_accel(self, curvature) -> float:
    """Comfort level learned for this curvature, before any control margin."""
    return float(np.interp(abs(curvature), self._curve_k, self._curve_a))

  def lat_accel_for_curvature(self, curvature) -> float:
    """Comfort level with the control margin applied (weather hooks omitted:
    this fork has no StarPilot weather toggle system)."""
    return float(np.interp(np.abs(curvature), self._curve_k, self._curve_a)) * CSC_COMFORT_MARGIN
