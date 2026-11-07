#!/usr/bin/env python3
import copy

import numpy as np
from opendbc.can import CANDefine, CANParser
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarStateBase
from opendbc.car.byd.tuning import Tuning
from opendbc.car.byd.values import (
  BydFlags, CanBus, CarControllerParams, DBC, LKASConfig, PLATFORM_ATTO3_GENERAL,
  PLATFORM_HAN_DMI, PLATFORM_N3, PLATFORM_QIN_SEAL06, PLATFORM_SEAL, PLATFORM_TENGSHI, PT_RADAR_CAR,
)
from opendbc.car.byd import bydcan
from opendbc.car.byd.byd_params import BydParams
from opendbc.sunnypilot.car.byd.mads import MadsCarState
from opendbc.sunnypilot.car.byd.carstate_ext import CarStateExt

ButtonType = structs.CarState.ButtonEvent.Type
DASHSPEED_BP = [0, 30, 60, 90, 120]
ATTO3_STEER_TEMPLATE_STABLE_FRAMES = 5
ATTO3_CRUISE_DROP_FRAMES = 5


class CarState(CarStateBase, MadsCarState, CarStateExt):
  def __init__(self, CP, CP_SP):
    CarStateBase.__init__(self, CP, CP_SP)
    MadsCarState.__init__(self, CP, CP_SP)
    CarStateExt.__init__(self, CP, CP_SP)

    self.CP = CP
    self.is_atto3_general = CP.carFingerprint in PLATFORM_ATTO3_GENERAL
    self.is_n3 = CP.carFingerprint in PLATFORM_N3

    can_define = CANDefine(DBC[CP.carFingerprint][Bus.pt])
    self.frame = 0
    self.params = BydParams()

    if self.is_n3:
      # VCU_Goal_Gear_S: 1=P 2=R 3=N 4=D (VAL_ in byd_n3_pt.dbc)
      self.n3_gear_values = can_define.dv["VCU_0x342"]["VCU_Goal_Gear_S"]
      self.n3_speed_set_prev = 0
      return

    if self.is_atto3_general:
      self.shifter_values = can_define.dv["DRIVE_STATE"]["GEAR"]
      self.speed_kph = 0
      self.atto3_lkas_hud = dict.fromkeys(bydcan.ATTO3_LKAS_HUD_PASSTHROUGH, 0)
      self.atto3_steer_template = None
      self._atto3_template_candidate = None
      self._atto3_template_frames = 0
      self.atto3_acc_off_frames = 0
      self.atto3_cruise_enabled_last = False
      self.atto3_prev_angle = 0.0
      self.atto3_button_states = {
        ButtonType.leftBlinker: False,
        ButtonType.rightBlinker: False,
        ButtonType.accelCruise: False,
        ButtonType.decelCruise: False,
        ButtonType.lkas: False,
        ButtonType.gapAdjustCruise: False,
      }
      return

    self.shifter_values = can_define.dv["CID_PFTVEH"]["sig_wymsqb"]
    self.speed_kph = 0
    self.mpc_lkas_config = LKASConfig.DISABLE
    self.acc_hud_adas_counter = 0
    self.acc_mpc_state_counter = 0
    self.acc_cmd_counter = 0
    self.eps_warning = False
    self.eps_state_warning_cnt = 0
    self.acc_active_last = 0
    self.low_speed_alert = False
    self.lkas_allowed_speed = False
    self.eps_state = 0
    self.acc_state = 0
    self.cruisemodedisp = 0
    self.adas_set_dist = 4
    self.adas_set_dist_changed = False
    self.adas_set_dist_changed_notified = False
    self.mpc_laks_output = 0
    self.mpc_laks_active = False
    self.mpc_laks_reqprepare = False
    self.fake_driver_torque = 0
    self.cam_lkas = {}
    self.cam_lkas_seal = {}
    self.cam_acc = {}
    self.cam_adas = {}
    self.esc_eps = {}
    self.esc_pcm = {}
    self.setTimeDelay = 0
    self.mrr_leading_dist = 255
    self.btn_acc_cancel = 0
    self.btn_acc_set_reset = 0
    self.modified_stock_long = False
    self.use_byd_tsr = False
    self.bsd_on_camerabus = self.params.get_bool("BydBsdType2")
    self.use_byd_low_speed_long = False
    self.lowCruiseActive = False
    self.lowCruiseSetSpeed = 30
    self.lowCruiseDeactivePending = False
    self.lowCruiseSetSpeedDisplay = 0
    self.speed_correct_30 = self.params.get_int("SpeedCorrect30") * 0.1
    self.speed_correct_60 = self.params.get_int("SpeedCorrect60") * 0.1
    self.speed_correct_90 = self.params.get_int("SpeedCorrect90") * 0.1
    self.speed_correct_120 = self.params.get_int("SpeedCorrect120") * 0.1
    self.dashspeed_fp = [0.0, self.speed_correct_30, self.speed_correct_60, self.speed_correct_90, self.speed_correct_120]

  def update_eps_state_warning(self, eps_state):
    if eps_state in (3, 5, 6, 7, 10):
      self.eps_state_warning_cnt += 1
    else:
      self.eps_state_warning_cnt = 0
    return self.eps_state_warning_cnt > Tuning.EPS_STATE_WARNING_CNT

  # --------------------------------------------------------------------------
  # ATTO3 (byd_general.dbc) angle-control state
  # --------------------------------------------------------------------------
  def _atto3_update_steer_template(self, cam_steer) -> None:
    if not cam_steer["STEER_REQ"]:
      self._atto3_template_candidate = None
      self._atto3_template_frames = 0
      return

    template = {k: int(cam_steer[k]) for k in bydcan.ATTO3_STEER_TEMPLATE_FIELDS}
    if not any(template.values()):
      return

    if template == self._atto3_template_candidate:
      self._atto3_template_frames += 1
    else:
      self._atto3_template_candidate = template
      self._atto3_template_frames = 1

    if self._atto3_template_frames >= ATTO3_STEER_TEMPLATE_STABLE_FRAMES:
      self.atto3_steer_template = template

  def _update_atto3(self, ret: structs.CarState, ret_sp: structs.CarStateSP, can_parsers) -> None:
    cp = can_parsers[Bus.pt]
    cp_cam = can_parsers[Bus.cam]

    ret.steeringAngleOffsetDeg = 0.0
    ret.steeringAngleDeg = cp.vl["STEER_MODULE_2"]["STEER_ANGLE_2"]
    ret.steeringRateDeg = (ret.steeringAngleDeg - self.atto3_prev_angle) / 0.01
    self.atto3_prev_angle = ret.steeringAngleDeg
    ret.steeringTorque = cp.vl["STEER_MODULE_2"]["DRIVER_EPS_TORQUE"]
    ret.steeringTorqueEps = cp.vl["STEERING_TORQUE"]["MAIN_TORQUE"]
    ret.steeringPressed = self.update_steering_pressed(ret.steeringTorque > 80, 5)

    ret.gasPressed = cp.vl["PEDAL"]["GAS_PEDAL"] > 1.0
    brake_pedal = cp.vl["PEDAL"]["BRAKE_PEDAL"]
    ret.brakePressed = brake_pedal > 0.03

    gear_map = {
      1: structs.CarState.GearShifter.park,
      2: structs.CarState.GearShifter.reverse,
      4: structs.CarState.GearShifter.drive,
    }
    ret.gearShifter = gear_map.get(int(cp.vl["DRIVE_STATE"]["GEAR"]), structs.CarState.GearShifter.unknown)

    _SPD_CORR = 40.0 / 53.0
    fl = cp.vl["WHEEL_SPEED"]["WHEELSPEED_FL"] * _SPD_CORR / 3.6
    fr = cp.vl["WHEEL_SPEED"]["WHEELSPEED_FR"] * _SPD_CORR / 3.6
    rl = cp.vl["WHEEL_SPEED"]["WHEELSPEED_BL"] * _SPD_CORR / 3.6
    rr = (fl + fr + rl) / 3.0
    ret.wheelSpeeds.fl = fl
    ret.wheelSpeeds.fr = fr
    ret.wheelSpeeds.rl = rl
    ret.wheelSpeeds.rr = rr
    ret.vEgoRaw = (fl + fr + rl) / 3.0
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    ret.standstill = ret.vEgoRaw < 0.05

    acc_main = bool(cp_cam.vl["ACC_HUD_ADAS"]["ACC_ON1"]) or bool(cp_cam.vl["ACC_HUD_ADAS"]["ACC_ON2"])
    acc_engaged = (bool(cp_cam.vl["ACC_CMD"]["ACC_ON_1"]) and bool(cp_cam.vl["ACC_CMD"]["ACC_ON_2"])
                   and not bool(cp_cam.vl["ACC_CMD"]["CMD_REQ_ACTIVE_LOW"]))

    if acc_engaged:
      self.atto3_acc_off_frames = 0
    else:
      self.atto3_acc_off_frames += 1
    if self.atto3_acc_off_frames == 0:
      self.atto3_cruise_enabled_last = True
    elif self.atto3_acc_off_frames >= ATTO3_CRUISE_DROP_FRAMES:
      self.atto3_cruise_enabled_last = False

    ret.cruiseState.enabled = self.atto3_cruise_enabled_last
    ret.cruiseState.available = acc_main
    ret.cruiseState.speed = cp_cam.vl["ACC_HUD_ADAS"]["SET_SPEED"] * CV.KPH_TO_MS
    ret.cruiseState.standstill = False

    ret.stockLkas = False
    self.atto3_lkas_hud = {k: cp_cam.vl["LKAS_HUD_ADAS"][k] for k in self.atto3_lkas_hud}
    self._atto3_update_steer_template(cp_cam.vl["STEERING_MODULE_ADAS"])

    ret.seatbeltUnlatched = not bool(cp.vl["METER_CLUSTER"]["SEATBELT_DRIVER"])
    ret.doorOpen = any([
      cp.vl["METER_CLUSTER"]["FRONT_LEFT_DOOR"],
      cp.vl["METER_CLUSTER"]["FRONT_RIGHT_DOOR"],
      cp.vl["METER_CLUSTER"]["BACK_LEFT_DOOR"],
      cp.vl["METER_CLUSTER"]["BACK_RIGHT_DOOR"],
    ])

    ret.leftBlinker = bool(cp.vl["STALKS"]["LEFT_BLINKER"])
    ret.rightBlinker = bool(cp.vl["STALKS"]["RIGHT_BLINKER"])

    button_map = {
      ButtonType.leftBlinker: ("STALKS", "LEFT_BLINKER"),
      ButtonType.rightBlinker: ("STALKS", "RIGHT_BLINKER"),
      ButtonType.accelCruise: ("PCM_BUTTONS", "RES_BTN"),
      ButtonType.decelCruise: ("PCM_BUTTONS", "SET_BTN"),
      ButtonType.lkas: ("PCM_BUTTONS", "LKAS_ON_BTN"),
      ButtonType.gapAdjustCruise: ("PCM_BUTTONS", "DEC_DISTANCE_BTN"),
    }
    button_events = []
    for event_type, (msg_name, sig_name) in button_map.items():
      val = bool(cp.vl[msg_name][sig_name])
      if event_type == ButtonType.gapAdjustCruise:
        inc_val = bool(cp.vl["PCM_BUTTONS"]["INC_DISTANCE_BTN"])
        if val != self.atto3_button_states[event_type] or inc_val != self.atto3_button_states[event_type]:
          event = structs.CarState.ButtonEvent.new_message()
          event.type = event_type
          event.pressed = val or inc_val
          button_events.append(event)
          self.atto3_button_states[event_type] = val or inc_val
      else:
        if val != self.atto3_button_states[event_type]:
          event = structs.CarState.ButtonEvent.new_message()
          event.type = event_type
          event.pressed = val
          button_events.append(event)
          self.atto3_button_states[event_type] = val
    ret.buttonEvents = button_events

  # --------------------------------------------------------------------------
  # generic port (byd_generic_pt.dbc)
  # --------------------------------------------------------------------------
  def _update_generic(self, ret: structs.CarState, can_parsers) -> None:
    cp = can_parsers[Bus.pt]
    cp_cam = can_parsers[Bus.cam]

    if self.frame > 500:
      self.modified_stock_long = self.params.get_bool("BydModifiedStockLong")
      self.use_byd_tsr = self.params.get_bool("BydMpcTsr")
      self.use_byd_low_speed_long = self.params.get_bool("BydLowSpdLong")
      self.frame = 0
    else:
      self.frame += 1

    self.mpc_lkas_config = int(cp_cam.vl["CID_HGZKCQ"]["sig_mfykom"])
    lkas_enabled = self.mpc_lkas_config != LKASConfig.DISABLE
    self.acc_state = int(cp_cam.vl["CID_XQYNBW"]["sig_hprcqm"])
    self.cruisemodedisp = int(cp_cam.vl["CID_XQYNBW"]["sig_ohsrtt"])
    old_gap = self.adas_set_dist
    self.adas_set_dist = int(cp_cam.vl["CID_XQYNBW"]["sig_ijrdxw"])
    if old_gap != self.adas_set_dist:
      self.adas_set_dist_changed = True
      self.adas_set_dist_changed_notified = False

    prev_btn_acc_cancel = self.btn_acc_cancel
    prev_btn_acc_set_reset = self.btn_acc_set_reset
    self.btn_acc_cancel = cp.vl["CID_YHMGPU"]["sig_ssvpvb"]
    self.btn_acc_set_reset = cp.vl["CID_YHMGPU"]["sig_ymtlod"]

    dash_speed = int(cp.vl["CID_QXPDTS"]["sig_mniqdb"])
    cluster_kph = dash_speed * CarControllerParams.K_DASHSPEED
    correction = np.interp(cluster_kph, DASHSPEED_BP, self.dashspeed_fp)
    self.speed_kph = float(cluster_kph + correction)
    ret.vEgoRaw = self.speed_kph * CV.KPH_TO_MS
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    ret.vEgoCluster = ret.vEgoRaw
    ret.standstill = dash_speed == 0

    if self.CP.minSteerSpeed > 0:
      if self.speed_kph > 0.5:
        self.lkas_allowed_speed = True
      elif self.speed_kph < 0.1:
        self.lkas_allowed_speed = False
    else:
      self.lkas_allowed_speed = True

    gear_raw = int(cp.vl["CID_PFTVEH"]["sig_wymsqb"])
    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(gear_raw, None))
    ret.genericToggle = bool(cp.vl["CID_QMUUVA"]["sig_pjswju"])

    if self.CP.deprecated.enableBsm:
      bsm_cp = cp_cam if self.bsd_on_camerabus else cp
      ret.leftBlindspot = bool(bsm_cp.vl["CID_WMSVRZ"]["sig_ebwnrw"])
      ret.rightBlindspot = bool(bsm_cp.vl["CID_WMSVRZ"]["sig_rxlfvj"])

    ret.steeringAngleOffsetDeg = Tuning.STEERING_ANGLE_OFFSET
    ret.steeringAngleDeg = cp.vl["CID_VSUYVS"]["sig_uefwof"] + Tuning.STEERING_ANGLE_OFFSET
    ret.steeringRateDeg = cp.vl["CID_VSUYVS"]["sig_ttcoap"]

    if self.CP.flags & BydFlags.ALT_INDICATOR:
      ret.leftBlinker = cp.vl["CID_QMUUVA"]["sig_cvzplw"] == 3
      ret.rightBlinker = cp.vl["CID_QMUUVA"]["sig_cvzplw"] == 5
    else:
      ret.leftBlinker = bool(cp.vl["CID_QMUUVA"]["sig_ecghww"])
      ret.rightBlinker = bool(cp.vl["CID_QMUUVA"]["sig_qofkml"])

    if self.CP.flags & BydFlags.SETSPEED_X10:
      set_speed_kph = cp_cam.vl["CID_XQYNBW"]["sig_gqnxpm"] * 10
    else:
      set_speed_kph = cp_cam.vl["CID_XQYNBW"]["sig_gqnxpm"]

    if self.CP.flags & BydFlags.BCM_SEAL:
      door_msg = cp.vl["CID_QSAUBE"]
      ret.doorOpen = any([
        door_msg["sig_lzlffi"] != 1, door_msg["sig_kftxmm"] != 1,
        door_msg["sig_ktlxyu"] != 1, door_msg["sig_jhvaxq"] != 1,
      ])
      ret.seatbeltUnlatched = door_msg["sig_kftyqu"] != 2
    else:
      door_msg = cp.vl["CID_SROETQ"]
      ret.doorOpen = any([door_msg["sig_lzlffi"], door_msg["sig_kftxmm"], door_msg["sig_ktlxyu"], door_msg["sig_jhvaxq"]])
      ret.seatbeltUnlatched = door_msg["sig_kftyqu"] != 1

    if self.CP.flags & BydFlags.ALT_PCM_BTN:
      button_events = [
        *create_button_events(self.btn_acc_cancel, prev_btn_acc_cancel, {1: ButtonType.setCruise}),
        *create_button_events(
          self.btn_acc_set_reset,
          prev_btn_acc_set_reset,
          {1: ButtonType.decelCruise, 3: ButtonType.accelCruise},
        ),
      ]
    else:
      button_events = [
        *create_button_events(self.btn_acc_cancel, prev_btn_acc_cancel, {1: ButtonType.cancel}),
        *create_button_events(
          self.btn_acc_set_reset,
          prev_btn_acc_set_reset,
          {1: ButtonType.decelCruise, 3: ButtonType.accelCruise},
        ),
      ]

    if self.CP.flags & BydFlags.ALT_ACC_EPS_SEAL:
      eps_msg = cp.vl["CID_KERMHK"]
      self.eps_state = int(eps_msg["sig_rcgbok"])
      self.eps_warning = self.update_eps_state_warning(self.eps_state)
      ret.steeringTorque = eps_msg["sig_bhnetn"]
      ret.steeringTorqueEps = eps_msg["sig_itfrci"]
      self.eps_state_counter = int(eps_msg["sig_fghgbq"])
      self.esc_eps = copy.copy(eps_msg)
    else:
      eps_msg = cp.vl["CID_IQMESB"] if "CID_IQMESB" in cp.vl else {}
      self.eps_state = int(eps_msg.get("sig_rcgbok", 0))
      self.eps_warning = self.update_eps_state_warning(self.eps_state)
      ret.steeringTorque = eps_msg.get("sig_bhnetn", 0)
      ret.steeringTorqueEps = eps_msg.get("sig_itfrci", 0)
      self.eps_state_counter = int(eps_msg.get("sig_fghgbq", 0))
      self.esc_eps = copy.copy(eps_msg)

    ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > Tuning.STEER_PRESSED_THRESHOLD, 5)
    brake_pedal_raw = int(cp.vl["CID_GDWRBP"]["sig_wrfhru"])
    ret.brakePressed = brake_pedal_raw != 0
    gas_pedal_raw = int(cp.vl["CID_GDWRBP"]["sig_oefitp"])
    ret.gasPressed = gas_pedal_raw != 0

    ret.cruiseState.available = lkas_enabled and not ret.steerFaultPermanent
    ret.cruiseState.enabled = ret.cruiseState.available and self.acc_state in (3, 5)
    ret.cruiseState.speed = set_speed_kph * CV.KPH_TO_MS
    ret.cruiseState.speedCluster = ret.cruiseState.speed
    ret.stockFcw = bool(cp_cam.vl["CID_XQYNBW"]["sig_znmccg"])
    ret.stockAeb = bool(cp_cam.vl["CID_XQYNBW"]["sig_rqvixu"])

    if self.CP.carFingerprint in PT_RADAR_CAR:
      track_id = int(cp_cam.vl["CID_NCBHOL"]["sig_qfnwgn"]) if "CID_NCBHOL" in cp_cam.vl else 0
      if track_id == 2 and bool(cp_cam.vl["CID_NCBHOL"]["sig_ijbmoi"]):
        self.mrr_leading_dist = int(cp_cam.vl["CID_NCBHOL"]["sig_voxvab"])
      elif track_id == 2:
        self.mrr_leading_dist = 255
      else:
        self.mrr_leading_dist = 0

    self.acc_hud_adas_counter = cp_cam.vl["CID_XQYNBW"]["sig_fghgbq"]
    self.acc_mpc_state_counter = cp_cam.vl["CID_HGZKCQ"]["sig_fghgbq"]
    self.acc_cmd_counter = cp_cam.vl["CID_RJDCMR"]["sig_fghgbq"]
    self.cam_lkas = copy.copy(cp_cam.vl["CID_HGZKCQ"])
    self.cam_adas = copy.copy(cp_cam.vl["CID_XQYNBW"])
    self.cam_acc = copy.copy(cp_cam.vl["CID_RJDCMR"])
    self.esc_pcm = copy.copy(cp.vl["CID_YHMGPU"])

    if self.CP.carFingerprint in (PLATFORM_SEAL | PLATFORM_TENGSHI | PLATFORM_QIN_SEAL06):
      self.cam_lkas_seal = copy.copy(cp_cam.vl["CID_TCDUBH"]) if "CID_TCDUBH" in cp_cam.vl else {}

    if self.adas_set_dist_changed:
      button_events.append(structs.CarState.ButtonEvent(pressed=not self.adas_set_dist_changed_notified,
                                                        type=ButtonType.gapAdjustCruise))
      self.adas_set_dist_changed_notified = not self.adas_set_dist_changed_notified
      if not self.adas_set_dist_changed_notified:
        self.adas_set_dist_changed = False

    ret.buttonEvents = button_events

  # --------------------------------------------------------------------------
  # N3 platform (byd_n3_pt.dbc, CAN FD SA6/N3A1)
  # --------------------------------------------------------------------------
  def _update_n3(self, ret: structs.CarState, ret_sp: structs.CarStateSP, can_parsers) -> None:
    cp = can_parsers[Bus.pt]
    cp_cam = can_parsers[Bus.cam]

    # --- steering: EPS_0x06D @10ms (64B), torque in physical Nm ---
    eps = cp.vl["EPS_0x06D"]
    ret.steeringAngleOffsetDeg = 0.0
    ret.steeringAngleDeg = eps["EPS_SteerWheelAg"] if eps["EPS_SteerWheelAgVld"] else 0.0
    ret.steeringRateDeg = eps["EPS_SteerWheelAgRat"] if eps["EPS_SteerWheelAgRatVld"] else 0.0
    ret.steeringTorque = eps["EPS_DrvrSteerTq"]  # Nm (factor 0.02 in DBC)
    ret.steeringTorqueEps = eps["EPS_DrvrSteerTqFlt"]
    ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > Tuning.N3_STEER_PRESSED_NM, 5)

    # --- wheel speeds: IPB_0x10C @10ms (64B), x0.06875 km/h ---
    ipb = cp.vl["IPB_0x10C"]
    fl = ipb["WheelSpeed_FL"] * 0.06875 / 3.6
    fr = ipb["WheelSpeed_FR"] * 0.06875 / 3.6
    rl = ipb["WheelSpeed_RL"] * 0.06875 / 3.6
    rr = ipb["WheelSpeed_RR"] * 0.06875 / 3.6
    ret.wheelSpeeds.fl = fl
    ret.wheelSpeeds.fr = fr
    ret.wheelSpeeds.rl = rl
    ret.wheelSpeeds.rr = rr
    ret.vEgoRaw = (fl + fr + rl + rr) / 4.0
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    ret.vEgoCluster = ret.vEgoRaw
    ret.standstill = ret.vEgoRaw < 0.1

    # --- pedals + gear: VCU_0x342 @50ms ---
    vcu = cp.vl["VCU_0x342"]
    ret.gasPressed = vcu["VCU_Accelerograph_Depth_S"] > 0
    ret.brakePressed = vcu["VCU_Brake_Depth_S"] > 0
    gear_raw = int(vcu["VCU_Goal_Gear_S"])
    ret.gearShifter = self.parse_gear_shifter(self.n3_gear_values.get(gear_raw, None))

    # --- ACC HUD / state: ADC_0x32D @20ms ---
    hud = cp_cam.vl["ADC_0x32D"]
    acc_mode = int(hud["ACC_Mode_Display_S"])
    # ACC_Mode_Display: 0=OFF 1=Passive 2=StandBy 3=Active 4=BrakeOnly 5=Override
    ret.cruiseState.available = acc_mode >= 2
    ret.cruiseState.enabled = acc_mode in (3, 5)
    ret.cruiseState.speed = hud["Set_Speed_S"] * CV.KPH_TO_MS
    ret.cruiseState.standstill = False
    self.adas_set_dist = int(hud["Tau_Gap_Set_S"])

    ret.stockFcw = bool(hud["CCR_FCW_Error_S"])
    ret.stockAeb = bool(hud["CCR_AEB_Error_S"])

    # --- steering wheel switches: SWS_0x3B0 @50ms ---
    # SWS_Speed_Set: 0=initial, 1/2=decel taps, 3/4=accel taps
    speed_set = int(cp.vl["SWS_0x3B0"]["SWS_Speed_Set_S"])
    ret.buttonEvents = create_button_events(speed_set, self.n3_speed_set_prev, {
      1: ButtonType.decelCruise, 2: ButtonType.decelCruise,
      3: ButtonType.accelCruise, 4: ButtonType.accelCruise,
    })
    self.n3_speed_set_prev = speed_set

  def update(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
    ret = structs.CarState()
    ret_sp = structs.CarStateSP()

    if self.is_atto3_general:
      self._update_atto3(ret, ret_sp, can_parsers)
    elif self.is_n3:
      self._update_n3(ret, ret_sp, can_parsers)
    else:
      self._update_generic(ret, can_parsers)

    MadsCarState.update_mads(self, ret, can_parsers)
    CarStateExt.update(self, ret, ret_sp, can_parsers)

    return ret, ret_sp

  @staticmethod
  def get_can_parsers(CP, CP_SP):
    if CP.carFingerprint in PLATFORM_N3:
      # bus 0 = powertrain/chassis entry (EPS/IPB/VCU/SWS), bus 2 = ADAS domain
      # (ADC echo + our commands). Physical wiring TBD on a real car.
      pt_messages = [
        ("EPS_0x06D", 10), ("IPB_0x10C", 10), ("VCU_0x342", 50), ("SWS_0x3B0", 50),
      ]
      cam_messages = [
        ("ADC_0x32D", 20), ("ADC_0x32E", 20), ("ADC_0x1E2", 20), ("ADC_0x316", 20),
      ]
      return {
        Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], pt_messages, CanBus(CP).ESC),
        Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], cam_messages, CanBus(CP).MPC),
      }

    if CP.carFingerprint in PLATFORM_ATTO3_GENERAL:
      pt_messages = [
        ("STEER_MODULE_2", 100),
        ("STEERING_TORQUE", 100),
        ("PEDAL", 50),
        ("DRIVE_STATE", 50),
        ("WHEEL_SPEED", 50),
        ("METER_CLUSTER", 10),
        ("PCM_BUTTONS", 20),
        ("STALKS", 10),
      ]
      cam_messages = [
        ("ACC_HUD_ADAS", 50),
        ("ACC_CMD", 50),
        ("LKAS_HUD_ADAS", 50),
        ("STEERING_MODULE_ADAS", 50),
      ]
      return {
        Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], pt_messages, CanBus(CP).ESC),
        Bus.cam: CANParser(DBC[CP.carFingerprint].get(Bus.cam, DBC[CP.carFingerprint][Bus.pt]), cam_messages, CanBus(CP).MPC),
      }

    params = BydParams()
    pt_messages = [
      ("CID_VSUYVS", 100), ("CID_QXPDTS", 50), ("CID_GDWRBP", 50),
      ("CID_PFTVEH", 50), ("CID_QMUUVA", 1), ("CID_YHMGPU", 20), ("CID_XMKCQO", 2),
    ]
    cam_messages = [("CID_XQYNBW", 50), ("CID_RJDCMR", 50), ("CID_HGZKCQ", 50)]

    if CP.deprecated.enableBsm:
      if params.get_bool("BydBsdType2"):
        cam_messages.append(("CID_WMSVRZ", 20))
      else:
        pt_messages.append(("CID_WMSVRZ", 20))

    if CP.carFingerprint in (PLATFORM_SEAL | PLATFORM_TENGSHI | PLATFORM_QIN_SEAL06):
      pt_messages.append(("CID_KERMHK", 50))
      pt_messages.append(("CID_QSAUBE", 20))
      cam_messages.append(("CID_TCDUBH", 50))
    elif CP.carFingerprint in PLATFORM_HAN_DMI:
      pt_messages.append(("CID_IQMESB", 50))
      pt_messages.append(("CID_QSAUBE", 20))
    else:
      pt_messages.append(("CID_IQMESB", 50))
      pt_messages.append(("CID_SROETQ", 1))

    if CP.carFingerprint in PT_RADAR_CAR:
      cam_messages.append(("CID_NCBHOL", 60))

    return {
      Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], pt_messages, CanBus(CP).ESC),
      Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], cam_messages, CanBus(CP).MPC),
    }
