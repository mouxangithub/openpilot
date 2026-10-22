#!/usr/bin/env python3
# Twilsonco's Lateral Neural Network Feedforward Controller (StarPilot port).
#
# NN-based lateral torque control. Adaptations vs StarPilot: this fork's
# LatControl signature (CP, CP_SP, CI, dt) and update() parameter order; the
# toggle system is replaced by the nnff_mode attribute (0=off, 1=lite,
# 2=full NN), set externally from Params. Pure model math lives in
# nnff_model.py (PC-testable).
import math
from collections import deque

import numpy as np

from openpilot.common.constants import ACCELERATION_DUE_TO_GRAVITY
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.pid import PIDController
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.selfdrive.controls.lib.nnff_model import (
  LAT_PLAN_MIN_IDX,
  LOW_SPEED_X,
  LOW_SPEED_Y,
  get_lookahead_value,
  get_nn_model,
  get_nnff_lat_jerk_friction_factor,
  get_predicted_lateral_jerk,
  roll_pitch_adjust,
  sign,
)
from openpilot.selfdrive.modeld.constants import ModelConstants


class LatControlNNFF(LatControl):
  def __init__(self, CP, CP_SP, CI, dt):
    super().__init__(CP, CP_SP, CI, dt)
    self.lat_torque_nn_model = get_nn_model(CP.carFingerprint, str(next((fw.fwVersion for fw in CP.carFw if fw.ecu == "eps"), "")).replace("\\", ""))
    self.nnff_loaded = self.lat_torque_nn_model is not None

    # 0=off (classic torque math), 1=lite (jerk-friction only), 2=full NN.
    # Set externally (controlsd) from Params every second.
    self.nnff_mode = 0
    self._sm = None

    self.torque_params = CP.lateralTuning.torque.as_builder()
    self.pid = PIDController(1.0, 0.3, 0.0, pos_limit=self.steer_max, neg_limit=-self.steer_max, rate=1 / self.dt)
    self.torque_from_lateral_accel = CI.torque_from_lateral_accel()
    self.steering_angle_deadzone_deg = self.torque_params.steeringAngleDeadzoneDeg

    # "Look ahead" to the future planned lateral jerk to gauge whether the
    # current desired jerk is "deliberate" or short-lived noise.
    self.friction_look_ahead_bp = [9.0, 30.0]  # speeds in m/s in [0, ~40]
    self.friction_look_ahead_v = [1.4, 2.0]  # seconds into the future in [0, ~2.1]

    # Scaling the lateral acceleration "friction response". Increase for a
    # stronger response, decrease for a weaker one.
    self.lat_accel_friction_factor = 0.7  # in [0, 3]
    self.lat_jerk_friction_factor = get_nnff_lat_jerk_friction_factor(CP.carFingerprint)

    # precompute time differences between ModelConstants.T_IDXS
    self.t_diffs = np.diff(ModelConstants.T_IDXS)

    self.pitch = FirstOrderFilter(0.0, 0.5, 0.01)

    # NN model takes current v_ego, lateral_accel, lat accel/jerk error, roll,
    # and past/future/planned data of lat accel and roll.
    self.nn_friction_override = self.lat_torque_nn_model.friction_override if self.lat_torque_nn_model else False

    # setup future time offsets
    lat_delay = CP.steerActuatorDelay
    self.future_times = [0.3, 0.6, 1.0, 1.5]  # seconds in the future
    self.nn_future_times = [time + lat_delay for time in self.future_times]

    # setup past time offsets
    self.past_times = [-0.3, -0.2, -0.1]
    history_check_frames = [int(abs(time) * 100) for time in self.past_times]
    self.history_frame_offsets = [history_check_frames[0] - time for time in history_check_frames]
    self.lateral_accel_desired_deque = deque(maxlen=history_check_frames[0])
    self.past_future_len = len(self.past_times) + len(self.nn_future_times)
    self.roll_deque = deque(maxlen=history_check_frames[0])

  def attach_sm(self, sm):
    self._sm = sm

  def update_live_delay(self, lat_delay):
    self.nn_future_times = [time + lat_delay for time in self.future_times]
    self.past_future_len = len(self.past_times) + len(self.nn_future_times)

  def update_live_torque_params(self, latAccelFactor, latAccelOffset, friction):
    self.torque_params.latAccelFactor = latAccelFactor
    self.torque_params.latAccelOffset = latAccelOffset
    self.torque_params.friction = friction

  def update(self, active, CS, VM, params, steer_limited_by_safety, desired_curvature,
             calibrated_pose, curvature_limited, lat_delay):
    from openpilot.cereal import log
    pid_log = log.ControlsState.LateralTorqueState.new_message()

    model_data = self._sm['modelV2'] if self._sm is not None else None
    nnff_lite = self.nnff_loaded and self.nnff_mode >= 1
    nnff_full = self.nnff_loaded and self.nnff_mode == 2

    if not active:
      output_torque = 0.0
      pid_log.active = False
    else:
      actual_curvature = -VM.calc_curvature(math.radians(CS.steeringAngleDeg - params.angleOffsetDeg), CS.vEgo, params.roll)
      roll_compensation = params.roll * ACCELERATION_DUE_TO_GRAVITY
      curvature_deadzone = abs(VM.calc_curvature(math.radians(self.steering_angle_deadzone_deg), CS.vEgo, 0.0))
      desired_lateral_accel = desired_curvature * CS.vEgo ** 2

      actual_lateral_accel = actual_curvature * CS.vEgo ** 2
      lateral_accel_deadzone = curvature_deadzone * CS.vEgo ** 2  # noqa: F841 (StarPilot verbatim)

      low_speed_factor = np.interp(CS.vEgo, LOW_SPEED_X, LOW_SPEED_Y)**2
      setpoint = desired_lateral_accel + low_speed_factor * desired_curvature
      measurement = actual_lateral_accel + low_speed_factor * actual_curvature
      gravity_adjusted_lateral_accel = desired_lateral_accel - roll_compensation

      lookahead_lateral_jerk = 0.0
      if nnff_lite:
        actual_curvature_rate = -VM.calc_curvature(math.radians(CS.steeringRateDeg), CS.vEgo, 0.0)
        actual_lateral_jerk = actual_curvature_rate * CS.vEgo ** 2

        model_good = model_data is not None and len(model_data.orientation.x) >= CONTROL_N

        if model_good:
          # prepare "look-ahead" desired lateral jerk
          lookahead = np.interp(CS.vEgo, self.friction_look_ahead_bp, self.friction_look_ahead_v)
          friction_upper_idx = next((idxs for idxs, value in enumerate(ModelConstants.T_IDXS) if value > lookahead), 16)

          predicted_lateral_jerk = get_predicted_lateral_jerk(model_data.acceleration.y, self.t_diffs)
          desired_lateral_jerk = (np.interp(lat_delay, ModelConstants.T_IDXS, model_data.acceleration.y) - desired_lateral_accel) / lat_delay

          lookahead_lateral_jerk = get_lookahead_value(predicted_lateral_jerk[LAT_PLAN_MIN_IDX:friction_upper_idx], desired_lateral_jerk)

          if lookahead_lateral_jerk == 0.0:
            actual_lateral_jerk = 0.0
            self.lat_accel_friction_factor = 1.0

          lateral_jerk_setpoint = self.lat_jerk_friction_factor * lookahead_lateral_jerk
          lateral_jerk_measurement = self.lat_jerk_friction_factor * actual_lateral_jerk
        else:
          lateral_jerk_setpoint = 0
          lateral_jerk_measurement = 0

        if nnff_full and model_good:
          # update past data
          pitch = 0
          roll = params.roll
          if calibrated_pose is not None:
            pitch = self.pitch.update(calibrated_pose.orientation.pitch)
            roll = roll_pitch_adjust(roll, pitch)

          self.roll_deque.append(roll)
          self.lateral_accel_desired_deque.append(desired_lateral_accel)

          # prepare past and future values, adjusted for longitudinal accel
          adjusted_future_times = [time + 0.5 * CS.aEgo * (time / max(CS.vEgo, 1.0)) for time in self.nn_future_times]
          past_rolls = [self.roll_deque[min(len(self.roll_deque) - 1, offset)] for offset in self.history_frame_offsets]
          future_rolls = [roll_pitch_adjust(np.interp(time, ModelConstants.T_IDXS, model_data.orientation.x) + roll,
                                            np.interp(time, ModelConstants.T_IDXS, model_data.orientation.y) + pitch)
                          for time in adjusted_future_times]

          past_lateral_accels_desired = [self.lateral_accel_desired_deque[min(len(self.lateral_accel_desired_deque) - 1, offset)]
                                         for offset in self.history_frame_offsets]
          future_lateral_accels = [np.interp(time, ModelConstants.T_IDXS, model_data.acceleration.y) for time in adjusted_future_times]

          base_input = [CS.vEgo, roll]
          nnff_common = past_rolls + future_rolls

          # compute NNFF error response
          nnff_setpoint_input = (base_input[:1] + [setpoint, lateral_jerk_setpoint] + base_input[1:] +
                                 [setpoint] * self.past_future_len + nnff_common)
          nnff_measurement_input = (base_input[:1] + [measurement, lateral_jerk_measurement] + base_input[1:] +
                                    [measurement] * self.past_future_len + nnff_common)

          torque_from_setpoint = self.lat_torque_nn_model.evaluate(nnff_setpoint_input)
          torque_from_measurement = self.lat_torque_nn_model.evaluate(nnff_measurement_input)

          pid_log.error = torque_from_setpoint - torque_from_measurement

          error_blend = np.interp(abs(desired_lateral_accel), [1.0, 2.0], [0.0, 1.0])
          if error_blend > 0.0:  # blend in stronger error response when in high lat accel
            torque_from_error = self.lat_torque_nn_model.evaluate([CS.vEgo, setpoint - measurement, lateral_jerk_setpoint - lateral_jerk_measurement, 0.0])
            if sign(pid_log.error) == sign(torque_from_error) and abs(pid_log.error) < abs(torque_from_error):
              pid_log.error = float(pid_log.error * (1.0 - error_blend) + torque_from_error * error_blend)

          # compute feedforward (same as nn setpoint output)
          error = setpoint - measurement
          friction_input = self.lat_accel_friction_factor * error + self.lat_jerk_friction_factor * lookahead_lateral_jerk
          nn_input = [CS.vEgo, desired_lateral_accel, friction_input, roll] + past_lateral_accels_desired + future_lateral_accels + nnff_common
          ff = self.lat_torque_nn_model.evaluate(nn_input)

          # apply friction override for cars with low NN friction response
          if self.nn_friction_override:
            pid_log.error += self.torque_from_lateral_accel(0.0, self.torque_params)
        else:
          torque_from_measurement = self.torque_from_lateral_accel(measurement, self.torque_params)
          torque_from_setpoint = self.torque_from_lateral_accel(setpoint, self.torque_params)

          pid_log.error = float(torque_from_setpoint - torque_from_measurement)

          error = desired_lateral_accel - actual_lateral_accel
          friction_input = self.lat_accel_friction_factor * error + self.lat_jerk_friction_factor * lookahead_lateral_jerk
          ff = self.torque_from_lateral_accel(gravity_adjusted_lateral_accel, self.torque_params)
      else:
        torque_from_measurement = self.torque_from_lateral_accel(measurement, self.torque_params)
        torque_from_setpoint = self.torque_from_lateral_accel(setpoint, self.torque_params)

        pid_log.error = float(torque_from_setpoint - torque_from_measurement)

        ff = self.torque_from_lateral_accel(gravity_adjusted_lateral_accel, self.torque_params)

      freeze_integrator = steer_limited_by_safety or CS.steeringPressed or CS.vEgo < 5
      output_torque = self.pid.update(pid_log.error,
                                      feedforward=ff,
                                      speed=CS.vEgo,
                                      freeze_integrator=freeze_integrator)

      pid_log.active = True
      pid_log.p = float(self.pid.p)
      pid_log.i = float(self.pid.i)
      pid_log.d = float(self.pid.d)
      pid_log.f = float(self.pid.f)
      pid_log.output = float(-output_torque)
      pid_log.actualLateralAccel = float(actual_lateral_accel)
      pid_log.desiredLateralAccel = float(desired_lateral_accel)
      pid_log.saturated = bool(self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS, steer_limited_by_safety, curvature_limited))

    # TODO left is positive in this convention
    return -output_torque, 0.0, pid_log
