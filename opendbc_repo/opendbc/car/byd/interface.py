#!/usr/bin/env python3
from math import exp

from opendbc.car import get_safety_config, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarInterfaceBase, TorqueFromLateralAccelCallbackType, LateralAccelFromTorqueCallbackType
from opendbc.car.byd.byd_params import BydParams
from opendbc.car.byd.carcontroller import CarController
from opendbc.car.byd.carstate import CarState
from opendbc.car.byd.radar_interface import RadarInterface
from opendbc.car.byd.tuning import Tuning
from opendbc.car.byd.values import (
  BydFlags, BydSafetyFlags, CAR, CanBus, EXP_LONG_CAR, PLATFORM_ATTO3_GENERAL,
  PLATFORM_N3, PLATFORM_QIN_SEAL06, PLATFORM_SEAL, PLATFORM_TENGSHI, PT_RADAR_CAR, RADAR_CAR, TORQUE_LAT_CAR,
)

ButtonType = structs.CarState.ButtonEvent.Type
GearShifter = structs.CarState.GearShifter
TransmissionType = structs.CarParams.TransmissionType
NetworkLocation = structs.CarParams.NetworkLocation


class CarInterface(CarInterfaceBase):
  CarState = CarState
  CarController = CarController
  RadarInterface = RadarInterface

  def torque_from_lateral_accel_siglin(self, latcontrol_inputs, torque_params: structs.CarParams.LateralTorqueTuning,
                                       lateral_accel_error: float, lateral_accel_deadzone: float, friction_compensation: bool,
                                       gravity_adjusted: bool) -> float:
    from opendbc.car import get_friction
    friction = get_friction(lateral_accel_error, lateral_accel_deadzone, 0.02, torque_params, friction_compensation)

    def sig(val):
      if val >= 0:
        return 1 / (1 + exp(-val)) - 0.5
      else:
        z = exp(val)
        return z / (1 + z) - 0.5

    a, b, c = Tuning.LAT_SIGLIN_TABLE
    steer_torque = (sig(latcontrol_inputs.lateral_acceleration * a) * b) + (latcontrol_inputs.lateral_acceleration * c)
    return float(steer_torque / torque_params.latAccelFactor + friction)

  def torque_from_lateral_accel(self) -> TorqueFromLateralAccelCallbackType:
    if BydParams().get_bool("BydLatUseSiglin"):
      return self.torque_from_lateral_accel_siglin
    return self.torque_from_lateral_accel_linear

  def lateral_accel_from_torque(self) -> LateralAccelFromTorqueCallbackType:
    return self.lateral_accel_from_torque_linear

  @staticmethod
  def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw, alpha_long, is_release, docs) -> structs.CarParams:
    ret.brand = "byd"
    params = BydParams()

    if params.get_bool("UseRedPanda"):
      ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.noOutput),
                           get_safety_config(structs.CarParams.SafetyModel.byd)]
      valid_safety_index = 1
    else:
      ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.byd)]
      valid_safety_index = 0

    ret.dashcamOnly = False
    ret.minEnableSpeed = -1.

    if params.get_bool("EnableExtRadar"):
      ret.radarUnavailable = False
    else:
      radar_car = candidate in (PT_RADAR_CAR | RADAR_CAR)
      ret.radarUnavailable = not radar_car

    ret.deprecated.enableBsm = 0x418 in fingerprint[CanBus(fingerprint=fingerprint).ESC]
    ret.transmissionType = TransmissionType.direct

    if candidate in PLATFORM_N3:
      # N3 (SA6/N3A1, CAN FD): angle control via 0x1E2, longitudinal via 0x32E.
      # MRR object list is on the radar bus.
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.N3.value
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ANGLE_MODE.value
      ret.radarUnavailable = False
      ret.steerControlType = structs.CarParams.SteerControlType.angle
      ret.flags |= BydFlags.ANGLE_CONTROL.value
      ret.openpilotLongitudinalControl = True
      ret.pcmCruise = True
      ret.minEnableSpeed = -1.
      ret.minSteerSpeed = 0.
      ret.autoResumeSng = True
      ret.stopAccel = -0.3
      ret.longitudinalActuatorDelay = 0.5
      ret.steerActuatorDelay = 0.1
      ret.steerLimitTimer = 0.5
      ret.longitudinalTuning.kiBP = [0.]
      ret.longitudinalTuning.kiV = [1.0]
      return ret

    # --- safety flags (platform flag in low bits, control-mode flags in high bits) ---
    if candidate in PLATFORM_ATTO3_GENERAL:
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ATTO3_GENERAL.value
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ANGLE_MODE.value
    elif candidate in (CAR.BYD_HAN_DM_20, CAR.BYD_HAN_EV_20, CAR.BYD_TANG_DM, CAR.BYD_QIN_PRO):
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.HAN_TANG_DMEV.value
    elif candidate in (CAR.BYD_TANG_DMI_21, CAR.BYD_TANG_DMI_24, CAR.BYD_TANG_DMP_22, CAR.BYD_TANG_DMP_23):
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.TANG_DMI.value
      if candidate in (CAR.BYD_TANG_DMP_22, CAR.BYD_HAN_DMI_22R):
        ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ACC_CRUISEDISP.value
    elif candidate in (CAR.BYD_SONG_PLUS_DMI_21, CAR.BYD_SONG_PLUS_DMI_22, CAR.BYD_SONG_PLUS_DMI_23,
                       CAR.BYD_SONG_PRO_DMI_22, CAR.BYD_SONG_L_DMI_24, CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_25,
                       CAR.BYD_HAN_DMI_22R):
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.SONG_PLUS_DMI.value
      if candidate in (CAR.BYD_HAN_DMI_22, CAR.BYD_HAN_DMI_22R, CAR.BYD_HAN_DMI_22J, CAR.BYD_HAN_DMI_25):
        ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ACC_CRUISEDISP.value
    elif candidate in PLATFORM_QIN_SEAL06:
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.QIN_PLUS_DMI.value
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ANGLE_MODE.value
      if ret.flags & BydFlags.ALT_ACC_CURISE_MODE:
        ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ACC_CRUISEDISP.value
    elif candidate in (CAR.BYD_QIN_PLUS_DMI_23,):
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.QIN_PLUS_DMI.value
    elif candidate in PLATFORM_SEAL:
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.SONG_PLUS_DMI.value
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ANGLE_MODE.value
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ACC_ON1.value
    elif candidate in PLATFORM_TENGSHI:
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.TANG_DMI.value
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ANGLE_MODE.value
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.ACC_CRUISEDISP.value
    elif candidate == CAR.BYD_YUAN_PLUS_DMI_22:
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.YUAN_PLUS_DMI_ATTO3.value
    else:
      ret.safetyConfigs[valid_safety_index].safetyParam |= BydSafetyFlags.SONG_PLUS_DMI.value

    # --- lateral control ---
    if candidate in TORQUE_LAT_CAR:
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    else:
      ret.steerControlType = structs.CarParams.SteerControlType.angle
      ret.flags |= BydFlags.ANGLE_CONTROL.value

    # --- longitudinal ---
    ret.openpilotLongitudinalControl = candidate in EXP_LONG_CAR
    # kpBP/kpV are deprecated in current opendbc LongitudinalPIDTuning; only kiBP/kiV are valid
    ret.longitudinalTuning.kiBP = [0.]
    ret.longitudinalTuning.kiV = [0.3]
    if ret.openpilotLongitudinalControl:
      ret.longitudinalTuning.kiV = [1.0]

    # --- per-platform params ---
    if candidate in TORQUE_LAT_CAR:
      ret.minEnableSpeed = -1.
      ret.minSteerSpeed = 0.1 * CV.KPH_TO_MS
      ret.autoResumeSng = True
      ret.stopAccel = -0.3
      ret.longitudinalActuatorDelay = 0.5
      ret.steerActuatorDelay = 0.2
      ret.steerLimitTimer = 0.6
    elif candidate in PLATFORM_QIN_SEAL06:
      ret.minEnableSpeed = -1.
      ret.minSteerSpeed = 0.
      ret.autoResumeSng = True
      ret.stopAccel = -0.3
      ret.longitudinalActuatorDelay = 0.5
      ret.steerActuatorDelay = 0.3
      ret.steerLimitTimer = 0.5
    elif candidate in (PLATFORM_SEAL | PLATFORM_TENGSHI):
      ret.minEnableSpeed = -1.
      ret.minSteerSpeed = 0.1 * CV.KPH_TO_MS
      ret.autoResumeSng = True
      ret.stopAccel = -0.3
      ret.longitudinalActuatorDelay = 0.5
      ret.steerActuatorDelay = 0.1
      ret.steerLimitTimer = 1.0
    elif candidate in PLATFORM_ATTO3_GENERAL:
      ret.steerControlType = structs.CarParams.SteerControlType.angle
      ret.steerActuatorDelay = 0.35
      ret.steerLimitTimer = 0.4
      ret.minSteerSpeed = 0.
      ret.minEnableSpeed = -1.
      ret.pcmCruise = True
      ret.openpilotLongitudinalControl = False
      ret.radarUnavailable = True
      ret.networkLocation = NetworkLocation.fwdCamera
      ret.longitudinalTuning.kiBP = [0., 35.]
      ret.longitudinalTuning.kiV = [0.18, 0.12]
      return ret
    else:
      ret.dashcamOnly = True

    if candidate in (CAR.BYD_HAN_DM_20, CAR.BYD_HAN_EV_20, CAR.BYD_TANG_DM, CAR.BYD_TANG_DMI_21,
                     CAR.BYD_SONG_PLUS_DMI_21, CAR.BYD_SONG_PLUS_DMI_22, CAR.BYD_SONG_PLUS_DMI_23,
                     CAR.BYD_SONG_PRO_DMI_22, CAR.BYD_QIN_PLUS_DMI_23):
      ret.dashcamOnly = False

    return ret
