from collections import deque
import copy
import math

from opendbc.can import CANDefine, CANParser
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.hyundai.hyundaicanfd import CanBus
from opendbc.car.hyundai.values import HyundaiFlags, CAR, DBC, Buttons, CarControllerParams
from opendbc.car.interfaces import CarStateBase
from opendbc.car.byd.byd_params import BydParams

from opendbc.sunnypilot.car.hyundai.carstate_ext import CarStateExt
from opendbc.sunnypilot.car.hyundai.escc import EsccCarStateBase
from opendbc.sunnypilot.car.hyundai.mads import MadsCarState
from opendbc.sunnypilot.car.hyundai.values import HyundaiFlagsSP

ButtonType = structs.CarState.ButtonEvent.Type

PREV_BUTTON_SAMPLES = 8
CLUSTER_SAMPLE_RATE = 20  # frames
# How often the stock-nav tunables (speed-camera distance, navi control, school zone)
# are re-read from Params. These change rarely, so poll at ~3 s (60 frames @20 Hz)
# instead of reading Params every carstate update.
VEHICLE_SPEED_CAMERA_PARAM_UPDATE_FRAMES = 60
STANDSTILL_THRESHOLD = 12 * 0.03125

# Cancel button can sometimes be ACC pause/resume button, main button can also enable on some cars
ENABLE_BUTTONS = (Buttons.RES_ACCEL, Buttons.SET_DECEL, Buttons.CANCEL)
BUTTONS_DICT = {Buttons.RES_ACCEL: ButtonType.accelCruise, Buttons.SET_DECEL: ButtonType.decelCruise,
                Buttons.GAP_DIST: ButtonType.gapAdjustCruise, Buttons.CANCEL: ButtonType.cancel}


CANFD_NAVI_PROFILE_MSG = "CANFD_NAVI_PROFILE_093"
CANFD_NAVI_STATUS_MSG = "CANFD_NAVI_STATUS_380"
CANFD_NAVI_CAMERA_ACTIVE_BIT = 0x40
CANFD_NAVI_STATUS_TIMEOUT_NS = 1_000_000_000

# PV5 wrapped-navigation HDA frame (0x364). This fork does not decode the PV5
# wrapped variant (canfd_wrapped_navi stays False), so the name is only a token.
CANFD_HDA_INFO_MSG = "CANFD_HDA_INFO_364"

# Stock-navigation camera/event tunables (carrot navi gates read these). The
# camera "kind" nibble values that mark a real speed camera; controlled-access
# road classes (highway/motorway) used to decide whether to honour the event.
VEHICLE_NAVI_CAMERA_KINDS = (1, 2, 3)
VEHICLE_NAVI_CONTROLLED_ACCESS_LINK_CLASSES = (1, 2)
VEHICLE_NAVI_CONTROLLED_ACCESS_ROAD_CLASSES = (1, 2)
VEHICLE_NAVI_CAMERA_MATCH_MARGIN = 5.0        # m tolerance matching a preview to its pass
VEHICLE_NAVI_MAX_EVENTS = 8                  # buffered navi events
VEHICLE_NAVI_MAX_EVENT_DISTANCE = 2000       # m, ignore previews farther than this
VEHICLE_NAVI_PASSED_EVENT_DISTANCE = 30      # m behind current distance counts as passed
VEHICLE_NAVI_SCHOOL_ZONE_MAX_DISTANCE = 500  # m a school-zone alert stays active
VEHICLE_NAVI_POSITION_TIMEOUT_NS = 3_000_000_000   # navi position validity
VEHICLE_NAVI_ROUTE_TIMEOUT_NS = 10_000_000_000     # navi route validity


def is_canfd_navi_camera_active(values) -> bool:
  return bool(int(values.get("CAMERA_STATUS", 0)) & CANFD_NAVI_CAMERA_ACTIVE_BIT)


class CarState(CarStateBase, EsccCarStateBase, MadsCarState, CarStateExt):
  def __init__(self, CP, CP_SP):
    CarStateBase.__init__(self, CP, CP_SP)
    EsccCarStateBase.__init__(self)
    MadsCarState.__init__(self, CP, CP_SP)
    CarStateExt.__init__(self, CP, CP_SP)
    can_define = CANDefine(DBC[CP.carFingerprint][Bus.pt])

    self.cruise_buttons: deque = deque([Buttons.NONE] * PREV_BUTTON_SAMPLES, maxlen=PREV_BUTTON_SAMPLES)
    self.main_buttons: deque = deque([Buttons.NONE] * PREV_BUTTON_SAMPLES, maxlen=PREV_BUTTON_SAMPLES)
    self.lda_button = 0

    self.gear_msg_canfd = "ACCELERATOR" if CP.flags & HyundaiFlags.EV else \
                          "GEAR_ALT" if CP.flags & HyundaiFlags.CANFD_ALT_GEARS else \
                          "GEAR_ALT_2" if CP.flags & HyundaiFlags.CANFD_ALT_GEARS_2 else \
                          "GEAR_SHIFTER"
    if CP.flags & HyundaiFlags.CANFD:
      self.shifter_values = can_define.dv[self.gear_msg_canfd]["GEAR"]
    elif CP.flags & (HyundaiFlags.HYBRID | HyundaiFlags.EV):
      self.shifter_values = can_define.dv["ELECT_GEAR"]["Elect_Gear_Shifter"]
    elif self.CP.flags & HyundaiFlags.CLUSTER_GEARS:
      self.shifter_values = can_define.dv["CLU15"]["CF_Clu_Gear"]
    elif self.CP.flags & HyundaiFlags.TCU_GEARS:
      self.shifter_values = can_define.dv["TCU12"]["CUR_GR"]
    elif CP.flags & HyundaiFlags.FCEV:
      self.shifter_values = can_define.dv["EMS20"]["HYDROGEN_GEAR_SHIFTER"]
    else:
      self.shifter_values = can_define.dv["LVR12"]["CF_Lvr_Gear"]

    self.accelerator_msg_canfd = "ACCELERATOR" if CP.flags & HyundaiFlags.EV else \
                                 "ACCELERATOR_ALT" if CP.flags & HyundaiFlags.HYBRID else \
                                 "ACCELERATOR_BRAKE_ALT"
    self.cruise_btns_msg_canfd = "CRUISE_BUTTONS_ALT" if CP.flags & HyundaiFlags.CANFD_ALT_BUTTONS else \
                                 "CRUISE_BUTTONS"
    self.is_metric = False
    self.buttons_counter = 0

    self.cruise_info = {}

    # On some cars, CLU15->CF_Clu_VehicleSpeed can oscillate faster than the dash updates. Sample at 5 Hz
    self.cluster_speed = 0
    self.cluster_speed_counter = CLUSTER_SAMPLE_RATE

    self.params = CarControllerParams(CP)
    # Persistent openpilot Params for the stock-nav CAN tunables below;
    # CarControllerParams only carries tuning constants (e.g. STEER_THRESHOLD).
    self.op_params = BydParams()

    # Stock-navigation CAN state (cp L6). Only the legacy 0x4BE-family profile exists here;
    # the PV5 wrapped-navigation variant is not in this fork.
    self.navi_profile_msg = "NEW_MSG_4BE"
    self.navi_position_4b4 = None
    self.navi_segment_4b9 = None
    self.navi_profile_4be = None
    self.hda_info_4a3 = None  # not decoded in this fork; navi helpers None-guard it
    self.pv5_section_start_prev = False
    # this fork does not decode the PV5 wrapped-navigation CAN variant, so the
    # CANFD nav section is never read from the alt/wrapped parser
    self.canfd_wrapped_navi = False
    self.totalDistance = 0.0
    self.vehicleSpeedCameraParamsCounter = 0
    self.vehicleSpeedCameraDistanceTime = 0.0
    self.vehicleNaviCanControl = min(3, max(0, self.op_params.get_int("VehicleNaviCanControl")))
    self.vehicleNaviSchoolZoneControl = self.op_params.get_bool("VehicleNaviSchoolZoneControl")
    self.vehicleNaviEvents = []
    self.vehicleNaviSegmentTimestamp = 0
    self.vehicleNaviProfileTimestamp = 0
    self.vehicleNaviAvailable = False
    self.vehicleNaviRouteResetTimestamp = 0
    self.vehicleNaviRouteState = 0
    self.vehicleNaviRoutePathIndex = None
    self.vehicleNaviRoadClass = 7
    self.vehicleNaviCameraTarget = None
    self.vehicleNaviCameraStatusEvent = None
    self.vehicleNaviCameraStatusSpeed = 0.0
    self.vehicleNaviCameraStatusTarget = None
    self.vehicleNaviSpeedZoneActive = False
    self.vehicleNaviSpeedZoneSpeed = 0.0
    self.vehicleNaviSchoolZoneActive = False
    self.vehicleNaviSchoolZoneStartDistance = 0.0
    self.vehicleNaviSchoolZoneUsesCameraStatus = False

  def recent_button_interaction(self) -> bool:
    # On some newer model years, the CANCEL button acts as a pause/resume button based on the PCM state
    # To avoid re-engaging when openpilot cancels, check user engagement intention via buttons
    # Main button also can trigger an engagement on these cars
    return any(btn in ENABLE_BUTTONS for btn in self.cruise_buttons) or any(self.main_buttons)

  def update(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
    cp = can_parsers[Bus.pt]
    cp_cam = can_parsers[Bus.cam]

    if self.CP.flags & HyundaiFlags.CANFD:
      return self.update_canfd(can_parsers)

    ret = structs.CarState()
    ret_sp = structs.CarStateSP()
    cp_cruise = cp_cam if self.CP.flags & HyundaiFlags.CAMERA_SCC else cp
    self.is_metric = cp.vl["CLU11"]["CF_Clu_SPEED_UNIT"] == 0
    speed_conv = CV.KPH_TO_MS if self.is_metric else CV.MPH_TO_MS

    ret.doorOpen = any([cp.vl["CGW1"]["CF_Gway_DrvDrSw"], cp.vl["CGW1"]["CF_Gway_AstDrSw"],
                        cp.vl["CGW2"]["CF_Gway_RLDrSw"], cp.vl["CGW2"]["CF_Gway_RRDrSw"]])

    ret.seatbeltUnlatched = cp.vl["CGW1"]["CF_Gway_DrvSeatBeltSw"] == 0

    self.parse_wheel_speeds(ret,
      cp.vl["WHL_SPD11"]["WHL_SPD_FL"],
      cp.vl["WHL_SPD11"]["WHL_SPD_FR"],
      cp.vl["WHL_SPD11"]["WHL_SPD_RL"],
      cp.vl["WHL_SPD11"]["WHL_SPD_RR"],
    )
    ret.standstill = cp.vl["WHL_SPD11"]["WHL_SPD_FL"] <= STANDSTILL_THRESHOLD and cp.vl["WHL_SPD11"]["WHL_SPD_RR"] <= STANDSTILL_THRESHOLD

    self.cluster_speed_counter += 1
    if self.cluster_speed_counter > CLUSTER_SAMPLE_RATE:
      self.cluster_speed = cp.vl["CLU15"]["CF_Clu_VehicleSpeed"]
      self.cluster_speed_counter = 0

      # Mimic how dash converts to imperial.
      # Sorento is the only platform where CF_Clu_VehicleSpeed is already imperial when not is_metric
      # TODO: CGW_USM1->CF_Gway_DrLockSoundRValue may describe this
      if not self.is_metric and self.CP.carFingerprint not in (CAR.KIA_SORENTO,):
        self.cluster_speed = math.floor(self.cluster_speed * CV.KPH_TO_MPH + CV.KPH_TO_MPH)

    ret.vEgoCluster = self.cluster_speed * speed_conv

    ret.steeringAngleDeg = cp.vl["SAS11"]["SAS_Angle"]
    ret.steeringRateDeg = cp.vl["SAS11"]["SAS_Speed"]
    ret.leftBlinker, ret.rightBlinker = self.update_blinker_from_lamp(
      50, cp.vl["CGW1"]["CF_Gway_TurnSigLh"], cp.vl["CGW1"]["CF_Gway_TurnSigRh"])
    ret.steeringTorque = cp.vl["MDPS12"]["CR_Mdps_StrColTq"]
    ret.steeringTorqueEps = cp.vl["MDPS12"]["CR_Mdps_OutTq"]
    ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > self.params.STEER_THRESHOLD, 5)
    ret.steerFaultTemporary = cp.vl["MDPS12"]["CF_Mdps_ToiUnavail"] != 0 or cp.vl["MDPS12"]["CF_Mdps_ToiFlt"] != 0

    # cruise state
    if self.CP.openpilotLongitudinalControl:
      # These are not used for engage/disengage since openpilot keeps track of state using the buttons
      ret.cruiseState.available = cp.vl["TCS13"]["ACCEnable"] == 0
      ret.cruiseState.enabled = cp.vl["TCS13"]["ACC_REQ"] == 1
      ret.cruiseState.standstill = False
      ret.cruiseState.nonAdaptive = False
    elif not self.CP_SP.flags & HyundaiFlagsSP.NON_SCC:
      ret.cruiseState.available = cp_cruise.vl["SCC11"]["MainMode_ACC"] == 1
      ret.cruiseState.enabled = cp_cruise.vl["SCC12"]["ACCMode"] != 0
      ret.cruiseState.standstill = cp_cruise.vl["SCC11"]["SCCInfoDisplay"] == 4.
      ret.cruiseState.nonAdaptive = cp_cruise.vl["SCC11"]["SCCInfoDisplay"] == 2.  # Shows 'Cruise Control' on dash
      ret.cruiseState.speed = cp_cruise.vl["SCC11"]["VSetDis"] * speed_conv

      # The gap the PCM is set to, so CruiseHelper can follow it instead of counting
      # distance-button presses. Ported from cp carstate.py:499. 0 means the car does
      # not report one.
      ret.pcmCruiseGap = int(cp_cruise.vl["SCC11"]["TauGapSet"])

    ret.brakePressed = cp.vl["TCS13"]["DriverOverride"] == 2  # 2 includes regen braking by user on HEV/EV
    ret.brakeHoldActive = cp.vl["TCS15"]["AVH_LAMP"] == 2  # 0 OFF, 1 ERROR, 2 ACTIVE, 3 READY
    ret.parkingBrake = cp.vl["TCS13"]["PBRAKE_ACT"] == 1
    ret.espDisabled = cp.vl["TCS11"]["TCS_PAS"] == 1
    ret.espActive = cp.vl["TCS11"]["ABS_ACT"] == 1
    ret.accFaulted = cp.vl["TCS13"]["ACCEnable"] != 0  # 0 ACC CONTROL ENABLED, 1-3 ACC CONTROL DISABLED

    if self.CP.flags & (HyundaiFlags.HYBRID | HyundaiFlags.EV | HyundaiFlags.FCEV):
      if self.CP.flags & HyundaiFlags.FCEV:
        ret.gasPressed = cp.vl["FCEV_ACCELERATOR"]["ACCELERATOR_PEDAL"] > 0
      elif self.CP.flags & HyundaiFlags.HYBRID:
        ret.gasPressed = cp.vl["E_EMS11"]["CR_Vcu_AccPedDep_Pos"] > 0
      else:
        ret.gasPressed = cp.vl["E_EMS11"]["Accel_Pedal_Pos"] > 0
    else:
      ret.gasPressed = bool(cp.vl["EMS16"]["CF_Ems_AclAct"])

    # Gear Selection via Cluster - For those Kia/Hyundai which are not fully discovered, we can use the Cluster Indicator for Gear Selection,
    # as this seems to be standard over all cars, but is not the preferred method.
    if self.CP.flags & (HyundaiFlags.HYBRID | HyundaiFlags.EV):
      gear = cp.vl["ELECT_GEAR"]["Elect_Gear_Shifter"]
    elif self.CP.flags & HyundaiFlags.FCEV:
      gear = cp.vl["EMS20"]["HYDROGEN_GEAR_SHIFTER"]
    elif self.CP.flags & HyundaiFlags.CLUSTER_GEARS:
      gear = cp.vl["CLU15"]["CF_Clu_Gear"]
    elif self.CP.flags & HyundaiFlags.TCU_GEARS:
      gear = cp.vl["TCU12"]["CUR_GR"]
    else:
      gear = cp.vl["LVR12"]["CF_Lvr_Gear"]

    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(gear))

    if (not self.CP.openpilotLongitudinalControl or self.CP.flags & HyundaiFlags.CAMERA_SCC) and not self.CP_SP.flags & HyundaiFlagsSP.NON_SCC:
      aeb_src = "FCA11" if self.CP.flags & HyundaiFlags.USE_FCA.value else "SCC12"
      aeb_sig = "FCA_CmdAct" if self.CP.flags & HyundaiFlags.USE_FCA.value else "AEB_CmdAct"
      aeb_warning = cp_cruise.vl[aeb_src]["CF_VSM_Warn"] != 0
      scc_warning = cp_cruise.vl["SCC12"]["TakeOverReq"] == 1  # sometimes only SCC system shows an FCW
      aeb_braking = cp_cruise.vl[aeb_src]["CF_VSM_DecCmdAct"] != 0 or cp_cruise.vl[aeb_src][aeb_sig] != 0
      ret.stockFcw = (aeb_warning or scc_warning) and not aeb_braking
      ret.stockAeb = aeb_warning and aeb_braking

    if self.CP.flags & HyundaiFlags.HAS_BSM:
      ret.leftBlindspot = cp.vl["LCA11"]["CF_Lca_IndLeft"] != 0
      ret.rightBlindspot = cp.vl["LCA11"]["CF_Lca_IndRight"] != 0

    # save the entire LKAS11 and CLU11
    self.lkas11 = copy.copy(cp_cam.vl["LKAS11"])
    self.clu11 = copy.copy(cp.vl["CLU11"])
    self.steer_state = cp.vl["MDPS12"]["CF_Mdps_ToiActive"]  # 0 NOT ACTIVE, 1 ACTIVE
    prev_cruise_buttons = self.cruise_buttons[-1]
    prev_main_buttons = self.main_buttons[-1]
    prev_lda_button = self.lda_button
    self.cruise_buttons.extend(cp.vl_all["CLU11"]["CF_Clu_CruiseSwState"])
    self.main_buttons.extend(cp.vl_all["CLU11"]["CF_Clu_CruiseSwMain"])
    if self.CP.flags & HyundaiFlags.HAS_LDA_BUTTON:
      self.lda_button = cp.vl["BCM_PO_11"]["LDA_BTN"]

    ret.buttonEvents = [*create_button_events(self.cruise_buttons[-1], prev_cruise_buttons, BUTTONS_DICT),
                        *create_button_events(self.main_buttons[-1], prev_main_buttons, {1: ButtonType.mainCruise}),
                        *create_button_events(self.lda_button, prev_lda_button, {1: ButtonType.lkas})]

    if self.CP.openpilotLongitudinalControl:
      ret.cruiseState.available = self.get_main_cruise(ret)

    CarStateExt.update(self, ret, ret_sp, can_parsers, speed_conv)

    ret.blockPcmEnable = not self.recent_button_interaction()

    # low speed steer alert hysteresis logic (only for cars with steer cut off above 10 m/s)
    if ret.vEgo < (self.CP.minSteerSpeed + 2.) and self.CP.minSteerSpeed > 10.:
      self.low_speed_alert = True
    if ret.vEgo > (self.CP.minSteerSpeed + 4.):
      self.low_speed_alert = False
    ret.lowSpeedAlert = self.low_speed_alert

    return ret, ret_sp

  def update_canfd(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
    cp = can_parsers[Bus.pt]
    cp_cam = can_parsers[Bus.cam]
    # Cache this frame's stock-navigation payloads. A message that has never arrived is
    # absent from vl; once present the dict is stable and freshness is judged via ts_nanos.
    self.navi_position_4b4 = cp.vl.get("NEW_MSG_4B4")
    self.navi_segment_4b9 = cp.vl.get("NEW_MSG_4B9")
    self.navi_profile_4be = cp.vl.get("NEW_MSG_4BE")

    ret = structs.CarState()
    ret_sp = structs.CarStateSP()

    self.is_metric = cp.vl["CRUISE_BUTTONS_ALT"]["DISTANCE_UNIT"] != 1
    speed_factor = CV.KPH_TO_MS if self.is_metric else CV.MPH_TO_MS

    if self.CP.flags & (HyundaiFlags.EV | HyundaiFlags.HYBRID):
      ret.gasPressed = cp.vl[self.accelerator_msg_canfd]["ACCELERATOR_PEDAL"] > 1e-5
    else:
      ret.gasPressed = bool(cp.vl[self.accelerator_msg_canfd]["ACCELERATOR_PEDAL_PRESSED"])

    ret.brakePressed = cp.vl["TCS"]["DriverBraking"] == 1

    ret.doorOpen = cp.vl["DOORS_SEATBELTS"]["DRIVER_DOOR"] == 1
    ret.seatbeltUnlatched = cp.vl["DOORS_SEATBELTS"]["DRIVER_SEATBELT"] == 0

    gear = cp.vl[self.gear_msg_canfd]["GEAR"]
    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(gear))

    # TODO: figure out positions
    self.parse_wheel_speeds(ret,
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdFLVal"],
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdFRVal"],
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdRLVal"],
      cp.vl["WHEEL_SPEEDS"]["WHL_SpdRRVal"],
    )
    ret.standstill = cp.vl["WHEEL_SPEEDS"]["WHL_SpdFLVal"] <= STANDSTILL_THRESHOLD and cp.vl["WHEEL_SPEEDS"]["WHL_SpdFRVal"] <= STANDSTILL_THRESHOLD and \
                     cp.vl["WHEEL_SPEEDS"]["WHL_SpdRLVal"] <= STANDSTILL_THRESHOLD and cp.vl["WHEEL_SPEEDS"]["WHL_SpdRRVal"] <= STANDSTILL_THRESHOLD

    ret.steeringRateDeg = cp.vl["STEERING_SENSORS"]["STEERING_RATE"]
    ret.steeringAngleDeg = cp.vl["STEERING_SENSORS"]["STEERING_ANGLE"]
    ret.steeringTorque = cp.vl["MDPS"]["MDPS_StrTqSnsrVal"]
    ret.steeringTorqueEps = cp.vl["MDPS"]["MDPS_OutTqVal"]
    ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > self.params.STEER_THRESHOLD, 5)
    ret.steerFaultTemporary = cp.vl["MDPS"]["MDPS_LkaFailSta"] != 0

    # TODO: alt signal usage may be described by cp.vl['BLINKERS']['USE_ALT_LAMP']
    left_blinker_sig, right_blinker_sig = "LEFT_LAMP", "RIGHT_LAMP"
    if self.CP.carFingerprint == CAR.HYUNDAI_KONA_EV_2ND_GEN or self.CP_SP.flags & HyundaiFlagsSP.CCNC:
      left_blinker_sig, right_blinker_sig = "LEFT_LAMP_ALT", "RIGHT_LAMP_ALT"
    ret.leftBlinker, ret.rightBlinker = self.update_blinker_from_lamp(50, cp.vl["BLINKERS"][left_blinker_sig],
                                                                      cp.vl["BLINKERS"][right_blinker_sig])
    if self.CP.flags & HyundaiFlags.HAS_BSM:
      ret.leftBlindspot = bool(cp.vl["ADAS_CMD_50_50ms"]["BCW_LtIndSta"])
      ret.rightBlindspot = bool(cp.vl["ADAS_CMD_50_50ms"]["BCW_RtIndSta"])

    # cruise state
    # CAN FD cars enable on main button press, set available if no TCS faults preventing engagement
    ret.cruiseState.available = cp.vl["TCS"]["ACCEnable"] == 0
    if self.CP.openpilotLongitudinalControl:
      # These are not used for engage/disengage since openpilot keeps track of state using the buttons
      ret.cruiseState.enabled = cp.vl["TCS"]["ACC_REQ"] == 1
      ret.cruiseState.standstill = False
    else:
      cp_cruise_info = cp_cam if self.CP.flags & HyundaiFlags.CANFD_CAMERA_SCC else cp
      ret.cruiseState.enabled = cp_cruise_info.vl["SCC_CONTROL"]["ACCMode"] in (1, 2)
      ret.cruiseState.standstill = cp_cruise_info.vl["SCC_CONTROL"]["CRUISE_STANDSTILL"] == 1
      ret.cruiseState.speed = cp_cruise_info.vl["SCC_CONTROL"]["VSetDis"] * speed_factor

      # Ported from cp carstate.py:1154. Clipped to 1..4 because DISTANCE_SETTING is a
      # raw signal and the cluster only has four gap positions; min/max rather than
      # np.clip since this module has no numpy dependency.
      ret.pcmCruiseGap = int(min(max(cp_cruise_info.vl["SCC_CONTROL"]["DISTANCE_SETTING"], 1), 4))
      self.cruise_info = copy.copy(cp_cruise_info.vl["SCC_CONTROL"])

    # Manual Speed Limit Assist is a feature that replaces non-adaptive cruise control on EV CAN FD platforms.
    # It limits the vehicle speed, overridable by pressing the accelerator past a certain point.
    # The car will brake, but does not respect positive acceleration commands in this mode
    # TODO: find this message on ICE & HYBRID cars + cruise control signals (if exists)
    if self.CP.flags & HyundaiFlags.EV:
      ret.cruiseState.nonAdaptive = cp.vl["MANUAL_SPEED_LIMIT_ASSIST"]["MSLA_ENABLED"] == 1

    prev_cruise_buttons = self.cruise_buttons[-1]
    prev_main_buttons = self.main_buttons[-1]
    prev_lda_button = self.lda_button
    self.cruise_buttons.extend(cp.vl_all[self.cruise_btns_msg_canfd]["CRUISE_BUTTONS"])
    self.main_buttons.extend(cp.vl_all[self.cruise_btns_msg_canfd]["ADAPTIVE_CRUISE_MAIN_BTN"])
    self.lda_button = cp.vl[self.cruise_btns_msg_canfd]["LDA_BTN"]
    self.buttons_counter = cp.vl[self.cruise_btns_msg_canfd]["COUNTER"]
    ret.accFaulted = cp.vl["TCS"]["ACCEnable"] != 0  # 0 ACC CONTROL ENABLED, 1-3 ACC CONTROL DISABLED

    if self.CP.flags & HyundaiFlags.CANFD_LKA_STEER_MSG:
      self.lfa_block_msg = copy.copy(cp_cam.vl["CAM_0x362"] if self.CP.flags & HyundaiFlags.CANFD_LKA_STEER_MSG_ALT
                                          else cp_cam.vl["CAM_0x2a4"])

    MadsCarState.update_mads_canfd(self, ret, can_parsers)

    ret.buttonEvents = [*create_button_events(self.cruise_buttons[-1], prev_cruise_buttons, BUTTONS_DICT),
                        *create_button_events(self.main_buttons[-1], prev_main_buttons, {1: ButtonType.mainCruise}),
                        *create_button_events(self.lda_button, prev_lda_button, {1: ButtonType.lkas})]

    if self.CP.openpilotLongitudinalControl:
      ret.cruiseState.available = self.get_main_cruise(ret)

    CarStateExt.update_canfd_ext(self, ret, ret_sp, can_parsers, speed_factor)

    ret.blockPcmEnable = not self.recent_button_interaction()

    # Stock-navigation CAN state machine (cp L6). Writes the vehicleNavi*/schoolZone
    # fields carrot's navi gates read; without it those gates permanently see defaults.
    self._update_vehicle_speed_camera_params()
    self._update_vehicle_navi_events(cp, ret, False, None)

    return ret, ret_sp

  @staticmethod
  def _vehicle_speed_camera_distance_time(raw_value):
    return min(200, max(10, raw_value)) / 10.0

  @staticmethod
  def _vehicle_navi_can_control_mode(raw_value):
    return min(3, max(0, raw_value))

  def _update_vehicle_speed_camera_params(self):
    self.vehicleSpeedCameraParamsCounter += 1
    if self.vehicleSpeedCameraParamsCounter < VEHICLE_SPEED_CAMERA_PARAM_UPDATE_FRAMES:
      return False

    self.vehicleSpeedCameraParamsCounter = 0
    distance_time_tenths = self.op_params.get_int("VehicleSpeedCameraDistanceTime")
    distance_time = self._vehicle_speed_camera_distance_time(distance_time_tenths)
    changed = distance_time != self.vehicleSpeedCameraDistanceTime
    self.vehicleSpeedCameraDistanceTime = distance_time
    if changed and self.vehicleNaviCameraStatusTarget is not None:
      self.vehicleNaviCameraStatusTarget = self.totalDistance + self.vehicleNaviCameraStatusSpeed * distance_time
    vehicle_navi_can_control = self._vehicle_navi_can_control_mode(self.op_params.get_int("VehicleNaviCanControl"))
    if vehicle_navi_can_control != self.vehicleNaviCanControl:
      self.vehicleNaviCanControl = vehicle_navi_can_control
      if not vehicle_navi_can_control:
        self._clear_vehicle_navi_events()
        self._clear_vehicle_navi_speed_zone()
      elif vehicle_navi_can_control >= 2:
        self._clear_vehicle_navi_route_filtered_events()
    vehicle_navi_school_zone_control = self.op_params.get_bool("VehicleNaviSchoolZoneControl")
    if vehicle_navi_school_zone_control != self.vehicleNaviSchoolZoneControl:
      self.vehicleNaviSchoolZoneControl = vehicle_navi_school_zone_control
      if not vehicle_navi_school_zone_control:
        self._clear_vehicle_navi_school_zone()
    return changed

  def _clear_vehicle_navi_events(self):
    self.vehicleNaviEvents = []
    self.vehicleNaviCameraTarget = None
    self.vehicleNaviCameraStatusEvent = None

  def _clear_vehicle_navi_route_filtered_events(self):
    if self.vehicleNaviCanControl < 2:
      return

    filtered_types = ("bump",) if self.vehicleNaviCanControl == 2 else ("camera", "bump")
    self.vehicleNaviEvents = [event for event in self.vehicleNaviEvents if event["type"] not in filtered_types]
    if self.vehicleNaviCameraStatusEvent is not None and self.vehicleNaviCameraStatusEvent not in self.vehicleNaviEvents:
      self.vehicleNaviCameraStatusEvent = None
      self.vehicleNaviCameraTarget = None
    if self.vehicleNaviCanControl == 3:
      self._clear_vehicle_navi_speed_zone()

  def _clear_vehicle_navi_school_zone(self):
    self.vehicleNaviSchoolZoneActive = False
    self.vehicleNaviSchoolZoneStartDistance = self.totalDistance
    self.vehicleNaviSchoolZoneUsesCameraStatus = False

  def _clear_vehicle_navi_speed_zone(self):
    self.vehicleNaviSpeedZoneActive = False
    self.vehicleNaviSpeedZoneSpeed = 0.0

  def _update_pv5_navi_section(self, cp, cp_alt):
    # PV5 byte 10 bit 4 pulses at entry and again within the section (about
    # five seconds in the 2026-09-07 logs). Latch only its
    # rising edge, and require fresh, agreeing navigation limits to retain it.
    def fresh(parser, name, address, size):
      if parser is None:
        return False
      timestamp = self._vehicle_navi_message_timestamp(parser, name)
      age = cp._last_update_nanos - timestamp
      return (timestamp > 0 and 0 <= age <= CANFD_NAVI_STATUS_TIMEOUT_NS and
              not parser.bus_timeout and len(parser.dat.get(address, b"")) == size)

    status_valid = fresh(cp_alt, CANFD_NAVI_STATUS_MSG, 0x380, 24)
    hda_valid = fresh(cp, CANFD_HDA_INFO_MSG, 0x364, 16)
    if not status_valid or not hda_valid or self.navi_status_380 is None or self.hda_info_4a3 is None:
      self._clear_vehicle_navi_speed_zone()
      # After a dropout, observe an alert-low frame before accepting a new
      # rising edge. A repeated old high must not resurrect a released cap.
      self.pv5_section_start_prev = True
      return

    start = bool(self.navi_status_380["SECTION_ALERT"])
    rising = start and not self.pv5_section_start_prev
    self.pv5_section_start_prev = start
    speed = int(self.navi_status_380["SPEED_LIMIT"])
    valid_limit = (30 < speed <= 150 and speed % 5 == 0 and
                   speed == int(self.hda_info_4a3["SPEED_LIMIT"]) and
                   int(self.hda_info_4a3["MapSource"]) == 2)
    if not self.vehicleNaviCanControl or not valid_limit:
      self._clear_vehicle_navi_speed_zone()
      return

    speed_kph = speed if self.is_metric else speed * CV.MPH_TO_KPH
    if self.vehicleNaviSpeedZoneActive and speed_kph != self.vehicleNaviSpeedZoneSpeed:
      self._clear_vehicle_navi_speed_zone()
    if rising:
      self.vehicleNaviSpeedZoneActive = True
      self.vehicleNaviSpeedZoneSpeed = speed_kph

  @staticmethod
  def _vehicle_navi_message_timestamp(cp, name):
    return max(cp.ts_nanos.get(name, {}).values(), default=0)

  @staticmethod
  def _decode_vehicle_navi_segment(values):
    raw = sum(int(values.get(f"BYTE_{i + 1}", 0)) << (i * 8) for i in range(8))
    return {
      "offset": raw & 0x1fff,
      "path_index": (raw >> 13) & 0x3f,
      "calculated_route": (raw >> 22) & 0x3,
      "functional_road_class": (raw >> 24) & 0x7,
    }

  def _vehicle_navi_is_controlled_access_road(self):
    link_class = int(self.hda_info_4a3.get("LinkClass", 0)) if self.hda_info_4a3 is not None else 0
    return (link_class in VEHICLE_NAVI_CONTROLLED_ACCESS_LINK_CLASSES or
            self.vehicleNaviRoadClass in VEHICLE_NAVI_CONTROLLED_ACCESS_ROAD_CLASSES)

  @staticmethod
  def _decode_vehicle_navi_profile(values):
    return {
      "value": int(values.get("PROLONG_VALUE", 0xffffffff)),
      "offset": int(values.get("PROLONG_OFFSET", 8191)),
      "counter": int(values.get("PROLONG_CYCLIC_COUNTER", 0)),
      "update": int(values.get("PROLONG_UPDATE", 0)),
      "path_index": int(values.get("PROLONG_PATH_INDEX", 0)),
      "profile_type": int(values.get("PROLONG_PROFILE_TYPE", 31)),
    }

  def _vehicle_navi_profile_allowed(self, event_type, profile):
    if not self.vehicleNaviCanControl:
      return False

    # Mode 1 accepts all future profiles. Mode 2 route-gates bumps, and mode 3
    # route-gates cameras and bumps. A route-gated profile must belong to the
    # currently calculated path reported by 0x4B9.
    route_required = (self.vehicleNaviCanControl == 3 or
                      (self.vehicleNaviCanControl == 2 and event_type == "bump"))
    if not route_required:
      return True
    return (self.vehicleNaviRouteState == 1 and
            profile["path_index"] == self.vehicleNaviRoutePathIndex)

  @staticmethod
  def _classify_vehicle_navi_profile(profile):
    if profile["profile_type"] != 16:
      return None

    value = profile["value"]
    if 0 < value <= 0x1ff:
      kind = value & 0xf
      speed_code = value >> 4
      if kind == 7 and profile["offset"] == 0 and 1 < speed_code <= 31:
        return "speed_limit_zone", (speed_code - 1) * 5, kind

    if not 0 < profile["offset"] <= VEHICLE_NAVI_MAX_EVENT_DISTANCE:
      return None
    if value == 6:
      return "bump", 0, 6

    if not 0 < value <= 0x1ff:
      return None
    kind = value & 0xf
    speed_code = value >> 4
    if kind not in VEHICLE_NAVI_CAMERA_KINDS or not 1 < speed_code <= 31:
      return None
    return "camera", (speed_code - 1) * 5, kind

  def _add_vehicle_navi_event(self, event_type, speed, kind, offset):
    target = self.totalDistance + offset
    for event in self.vehicleNaviEvents:
      if event["type"] == event_type and event["speed"] == speed and event["kind"] == kind and abs(event["target"] - target) < 20:
        event["target"] = target
        return

    self.vehicleNaviEvents.append({"type": event_type, "speed": speed, "kind": kind, "target": target})
    self.vehicleNaviEvents.sort(key=lambda event: event["target"])
    self.vehicleNaviEvents = self.vehicleNaviEvents[:VEHICLE_NAVI_MAX_EVENTS]

  def _update_vehicle_navi_events(self, cp, ret, speed_limit_cam, cp_alt=None):
    ret.speedBumpDistance = 0.0
    ret.schoolZoneActive = False
    ret.vehicleNaviActive = False
    ret.vehicleNaviSectionActive = False
    ret.vehicleNaviSpeed = 0.0
    if self.canfd_wrapped_navi:
      self._update_pv5_navi_section(cp, cp_alt)
    profile_timestamp = self._vehicle_navi_message_timestamp(cp, self.navi_profile_msg)
    self.vehicleNaviAvailable = self.vehicleNaviAvailable or profile_timestamp > 0 or self.vehicleNaviSpeedZoneActive
    ret.vehicleNaviAvailable = self.vehicleNaviAvailable
    self.vehicleNaviCameraTarget = None

    # Track the current warning independently of future 0x4BE previews. A new
    # warning must not inherit a distant preview's virtual-distance origin.
    camera_status_speed = ret.speedLimit if speed_limit_cam else 0
    if camera_status_speed != self.vehicleNaviCameraStatusSpeed:
      self.vehicleNaviCameraStatusTarget = (self.totalDistance + camera_status_speed * self.vehicleSpeedCameraDistanceTime
                                            if camera_status_speed > 0 else None)
      self.vehicleNaviCameraStatusSpeed = camera_status_speed

    # 0x4B4 is periodic while the stock navigation is running. Its range
    # average speed is zero outside a section-camera zone and valid inside it.
    # It is therefore authoritative for the *current* section state; 0x4BE is
    # sparse future spot data and must not be used alone to hold this state.
    position_timestamp = self._vehicle_navi_message_timestamp(cp, "NEW_MSG_4B4")
    position_seen = position_timestamp > 0
    position_age = getattr(cp, "_last_update_nanos", position_timestamp) - position_timestamp
    position_recent = position_seen and 0 <= position_age <= VEHICLE_NAVI_POSITION_TIMEOUT_NS
    range_avg_speed = (int(self.navi_position_4b4.get("POS_RANGE_AVG_SPEED", 0))
                       if position_recent and self.navi_position_4b4 is not None else 0)
    range_section_active = 0 < range_avg_speed < 511

    if self.navi_segment_4b9 is not None:
      timestamp = self._vehicle_navi_message_timestamp(cp, "NEW_MSG_4B9")
      if timestamp > self.vehicleNaviSegmentTimestamp:
        self.vehicleNaviSegmentTimestamp = timestamp
        segment = self._decode_vehicle_navi_segment(self.navi_segment_4b9)
        previous_route_state = self.vehicleNaviRouteState
        previous_path_index = self.vehicleNaviRoutePathIndex
        self.vehicleNaviRouteState = segment["calculated_route"]
        self.vehicleNaviRoutePathIndex = (segment["path_index"]
                                          if segment["calculated_route"] in (0, 1) else None)
        if segment["functional_road_class"] != 7:
          self.vehicleNaviRoadClass = segment["functional_road_class"]
        if segment["calculated_route"] == 2:
          self.vehicleNaviRouteResetTimestamp = timestamp
          self._clear_vehicle_navi_events()
          self._clear_vehicle_navi_speed_zone()
          self._clear_vehicle_navi_school_zone()
        elif (self.vehicleNaviCanControl >= 2 and
              (segment["calculated_route"] != 1 or
               (previous_route_state == 1 and previous_path_index != segment["path_index"]))):
          self._clear_vehicle_navi_route_filtered_events()

    route_age = getattr(cp, "_last_update_nanos", max(profile_timestamp, self.vehicleNaviSegmentTimestamp)) - self.vehicleNaviSegmentTimestamp
    if (self.vehicleNaviCanControl >= 2 and self.vehicleNaviRouteState == 1 and
        (route_age < 0 or route_age > VEHICLE_NAVI_ROUTE_TIMEOUT_NS)):
      self.vehicleNaviRouteState = 0
      self.vehicleNaviRoutePathIndex = None
      self._clear_vehicle_navi_route_filtered_events()

    on_controlled_access_road = self._vehicle_navi_is_controlled_access_road()
    if on_controlled_access_road:
      self._clear_vehicle_navi_school_zone()
    if not (self.vehicleNaviCanControl or self.vehicleNaviSchoolZoneControl):
      return False

    if self.navi_profile_4be is not None:
      timestamp = profile_timestamp
      if timestamp > self.vehicleNaviProfileTimestamp:
        self.vehicleNaviProfileTimestamp = timestamp
        profile = self._decode_vehicle_navi_profile(self.navi_profile_4be)
        event = self._classify_vehicle_navi_profile(profile)
        if event is not None and timestamp > self.vehicleNaviRouteResetTimestamp:
          if event[0] == "speed_limit_zone":
            if self.vehicleNaviZoneControlSupported:
              if self._vehicle_navi_profile_allowed("camera", profile) and event[1] > 30:
                self.vehicleNaviSpeedZoneActive = True
                self.vehicleNaviSpeedZoneSpeed = event[1]
              if self.vehicleNaviSchoolZoneControl:
                # 0x77 describes a generic 30 km/h zone and also appears outside
                # school zones. Only use it for the school cap while 0x4A3
                # independently confirms an active 30 km/h camera/zone.
                if event[1] == 30 and speed_limit_cam and ret.speedLimit == 30 and not on_controlled_access_road:
                  self.vehicleNaviSchoolZoneActive = True
                  self.vehicleNaviSchoolZoneStartDistance = self.totalDistance
                  self.vehicleNaviSchoolZoneUsesCameraStatus = True
                else:
                  self._clear_vehicle_navi_school_zone()
          elif self._vehicle_navi_profile_allowed(event[0], profile) and (not on_controlled_access_road or
                                                                          (event[0] != "bump" and not (event[0] == "camera" and event[1] == 30))):
            self._add_vehicle_navi_event(*event, profile["offset"])

    if position_seen:
      if not range_section_active or not self.vehicleNaviCanControl or 0 < ret.speedLimit <= 30:
        self._clear_vehicle_navi_speed_zone()
      elif 30 < ret.speedLimit < 255:
        self.vehicleNaviSpeedZoneActive = True
        self.vehicleNaviSpeedZoneSpeed = ret.speedLimit

    self.vehicleNaviEvents = [event for event in self.vehicleNaviEvents
                              if event["target"] >= self.totalDistance - VEHICLE_NAVI_PASSED_EVENT_DISTANCE and
                              (not on_controlled_access_road or
                               (event["type"] != "bump" and not (event["type"] == "camera" and event["speed"] == 30)))]

    # 0x4BE announces cameras far enough ahead to start a smooth deceleration,
    # but its offset can point 30-40 m beyond the physical camera. Associate
    # the stock 0x4A3 camera status with the matching queued event and retire
    # that event as soon as the status ends. A same-speed profile beyond the
    # warning's initial virtual endpoint (plus offset margin) is a future
    # preview, not evidence of the current camera's distance. Keep this bound
    # fixed in traveled-distance coordinates so later profiles cannot extend it.
    status_event = self.vehicleNaviCameraStatusEvent
    if speed_limit_cam:
      if status_event is not None and status_event["speed"] != camera_status_speed:
        self.vehicleNaviEvents = [event for event in self.vehicleNaviEvents if event is not status_event]
        status_event = None
      if status_event is None:
        matching_cameras = [event for event in self.vehicleNaviEvents
                            if event["type"] == "camera" and event["speed"] == camera_status_speed and
                            self.totalDistance - VEHICLE_NAVI_PASSED_EVENT_DISTANCE <= event["target"] <=
                            (self.vehicleNaviCameraStatusTarget or self.totalDistance) + VEHICLE_NAVI_CAMERA_MATCH_MARGIN]
        if matching_cameras:
          status_event = matching_cameras[0]
      self.vehicleNaviCameraStatusEvent = status_event
    elif status_event is not None:
      self.vehicleNaviEvents = [event for event in self.vehicleNaviEvents if event is not status_event]
      self.vehicleNaviCameraStatusEvent = None

    upcoming = [event for event in self.vehicleNaviEvents if event["target"] > self.totalDistance]

    bumps = [event for event in upcoming if event["type"] == "bump"]
    if bumps:
      ret.speedBumpDistance = bumps[0]["target"] - self.totalDistance

    if self.vehicleNaviSpeedZoneActive and not self.canfd_wrapped_navi and (not position_seen and not speed_limit_cam):
      self._clear_vehicle_navi_speed_zone()

    if self.vehicleNaviSchoolZoneActive:
      camera_status_ended = (self.vehicleNaviSchoolZoneUsesCameraStatus and
                             (not speed_limit_cam or ret.speedLimit != 30))
      distance_expired = self.totalDistance - self.vehicleNaviSchoolZoneStartDistance >= VEHICLE_NAVI_SCHOOL_ZONE_MAX_DISTANCE
      if camera_status_ended or distance_expired:
        self._clear_vehicle_navi_school_zone()

    if self.vehicleNaviSchoolZoneControl and self.vehicleNaviSchoolZoneActive and not on_controlled_access_road:
      ret.schoolZoneActive = True
      ret.speedLimit = 30
      if self.vehicleNaviCanControl:
        ret.vehicleNaviActive = True
        ret.vehicleNaviSpeed = 30
      return False

    if self.vehicleNaviCanControl and self.vehicleNaviSpeedZoneActive:
      ret.vehicleNaviActive = True
      ret.vehicleNaviSectionActive = True
      ret.vehicleNaviSpeed = self.vehicleNaviSpeedZoneSpeed

    cameras = [event for event in upcoming if event["type"] == "camera"]
    # While 0x4A3 identifies the current camera, never replace it with a
    # different future 0x4BE event. If no exact match exists, the caller falls
    # back to the established virtual-distance calculation from 0x4A3.
    camera = self.vehicleNaviCameraStatusEvent if speed_limit_cam else (cameras[0] if cameras else None)
    if camera is not None:
      self.vehicleNaviCameraTarget = camera["target"]
      ret.speedLimit = camera["speed"]
      ret.vehicleNaviActive = True
      if ret.vehicleNaviSpeed <= 0:
        ret.vehicleNaviSpeed = camera["speed"]

    if bumps:
      ret.vehicleNaviActive = True

    return camera is not None

  def get_can_parsers_canfd(self, CP):
    # Stock-navigation position/route/profile messages registered as optional (NaN
    # frequency) from startup, so sparse profiles are not missed by dynamic timing.
    msgs = [("NEW_MSG_4B4", math.nan), ("NEW_MSG_4B9", math.nan), ("NEW_MSG_4BE", math.nan)]
    if not (CP.flags & HyundaiFlags.CANFD_ALT_BUTTONS):
      # TODO: this can be removed once we add dynamic support to vl_all
      msgs += [
        # this message is 50Hz but the ECU frequently stops transmitting for ~0.5s
        ("CRUISE_BUTTONS", 1)
      ]
    return {
      Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], msgs, CanBus(CP).ECAN),
      Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], [], CanBus(CP).CAM),
    }

  def get_can_parsers(self, CP, CP_SP):
    if CP.flags & HyundaiFlags.CANFD:
      return self.get_can_parsers_canfd(CP)

    return {
      Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], [], 0),
      Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], [], 2),
    }
