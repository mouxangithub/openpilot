from collections import deque

import math
import numpy as np

from cereal import log
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N

from opendbc.car.interfaces import LatControlInputs
from opendbc.car.vehicle_model import ACCELERATION_DUE_TO_GRAVITY
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.common.pid import PIDController

from openpilot.common.params import Params

# At higher speeds (25+mph) we can assume:
# Lateral acceleration achieved by a specific car correlates to
# torque applied to the steering rack. It does not correlate to
# wheel slip, or to speed.

# This controller applies torque to achieve desired lateral
# accelerations. To compensate for the low speed effects we
# use a LOW_SPEED_FACTOR in the error. Additionally, there is
# friction in the steering wheel that needs to be overcome to
# move it at all, this is compensated for too.

LOW_SPEED_X = [0, 10, 20, 30]
LOW_SPEED_Y = [15, 13, 10, 5]


class LatControlTorque(LatControl):
  def __init__(self, CP, CI):
    super().__init__(CP, CI)
    self.torque_params = CP.lateralTuning.torque.as_builder()
    self.pid = PIDController(self.torque_params.kp, self.torque_params.ki,
                             k_f=self.torque_params.kf, pos_limit=self.steer_max, neg_limit=-self.steer_max)
    self.torque_from_lateral_accel = CI.torque_from_lateral_accel()
    self.use_steering_angle = self.torque_params.useSteeringAngle
    self.steering_angle_deadzone_deg = self.torque_params.steeringAngleDeadzoneDeg

    # carrot
    self.frame = 0
    self.params = Params()
    self.lateralTorqueCustom = self.params.get_int("LateralTorqueCustom")
    self.latAccelFactor_default = self.torque_params.latAccelFactor
    self.latAccelOffset_default = self.torque_params.latAccelOffset
    self.friction_default = self.torque_params.friction


  def update_live_torque_params(self, latAccelFactor, latAccelOffset, friction):
    if self.lateralTorqueCustom > 0:
      return

    self.torque_params.latAccelFactor = latAccelFactor
    self.torque_params.latAccelOffset = latAccelOffset
    self.torque_params.friction = friction

  def update(self, active, CS, VM, params, steer_limited_by_controls, desired_curvature, llk, curvature_limited):
    self.frame += 1
    if self.frame % 10 == 0:
      lateralTorqueCustom = self.params.get_int("LateralTorqueCustom")
      if lateralTorqueCustom > 0:
        self.torque_params.latAccelFactor = self.params.get_float("LateralTorqueAccelFactor")*0.001
        self.torque_params.friction = self.params.get_float("LateralTorqueFriction")*0.001
        lateralTorqueKp = self.params.get_float("LateralTorqueKpV")*0.01
        lateralTorqueKi = self.params.get_float("LateralTorqueKiV")*0.01
        lateralTorqueKf = self.params.get_float("LateralTorqueKf")*0.01
        lateralTorqueKd = self.params.get_float("LateralTorqueKd")*0.01
        self.pid._k_p = [[0], [lateralTorqueKp]]
        self.pid._k_i = [[0], [lateralTorqueKi]]
        self.pid.k_f = lateralTorqueKf
        self.pid._k_d = [[0], [lateralTorqueKd]]
        self.torque_params.latAccelOffset = self.latAccelOffset_default
      elif self.lateralTorqueCustom > 1:  # 1 -> 0, reset to default
        self.torque_params.latAccelFactor = self.latAccelFactor_default
        self.torque_params.friction = self.friction_default
        self.torque_params.latAccelOffset = self.latAccelOffset_default
      self.lateralTorqueCustom = lateralTorqueCustom

    pid_log = log.ControlsState.LateralTorqueState.new_message()
    if not active:
      output_torque = 0.0
      pid_log.active = False
      angle_steers_des = float(CS.steeringAngleDeg)
    else:
      angle_steers_des = math.degrees(VM.get_steer_from_curvature(-desired_curvature, CS.vEgo, params.roll))
      angle_steers_des += params.angleOffsetDeg

      actual_curvature_vm = -VM.calc_curvature(math.radians(CS.steeringAngleDeg - params.angleOffsetDeg), CS.vEgo, params.roll)
      roll_compensation = params.roll * ACCELERATION_DUE_TO_GRAVITY
      if self.use_steering_angle:
        actual_curvature = actual_curvature_vm
        curvature_deadzone = abs(VM.calc_curvature(math.radians(self.steering_angle_deadzone_deg), CS.vEgo, 0.0))
      else:
        actual_curvature_llk = llk.angularVelocityCalibrated.value[2] / CS.vEgo
        actual_curvature = np.interp(CS.vEgo, [2.0, 5.0], [actual_curvature_vm, actual_curvature_llk])
        curvature_deadzone = 0.0
      desired_lateral_accel = desired_curvature * CS.vEgo ** 2

      # desired rate is the desired rate of change in the setpoint, not the absolute desired curvature
      # desired_lateral_jerk = desired_curvature_rate * CS.vEgo ** 2
      actual_lateral_accel = actual_curvature * CS.vEgo ** 2
      lateral_accel_deadzone = curvature_deadzone * CS.vEgo ** 2

      low_speed_factor = np.interp(CS.vEgo, LOW_SPEED_X, LOW_SPEED_Y)**2
      setpoint = desired_lateral_accel + low_speed_factor * desired_curvature
      measurement = actual_lateral_accel + low_speed_factor * actual_curvature
      gravity_adjusted_lateral_accel = desired_lateral_accel - roll_compensation
      torque_from_setpoint = self.torque_from_lateral_accel(LatControlInputs(setpoint, roll_compensation, CS.vEgo, CS.aEgo), self.torque_params,
                                                            setpoint, lateral_accel_deadzone, friction_compensation=False, gravity_adjusted=False)
      torque_from_measurement = self.torque_from_lateral_accel(LatControlInputs(measurement, roll_compensation, CS.vEgo, CS.aEgo), self.torque_params,
                                                               measurement, lateral_accel_deadzone, friction_compensation=False, gravity_adjusted=False)
      pid_log.error = float(torque_from_setpoint - torque_from_measurement)
      ff = self.torque_from_lateral_accel(LatControlInputs(gravity_adjusted_lateral_accel, roll_compensation, CS.vEgo, CS.aEgo), self.torque_params,
                                          desired_lateral_accel - actual_lateral_accel, lateral_accel_deadzone, friction_compensation=True,
                                          gravity_adjusted=True)

      freeze_integrator = steer_limited_by_controls or CS.steeringPressed or CS.vEgo < 5
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
      pid_log.saturated = bool(self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS, steer_limited_by_controls, curvature_limited))

    # TODO left is positive in this convention
    return -output_torque,angle_steers_des, pid_log
