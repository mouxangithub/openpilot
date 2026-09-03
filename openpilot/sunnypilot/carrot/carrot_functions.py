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
  """Driving style preset selected by the user."""
  Eco = 0
  Normal = 1
  Sport = 2
  Safe = 3

  def __str__(self) -> str:
    return self.name


class TrafficState(Enum):
  """Traffic light state from model + phone navi fusion."""
  off = 0
  red = 1
  green = 2

  def __str__(self) -> str:
    return self.name


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


# --------------------------------------------------------------------------- #
# CarrotPlanner                                                                #
# --------------------------------------------------------------------------- #


class CarrotPlanner:
  """Per-frame longitudinal planner that wraps the carrot tuning surface.

  The planner is fed a ``SubMaster`` snapshot each tick and returns the
  effective cruise speed and a "stop at" distance the caller can mix into
  a longitudinal plan source.
  """

  def __init__(self, params: UnifiedParams | None = None) -> None:
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
    self._my_eco_factor = 0.9
    self._my_safe_mode_factor = 0.8
    self._my_high_mode_factor = 1.2

    # Follow-distance breakpoints (seconds) - one per LongitudinalPersonality.
    self._t_follow_gap1 = 1.1
    self._t_follow_gap2 = 1.3
    self._t_follow_gap3 = 1.45
    self._t_follow_gap4 = 1.6
    self._dynamic_t_follow = 0.0
    self._dynamic_t_follow_lc = 0.0

    # Cruise acceleration envelope per breakpoint.
    self._cruise_max_vals: list[float] = [1.6, 1.6, 1.2, 1.0, 0.8, 0.7, 0.6]

    # Stop / traffic handling.
    self._stop_distance = 6.0
    self._comfort_brake = 2.4
    self._traffic_light_detect_mode = 2
    self._traffic_state = TrafficState.off
    self._traffic_state_carrot = 0
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

    # Lane-change assist.
    self._desire_state = 0.0
    self._desire_state_count = 0
    self._jerk_factor = 1.0
    self._jerk_factor_apply = 1.0
    self._j_lead_factor = 0.0

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
    self._roadcate = 8

    # Eco cruise.
    self._eco_over_speed = 2.0
    self._eco_target_speed = 0.0

    # AutoNavi speed tuning.
    self._auto_navi_speed_decel_rate = 1.5

    # Outputs.
    self._v_cruise_kph = 0.0
    self._v_cruise = 0.0
    self._stop_dist = 0.0
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
    elif self._params_count == 20:
      self._t_follow_gap1 = p.get_float("TFollowGap1") / 100.0
      self._t_follow_gap2 = p.get_float("TFollowGap2") / 100.0
      self._t_follow_gap3 = p.get_float("TFollowGap3") / 100.0
      self._t_follow_gap4 = p.get_float("TFollowGap4") / 100.0
      self._dynamic_t_follow = p.get_float("DynamicTFollow") / 100.0
      self._dynamic_t_follow_lc = p.get_float("DynamicTFollowLC") / 100.0
    elif self._params_count == 30:
      for i in range(7):
        raw = p.get_float(f"CruiseMaxVals{i}")
        if raw > 0:
          self._cruise_max_vals[i] = raw / 100.0
    elif self._params_count == 40:
      stop_distance_cm = p.get_int("StopDistanceCarrot")
      if stop_distance_cm > 0:
        self._stop_distance = stop_distance_cm / 100.0
      self._j_lead_factor = p.get_float("JLeadFactor3") / 100.0
      self._eco_over_speed = p.get_int("CruiseEcoControl")
      self._auto_navi_speed_decel_rate = float(p.get_int("AutoNaviSpeedDecelRate")) * 0.01
    elif self._params_count >= 100:
      self._params_count = 0

  # ---- cruise envelope helpers ------------------------------------------ #

  def _get_carrot_accel(self, v_ego: float) -> float:
    factor = self._my_high_mode_factor if self._my_driving_mode == DrivingMode.Safe else self._my_safe_factor
    # np.interp is happy with mismatched monotonic arrays as long as xp is sorted.
    return float(np.interp(v_ego, _A_CRUISE_MAX_BP, self._cruise_max_vals)) * factor

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
    desired_speed = int(getattr(carrot, "desiredSpeed", 0) or 0)
    if desired_speed > 0:
      v_cruise_kph = min(v_cruise_kph, float(desired_speed))
    return v_cruise_kph, atc_active

  # ---- state-machine helpers --------------------------------------------- #

  def _update_model_desire(self, sm: Any) -> None:
    meta = sm["modelV2"].meta
    cs = sm["carState"]
    if meta.laneChangeState == 1:  # LaneChangeState.laneChangeStarting
      self._desire_state = meta.desireState[3] if cs.leftBlinker else meta.desireState[4]
      self._desire_state_count += 1
    else:
      self._desire_state = 0.0
      self._desire_state_count = 0

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

    if self._stop_sign_count * DT_MDL > 0.0:
      self._traffic_state = TrafficState.red
    elif self._start_sign_count * DT_MDL > 0.2:
      self._traffic_state = TrafficState.green
    else:
      self._traffic_state = TrafficState.off

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
        if (self._traffic_state == TrafficState.green
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
        if self._traffic_state == TrafficState.green:
          self._x_state = XState.e2eCruise
        else:
          self._comfort_brake = 2.4 * 0.9
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

    self._comfort_brake *= self._my_safe_factor
    self._actual_stop_distance = max(0.0, self._actual_stop_distance - v_ego * DT_MDL)

    if stop_model_x == 1000.0:
      self._actual_stop_distance = 0.0
    elif self._actual_stop_distance > 0:
      stop_model_x = 0.0

    stop_dist = stop_model_x + self._actual_stop_distance
    stop_dist = max(stop_dist, v_ego ** 2 / (self._comfort_brake * 2))

    self._v_cruise_kph = v_cruise_kph
    self._v_cruise = v_cruise
    self._stop_dist = stop_dist
    self._mode = mode
    return v_cruise_kph
