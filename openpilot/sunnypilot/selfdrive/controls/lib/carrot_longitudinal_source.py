from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""
Carrot longitudinal control adapter.

Wraps :class:`CarrotPlanner` so it can be consumed by ``LongitudinalPlannerSP``
as a first-class ``LongitudinalPlanSource``. The adapter normalizes the
planner's outputs into ``(v_target, a_target, should_stop, stop_dist, active)``
and adds packet-freshness gating using the ``CarrotSourceTimeoutMs`` killswitch
so a stale/lost 7706/7714 stream cannot keep commanding a stop.

The module deliberately avoids importing cereal so it can be unit-tested
without a compiled capnp runtime; the caller (``LongitudinalPlannerSP``) already
imports custom.
"""

from typing import Any

from openpilot.sunnypilot.carrot.carrot_functions import CarrotPlanner, XState
from openpilot.sunnypilot.carrot.config import UnifiedParams

# Fallback used before the killswitch param is read (and if it is absent).
_CARROT_SOURCE_TIMEOUT_MS_DEFAULT = 2000


class CarrotLongitudinalSource:
  """Adapter exposing a normalized longitudinal interface over ``CarrotPlanner``."""

  def __init__(self, carrot: CarrotPlanner | None = None) -> None:
    self._params = UnifiedParams()
    self.carrot = carrot if carrot is not None else CarrotPlanner(self._params)
    self._timeout_ms = _CARROT_SOURCE_TIMEOUT_MS_DEFAULT
    self._active = False

  # -- freshness --------------------------------------------------------- #

  def _update_freshness(self, sm: Any) -> None:
    """Mark the source inactive if the carrot packet is missing or too old."""
    try:
      carrot_ts = sm.logMonoTime.get("carrotManSP", None)
      ref_ts = sm.logMonoTime.get("modelV2", None) or sm.logMonoTime.get("carState", None)
    except Exception:
      carrot_ts = ref_ts = None
    if carrot_ts is None or ref_ts is None:
      self._active = False
      return
    age_ns = ref_ts - carrot_ts
    # Negative age means the carrot sample is from a future cycle; treat as fresh.
    self._active = 0 <= age_ns <= self._timeout_ms * 1_000_000

  # -- update ------------------------------------------------------------ #

  def update(self, sm: Any, v_cruise_kph: float, mpc_mode: str) -> None:
    self._timeout_ms = self._params.get_int("CarrotSourceTimeoutMs", _CARROT_SOURCE_TIMEOUT_MS_DEFAULT)
    self.carrot.update(sm, v_cruise_kph, mpc_mode)
    self._update_freshness(sm)

  # -- interface --------------------------------------------------------- #

  @property
  def v_target(self) -> float:
    """Target speed in m/s (the planner's effective cruise speed)."""
    return float(self.carrot.v_cruise)

  @property
  def a_target(self) -> float:
    """Comfortable target acceleration in m/s^2 from the planner."""
    return float(self.carrot.comfort_a_target)

  @property
  def should_stop(self) -> bool:
    """True when the planner is commanding a stop (e2eStop / e2eStopped)."""
    return self.carrot.x_state in (XState.e2eStop, XState.e2eStopped)

  @property
  def stop_dist(self) -> float:
    """Remaining distance to the planned stop, in meters."""
    return float(self.carrot.stop_distance)

  @property
  def t_follow(self) -> float:
    """Dynamic following-time gap requested by the planner (s)."""
    return float(self.carrot.get_T_FOLLOW())

  @property
  def jerk_factor(self) -> float:
    """Comfort-scaled jerk multiplier for MPC cost weights."""
    return float(self.carrot.jerk_factor)

  @property
  def comfort_brake(self) -> float:
    """Comfort deceleration value for obstacle-distance computation."""
    return float(self.carrot.comfort_brake)

  @property
  def stop_dist(self) -> float:
    """Remaining distance to the planned stop, in meters."""
    return float(self.carrot.stop_distance)

  @property
  def stop_distance(self) -> float:
    """Remaining distance to the planned stop, in meters (alias of stop_dist)."""
    return float(self.carrot.stop_distance)

  @property
  def stop_distance_margin(self) -> float:
    """Configured stop-distance safety margin (m) for the MPC."""
    return float(self.carrot.stop_distance_margin)

  @property
  def traffic_stop_distance_adjust(self) -> float:
    """Configured signal-stop distance offset (m, negative = closer)."""
    return float(self.carrot.traffic_stop_distance_adjust)

  @property
  def traffic_stop_model_lead_offset(self) -> float:
    """Model-lead matched stop offset; 0 when no queued lead is detected."""
    return float(self.carrot.traffic_stop_model_lead_offset)

  @property
  def lane_change_active(self) -> bool:
    """True while an active lane-change maneuver is in progress."""
    return bool(self.carrot.lane_change_active)

  @property
  def lane_change_gap(self):
    """The latest :class:`LaneChangeGapPlan` produced by the tracker."""
    return self.carrot.lane_change_gap

  @property
  def dynamic_t_follow_lc(self) -> float:
    """Dynamic T-Follow ratio used to size the lane-change gap credit (0..1)."""
    return float(self.carrot.dynamic_t_follow_lc)

  @property
  def active(self) -> bool:
    """True only when the carrot packet is fresh AND the planner has a real
    (carrot-connected) output. Times out to False via ``CarrotSourceTimeoutMs``."""
    return self._active and self.carrot.active
