#!/usr/bin/env python3
import math
from numbers import Number

from openpilot.cereal import log
from opendbc.car.structs import car
import openpilot.cereal.messaging as messaging
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.dm import is_dm_disabled
from openpilot.common.realtime import config_realtime_process, DT_CTRL, Priority, Ratekeeper
from openpilot.common.swaglog import cloudlog

from opendbc.car.car_helpers import interfaces
from opendbc.car.vehicle_model import VehicleModel
from openpilot.selfdrive.controls.lib.drive_helpers import clip_curvature
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle, STEER_ANGLE_SATURATION_THRESHOLD
from openpilot.selfdrive.controls.lib.latcontrol_curvature import LatControlCurvature
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.modeld.modeld import LAT_SMOOTH_SECONDS
from openpilot.sunnypilot.selfdrive.controls.lib.stopping_controller import StoppingController
from openpilot.sunnypilot.selfdrive.controls.lib.steer_ratio import resolve_vehicle_model_steer_ratio
from openpilot.sunnypilot.common.lateral_arbitration import (
  resolve_torque_control_params,
  resolve_vehicle_model_params,
)
from openpilot.sunnypilot.common.lateral_arbitration_params import read_lateral_arbitration_state
from openpilot.sunnypilot.common.param_read import read_bool, read_float
from openpilot.sunnypilot.common.safe_mode_runtime import enforce_safe_mode
from openpilot.selfdrive.locationd.helpers import PoseCalibrator, Pose

from openpilot.sunnypilot.selfdrive.controls.controlsd_ext import ControlsExt

State = log.SelfdriveState.OpenpilotState
LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection

ACTUATOR_FIELDS = tuple(car.CarControl.Actuators.schema.fields.keys())

# How often the learned-vs-user arbitration state is re-read from Params.
# The knobs behind it are user-facing, so a couple of seconds of latency is
# invisible; Params reads are filesystem hits and must stay off the hot path.
ARBITRATION_REFRESH_FRAMES = 300


class Controls(ControlsExt):
  def __init__(self) -> None:
    self.params = Params()
    cloudlog.info("controlsd is waiting for CarParams")
    self.CP = messaging.log_from_bytes(self.params.get("CarParams", block=True), car.CarParams)
    cloudlog.info("controlsd got CarParams")

    # Initialize sunnypilot controlsd extension and base model state
    ControlsExt.__init__(self, self.CP, self.params)

    self.CI = interfaces[self.CP.carFingerprint](self.CP, self.CP_SP)

    self.sm = messaging.SubMaster(['lateralDelay', 'vehicleParameters', 'lateralTorqueParameters', 'modelV2', 'selfdriveState',
                                   'extrinsicsCalibration', 'deviceMotion', 'longitudinalPlan', 'lateralManeuverPlan', 'carState', 'carOutput',
                                   'driverMonitoringState', 'onroadEvents', 'driverAssistance',
                                   # carrot navigation state, surfaced on HUDControl for brand
                                   # controllers that show it (Hyundai camera-deceleration haptic).
                                   'carrotManSP'] + self.sm_services_ext,
                                  poll='selfdriveState')
    self.pm = messaging.PubMaster(['carControl', 'controlsState'] + self.pm_services_ext)

    self.steer_limited_by_safety = False
    self.curvature = 0.0
    self.desired_curvature = 0.0

    self.pose_calibrator = PoseCalibrator()
    self.calibrated_pose: Pose | None = None

    self.LoC = LongControl(self.CP, self.CP_SP)
    self.stopping_controller = StoppingController(self.CP.stopAccel)
    self.VM = VehicleModel(self.CP)
    self.LaC: LatControl
    # StarPilot lane-centering controller (lazy; enabled via LaneCenteringEnabled)
    self.lane_centering = None
    self._lane_centering_enabled = False
    self._lane_center_offset = 0.0
    self._lane_centering_e2e = 0.0
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      self.LaC = LatControlAngle(self.CP, self.CP_SP, self.CI, DT_CTRL)
    elif self.CP.steerControlType == car.CarParams.SteerControlType.curvature:
      self.LaC = LatControlCurvature(self.CP, self.CP_SP, self.CI, DT_CTRL)
    elif self.CP.lateralTuning.which() == 'pid':
      self.LaC = LatControlPID(self.CP, self.CP_SP, self.CI, DT_CTRL)
    elif self.CP.lateralTuning.which() == 'torque':
      # StarPilot NNFF lateral controller (gated by NNFFMode: 0=off,
      # 1=lite jerk-friction, 2=full NN). Without a matching per-vehicle
      # model it degrades to classic torque math. Note: when a zp tune
      # version resolver builds V0/V2 controllers below, those take over.
      from openpilot.selfdrive.controls.lib.latcontrol_nnff import LatControlNNFF
      nnff_mode = self._nnff_mode_param()
      if nnff_mode > 0:
        self.LaC = LatControlNNFF(self.CP, self.CP_SP, self.CI, DT_CTRL)
        self.LaC.nnff_mode = nnff_mode
        self.LaC.attach_sm(self.sm)
      else:
        self.LaC = LatControlTorque(self.CP, self.CP_SP, self.CI, DT_CTRL)

    self.LaC = ControlsExt.initialize_lateral_control(self, self.LaC, self.CI, DT_CTRL)

  def _nnff_mode_param(self) -> int:
    """0=off, 1=lite (jerk friction only), 2=full NN feedforward."""
    try:
      return int(self.params.get_int("NNFFMode"))
    except Exception:
      # The key is registered in params_keys.h but the device may still be
      # running a libparams_c.so that predates it; treat that as "off".
      return 0

  def _lateral_arbitration_state(self):
    """Read the learned-vs-user arbitration state for the lateral parameters.

    Refreshed on a slow cadence: these are user-facing knobs, so a couple of
    seconds of latency is invisible, and Params reads are filesystem hits.
    """
    self._arbitration_frame = getattr(self, "_arbitration_frame", 0) + 1
    if self._arbitration_frame % ARBITRATION_REFRESH_FRAMES == 0 or not hasattr(self, "_arbitration_state"):
      torque_tune = self.CP.lateralTuning.torque if self.CP.lateralTuning.which() == 'torque' else None
      is_torque_car = torque_tune is not None
      self._arbitration_state = read_lateral_arbitration_state(
        self.params,
        stock_steer_ratio=self.CP.steerRatio,
        stock_friction=float(torque_tune.friction) if torque_tune is not None else 0.0,
        stock_lat_accel_factor=float(torque_tune.latAccelFactor) if torque_tune is not None else 0.0,
        is_torque_car=is_torque_car,
      )
    return self._arbitration_state

  def update(self):
    self.sm.update(15)
    if self.sm.updated["extrinsicsCalibration"]:
      self.pose_calibrator.feed_extrinsics_calibration(self.sm['extrinsicsCalibration'])
    if self.sm.updated["deviceMotion"]:
      device_motion = Pose.from_device_motion(self.sm['deviceMotion'])
      self.calibrated_pose = self.pose_calibrator.build_calibrated_pose(device_motion)

  def state_control(self):
    CS = self.sm['carState']

    # Update VehicleModel
    lp = self.sm['vehicleParameters']
    # StarPilot arbitration: the learner in paramsd keeps refining the steering
    # ratio, but a user-set ratio (CustomSR / SteerRatio) wins over it, and
    # ForceAutoTuneOff pins the model to the user's numbers entirely.
    arbitration = self._lateral_arbitration_state()
    # The live scaling rate applies to the learned ratio only. A ratio the
    # user chose is absolute and must not be scaled a second time - that was
    # the old behaviour of resolve_vehicle_model_steer_ratio, which returned
    # the custom value before it ever looked at the rate.
    learned_sr = resolve_vehicle_model_steer_ratio(lp.steerRatio,
                                                   self.params.get_float("SteerRatioRate"),
                                                   0.0)
    steer_ratio, stiffness = resolve_vehicle_model_params(learned_sr, lp.stiffnessFactor, arbitration)
    x = max(stiffness, 0.1)
    sr = steer_ratio
    self.VM.update_params(x, sr)

    steer_angle_without_offset = math.radians(CS.steeringAngleDeg - lp.angleOffsetDeg)
    self.curvature = -self.VM.calc_curvature(steer_angle_without_offset, CS.vEgo, lp.roll)

    # Update Torque Params
    if self.CP.lateralTuning.which() == 'torque':
      torque_params = self.sm['lateralTorqueParameters']
      torque_tune = self.CP.lateralTuning.torque
      # StarPilot arbitration: the friction and lateral-acceleration factors
      # are learned online, but a user-set value wins over the learned one.
      # ForceAutoTune opens the live path even on a car the learner does not
      # support, which is what makes it a usable override.
      use_live_params = bool(self.sm.all_checks(['lateralTorqueParameters'])) and (
        bool(torque_params.useParams) or arbitration.force_auto_tune)
      lat_accel_factor, lat_accel_offset, friction = resolve_torque_control_params(
        torque_tune.latAccelFactor, torque_tune.latAccelOffset, torque_tune.friction,
        torque_params.latAccelFactorFiltered, torque_params.latAccelOffsetFiltered,
        torque_params.frictionCoefficientFiltered,
        arbitration, use_live_params)
      if use_live_params:
        self.LaC.update_torque_parameters(lat_accel_factor, lat_accel_offset, friction)

        self.LaC.extension.update_limits()

      self.LaC.extension.update_model_v2(self.sm['modelV2'])

      self.LaC.extension.update_lateral_lag(self.lat_delay)

      # Carrot's curve speed, for the `UseLaneLineCurveSpeed` gate in the lane
      # assist: below the configured magnitude the lane-line-derived curvature
      # correction is suppressed, so the model path guides the bend instead. This
      # is the fork's home for cp's `lanefull_mode_enabled` coupling
      # (cp controls/controlsd.py:215); carrotManSP is already subscribed here.
      if self.sm.valid.get('carrotManSP', False):
        self.LaC.extension.update_curve_speed(self.sm['carrotManSP'].vTurnSpeed)

    long_plan = self.sm['longitudinalPlan']
    model_v2 = self.sm['modelV2']

    CC = car.CarControl.new_message()
    CC.enabled = self.sm['selfdriveState'].enabled

    # Check which actuators can be enabled
    standstill = abs(CS.vEgo) <= max(self.CP.minSteerSpeed, 0.3) or CS.standstill

    # Get which state to use for active lateral control
    _lat_active = self.get_lat_active(self.sm)

    CC.latActive = _lat_active and not CS.steerFaultTemporary and not CS.steerFaultPermanent and \
                   (not standstill or self.CP.steerAtStandstill)
    # NOTE: carrot's lat-suspend used to override CC.latActive here, i.e. AFTER the
    # sunnypilot lateral-enable arbitration in get_lat_active(). That made it a second
    # independent gate on the actuator, and it ran regardless of CarrotEnabled because
    # nothing consulted that switch. It is now folded into ControlsExt.get_lat_active
    # (blinker_pause_lateral -> carrot_controls.wants_suspend -> MADS), so lateral
    # enable has exactly one decision point.
    CC.longActive = CC.enabled and not any(e.overrideLongitudinal for e in self.sm['onroadEvents']) and \
                    (self.CP.openpilotLongitudinalControl or not self.pcm_cruise_speed)

    actuators = CC.actuators
    actuators.longControlState = self.LoC.long_control_state

    # Enable blinkers while lane changing
    if model_v2.meta.laneChangeState != LaneChangeState.off:
      CC.leftBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.left
      CC.rightBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.right

    if not CC.latActive:
      self.LaC.reset()
    if not CC.longActive:
      self.LoC.reset()

    # accel PID loop
    pid_accel_limits = self.CI.get_pid_accel_limits(self.CP, self.CP_SP, CS.vEgo, CS.vCruise * CV.KPH_TO_MS)
    actuators.accel = float(self.LoC.update(CC.longActive, CS, long_plan.aTarget, long_plan.shouldStop, pid_accel_limits))
    self.long_accel_sp(actuators, CS, long_plan, pid_accel_limits)  # sunnypilot hook

    # Steering PID loop and lateral MPC
    # Reset desired curvature to current to avoid violating the limits on engage
    if self.sm.valid['lateralManeuverPlan']:
      new_desired_curvature = self.sm['lateralManeuverPlan'].desiredCurvature if CC.latActive else self.curvature
    else:
      new_desired_curvature = model_v2.action.desiredCurvature if CC.latActive else self.curvature
    lat_jerk_factor = self.lane_change_jerk_factor(self.sm, CC.latActive, new_desired_curvature, self.desired_curvature)
    # StarPilot vision lane-centering correction (gated, default off). Adds a
    # small bounded curvature correction toward the (optionally offset) lane
    # center when the model's lane detection is confident. Separate from the
    # integral LateralLaneCentering; do not enable both.
    self._lc_frame = getattr(self, '_lc_frame', 0) + 1
    if self._lc_frame % 100 == 0:
      self._lane_centering_enabled = read_bool(self.params, "LaneCenteringEnabled")
      self._lane_center_offset = read_float(self.params, "LaneCenterOffset")
      self._lane_centering_e2e = 1.0 if read_bool(self.params, "LaneCenteringE2EAuthority") else 0.0
    if self._lane_centering_enabled:
      if self.lane_centering is None:
        from openpilot.selfdrive.controls.lib.lane_centering import LaneCenteringController
        self.lane_centering = LaneCenteringController()
      lane_change_active = self.sm['modelV2'].meta.laneChangeState != 0  # 0 = LaneChangeState.off
      new_desired_curvature = self.lane_centering.update(
        new_desired_curvature, self.sm['modelV2'], CS.vEgo,
        True, self._lane_center_offset, self._lane_centering_e2e,
        CC.latActive, bool(self.sm.all_checks(['modelV2'])),
        lane_change_active=lane_change_active,
        pause_on_signal=True, turn_signal_active=bool(CS.leftBlinker or CS.rightBlinker),
        driver_override=bool(CS.steeringPressed))

    self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll, lat_jerk_factor)
    lat_delay = self.sm["lateralDelay"].lateralDelay + LAT_SMOOTH_SECONDS
    if type(self.LaC).__name__ == 'LatControlNNFF':
      # avoid a hard import just for the isinstance check on every frame
      self.LaC.update_live_delay(lat_delay)
      self._nnff_frame = getattr(self, '_nnff_frame', 0) + 1
      if self._nnff_frame % 100 == 0:
        self.LaC.nnff_mode = self._nnff_mode_param()

    actuators.curvature = self.desired_curvature
    steer, lateral_output, lac_log = self.LaC.update(CC.latActive, CS, self.VM, lp,
                                                     self.steer_limited_by_safety, self.desired_curvature,
                                                     self.calibrated_pose, curvature_limited, lat_delay)
    actuators.torque = float(steer)
    if self.CP.steerControlType == car.CarParams.SteerControlType.curvature:
      actuators.curvature = float(lateral_output)
    else:
      actuators.steeringAngleDeg = float(lateral_output)
    # Ensure no NaNs/Infs
    for p in ACTUATOR_FIELDS:
      attr = getattr(actuators, p)
      if not isinstance(attr, Number):
        continue

      if not math.isfinite(attr):
        cloudlog.error(f"actuators.{p} not finite {actuators.to_dict()}")
        setattr(actuators, p, 0.0)

    return CC, lac_log

  def publish(self, CC, lac_log):
    CS = self.sm['carState']

    # Orientation and angle rates can be useful for carcontroller
    # Only calibrated (car) frame is relevant for the carcontroller
    CC.currentCurvature = self.curvature
    if self.calibrated_pose is not None:
      CC.orientationNED = self.calibrated_pose.orientation.xyz.tolist()
      CC.angularVelocity = self.calibrated_pose.angular_velocity.xyz.tolist()

    CC.cruiseControl.override = CC.enabled and not CC.longActive and (self.CP.openpilotLongitudinalControl or not self.pcm_cruise_speed)
    CC.cruiseControl.cancel = CS.cruiseState.enabled and (not CC.enabled or not self.CP.pcmCruise)
    CC.cruiseControl.resume = CC.enabled and CS.cruiseState.standstill and not self.sm['longitudinalPlan'].shouldStop

    hudControl = CC.hudControl
    hudControl.setSpeed = float(CS.vCruiseCluster * CV.KPH_TO_MS)
    hudControl.speedVisible = CC.enabled
    hudControl.lanesVisible = CC.enabled
    hudControl.leadVisible = self.sm['longitudinalPlan'].hasLead
    hudControl.leadDistanceBars = self.sm['selfdriveState'].personality.raw + 1
    hudControl.visualAlert = self.sm['selfdriveState'].alertHudVisual

    # Carrot navigation state for the brand controllers that present it. These are
    # read-only presentation values (HUDControl, not Actuators) - they let a carcontroller
    # react to "carrot is decelerating for a hazard" without giving carrot a control path.
    # Guarded on validity because carrot_man may not be running at all.
    if self.sm.valid.get('carrotManSP', False):
      carrot = self.sm['carrotManSP']
      hudControl.activeCarrot = int(getattr(carrot, 'activeCarrot', 0) or 0)
      hudControl.atcDistance = float(getattr(carrot, 'xDistToTurn', 0) or 0)
    else:
      hudControl.activeCarrot = 0
      hudControl.atcDistance = 0.0

    hudControl.rightLaneVisible = True
    hudControl.leftLaneVisible = True
    if self.sm.valid['driverAssistance']:
      hudControl.leftLaneDepart = self.sm['driverAssistance'].leftLaneDeparture
      hudControl.rightLaneDepart = self.sm['driverAssistance'].rightLaneDeparture

    if self.get_lat_active(self.sm):
      CO = self.sm['carOutput']
      if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
        self.steer_limited_by_safety = abs(CC.actuators.steeringAngleDeg - CO.actuatorsOutput.steeringAngleDeg) > \
                                              STEER_ANGLE_SATURATION_THRESHOLD
      else:
        self.steer_limited_by_safety = abs(CC.actuators.torque - CO.actuatorsOutput.torque) > 1e-2

    # TODO: both controlsState and carControl valids should be set by
    #       sm.all_checks(), but this creates a circular dependency

    # controlsState
    dat = messaging.new_message('controlsState')
    dat.valid = CS.canValid
    cs = dat.controlsState

    cs.curvature = self.curvature
    cs.longitudinalPlanMonoTime = self.sm.logMonoTime['longitudinalPlan']
    cs.lateralPlanMonoTime = self.sm.logMonoTime['modelV2']
    cs.desiredCurvature = self.desired_curvature
    cs.longControlState = self.LoC.long_control_state
    cs.upAccelCmd = float(self.LoC.pid.p)
    cs.uiAccelCmd = float(self.LoC.pid.i)
    cs.ufAccelCmd = float(self.LoC.pid.f)
    cs.forceDecel = bool((not is_dm_disabled(self.params) and self.sm['driverMonitoringState'].noResponseForceDecel) or
                         (self.sm['selfdriveState'].state == State.softDisabling))

    # trigger the car's stock driver monitoring escalation
    CC.driverMonitoringEscalation = cs.forceDecel

    lat_tuning = self.CP.lateralTuning.which()
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      cs.lateralControlState.angleState = lac_log
    elif self.CP.steerControlType == car.CarParams.SteerControlType.curvature:
      cs.lateralControlState.curvatureState = lac_log
    elif lat_tuning == 'pid':
      cs.lateralControlState.pidState = lac_log
    elif lat_tuning == 'torque':
      cs.lateralControlState.torqueState = lac_log

    self.pm.send('controlsState', dat)

    # carControl
    cc_send = messaging.new_message('carControl')
    cc_send.valid = CS.canValid
    cc_send.carControl = CC
    self.pm.send('carControl', cc_send)

  def run(self):
    rk = Ratekeeper(100, print_delay_threshold=None)
    frame = 0
    while True:
      self.update()
      # Safe Mode re-forces its managed knobs on a slow cadence, because the
      # settings UI and other daemons can write the same keys. It is a no-op
      # when the switch is off.
      enforce_safe_mode(self.params, frame)
      frame += 1
      CC, lac_log = self.state_control()
      self.publish(CC, lac_log)
      self.get_params_sp(self.sm)
      self.run_ext(self.sm, self.pm)
      rk.monitor_time()


def main():
  config_realtime_process(6, Priority.CTRL_HIGH)
  controls = Controls()
  controls.run()


if __name__ == "__main__":
  main()
