import numpy as np
from opendbc.car.structs import car
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N
from openpilot.common.pid import PIDController
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.selfdrive.controls.lib.longcontrol import LongControlSP

CONTROL_N_T_IDX = ModelConstants.T_IDXS[:CONTROL_N]

STOPPING_DECEL_RATE = 0.3  # m/s^2/s while trying to stop

LongCtrlState = car.CarControl.Actuators.LongControlState


def long_control_state_trans(CP_SP, active, long_control_state,
                             should_stop, brake_pressed, cruise_standstill,
                             allow_stopping_release=False):
  # Gas Interceptor
  cruise_standstill = cruise_standstill and not CP_SP.enableGasInterceptor

  starting_condition = (not should_stop and
                        not cruise_standstill and
                        not brake_pressed)

  # StarPilot: some stock ACC platforms keep standstill latched until they see
  # positive drive torque. Once the release request is sustained (hysteresis
  # tracked by the caller), allow leaving stopping even if the bit has not
  # dropped yet. Gated: allow_stopping_release stays False when disabled.
  stopping_release_condition = starting_condition or (
    allow_stopping_release and not should_stop and not brake_pressed)

  if not active:
    long_control_state = LongCtrlState.off

  else:
    if long_control_state == LongCtrlState.off:
      if not starting_condition:
        long_control_state = LongCtrlState.stopping
      else:
        long_control_state = LongCtrlState.pid

    elif long_control_state == LongCtrlState.stopping:
      if stopping_release_condition:
        long_control_state = LongCtrlState.pid

    elif long_control_state == LongCtrlState.pid:
      if should_stop:
        long_control_state = LongCtrlState.stopping

  return long_control_state


class LongControl(LongControlSP):
  def __init__(self, CP, CP_SP):
    self.CP = CP
    self.CP_SP = CP_SP
    self.long_control_state = LongCtrlState.off
    self.pid = PIDController(0.0, (CP.longitudinalTuning.kiBP, CP.longitudinalTuning.kiV),
                             rate=1 / DT_CTRL)
    self.last_output_accel = 0.0
    # StarPilot gates (default off; refreshed once per second of runtime).
    # Params is constructed lazily/defensively so PC test hosts can instantiate
    # LongControl without the fcntl chain.
    self._gate_frame = 0
    self._stop_release_enabled = False
    self._creep_guard_enabled = False
    self._params = None
    self._stop_release_tracker = None

  def _refresh_gates(self):
    self._gate_frame += 1
    if self._gate_frame % 100 != 0:  # 1 s @ 100 Hz
      return
    try:
      if self._params is None:
        from openpilot.common.params import Params
        self._params = Params()
      self._stop_release_enabled = self._params.get_bool("StoppingReleaseHysteresisEnabled")
      self._creep_guard_enabled = self._params.get_bool("NegativeTargetCreepGuardEnabled")
    except Exception:
      # PC test hosts (no fcntl): gates stay off, stock behavior preserved.
      self._stop_release_enabled = False
      self._creep_guard_enabled = False

  def reset(self):
    self.pid.reset()

  def update(self, active, CS, a_target, should_stop, accel_limits):
    """Update longitudinal control. This updates the state machine and runs a PID loop"""
    self.pid.neg_limit = accel_limits[0]
    self.pid.pos_limit = accel_limits[1]

    self._refresh_gates()

    previous_state = self.long_control_state

    # StarPilot stopping-release hysteresis (gated): a sustained planner
    # release request lets the state machine leave stopping even while a
    # stock ACC platform keeps cruiseState.standstill latched.
    allow_stopping_release = False
    if self._stop_release_enabled:
      if self._stop_release_tracker is None:
        from openpilot.selfdrive.controls.lib.longcontrol_stop_release import StopReleaseTracker
        self._stop_release_tracker = StopReleaseTracker()
      allow_stopping_release = self._stop_release_tracker.ready(
        previous_state == LongCtrlState.stopping, float(CS.vEgo), float(a_target),
        bool(should_stop), bool(CS.brakePressed), bool(CS.cruiseState.standstill))

    self.long_control_state = long_control_state_trans(self.CP_SP, active, self.long_control_state,
                                                       should_stop, CS.brakePressed,
                                                       CS.cruiseState.standstill,
                                                       allow_stopping_release=allow_stopping_release)

    if not self.should_exit_stopping(previous_state == LongCtrlState.stopping,
                                     self.long_control_state == LongCtrlState.pid,
                                     a_target):
      self.long_control_state = LongCtrlState.stopping

    if self.long_control_state == LongCtrlState.off:
      self.reset()
      output_accel = 0.

    elif self.long_control_state == LongCtrlState.stopping:
      output_accel = self.last_output_accel
      if output_accel > self.CP.stopAccel:
        output_accel = min(output_accel, 0.0)
        # TODO: can we just go straight to stopAccel?
        output_accel -= self.stopping_decel_rate(CS.vEgo) * DT_CTRL
      self.reset()

    else:  # LongCtrlState.pid
      error = a_target - CS.aEgo
      # StarPilot negative-target creep guard (gated): bleed stale positive
      # integrator charge before update so the command can cross through zero.
      if self._creep_guard_enabled:
        from openpilot.selfdrive.controls.lib.longcontrol_stop_release import (
          cap_positive_output_on_negative_target,
          trim_positive_overshoot_integrator,
        )
        self.pid.i = trim_positive_overshoot_integrator(self.pid.i, float(a_target), float(error), float(CS.vEgo))

      output_accel = self.pid.update(error, speed=CS.vEgo,
                                     feedforward=a_target)

      if self._creep_guard_enabled:
        output_accel = cap_positive_output_on_negative_target(output_accel, float(a_target), float(error), float(CS.vEgo))

      if previous_state == LongCtrlState.stopping:
        output_accel = self.limit_stop_release(self.last_output_accel, output_accel)

    self.last_output_accel = np.clip(output_accel, accel_limits[0], accel_limits[1])
    return self.last_output_accel
