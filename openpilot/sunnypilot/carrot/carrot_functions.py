from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

"""
Carrot planner: long-control layer for the carrot (Korean TMAP) phone
projection + amap navigation stack.

Ported and adapted from CarrotPilot. The module exposes a single
``CarrotPlanner`` class which:

* drives a 6-state machine (``lead`` / ``cruise`` / ``e2eCruise`` /
  ``e2ePrepare`` / ``e2eStop`` / ``e2eStopped``) that decides whether to
  brake for a model-detected stop line, follow the radar lead, or just
  track the set speed;
* maps a 4-mode driving preset (``Eco`` / ``Normal`` / ``Sport`` / ``Safe``)
  to per-mode jerk and cruise-acceleration profiles, with an automatic
  mode detector that flips to ``Safe`` in stop-and-go traffic;
* computes an eco-cruise cap to keep the set speed from overshooting when
  the user is at the wheel of a long highway stretch;
* routes a "lowest target wins" arbitration between carrot, SCC and stock
  cruise so callers can consume ``(v_cruise, stop_dist, mode)`` from a
  single ``update()`` call.

The class is intentionally self-contained: it reads its tuning from
``UnifiedParams`` and never touches cereal state directly, which keeps the
unit tests honest.
"""

from collections import deque
from enum import Enum
from typing import Any

import numpy as np

from opendbc.car.common.conversions import Conversions as CV
from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot.carrot.config import UnifiedParams
from openpilot.sunnypilot.carrot.radar_motion.lane_change_gap import (
  LaneChangeGapPlan,
  LaneChangeGapTracker,
)
from openpilot.sunnypilot.carrot.t_follow import (
  get_t_follow_mode_factor,
  get_t_follow_mode_max,
  ramp_t_follow,
)
from openpilot.sunnypilot.carrot.traffic_stop import TrafficStopModelLeadMatcher


# Model leads in modelV2.leadsV3 are expressed in the radar frame; remove the
# forward offset so they line up with the radar lead's dRel (camera frame). Kept
# local so this module stays importable without the controls package / capnp.
RADAR_TO_CAMERA = 1.52  # RADAR is ~ 1.5 m ahead of the center of the mesh frame


# --------------------------------------------------------------------------- #
# Enumerations                                                                #
# --------------------------------------------------------------------------- #


class XState(Enum):
  """Longitudinal control state for the carrot planner."""
  lead = 0          # Following a radar lead.
  cruise = 1        # Plain cruise - no lead, no stop needed.
  e2eCruise = 2     # Cruising toward a stop line / signal.
  e2eStop = 3       # Braking to a model stop line / signal.
  e2ePrepare = 4    # Just rolled into a stop, holding it.
  e2eStopped = 5    # Stationary, waiting for green or gas pedal.

  def __str__(self) -> str:
    return self.name


class DrivingMode(Enum):
  """Driving style preset selected by the user.

  Values mirror CarrotPilot so phone-app settings and cross-fork defaults agree:
  Eco=1, Safe=2, Normal=3, High=4.
  """
  Eco = 1
  Safe = 2
  Normal = 3
  High = 4

  def __str__(self) -> str:
    return self.name


# Default factor table for the four modes. Eco/Safe reduce acceleration and
# increase following time; High increases acceleration and keeps a short gap.
_ECO_FACTOR = 0.9
_SAFE_FACTOR = 0.8
_HIGH_FACTOR = 1.2

# Comfort deceleration fallback, matching LongitudinalMpcTuningComfortBrake's own
# default. The live value is read from that param in _params_update so the Carrot
# source does not override the user's Longitudinal MPC Tuning entry.
_DEFAULT_COMFORT_BRAKE = 2.5


def get_driving_mode_factors(driving_mode: DrivingMode,
                             eco_factor: float = _ECO_FACTOR,
                             safe_factor: float = _SAFE_FACTOR) -> tuple[float, float]:
  """Return (accel_factor, t_follow_factor) for the selected drive mode."""
  if driving_mode == DrivingMode.Eco:
    return eco_factor, get_t_follow_mode_factor(eco_factor)
  if driving_mode == DrivingMode.Safe:
    return safe_factor, get_t_follow_mode_factor(safe_factor)
  if driving_mode == DrivingMode.High:
    return _HIGH_FACTOR, 1.0
  return 1.0, 1.0


def get_driving_mode_comfort_brake_factor(driving_mode: DrivingMode) -> float:
  """Give Safe mode a slightly earlier braking profile while keeping Eco efficient."""
  return 0.9 if driving_mode == DrivingMode.Safe else 1.0


class TrafficState(Enum):
  """Traffic light state from model + phone navi fusion."""
  off = 0
  red = 1
  green = 2
  left = 3   # left-turn green (carrot / amap only; vision cannot confirm it)

  def __str__(self) -> str:
    return self.name


# Traffic-light confirmation thresholds (frames @ ~20 Hz model ticks). Vision
# red/green must be sustained before CarrotPlanner trusts them so a single
# misdetected frame (oncoming green, shadow, billboard) cannot trigger a stop or
# a false start. These are intentionally NOT params: they are safety-critical and
# the killswitch params registered in params_keys.h stay off-by-default.
_TRAFFIC_RED_CONFIRM_FRAMES = 5
_TRAFFIC_GREEN_CONFIRM_FRAMES = 8

# Above this speed (km/h) a phone-navigation-only red light is no longer allowed
# to command a stop or slam the target speed down; only a vision-confirmed stop
# line may. This prevents high-speed false braking on a single nav source.
_HIGH_SPEED_KPH = 60.0
_HIGH_SPEED_FLOOR_RATIO = 0.9  # keep at least 90% of set speed from a nav-only red


# Cruise acceleration breakpoints (m/s) for the per-mode envelope.
_A_CRUISE_MAX_BP: tuple[float, ...] = (
  0.0,
  10 * CV.KPH_TO_MS,
  40 * CV.KPH_TO_MS,
  60 * CV.KPH_TO_MS,
  80 * CV.KPH_TO_MS,
  110 * CV.KPH_TO_MS,
  140 * CV.KPH_TO_MS,
)


# --------------------------------------------------------------------------- #
# Lightweight helpers                                                         #
# --------------------------------------------------------------------------- #


class _MovingAverage:
  """Plain fixed-size moving average (avoids depending on a missing helper)."""

  def __init__(self, window: int) -> None:
    self._window = max(1, int(window))
    self._buf: deque[float] = deque(maxlen=self._window)

  def process(self, value: float, median: bool = False) -> float:
    if not np.isfinite(value):
      value = 0.0
    if median:
      # Median filter ignores the FIFO constraint of deque, so re-implement.
      arr = np.fromiter(self._buf, dtype=float)
      if not arr.size:
        out = float(value)
      else:
        out = float(np.median(np.append(arr, value)))
      self._buf.append(value)
      return out
    self._buf.append(value)
    return float(np.mean(self._buf))


# --------------------------------------------------------------------------- #
# Automatic driving-mode detector                                              #
# --------------------------------------------------------------------------- #


class DrivingModeDetector:
  """Flip to ``Safe`` whenever we are stuck in stop-and-go traffic."""

  def __init__(self) -> None:
    self._congested = False
    self._speed_threshold = 2.0          # km/h
    self._accel_threshold = 1.5          # m/s^2
    self._distance_threshold = 12.0      # m
    self._lead_speed_exit_threshold = 35.0  # km/h

  def update_data(self, my_speed: float, lead_speed: float, my_accel: float,
                  lead_accel: float, distance: float) -> None:
    # 1. Congested: lead is stopped close in front of us.
    if distance <= self._distance_threshold and lead_speed <= self._speed_threshold:
      self._congested = True
    # 2. Free: lead is accelerating, we're moving, or the gap has stretched.
    if (lead_accel > self._accel_threshold
            or my_speed > self._lead_speed_exit_threshold
            or distance >= 200.0):
      self._congested = False

  def get_mode(self) -> DrivingMode:
    return DrivingMode.Safe if self._congested else DrivingMode.Normal


# Longitudinal personality values used by the openpilot longitudinal stack.
# We avoid importing ``log.LongitudinalPersonality`` at module load so unit
# tests can run without a compiled cereal runtime.
class _LongitudinalPersonality:
  moreRelaxed = 0
  relaxed = 1
  standard = 2
  aggressive = 3


# --------------------------------------------------------------------------- #
# CarrotPlanner                                                                #
# --------------------------------------------------------------------------- #


class CarrotPlanner:
  """Per-frame longitudinal planner that wraps the carrot tuning surface.

  The planner is fed a ``SubMaster`` snapshot each tick and returns the
  effective cruise speed and a "stop at" distance the caller can mix into
  a longitudinal plan source.
  """

  def __init__(self, params: UnifiedParams | None = None, roadcate: int = 8) -> None:
    self._params = params or UnifiedParams()
    self._frame: int = 0
    self._params_count: int = 0
    self._params_stale_after: int = 0  # forces a parameter refresh on first tick.

    # Driving mode.
    driving_mode_value = self._params.get_int("MyDrivingMode")
    if driving_mode_value not in {m.value for m in DrivingMode}:
      driving_mode_value = DrivingMode.Normal.value
    self._my_driving_mode = DrivingMode(driving_mode_value)
    self._my_driving_mode_last = self._my_driving_mode
    self._my_driving_mode_auto_disable = False
    self._my_driving_mode_auto = self._params.get_int("MyDrivingModeAuto")
    self._driving_mode_detector = DrivingModeDetector()
    self._my_safe_factor = 1.0
    self._my_eco_factor = _ECO_FACTOR
    self._my_safe_mode_factor = _SAFE_FACTOR
    self._my_high_mode_factor = _HIGH_FACTOR
    self._my_t_follow_factor = 1.0
    self._apply_driving_mode_factors()

    # Follow-distance breakpoints (seconds) - one per LongitudinalPersonality.
    self._t_follow_gap1 = 1.1
    self._t_follow_gap2 = 1.3
    self._t_follow_gap3 = 1.45
    self._t_follow_gap4 = 1.6
    self._dynamic_t_follow_lc = 0.0
    self._lead_accel_response = 0
    self._enable_speed_tf = 0
    self._t_follow_decel_boost = 0.0
    self._t_follow_decel_extra = 0.0
    self._t_follow_decel_base = 0.0
    self._tf_applied = 1.45
    self._t_follow_last = 1.45
    self._t_follow_base_last = 1.45

    # Cruise acceleration envelope per breakpoint.
    self._cruise_max_vals: list[float] = [1.6, 1.6, 1.2, 1.0, 0.8, 0.7, 0.6]

    # Stop / traffic handling.
    self._stop_distance = 6.0
    # Base comfort deceleration; scaled per-tick by the driving-mode factors below.
    self._comfort_brake_base = _DEFAULT_COMFORT_BRAKE
    self._comfort_brake = _DEFAULT_COMFORT_BRAKE
    self._comfort_brake_comfort_factor = 1.0
    self._traffic_light_detect_mode = 2
    self._traffic_state = TrafficState.off
    self._traffic_state_carrot = 0
    # Multi-frame confirmation counters (vision red/green must be sustained).
    self._stop_frames = 0
    self._start_frames = 0
    self._red_lost_frames = 0
    self._green_lost_frames = 0
    self._carrot_stay_stop = False
    self._x_stop_filter = _MovingAverage(3)
    self._x_stop_filter2 = _MovingAverage(15)
    self._v_filter = _MovingAverage(10)
    self._x_stop = 0.0
    self._actual_stop_distance = 0.0
    self._stopping_count = 0.0
    self._traffic_starting_count = 0.0
    self._user_stop_distance = -1.0
    self._start_sign_count = 0
    self._stop_sign_count = 0
    self._x_state = XState.cruise

    # E2E model-lead stop-point matcher: exposes a queued vehicle's approximate
    # position as the MPC obstacle when the E2E stop point sits ~2 m behind it.
    self._traffic_stop_model_lead_matcher = TrafficStopModelLeadMatcher()
    self.trafficStopModelLeadOffset = 0.0

    # Lane-change assist.
    self._desire_state = 0.0
    self._desire_state_count = 0
    self._jerk_factor = 1.0
    self._jerk_factor_apply = 1.0
    self._j_lead_factor = 0.0

    # Lane-change gap tracker (ported from CarrotPilot). Consumed later by the
    # longitudinal MPC to credit a bounded ACC departure once the gap is clear.
    self.lane_change_active = False
    self.lane_change_gap = LaneChangeGapPlan()
    self._lane_change_tracker = LaneChangeGapTracker()
    self._lane_change_model_ns = 0

    # Carrot phone navi advisory.
    self._active_carrot = 0
    self._x_dist_to_turn = 0
    self._atc_type = ""
    self._atc_active = False

    # Curve speed tuning (P0-2/P0-3).
    self._auto_curve_speed_factor = 1.0
    self._auto_curve_speed_aggressiveness = 1.0
    self._auto_curve_speed_factor_h = 0.8
    self._auto_curve_speed_aggressiveness_h = 1.2
    self._curvature_filter = _MovingAverage(20)
    self._lat_a = 0.0
    self._max_curve = 0.0
    # Road class from the navi packet (1 = highway, > 1 = surface street). Supplied
    # by the caller because CarrotPlanner has no view of the raw packet; it gates
    # the highway/surface split in vturn_speed(). Defaults to 8 so a caller that
    # does not pass it keeps the historical surface-street behaviour.
    self._roadcate = roadcate

    # Eco cruise.
    self._eco_over_speed = 2.0
    self._eco_target_speed = 0.0

    # AutoNavi speed tuning.
    self._auto_navi_speed_decel_rate = 1.5

    # Misc longitudinal tuning.
    self._traffic_stop_distance_adjust = -1.5

    # Outputs.
    self._v_cruise_kph = 0.0
    self._v_cruise = 0.0
    self._stop_dist = 0.0
    self._v_ego = 0.0
    self._mode: str = "acc"

  # ---- accessors --------------------------------------------------------- #

  @property
  def x_state(self) -> XState:
    return self._x_state

  @property
  def traffic_state(self) -> TrafficState:
    return self._traffic_state

  @property
  def atc_active(self) -> bool:
    return self._atc_active

  @property
  def atc_type(self) -> str:
    return self._atc_type

  @property
  def active_carrot(self) -> int:
    return self._active_carrot

  @property
  def stop_distance(self) -> float:
    return self._stop_dist

  @property
  def v_cruise(self) -> float:
    return self._v_cruise

  @property
  def v_cruise_kph(self) -> float:
    return self._v_cruise_kph

  @property
  def mode(self) -> str:
    return self._mode

  @property
  def comfort_a_target(self) -> float:
    """Comfortable deceleration the planner would command right now.

    Returns a non-positive acceleration: a smooth brake toward the configured
    stop distance when the planner is in a stopping state, otherwise 0. This is
    computed inside the planner (not approximated by the adapter) so the
    longitudinal source exposes a physically meaningful target.
    """
    if self._x_state in (XState.e2eStop, XState.e2eStopped):
      stop_dist = max(self._stop_dist, 1.0)
      # Kinematic decel needed to stop within stop_dist, capped by comfort brake.
      a = -(self._v_ego ** 2) / (2.0 * stop_dist)
      return -min(abs(self._comfort_brake), abs(a))
    return 0.0

  @property
  def active(self) -> bool:
    """True when the planner has a non-trivial (carrot-connected) output.

    Reflects that the carrot phone projection is feeding data. Freshness /
    timeout gating is applied one layer up in ``CarrotLongitudinalSource``.
    """
    return self._active_carrot > 0

  @property
  def driving_mode(self) -> DrivingMode:
    return self._my_driving_mode

  @property
  def jerk_factor(self) -> float:
    """Comfort-scaled jerk multiplier currently used by the planner."""
    return float(self._jerk_factor)

  @property
  def comfort_brake(self) -> float:
    """Comfort deceleration value used by the MPC for obstacle distance."""
    return float(self._comfort_brake)

  @property
  def traffic_stop_distance_adjust(self) -> float:
    """Configured signal-stop distance offset (meters, negative = closer)."""
    return float(self._traffic_stop_distance_adjust)

  @property
  def traffic_stop_model_lead_offset(self) -> float:
    """Model-lead matched stop offset; zero when no queued lead is detected."""
    return float(self.trafficStopModelLeadOffset)

  @property
  def stop_distance_margin(self) -> float:
    """Configured stop-distance safety margin (m), fed to the MPC when active."""
    return float(self._stop_distance)

  @property
  def dynamic_t_follow_lc(self) -> float:
    """Dynamic T-Follow ratio used to size the lane-change gap credit (0..1)."""
    return float(self._dynamic_t_follow_lc)

  # ---- parameter refresh ------------------------------------------------- #

  def _params_update(self) -> None:
    """Refresh cached tuning parameters in a staggered way to avoid hot loops."""
    self._frame += 1
    self._params_count += 1
    p = self._params

    # Always force a refresh on the first tick so we don't run with defaults
    # if the user has changed a value while the daemon was not running.
    if self._params_stale_after == 0:
      self._params_stale_after = self._frame + 1

    if self._params_count % 10 == 0:
      driving_mode_value = p.get_int("MyDrivingMode")
      if driving_mode_value not in {m.value for m in DrivingMode}:
        driving_mode_value = DrivingMode.Normal.value
      mode_now = DrivingMode(driving_mode_value)
      if mode_now != self._my_driving_mode_last:
        self._my_driving_mode_auto_disable = True
      self._my_driving_mode_last = mode_now

      self._my_driving_mode_auto = p.get_int("MyDrivingModeAuto")
      if self._my_driving_mode_auto > 0 and not self._my_driving_mode_auto_disable:
        self._my_driving_mode = self._driving_mode_detector.get_mode()
      else:
        self._my_driving_mode = mode_now

    if self._params_count == 10:
      self._my_high_mode_factor = 1.2
      self._traffic_light_detect_mode = p.get_int("TrafficLightDetectMode")
      self._apply_driving_mode_factors()
    elif self._params_count == 20:
      self._t_follow_gap1 = p.get_float("TFollowGap1") / 100.0
      self._t_follow_gap2 = p.get_float("TFollowGap2") / 100.0
      self._t_follow_gap3 = p.get_float("TFollowGap3") / 100.0
      self._t_follow_gap4 = p.get_float("TFollowGap4") / 100.0
      self._dynamic_t_follow_lc = p.get_float("DynamicTFollowLC") / 100.0
      self._lead_accel_response = int(np.clip(p.get_int("LeadAccelResponse"), 0, 5))
      self._enable_speed_tf = p.get_int("EnableSpeedTF")
      self._t_follow_decel_boost = p.get_float("TFollowDecelBoost") / 100.0
    elif self._params_count == 30:
      for i in range(7):
        raw = p.get_float(f"CruiseMaxVals{i}")
        if raw > 0:
          self._cruise_max_vals[i] = raw / 100.0
    elif self._params_count == 40:
      # Merged: the stop target distance now comes from sunnypilot's own tuning
      # entry, the same one the MPC solver uses, so a single control governs both.
      # Carrot's StopDistanceCarrot (cm) was retired; params_migration copies an
      # explicitly-set value across as metres.
      stop_distance_m = p.get_float("LongitudinalMpcTuningStopDistance")
      if stop_distance_m > 0:
        self._stop_distance = stop_distance_m
      self._j_lead_factor = p.get_float("JLeadFactor3") / 100.0
      self._eco_over_speed = p.get_int("CruiseEcoControl")
      self._auto_navi_speed_decel_rate = float(p.get_int("AutoNaviSpeedDecelRate")) * 0.01
      self._traffic_stop_distance_adjust = p.get_float("TrafficStopDistanceAdjust") / 100.0
      self._comfort_brake_comfort_factor = get_driving_mode_comfort_brake_factor(self._my_driving_mode)
      comfort_brake = p.get_float("LongitudinalMpcTuningComfortBrake")
      if comfort_brake > 0:
        self._comfort_brake_base = comfort_brake
    elif self._params_count >= 100:
      self._params_count = 0

  # ---- driving-mode helpers --------------------------------------------- #

  def _apply_driving_mode_factors(self) -> None:
    """Cache accel/t_follow factors derived from the active driving mode."""
    accel_factor, t_follow_factor = get_driving_mode_factors(self._my_driving_mode,
                                                              self._my_eco_factor,
                                                              self._my_safe_mode_factor)
    self._my_safe_factor = accel_factor
    self._my_t_follow_factor = t_follow_factor

  # ---- cruise envelope helpers ------------------------------------------ #

  # NOTE: no caller, and the CruiseMaxVals0-6 rows are no longer shown in either UI
  # (they are in CARROT_TUNING_UNAVAILABLE). Carrot's cruise-acceleration envelope was
  # never wired in: feeding it through would also need CarrotLongitudinalSource.a_target
  # to be consumed by the MPC, which today only publishes it as an observability field
  # (carrot_plan.aTarget). openpilot's own hardcoded A_CRUISE_MAX_VALS / A_CRUISE_MAX_BP
  # (longitudinal_planner.py:23-24) is what actually governs, and it is a coarser version
  # of the same curve. Wiring this would replace that envelope, so it needs device
  # validation; the params stay registered so it can be finished later.
  def _get_carrot_accel(self, v_ego: float) -> float:
    factor = self._my_high_mode_factor if self._my_driving_mode == DrivingMode.High else self._my_safe_factor
    # np.interp is happy with mismatched monotonic arrays as long as xp is sorted.
    return float(np.interp(v_ego, _A_CRUISE_MAX_BP, self._cruise_max_vals)) * factor

  # ---- following-time helpers ------------------------------------------- #

  def _get_base_t_follow(self, personality: int, v_ego: float,
                         use_speed_tf: bool = True) -> float:
    """Return the unscaled following-time target for this personality."""
    if use_speed_tf and self._enable_speed_tf < 0:
      tf_speed_bps = {
        -1: [0, 30, 60, 90],
        -2: [0, 40, 80, 120],
        -3: [0, 50, 100, 150],
      }
      v_kph = v_ego * CV.MS_TO_KPH
      bp = tf_speed_bps.get(self._enable_speed_tf, [0, 30, 60, 90])
      tf_base = float(np.interp(
        v_kph, bp,
        [self._t_follow_gap1, self._t_follow_gap2, self._t_follow_gap3, self._t_follow_gap4],
      ))
      self._jerk_factor = float(np.interp(v_kph, bp, [1.0, 0.7, 0.5, 0.5]))
      if personality == _LongitudinalPersonality.moreRelaxed:
        tf_base *= 2.0
      elif personality == _LongitudinalPersonality.relaxed:
        tf_base *= 1.6
      elif personality == _LongitudinalPersonality.standard:
        tf_base *= 1.3
      elif personality == _LongitudinalPersonality.aggressive:
        tf_base *= 1.0
      else:
        raise NotImplementedError("Longitudinal personality not supported")
    else:
      if personality == _LongitudinalPersonality.moreRelaxed:
        self._jerk_factor = 1.0
        tf_base = self._t_follow_gap4
      elif personality == _LongitudinalPersonality.relaxed:
        self._jerk_factor = 1.0
        tf_base = self._t_follow_gap3
      elif personality == _LongitudinalPersonality.standard:
        self._jerk_factor = 1.0 if self._my_driving_mode == DrivingMode.Safe else 0.7
        tf_base = self._t_follow_gap2
      elif personality == _LongitudinalPersonality.aggressive:
        self._jerk_factor = 1.0 if self._my_driving_mode == DrivingMode.Safe else 0.5
        tf_base = self._t_follow_gap1
      else:
        raise NotImplementedError("Longitudinal personality not supported")
    return float(tf_base)

  def _apply_speed_t_follow_scale(self, tf_base: float, v_ego: float) -> float:
    """Shrink the gap at low speed when the user enables speed-based scaling."""
    tf_target = float(tf_base)
    if self._enable_speed_tf > 0:
      reduce = self._enable_speed_tf * 0.01
      s = float(np.clip(v_ego * CV.MS_TO_KPH / 100.0, 0.0, 1.0))
      scale = (1.0 - reduce) + reduce * s
      tf_target *= scale
    return float(tf_target)

  def _apply_decel_hold_and_boost_t_follow(self, tf_target: float, a_ego: float) -> float:
    """Hold the unboosted baseline and add a transient braking-distance margin."""
    previous_extra = getattr(self, "_tf_decel_extra", 0.0)
    previous_base = getattr(self, "_tf_decel_base", getattr(self, "_tf_applied", tf_target) - previous_extra)
    self._tf_decel_base = max(tf_target, previous_base) if a_ego <= -0.2 else tf_target
    requested_extra = float(np.interp(a_ego, [-2.5, -1.0, -0.3, 0.0], [0.50, 0.25, 0.06, 0.0])) * self._t_follow_decel_boost
    # Add braking margin promptly; release only the extra margin progressively.
    self._tf_decel_extra = max(requested_extra, previous_extra - 0.10 * DT_MDL)
    return float(self._tf_decel_base + self._tf_decel_extra)

  def _clip_t_follow(self, t_follow: float) -> float:
    tf_min = float(min(self._t_follow_gap1, self._t_follow_gap2, self._t_follow_gap3, self._t_follow_gap4))
    tf_max = float(max(self._t_follow_gap1, self._t_follow_gap2, self._t_follow_gap3, self._t_follow_gap4))
    tf_max = get_t_follow_mode_max(tf_max, self._my_t_follow_factor, self._tf_decel_extra)
    return float(np.clip(t_follow, max(0.3, tf_min), tf_max))

  def get_T_FOLLOW(self, personality: int = _LongitudinalPersonality.standard,
                   v_ego: float = 0.0, a_ego: float = 0.0,
                   lead_status: bool = False, lead_accel: float = 0.0) -> float:
    """Return the final following-time gap for the current planner state.

    Mirrors the CarrotPlanner interface used by CarrotPilot's longitudinal MPC.
    """
    force_configured_tf_target = (
      lead_status and not getattr(self, 'lane_change_active', False)
      and np.isfinite(lead_accel)
      and lead_accel > 0.5
      and self._lead_accel_response >= 2
    )
    tf_base = self._get_base_t_follow(personality, v_ego, use_speed_tf=not force_configured_tf_target)
    if force_configured_tf_target:
      tf_mode_target = tf_base
    else:
      tf_target = self._apply_speed_t_follow_scale(tf_base, v_ego)
      tf_mode_target = float(tf_target * self._my_t_follow_factor)
    tf_adjusted = self._apply_decel_hold_and_boost_t_follow(tf_mode_target, a_ego)
    tf_final = self._clip_t_follow(tf_adjusted)
    self._tf_applied = float(tf_final)
    self._tf_base_last = ramp_t_follow(tf_final, getattr(self, '_tf_base_last', self._t_follow_last), self._tf_decel_extra, DT_MDL)
    self._t_follow_last = float(self._tf_base_last)
    return self._t_follow_last

  def _eco_cruise_control(self, v_ego_kph: float, v_cruise_kph: float) -> float:
    v_cruise_apply = v_cruise_kph
    if self._eco_over_speed <= 0:
      self._eco_target_speed = 0.0
      return v_cruise_apply
    if self._eco_target_speed > 0:
      if self._eco_target_speed < v_cruise_kph:
        self._eco_target_speed = v_cruise_kph
      elif self._eco_target_speed > v_cruise_kph:
        self._eco_target_speed = 0.0
    elif self._eco_target_speed == 0 and v_ego_kph + 3 < v_cruise_kph and v_cruise_kph > 20.0:
      self._eco_target_speed = v_cruise_kph

    if self._eco_target_speed != 0:
      if v_ego_kph > self._eco_target_speed:
        self._eco_target_speed = 0.0
      else:
        v_cruise_apply = self._eco_target_speed + self._eco_over_speed
    return v_cruise_apply

  # ---- carrot advisory helpers ------------------------------------------- #

  def _update_carrot_man(self, sm: Any, v_ego_kph: float, v_cruise_kph: float) -> tuple[float, bool]:
    """Pull cruise & ATC advisories out of the phone projection.

    Returns the (possibly lowered) cruise speed and whether the auto turn
    control is requesting a maneuver.
    """
    atc_active = False
    if not sm.valid.get("carrotManSP", False) or not sm.alive.get("carrotManSP", False):
      return v_cruise_kph, atc_active

    carrot = sm["carrotManSP"]
    traffic_state_carrot = getattr(carrot, "trafficState", 0) or 0
    trigger_start = False

    if self._traffic_state_carrot == 1 and traffic_state_carrot == 2:  # red -> green
      trigger_start = True
    self._traffic_state_carrot = traffic_state_carrot

    if trigger_start:
      if self._x_state in (XState.e2eStop, XState.e2eStopped):
        self._x_state = XState.e2eCruise
        self._traffic_starting_count = 10.0 / DT_MDL

    self._active_carrot = int(getattr(carrot, "activeCarrot", 0) or 0)
    self._x_dist_to_turn = int(getattr(carrot, "xDistToTurn", 0) or 0)
    atc_active = self._active_carrot > 1 and 0 < self._x_dist_to_turn < 100
    self._atc_type = getattr(carrot, "atcType", "") or ""
    # NOTE: `desiredSpeed` is still published on carrotManSP for HUD/webui display
    # only. It intentionally no longer lowers `v_cruise_kph` here: sunnypilot's
    # Speed Limit Assist (SLA) is the single executor of the road-speed-limit
    # target, and `desiredSpeed` is already a post-`calculate_current_speed`
    # "currently permitted speed". Feeding it back as a set-speed change would
    # double-count Carrot's own deceleration on top of SLA's LIMIT_ADAPT_ACC.
    return v_cruise_kph, atc_active

  # ---- state-machine helpers --------------------------------------------- #

  def _update_model_desire(self, sm: Any) -> None:
    meta = sm["modelV2"].meta
    cs = sm["carState"]
    # LaneChangeState.laneChangeStarting (1) / laneChangeFinishing (2) mark an
    # active lane change; gate the gap tracker on this so it only runs mid-maneuver.
    self.lane_change_active = meta.laneChangeState in (1, 2)
    if meta.laneChangeState == 1:  # LaneChangeState.laneChangeStarting
      self._desire_state = meta.desireState[3] if cs.leftBlinker else meta.desireState[4]
      self._desire_state_count += 1
    else:
      self._desire_state = 0.0
      self._desire_state_count = 0

    self._update_lane_change_gap(sm)

  def _update_lane_change_gap(self, sm: Any) -> None:
    """Feed live pose / radar leads into the lane-change gap tracker.

    Mirrors CarrotPilot's wiring: reads carState, modelV2, radarState and
    livePose from the SubMaster, derives the change direction from the blinker
    state, and updates the tracker. A fast radar feed must not double-count the
    same model/pose frame, so identical model logMonoTime is skipped.
    """
    state, model, radar = sm["carState"], sm["modelV2"], sm["radarState"]
    signal = bool(state.leftBlinker) != bool(state.rightBlinker)
    direction = ((-1 if state.leftBlinker else 1) if signal else self._lane_change_tracker.direction) \
        if self.lane_change_active else 0
    now_ns = int(sm.logMonoTime["modelV2"])
    valid = all(sm.valid[key] and sm.alive[key] for key in ("carState", "modelV2", "radarState"))
    valid = valid and abs(now_ns - int(sm.logMonoTime["radarState"])) <= 200_000_000
    if not valid or direction == 0:
      self._lane_change_tracker.reset()
      self.lane_change_gap = LaneChangeGapPlan(
        active=self.lane_change_active,
        reason="invalid-input" if self.lane_change_active else "inactive",
      )
      self._lane_change_model_ns = 0
      return
    if now_ns == self._lane_change_model_ns:
      return  # fast radar must not count the same model/pose twice
    self._lane_change_model_ns = now_ns
    pose = sm["livePose"]
    angular = pose.angularVelocityDevice
    pose_valid = (
      sm.valid["livePose"] and sm.alive["livePose"]
      and pose.inputsOK and pose.sensorsOK and angular.valid
      and abs(now_ns - int(sm.logMonoTime["livePose"])) <= 150_000_000
    )
    self.lane_change_gap = self._lane_change_tracker.update(
      now=now_ns * 1e-9,
      direction=direction,
      v_ego=float(state.vEgo),
      yaw_rate=float(angular.z) if pose_valid else float("nan"),
      path_t=tuple(model.position.t),
      path_x=tuple(model.position.x),
      path_y=tuple(model.position.y),
      primary=radar.leadOne,
      secondary=radar.leadTwo,
      blindspot=not signal or bool(state.leftBlindspot if direction == -1 else state.rightBlindspot),
      valid=valid,
    )

  def _check_model_stopping(self, v_cruise_set: float, v_model: np.ndarray, v_ego: float,
                            a_ego: float, model_x_last: float, model_y: np.ndarray,
                            d_rel: float) -> None:
    model_v_last = self._v_filter.process(float(v_model[-1]))
    start_sign = model_v_last > 5.0 or model_v_last > (float(v_model[0]) + 2)

    v_ego_kph = v_ego * CV.MS_TO_KPH
    if v_ego_kph < 1.0:
      stop_sign = model_x_last < 20.0 and model_v_last < 10.0
    elif v_ego_kph < 82.0:
      stop_sign = (
        model_x_last < d_rel - 3.0
        and model_x_last < float(np.interp(v_model[0] * 3.6, [60, 80], [120.0, 150]))
        and ((model_v_last < 3.0) or (model_v_last < v_model[0] * 0.7))
      )
      if v_cruise_set != 0 and self._x_state == XState.e2eCruise and a_ego < -1.0:
        stop_sign = False
    else:
      stop_sign = False

    self._stop_sign_count = self._stop_sign_count + 1 if stop_sign else 0
    self._start_sign_count = self._start_sign_count + 1 if (start_sign and not stop_sign) else 0

    # Multi-frame confirmation: a single misdetected frame must not flip the
    # traffic state. Red needs _TRAFFIC_RED_CONFIRM_FRAMES of sustained vision
    # stop evidence; green needs _TRAFFIC_GREEN_CONFIRM_FRAMES. Once a state is
    # confirmed it is held until the opposite is confirmed, or the signal is lost
    # for a matching number of frames, which suppresses rapid red<->green chatter.
    if stop_sign:
      self._stop_frames += 1
      self._start_frames = 0
    elif start_sign:
      self._start_frames += 1
      self._stop_frames = 0
    else:
      self._stop_frames = 0
      self._start_frames = 0

    if self._traffic_state == TrafficState.red:
      if self._start_frames >= _TRAFFIC_GREEN_CONFIRM_FRAMES:
        self._traffic_state = TrafficState.green
        self._red_lost_frames = 0
      elif not stop_sign:
        self._red_lost_frames += 1
        if self._red_lost_frames >= _TRAFFIC_RED_CONFIRM_FRAMES:
          self._traffic_state = TrafficState.off
      else:
        self._red_lost_frames = 0
    elif self._traffic_state == TrafficState.green:
      if self._stop_frames >= _TRAFFIC_RED_CONFIRM_FRAMES:
        self._traffic_state = TrafficState.red
        self._green_lost_frames = 0
      elif not start_sign:
        self._green_lost_frames += 1
        if self._green_lost_frames >= _TRAFFIC_GREEN_CONFIRM_FRAMES:
          self._traffic_state = TrafficState.off
      else:
        self._green_lost_frames = 0
    else:  # off
      if self._stop_frames >= _TRAFFIC_RED_CONFIRM_FRAMES:
        self._traffic_state = TrafficState.red
      elif self._start_frames >= _TRAFFIC_GREEN_CONFIRM_FRAMES:
        self._traffic_state = TrafficState.green

  def _update_x_state(self, sm: Any, v_ego: float, v_ego_kph: float,
                     a_ego: float, x_last: float) -> None:
    cs = sm["carState"]
    radar = sm["radarState"]
    lead_one = radar.leadOne
    lead_detected = bool(lead_one.status)

    # Disable stop detection when steering hard or in a high-energy mode.
    if self._my_driving_mode == DrivingMode.Safe and self._traffic_light_detect_mode == 0:
      self._traffic_state = TrafficState.off
    if abs(getattr(cs, "steeringAngleDeg", 0.0)) > 20.0:
      self._traffic_state = TrafficState.off

    if cs.gasPressed or cs.brakePressed:
      self._user_stop_distance = -1.0

    if self._x_state == XState.e2eStopped:
      if cs.gasPressed:
        self._x_state = XState.e2eCruise
      elif lead_detected and (lead_one.dRel - x_last) < 2.0:
        self._x_state = XState.lead
      elif self._stopping_count == 0:
        # Carrot left-turn green (3) is only detectable by the phone navi, so we
        # trust it to release a stopped state; straight green (2) must be
        # confirmed by the vision model before we start, to avoid running a red
        # on a misread phone signal.
        can_go = self._traffic_state == TrafficState.green or self._traffic_state_carrot == 3
        if (can_go
                and not self._carrot_stay_stop
                and not cs.leftBlinker
                and self._traffic_light_detect_mode != 1):
          self._x_state = XState.e2eCruise
      self._stopping_count = max(0.0, self._stopping_count - 1)
      self._v_cruise = 0.0
    elif self._x_state == XState.e2eStop:
      self._stopping_count = 0.0
      if cs.gasPressed:
        self._x_state = XState.e2eCruise
        self._traffic_starting_count = 10.0 / DT_MDL
      elif lead_detected and (lead_one.dRel - x_last) < 2.0:
        self._x_state = XState.lead
      else:
        can_go = self._traffic_state == TrafficState.green or self._traffic_state_carrot == 3
        if can_go:
          self._x_state = XState.e2eCruise
        else:
          self._comfort_brake = self._comfort_brake_base * self._comfort_brake_comfort_factor
          traffic_stop_adjust_ratio = float(np.interp(v_ego_kph, [0, 100], [1.0, 0.7]))
          stop_dist = x_last * float(np.interp(x_last, [0, 50], [1.0, traffic_stop_adjust_ratio]))
          if stop_dist > 10.0:
            self._actual_stop_distance = stop_dist
          x_last = 0.0
          if v_ego < 0.3:
            self._stopping_count = 0.5 / DT_MDL
            self._x_state = XState.e2eStopped
    elif self._x_state == XState.e2ePrepare:
      if lead_detected:
        self._x_state = XState.lead
      elif self._atc_active:
        if cs.gasPressed:
          self._x_state = XState.e2eCruise
      elif v_ego_kph < 5.0 and self._traffic_state != TrafficState.green:
        self._x_state = XState.e2eStop
        self._actual_stop_distance = 5.0
      elif v_ego_kph > 5.0:
        self._x_state = XState.e2eCruise
    else:  # lead / cruise / e2eCruise
      self._traffic_starting_count = max(0.0, self._traffic_starting_count - 1)
      if lead_detected:
        self._x_state = XState.lead
      elif (self._traffic_state == TrafficState.red
            and abs(getattr(cs, "steeringAngleDeg", 0.0)) < 30.0
            and self._traffic_starting_count == 0):
        self._x_state = XState.e2eStop
        self._actual_stop_distance = self._x_stop
      else:
        self._x_state = XState.e2eCruise

  # ---- curve speed (P0-2 / P0-3) ----------------------------------------- #

  def carrot_curve_speed_params(self) -> None:
    """Load curve-speed tuning parameters from UnifiedParams."""
    self._auto_curve_speed_factor = self._params.get_float("AutoCurveSpeedFactor") * 0.01
    self._auto_curve_speed_aggressiveness = self._params.get_float("AutoCurveSpeedAggressiveness") * 0.01
    self._auto_curve_speed_factor_h = self._params.get_float("AutoCurveSpeedFactorH") * 0.01
    self._auto_curve_speed_aggressiveness_h = self._params.get_float("AutoCurveSpeedAggressivenessH") * 0.01

  def carrot_curve_speed(self, sm: Any) -> float:
    """Calculate curve speed using modelV2 orientation rate.

    Returns:
      Recommended curve speed in km/h (signed by curvature direction).
    """
    self.carrot_curve_speed_params()

    if not sm.alive['carState'] and not sm.alive['modelV2']:
      return 250.0

    model_data = sm['modelV2']
    if len(model_data.orientationRate.z) == 0:
      return 250.0

    return self.vturn_speed(sm['carState'], sm)

  def vturn_speed(self, cs: Any, sm: Any) -> float:
    """Calculate turn speed for a curve using modelV2 orientation rate.

    Uses ``orientationRate.z`` and ``velocity.x`` from modelV2 to estimate
    the maximum lateral acceleration and derive a safe curve speed.
    """
    target_lat_a = 1.9  # m/s^2

    model_data = sm['modelV2']
    v_ego = max(cs.vEgo, 0.1)

    # Set the curve sensitivity based on road category
    if self._roadcate > 1:  # 普通道路 (normal road)
      orientation_rate = np.array(model_data.orientationRate.z) * self._auto_curve_speed_factor
    else:  # 高速公路 (highway)
      orientation_rate = np.array(model_data.orientationRate.z) * self._auto_curve_speed_factor_h

    velocity = np.array(model_data.velocity.x)

    # Get the maximum lat accel from the model
    max_index = np.argmax(np.abs(orientation_rate))
    curv_direction = np.sign(orientation_rate[max_index])
    max_pred_lat_acc = np.amax(np.abs(orientation_rate) * velocity)

    # Get the maximum curve based on the current velocity
    max_curve = max_pred_lat_acc / (v_ego ** 2) if v_ego > 0 else 0.0

    self._lat_a = max_pred_lat_acc
    self._max_curve = max_curve

    # Set the target lateral acceleration based on road category
    if self._roadcate > 1:  # 普通道路
      adjusted_target_lat_a = target_lat_a * self._auto_curve_speed_aggressiveness
    else:  # 高速公路
      adjusted_target_lat_a = target_lat_a * self._auto_curve_speed_aggressiveness_h

    # Get the target velocity for the maximum curve
    turn_speed = max(abs(adjusted_target_lat_a / max_curve) ** 0.5 * 3.6, 5.0)
    turn_speed = min(turn_speed, 250.0)

    return turn_speed * curv_direction

  # ---- public API --------------------------------------------------------- #

  def update(self, sm: Any, v_cruise_kph: float, mode: str = "acc") -> float:
    """Run a single planner tick and return the recommended cruise set speed."""
    self._params_update()
    self._update_model_desire(sm)
    cs = sm["carState"]
    radar = sm["radarState"]
    model = sm["modelV2"]

    v_ego = float(cs.vEgo)
    a_ego = float(cs.aEgo)
    v_ego_kph = v_ego * CV.MS_TO_KPH
    self._v_ego = v_ego
    v_ego_cluster_kph = float(getattr(cs, "vEgoCluster", v_ego)) * CV.MS_TO_KPH

    # Driving mode-aware safety factor.
    self._my_safe_factor = 1.0
    lead_one = radar.leadOne
    if lead_one.status and lead_one.vLead < 5:
      self._my_safe_factor = self._my_safe_mode_factor
    elif self._my_driving_mode == DrivingMode.Eco:
      self._my_safe_factor = self._my_eco_factor
    elif self._my_driving_mode == DrivingMode.Safe:
      self._my_safe_factor = self._my_safe_mode_factor

    if self._frame % 20 == 0:  # once per second at 20 Hz
      v_lead = float(lead_one.vLead) * CV.MS_TO_KPH if lead_one.status else 0.0
      a_lead = float(lead_one.aLeadK) if lead_one.status else 0.0
      d_rel = float(lead_one.dRel) if lead_one.status else 200.0
      self._driving_mode_detector.update_data(
        v_ego_kph, v_lead, a_ego, a_lead, d_rel,
      )

    v_cruise_kph = self._eco_cruise_control(v_ego_cluster_kph, v_cruise_kph)
    v_cruise_kph, atc_active = self._update_carrot_man(sm, v_ego_kph, v_cruise_kph)
    self._atc_active = atc_active

    # Default vCluRatio to 1.0 (SunnyPilot does not always expose vCluRatio).
    v_clu_ratio = float(getattr(cs, "vCluRatio", 1.0) or 1.0)
    v_cruise = v_cruise_kph * CV.KPH_TO_MS
    if v_clu_ratio > 0.5:
      v_cruise *= v_clu_ratio

    x = np.asarray(model.position.x, dtype=float)
    y = np.asarray(model.position.y, dtype=float)
    v = np.asarray(model.velocity.x, dtype=float)

    lead_detected = bool(lead_one.status)
    d_rel_for_model = float(lead_one.dRel) if lead_detected else 1000.0

    self._x_stop = float(self._x_stop_filter2.process(self._x_stop_filter.process(float(x[31]), median=True)))
    stop_model_x = self._x_stop

    self._check_model_stopping(v_cruise, v, v_ego, a_ego, float(x[-1]), y, d_rel_for_model)
    self._update_x_state(sm, v_ego, v_ego_kph, a_ego, stop_model_x)

    if self._traffic_state in (TrafficState.off, TrafficState.green) or self._x_state not in (XState.e2eStop, XState.e2eStopped):
      stop_model_x = 1000.0

    if self._user_stop_distance >= 0:
      self._user_stop_distance = max(0.0, self._user_stop_distance - v_ego * DT_MDL)
      self._actual_stop_distance = self._user_stop_distance
      self._x_state = XState.e2eStop if self._user_stop_distance > 0 else XState.e2eStopped

    if mode == "acc" and self._x_state == XState.e2ePrepare:
      mode = "blended"

    # Recompute from the base every tick. This used to be `*=`, which decayed the
    # value geometrically at 20 Hz whenever a factor != 1 was active.
    self._comfort_brake = self._comfort_brake_base * self._my_safe_factor * self._comfort_brake_comfort_factor
    self._actual_stop_distance = max(0.0, self._actual_stop_distance - v_ego * DT_MDL)

    if stop_model_x == 1000.0:
      self._actual_stop_distance = 0.0
    elif self._actual_stop_distance > 0:
      stop_model_x = 0.0

    stop_dist = stop_model_x + self._actual_stop_distance
    stop_dist = max(stop_dist, v_ego ** 2 / (self._comfort_brake * 2))

    # ---- E2E model-lead stop-point matcher --------------------------------- #
    stopping_active = self._x_state in (XState.e2eStop, XState.e2eStopped)

    # Pull the primary model lead (modelV2.leadsV3[0]) only while we are stopping
    # behind an E2E stop line with no radar lead in front. Access is defensive so
    # a model without leadsV3 (or a mocked test model) degrades to NaN inputs,
    # which the matcher treats as "no confirmation".
    model_lead = None
    leads = getattr(model, "leadsV3", None)
    if stopping_active and not lead_detected and leads is not None:
      try:
        if len(leads) > 0:
          model_lead = leads[0]
      except (TypeError, ValueError):
        model_lead = None

    def _lead_scalar(lead, field, default=np.nan):
      if lead is None:
        return default
      raw = getattr(lead, field, None)
      if raw is None:
        return default
      try:
        arr = np.asarray(raw, dtype=float)
      except (TypeError, ValueError):
        return default
      if arr.size == 0:
        return default
      return float(arr.flat[0])

    self.trafficStopModelLeadOffset = self._traffic_stop_model_lead_matcher.update(
      stop_active=stopping_active and stop_dist < 300.0,
      allow_confirmation=self._traffic_state == TrafficState.red and v_ego > 0.3,
      active_lead=lead_detected,
      stop_distance=stop_dist,
      lead_probability=_lead_scalar(model_lead, "prob"),
      lead_distance=_lead_scalar(model_lead, "x") - RADAR_TO_CAMERA,
      lead_velocity=_lead_scalar(model_lead, "v"),
      lead_x_std=_lead_scalar(model_lead, "xStd"),
      lead_y_std=_lead_scalar(model_lead, "yStd"),
      lead_v_std=_lead_scalar(model_lead, "vStd"),
    )

    # High-speed protection: a phone-navigation-only red light must not command a
    # stop by itself at speed. Only a vision-confirmed stop line may. This
    # satisfies the safety review's "high-speed single-source nav red must not
    # enter e2eStop" rule.
    if v_ego_kph > _HIGH_SPEED_KPH:
      vision_red = self._traffic_state == TrafficState.red
      carrot_only_red = (self._traffic_state_carrot == 1) and not vision_red
      if carrot_only_red and self._x_state in (XState.e2eStop, XState.e2eStopped):
        self._x_state = XState.e2eCruise

    self._v_cruise_kph = v_cruise_kph
    self._v_cruise = v_cruise
    self._stop_dist = stop_dist
    self._mode = mode

    # High-speed floor (m/s): a nav-only red may not drop the target below a safe
    # fraction of the set speed. Vision-confirmed stops are exempt.
    if v_ego_kph > _HIGH_SPEED_KPH:
      vision_red = self._traffic_state == TrafficState.red
      carrot_only_red = (self._traffic_state_carrot == 1) and not vision_red
      if carrot_only_red:
        self._v_cruise = max(self._v_cruise, v_cruise * _HIGH_SPEED_FLOOR_RATIO)
    return v_cruise_kph
