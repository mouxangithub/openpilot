import math
import numpy as np

from opendbc.car import structs
from opendbc.car.structs import car
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.selfdrive.car.cruise_ext import VCruiseHelperSP
# The gap-cycle helpers live with the distance-button handling; VCruiseCarrot reuses them
# so both paths agree on how many levels a car has.
from openpilot.sunnypilot.selfdrive.car.cruise_helpers import (
  cruise_gap_levels, next_gap_personality, supported_gap_levels,
)


# WARNING: this value was determined based on the model's training distribution,
#          model predictions above this speed can be unpredictable
# V_CRUISE's are in kph
V_CRUISE_MIN = 8
V_CRUISE_MAX = 145
V_CRUISE_UNSET = 255
V_CRUISE_INITIAL = 40
V_CRUISE_INITIAL_EXPERIMENTAL_MODE = 105
IMPERIAL_INCREMENT = round(CV.MPH_TO_KPH, 1)  # round here to avoid rounding errors incrementing set speed

ButtonEvent = car.CarState.ButtonEvent
# Symbols the VCruiseCarrot port needs. V_CRUISE_MAX / V_CRUISE_UNSET already exist above.
GearShifter = structs.CarState.GearShifter

# Above this steering angle an automatic engagement is refused: the driver is mid-manoeuvre.
AUTO_CRUISE_MAX_STEERING_ANGLE = 70.0


def is_hold_interlock_active(CS) -> bool:
  """True while AVH or the parking brake, not us, owns longitudinal control."""
  return CS.brakeHoldActive or CS.parkingBrake


ButtonType = car.CarState.ButtonEvent.Type
CRUISE_LONG_PRESS = 50
TOYOTA_VIRTUAL_CRUISE_LONG_PRESS = 65
CRUISE_NEAREST_FUNC = {
  ButtonType.accelCruise: math.ceil,
  ButtonType.decelCruise: math.floor,
}
CRUISE_INTERVAL_SIGN = {
  ButtonType.accelCruise: +1,
  ButtonType.decelCruise: -1,
}


class VCruiseHelper(VCruiseHelperSP):
  def __init__(self, CP, CP_SP):
    VCruiseHelperSP.__init__(self, CP, CP_SP)
    self.CP = CP
    self.v_cruise_kph = V_CRUISE_UNSET
    self.v_cruise_cluster_kph = V_CRUISE_UNSET
    self.v_cruise_kph_last = 0
    self.button_timers = {ButtonType.decelCruise: 0, ButtonType.accelCruise: 0}
    self.button_change_states = {btn: {"standstill": False, "enabled": False} for btn in self.button_timers}

  @property
  def v_cruise_initialized(self):
    return self.v_cruise_kph != V_CRUISE_UNSET

  @property
  def software_pcm_cruise_speed(self) -> bool:
    return self.CP.brand == "toyota" and self.CP.pcmCruise and self.CP.openpilotLongitudinalControl and not self.CP_SP.pcmCruiseSpeed

  @property
  def cruise_long_press_frames(self) -> int:
    return TOYOTA_VIRTUAL_CRUISE_LONG_PRESS if self.software_pcm_cruise_speed else CRUISE_LONG_PRESS

  @property
  def software_pcm_cruise_initialized(self) -> bool:
    return 0 < self.v_cruise_kph < V_CRUISE_UNSET and 0 < self.v_cruise_cluster_kph < V_CRUISE_UNSET

  def _apply_software_pcm_cruise_delta(self, delta_kph: float, is_metric: bool) -> None:
    """Move Toyota's planner/display targets together while respecting both targets' bounds."""
    cluster_min_kph = self.v_cruise_min if is_metric else self.v_cruise_min * CV.MPH_TO_KPH
    min_delta = max(V_CRUISE_MIN - self.v_cruise_kph, cluster_min_kph - self.v_cruise_cluster_kph)
    max_delta = min(V_CRUISE_MAX - self.v_cruise_kph, V_CRUISE_MAX - self.v_cruise_cluster_kph)
    if delta_kph > 0:
      applied_delta = min(delta_kph, max(0., max_delta))
    else:
      applied_delta = max(delta_kph, min(0., min_delta))
    self.v_cruise_kph = round(self.v_cruise_kph + applied_delta, 1)
    self.v_cruise_cluster_kph = round(self.v_cruise_cluster_kph + applied_delta, 1)

  def update_v_cruise(self, CS, enabled, is_metric):
    self.v_cruise_kph_last = self.v_cruise_kph

    self.get_minimum_set_speed(is_metric)

    _enabled = self.update_enabled_state(CS, enabled)

    if CS.cruiseState.available:
      software_pcm_enabled = not self.CP_SP.pcmCruiseSpeed and _enabled
      if self.software_pcm_cruise_speed:
        software_pcm_enabled = software_pcm_enabled and self.software_pcm_cruise_initialized

      if not self.CP.pcmCruise or software_pcm_enabled:
        # if stock cruise is completely disabled, then we can use our own set speed logic
        self._update_v_cruise_non_pcm(CS, _enabled, is_metric)
        v_cruise_kph_before_sla = self.v_cruise_kph
        self.update_speed_limit_assist_v_cruise_non_pcm()
        if self.software_pcm_cruise_speed:
          sla_delta_kph = self.v_cruise_kph - v_cruise_kph_before_sla
          self.v_cruise_kph = v_cruise_kph_before_sla
          self._apply_software_pcm_cruise_delta(sla_delta_kph, is_metric)
        else:
          self.v_cruise_cluster_kph = self.v_cruise_kph
      else:
        self.v_cruise_kph = CS.cruiseState.speed * CV.MS_TO_KPH
        self.v_cruise_cluster_kph = CS.cruiseState.speedCluster * CV.MS_TO_KPH
        if CS.cruiseState.speed == 0:
          self.v_cruise_kph = V_CRUISE_UNSET
          self.v_cruise_cluster_kph = V_CRUISE_UNSET
        elif CS.cruiseState.speed == -1:
          self.v_cruise_kph = -1
          self.v_cruise_cluster_kph = -1
    else:
      self.v_cruise_kph = V_CRUISE_UNSET
      self.v_cruise_cluster_kph = V_CRUISE_UNSET

    if not self.CP.pcmCruise or not self.CP_SP.pcmCruiseSpeed:
      self.update_button_timers(CS, enabled)

  def _update_v_cruise_non_pcm(self, CS, enabled, is_metric):
    # handle button presses. TODO: this should be in state_control, but a decelCruise press
    # would have the effect of both enabling and changing speed is checked after the state transition
    if not enabled:
      return

    long_press = False
    button_type = None

    v_cruise_delta = 1. if is_metric else IMPERIAL_INCREMENT

    for b in CS.buttonEvents:
      if b.type.raw in self.button_timers and not b.pressed:
        if self.button_timers[b.type.raw] > self.cruise_long_press_frames:
          return  # end long press
        button_type = b.type.raw
        break
    else:
      for k, timer in self.button_timers.items():
        if timer and timer % self.cruise_long_press_frames == 0:
          button_type = k
          long_press = True
          break

    if button_type is None:
      return

    # Don't adjust speed when pressing resume to exit standstill
    cruise_standstill = self.button_change_states[button_type]["standstill"] or CS.cruiseState.standstill
    if button_type == ButtonType.accelCruise and cruise_standstill:
      return

    # Don't adjust speed if we've enabled since the button was depressed (some ports enable on rising edge)
    if not self.button_change_states[button_type]["enabled"]:
      return

    # Speed Limit Assist for Non PCM long cars.
    # True: Disallow set speed changes when user confirmed the target set speed during preActive state
    # False: Allow set speed changes as SLA is not requesting user confirmation
    if self.update_speed_limit_assist_pre_active_confirmed(button_type):
      return

    long_press, v_cruise_delta = VCruiseHelperSP.update_v_cruise_delta(self, long_press, v_cruise_delta)
    # Toyota's canonical PCM set speed and displayed cluster set speed can differ. In
    # software-owned PCM mode, round the value the driver sees and apply the same delta
    # to both targets so the planner/cluster calibration offset remains intact.
    v_cruise_reference = self.v_cruise_cluster_kph if self.software_pcm_cruise_speed else self.v_cruise_kph
    if long_press and v_cruise_reference % v_cruise_delta != 0:  # partial interval
      v_cruise_reference_new = CRUISE_NEAREST_FUNC[button_type](v_cruise_reference / v_cruise_delta) * v_cruise_delta
    else:
      v_cruise_reference_new = v_cruise_reference + v_cruise_delta * CRUISE_INTERVAL_SIGN[button_type]

    if self.software_pcm_cruise_speed:
      delta_kph = v_cruise_reference_new - v_cruise_reference

      # If SET is pressed while overriding, do not lower the target below the current speed.
      if CS.gasPressed and button_type in (ButtonType.decelCruise, ButtonType.setCruise):
        delta_kph = max(delta_kph, CS.vEgo * CV.MS_TO_KPH - self.v_cruise_kph)

      self._apply_software_pcm_cruise_delta(delta_kph, is_metric)
      return

    self.v_cruise_kph += v_cruise_reference_new - v_cruise_reference

    # If set is pressed while overriding, clip cruise speed to minimum of vEgo
    if CS.gasPressed and button_type in (ButtonType.decelCruise, ButtonType.setCruise):
      self.v_cruise_kph = max(self.v_cruise_kph, CS.vEgo * CV.MS_TO_KPH)

    self.v_cruise_kph = np.clip(round(self.v_cruise_kph, 1), self.v_cruise_min, V_CRUISE_MAX)

  def update_button_timers(self, CS, enabled):
    if self.software_pcm_cruise_speed and (not enabled or not CS.cruiseState.available or not self.software_pcm_cruise_initialized):
      for k in self.button_timers:
        self.button_timers[k] = 0
        self.button_change_states[k] = {"standstill": False, "enabled": False}
      return

    # increment timer for buttons still pressed
    for k in self.button_timers:
      if self.button_timers[k] > 0:
        self.button_timers[k] += 1

    for b in CS.buttonEvents:
      if b.type.raw in self.button_timers:
        # Start/end timer and store current state on change of button pressed
        self.button_timers[b.type.raw] = 1 if b.pressed else 0
        self.button_change_states[b.type.raw] = {"standstill": CS.cruiseState.standstill, "enabled": enabled}

  def initialize_v_cruise(self, CS, experimental_mode: bool, dynamic_experimental_control: bool) -> None:
    # initializing is handled by the PCM
    if self.CP.pcmCruise:
      return

    initial_experimental_mode = experimental_mode and not dynamic_experimental_control
    initial = V_CRUISE_INITIAL_EXPERIMENTAL_MODE if initial_experimental_mode else V_CRUISE_INITIAL

    if any(b.type in (ButtonType.accelCruise, ButtonType.resumeCruise) for b in CS.buttonEvents) and self.v_cruise_initialized:
      self.v_cruise_kph = self.v_cruise_kph_last
    else:
      self.v_cruise_kph = int(round(np.clip(CS.vEgo * CV.MS_TO_KPH, initial, V_CRUISE_MAX)))

    self.v_cruise_cluster_kph = self.v_cruise_kph


class VCruiseCarrot(VCruiseHelper):
  """cp's cruise-button and speed state machine, on top of sunnypilot's helper.

  Inherits VCruiseHelper so the SLA surface (update_speed_limit_assist and the cluster
  target comparison) stays available. cp's version stands alone and has no SLA handling at
  all - substituting it wholesale would silently stop Speed Limit Assist from reaching
  v_cruise, which is why this composes rather than replaces.

  __init__ chains to the parent, which needs (CP, CP_SP).
  """

  def __init__(self, CP, CP_SP):
    super().__init__(CP, CP_SP)
    self.CP = CP
    self.frame = 0
    self.params_memory = Params("/dev/shm/params")
    self.params = Params()
    from openpilot.sunnypilot.selfdrive.controls.lib.drive_helpers_ext import is_volkswagen_meb
    self.is_vw_meb = is_volkswagen_meb(CP)
    self.v_cruise_kph = 20 #V_CRUISE_UNSET
    self.v_cruise_cluster_kph = 20 #V_CRUISE_UNSET
    self.v_cruise_kph_last = 20
    self._cruise_speed_initialized = False

    self.enabled_last = False

    self.long_pressed = False
    self.button_cnt = 0
    self.button_prev = ButtonType.unknown
    self.button_long_time = 40
    self.button_big_step = False  # VW stage-2 (swipe) press -> immediate +10 (round) on release

    self.is_metric = True

    self.v_ego_kph_set = 0
    self._cruise_speed_min, self._cruise_speed_max = 5, 161
    self._cruise_speed_unit = 10
    self._cruise_speed_unit_basic = 1
    self._cruise_button_mode = 2
    self._cancel_button_mode = 0
    self._lfa_button_mode = 0
    self.disengage_on_accelerator = self.params.get_bool("DisengageOnAccelerator")

    self._gas_pressed_count = 0
    self._gas_pressed_count_last = 0
    self._gas_pressed_value = 0
    self._gas_tok_timer = int(0.4 / 0.01) # 0.4 sec
    self._gas_tok = False
    self._brake_pressed_count = 0
    self._soft_hold_count = 0
    self._soft_hold_active = 0
    self.soft_hold_on_cancel = self.params.get_bool("SoftHoldOnCancel")
    self._cruise_ready = False
    self._cruise_cancel_state = False
    self._pause_auto_speed_up = False
    self._activate_cruise = 0
    self._cruise_available = False
    self._hold_interlock_active = False
    self._steering_interlock_active = False
    self._lat_enabled = self.params.get("AutoEngage") > 0
    self._v_cruise_kph_at_brake = 0
    self.cruise_state_available_last = False

    self._paddle_decel_active = False
    self.carrot_cruise_active = False

    #self.events = []
    self.xState = 0
    self.trafficState = 0
    self.aTarget = 0
    self.nRoadLimitSpeed = 30
    self.desiredSpeed = 250
    self.road_limit_kph = 30
    self.nRoadLimitSpeed_last = 30

    self.carrot_cmd_index_last = 0
    self.carrot_cmd_index = 0
    self.carrot_cmd = ""
    self.carrot_arg = ""


    self._cancel_timer = 0
    self.d_rel = 0
    self.v_rel = 0
    self.v_lead_kph = 0
    self.model_v_kph = 0

    self._log_timer = 0
    self._log_timeout = int(3/0.01)
    self.log = ""

    self.autoCruiseControl = 0
    self.autoCruiseControl_cancel_timer = 0
    self.AutoSpeedUptoRoadSpeedLimit = 0.0
    self.autoGasCancelSpeed = 30

    self.useLaneLineSpeed = self.params.get("UseLaneLineSpeed")
    self.useLaneLineSpeedApply = self.useLaneLineSpeed


  @property
  def v_cruise_initialized(self):
    return self.v_cruise_kph != V_CRUISE_UNSET

  def _add_log(self, log):
    if len(log) == 0:
      self._log_timer = max(0, self._log_timer - 1)
      if self._log_timer <= 0:
        self.log = ""
        #self.event = -1
    else:
      self.log = log
      #self.event = event
      self._log_timer = self._log_timeout

  def _current_speed_for_initial_resume(self):
    return max(self.v_ego_kph_set, self._cruise_speed_min)

  def update_params(self, is_metric):
    unit_factor = 1.0 if is_metric else CV.MPH_TO_KPH
    if self.frame % 10 == 0:
      self.autoCruiseControl = self.params.get("AutoCruiseControl") * unit_factor
      self.soft_hold_on_cancel = self.params.get_bool("SoftHoldOnCancel")
      self.autoGasTokSpeed = self.params.get("AutoGasTokSpeed") * unit_factor
      self.autoGasCancelSpeed = self.params.get("AutoGasCancelSpeed") * unit_factor
      self.autoGasSyncSpeed = self.params.get("AutoGasSyncSpeed")
      self.applyModelSpeed = self.params.get("ApplyModelSpeed") * 0.01
      self.autoSpeedUptoRoadSpeedLimit = self.params.get("AutoSpeedUptoRoadSpeedLimit") * 0.01
      self.autoRoadSpeedAdjust = self.params.get("AutoRoadSpeedAdjust") * 0.01

      useLaneLineSpeed = self.params.get("UseLaneLineSpeed") * unit_factor
      if self.useLaneLineSpeed != useLaneLineSpeed:
        self.useLaneLineSpeedApply = useLaneLineSpeed
      self.useLaneLineSpeed = useLaneLineSpeed

      self.speed_from_pcm = self.params.get("SpeedFromPCM")
      self._cruise_speed_unit = self.params.get("CruiseSpeedUnit")
      self._cruise_button_long_delay = self.params.get("CruiseButtonLongDelay")
      self._cruise_speed_unit_basic = self.params.get("CruiseSpeedUnitBasic")
      self._paddle_mode = self.params.get("PaddleMode")
      self._cruise_button_mode = self.params.get("CruiseButtonMode")
      self._cancel_button_mode = self.params.get("CancelButtonMode")
      self._lfa_button_mode = self.params.get("LfaButtonMode")
      self.disengage_on_accelerator = self.params.get_bool("DisengageOnAccelerator")
      self.autoRoadSpeedLimitOffset = self.params.get("AutoRoadSpeedLimitOffset")
      self.autoNaviSpeedSafetyFactor = self.params.get("AutoNaviSpeedSafetyFactor") * 0.01
      self.cruiseOnDist = self.params.get("CruiseOnDist") * 0.01
      cruiseSpeed1 = self.params.get("CruiseSpeed1") * unit_factor
      cruiseSpeed2 = self.params.get("CruiseSpeed2") * unit_factor
      cruiseSpeed3 = self.params.get("CruiseSpeed3") * unit_factor
      cruiseSpeed4 = self.params.get("CruiseSpeed4") * unit_factor
      cruiseSpeed5 = self.params.get("CruiseSpeed5") * unit_factor
      if cruiseSpeed1 <= 0:
        if self.autoRoadSpeedLimitOffset < 0:
          cruiseSpeed1 = self.nRoadLimitSpeed * self.autoNaviSpeedSafetyFactor
        else:
          cruiseSpeed1 = self.nRoadLimitSpeed + self.autoRoadSpeedLimitOffset
      self._cruise_speed_table = [cruiseSpeed1, cruiseSpeed2, cruiseSpeed3, cruiseSpeed4, cruiseSpeed5]

  def _update_carrot_man(self, sm):
    # sunnypilot publishes the phone-projection state on carrotManSP; the legacy
    # cp 'carrotMan' service is not registered in cereal/services.py.
    if sm.valid.get('carrotManSP', False):
      carrot_man = sm['carrotManSP']
      self.nRoadLimitSpeed = carrot_man.nRoadLimitSpeed
      self.desiredSpeed = carrot_man.desiredSpeed
      self.carrot_cmd_index = carrot_man.carrotCmdIndex
      self.carrot_cmd = carrot_man.carrotCmd
      self.carrot_arg = carrot_man.carrotArg
    else:
      self.nRoadLimitSpeed = 0
      self.desiredSpeed = 250
      self.carrot_cmd = ""
      self.carrot_arg = ""

  def update_v_cruise(self, CS, enabled, is_metric, sm=None, CS_SP=None):
    self._add_log("")
    self.update_params(is_metric)
    self.frame += 1
    # MEB(ID.4): SET/RESUME으로 (재)인게이지하면 상시조향도 복구.
    # TA 버튼 등으로 조향만 꺼진 뒤 SET 재인게이지 시 롱컨만 살고 조향이 죽는 문제 방지
    # (가감속 버튼 핸들러는 이미 _lat_enabled를 켜지만 setCruise는 핸들러가 없음).
    if self.is_vw_meb and not self._lat_enabled:
      for be in CS.buttonEvents:
        if be.pressed and be.type in (ButtonType.setCruise, ButtonType.resumeCruise):
          self._lat_enabled = True
          self._add_log("Lateral enabled (set/resume engage)")
          break
    if CS.gearShifter != GearShifter.drive:
      self.autoCruiseControl_cancel_timer = 20 * 100  # 20 sec
    else:
      self.autoCruiseControl_cancel_timer = max(0, self.autoCruiseControl_cancel_timer - 1)

    if sm is None:
      return

    CC = sm['carControl']
    # CS_SP carries the fork-only bits VCruiseCarrot needs (VW stage-2 stalk latch).
    # It is passed in by card.py, which owns carStateSP; it is NOT in SubMaster.
    self._update_carrot_man(sm)
    if sm.alive['longitudinalPlan']:
      lp = sm['longitudinalPlan']
      # xState/trafficState are cp-specific; sunnypilot's LongitudinalPlan only
      # has aTarget. Default to 0 so traffic-sign logic stays inactive.
      self.xState = getattr(lp, 'xState', 0)
      self.trafficState = getattr(lp, 'trafficState', 0)
      self.aTarget = lp.aTarget
    if sm.alive['radarState']:
      lead = sm['radarState'].leadOne
      self.d_rel = lead.dRel if lead.present else 0
      self.v_rel = lead.vRel if lead.present else 0
      self.v_lead_kph = lead.vLeadK * CV.MS_TO_KPH if lead.present else 0
    if sm.alive['drivingModelData']:
      # desiredVelocity only exists in cp's ModelDataV2.Action; sunnypilot's
      # DrivingModelData.Action has desiredCurvature/desiredAcceleration/shouldStop.
      self.model_v_kph = getattr(sm['drivingModelData'].action, 'desiredVelocity', 0.0) * CV.MS_TO_KPH

    self.v_cruise_kph_last = self.v_cruise_kph
    self.is_metric = is_metric

    self._cancel_timer = max(0, self._cancel_timer - 1)

    #self.events = []
    self.v_ego_kph_set = int(CS.vEgoCluster * CV.MS_TO_KPH + 0.5)
    self._activate_cruise = 0
    self._cruise_available = CS.cruiseState.available
    if not self._cruise_available:
      self._cruise_ready = False
      self._paddle_decel_active = False
      self._soft_hold_count = 0
      self._soft_hold_active = 0
    self._hold_interlock_active = is_hold_interlock_active(CS)
    self._steering_interlock_active = abs(CS.steeringAngleDeg) >= AUTO_CRUISE_MAX_STEERING_ANGLE
    if self._hold_interlock_active:
      # Drop queued automatic engagement state while AVH or the parking brake
      # owns longitudinal control.
      self._cruise_ready = False
      self._paddle_decel_active = False
      self._soft_hold_active = 0
    self._prepare_brake_gas(CS, CC)
    if CC.enabled:
      self._cruise_ready = False
    v_cruise_kph = self._update_cruise_buttons(CS, CC, self.v_cruise_kph, CS_SP)

    if self._activate_cruise > 0:
      #self.events.append(EventName.buttonEnable)
      self._cruise_ready = False
    elif self._activate_cruise < 0:
      #self.events.append(EventName.buttonCancel)
      self._cruise_ready = True if self._activate_cruise == -2 else False

    if CS.cruiseState.available:
      if not self.cruise_state_available_last:
        self._lat_enabled = True
        v_cruise_kph = self.v_ego_kph_set
      if not self.CP.pcmCruise:
        # if stock cruise is completely disabled, then we can use our own set speed logic
        self.v_cruise_kph = np.clip(v_cruise_kph, self._cruise_speed_min, self._cruise_speed_max)
        self.v_cruise_cluster_kph = self.v_cruise_kph
      else:
        if self.speed_from_pcm == 1:
          self.v_cruise_kph = CS.cruiseState.speed * CV.MS_TO_KPH
          self.v_cruise_cluster_kph = CS.cruiseState.speedCluster * CV.MS_TO_KPH
        else:
          self.v_cruise_kph = np.clip(v_cruise_kph, 30, self._cruise_speed_max)
          self.v_cruise_cluster_kph = self.v_cruise_kph
    else:
      self.v_cruise_kph = np.clip(v_cruise_kph, self._cruise_speed_min, self._cruise_speed_max) #max(20, self.v_ego_kph_set) #V_CRUISE_UNSET
      self.v_cruise_cluster_kph = self.v_cruise_kph #V_CRUISE_UNSET  # noqa: E262
      #if self.cruise_state_available_last: # 최초 한번이라도 cruiseState.available이 True였다면
      #  self._lat_enabled = False

    self.cruise_state_available_last = CS.cruiseState.available
    self.enabled_last = CC.enabled

  def initialize_v_cruise(self, CS, experimental_mode: bool, dynamic_experimental_control: bool = False) -> None:
    """No-op override; the inherited VCruiseHelper.initialize_v_cruise owns v_cruise.

    The signature must stay identical to the base class because card.py calls the
    helper polymorphically with (CS, experimental_mode, dynamic_experimental_control).
    The previous two-argument override raised
    `TypeError: takes 3 positional arguments but 4 were given` on every SET press.
    """
    return

  def _prepare_buttons(self, CS, v_cruise_kph, CS_SP=None):
    button_kph = v_cruise_kph
    button_type = 0
    buttonEvents = CS.buttonEvents

    SPEED_UP_UNIT = self._cruise_speed_unit_basic
    SPEED_DOWN_UNIT = self._cruise_speed_unit if self._cruise_button_mode in [1, 2, 3] else self._cruise_speed_unit_basic
    V_CRUISE_DELTA = 10
    is_metric = self.is_metric

    # VW stage-2 stalk swipe latch. The bit lives on CarStateSP (fork-only), not on
    # carState: opendbc's CarState has no such member, and reading CS.cruiseSpeedBigStep
    # crashed card.py on the first button press. No publisher fills it yet, so this
    # stays False and every press is treated as a short press.
    big_step_available = bool(getattr(CS_SP, 'carrotCruiseSpeedBigStep', False))

    # long press tracking
    if self.button_cnt > 0:
      self.button_cnt += 1
      # VW 쓸어올리기(2단) 래치: GRA_Tip_Stufe_2는 2단으로 밀고 있는 동안만 1이고 뗄 때는 이미 0.
      # 뗄 때 샘플하면 항상 짧은누름으로 오인되므로, 누르고 있는 동안 한 번이라도 1이면 래치.
      if self.button_prev in [ButtonType.accelCruise, ButtonType.decelCruise] and big_step_available:
        self.button_big_step = True

    for b in buttonEvents:
      bt = b.type

      if bt in [ButtonType.paddleLeft, ButtonType.paddleRight] and b.pressed:
        # Paddle: 즉시 이벤트 발생
        button_type = bt
        self.long_pressed = False
        self.button_cnt = 0
        continue

      if b.pressed and self.button_cnt == 0 and bt in [
        ButtonType.accelCruise, ButtonType.decelCruise,
        ButtonType.gapAdjustCruise, ButtonType.cancel,
        ButtonType.lfaButton
      ]:
        self.button_cnt = 1
        self.button_prev = bt
        # VW 쓸어올리기(2단): 누르기 시작 시점의 GRA_Tip_Stufe_2 샘플 (이후 유지 중 래치로 보강)
        self.button_big_step = bt in [ButtonType.accelCruise, ButtonType.decelCruise] and big_step_available
        self.button_long_time = self._cruise_button_long_delay if bt in [ButtonType.accelCruise, ButtonType.decelCruise] else self._cruise_button_long_delay + 30

      elif not b.pressed and self.button_cnt > 0 and bt == self.button_prev:
        # VW 쓸어올리기: 래치된 self.button_big_step 사용 (뗄 때 신호를 다시 읽으면 이미 0)
        if bt == ButtonType.cancel:
          button_type = bt
        elif self.button_big_step and not self.long_pressed and bt in [ButtonType.accelCruise, ButtonType.decelCruise]:
          # VW swipe (stage-2): jump to next multiple of V_CRUISE_DELTA (=+10 like the stock stalk)
          mod = button_kph % V_CRUISE_DELTA
          if bt == ButtonType.accelCruise:
            button_kph += V_CRUISE_DELTA - mod
          else:
            button_kph -= V_CRUISE_DELTA - (-mod % V_CRUISE_DELTA)
          button_type = bt
        elif not self.long_pressed:
          if bt == ButtonType.accelCruise:
            unit = SPEED_UP_UNIT if is_metric else SPEED_UP_UNIT * CV.MPH_TO_KPH
            button_kph = math.ceil((button_kph + 0.01) / unit) * unit
          elif bt == ButtonType.decelCruise:
            unit = SPEED_DOWN_UNIT if is_metric else SPEED_DOWN_UNIT * CV.MPH_TO_KPH
            button_kph = math.floor((button_kph - 0.01) / unit) * unit
          button_type = bt
        self.long_pressed = False
        self.button_cnt = 0
        self.button_big_step = False

    # Long press 처리
    if self.button_cnt > self.button_long_time:
      self.long_pressed = True
      bt = self.button_prev

      #if bt == ButtonType.cancel:
      #  button_type = bt
      #  self.button_cnt = 0
      if bt in [ButtonType.accelCruise, ButtonType.decelCruise]:
        mod = button_kph % V_CRUISE_DELTA
        if bt == ButtonType.accelCruise:
          button_kph += V_CRUISE_DELTA - mod
        else:
          button_kph -= V_CRUISE_DELTA - (-mod % V_CRUISE_DELTA)
        button_type = bt
        self.button_cnt %= self.button_long_time
      else: #if bt in [ButtonType.gapAdjustCruise, ButtonType.lfaButton]:
        if self.button_cnt < self.button_long_time + 2:
          button_type = bt
        #self.button_cnt %= self.button_long_time

    return button_kph, button_type, self.long_pressed

  def _carrot_command(self, v_cruise_kph, button_type, long_pressed):
    if self.carrot_cmd_index_last != self.carrot_cmd_index:
      self.carrot_cmd_index_last = self.carrot_cmd_index
      cloudlog.debug(f"Carrot command(cruise.py): {self.carrot_cmd} {self.carrot_arg}")
      if self.carrot_cmd == "CRUISE":
        if self.carrot_arg == "OFF":
          self._cruise_control(-2, -1, "Cruise off (carrot command)")
        elif self.carrot_arg == "ON":
          self._cruise_control(1, -1, "Cruise on (carrot command)")
        elif self.carrot_arg == "GO":
          if button_type == 0:
            button_type = ButtonType.accelCruise
            long_pressed = False
            self._add_log("Cruise accelCruise (carrot command)")
        elif self.carrot_arg == "STOP":
          v_cruise_kph = 5
          self._cruise_speed_initialized = False
          self._add_log("Cruise stop (carrot command)")

      elif self.carrot_cmd == "SPEED":
        if self.carrot_arg == "UP":
          v_cruise_kph = self._auto_speed_up(v_cruise_kph)
          self._add_log("Cruise speed up (carrot command)")
        elif self.carrot_arg == "DOWN":
          if v_cruise_kph > 20:
            v_cruise_kph -= 10
            self._add_log("Cruise speed downup (carrot command)")
        else:
          speed_kph = int(self.carrot_arg)
          if 0 < speed_kph < 200:
            v_cruise_kph = speed_kph
            self._add_log(f"Cruise speed set to {v_cruise_kph} (carrot command)")       
    
    return v_cruise_kph, button_type, long_pressed

  def _update_cruise_buttons(self, CS, CC, v_cruise_kph, CS_SP=None):
    button_kph, button_type, long_pressed = self._prepare_buttons(CS, v_cruise_kph, CS_SP)

    v_cruise_kph, button_type, long_pressed = self._carrot_command(v_cruise_kph, button_type, long_pressed)

    if button_type in [ButtonType.accelCruise, ButtonType.decelCruise]:
      self._paddle_decel_active = False
      if self.autoCruiseControl_cancel_timer > 0:
        self._add_log(f"AutoCruiseControl cancel timer RESET {button_type}")
        self.autoCruiseControl_cancel_timer = 0
      if self._cruise_cancel_state:
        self._add_log(f"Cruise Cancel state RESET {button_type}")
        self._cruise_cancel_state = False

    if not long_pressed:
      if button_type == ButtonType.accelCruise:
        self._lat_enabled = True
        self._pause_auto_speed_up = False
        if self._soft_hold_active > 0:
          self._soft_hold_active = 0
        elif self.carrot_cruise_active:
          self._v_cruise_kph_at_brake = 0
        elif self._cruise_ready or not CC.enabled or CS.cruiseState.standstill:
          if self._v_cruise_kph_at_brake > 0:
            v_cruise_kph = max(v_cruise_kph, self._v_cruise_kph_at_brake)
            self._v_cruise_kph_at_brake = 0
            self._cruise_speed_initialized = True
          elif not self._cruise_speed_initialized:
            v_cruise_kph = self._current_speed_for_initial_resume()
            self._cruise_speed_initialized = True
            self._add_log(f"{v_cruise_kph} Cruise resume from current speed")
          if False: #self._cruise_button_mode in [2, 3]:
            road_limit_kph = self.nRoadLimitSpeed * self.autoSpeedUptoRoadSpeedLimit
            if road_limit_kph > 1.0:
              v_cruise_kph = max(v_cruise_kph, road_limit_kph)
        else:
          # Once cruise is already active, RES/+ is a speed adjustment. Stale resume or
          # initialization state must not consume the first press without changing speed.
          self._v_cruise_kph_at_brake = 0
          if self._cruise_button_mode == 0:
            v_cruise_kph = button_kph
          else:
            v_cruise_kph = self._v_cruise_desired(CS, v_cruise_kph)
        self._cruise_speed_initialized = True
        self.carrot_cruise_active = False

      elif button_type == ButtonType.decelCruise:
        self._lat_enabled = True
        self._pause_auto_speed_up = True
        #self.carrot_cruise_active = False

        if self._soft_hold_active > 0:
          self._cruise_control(-1, -1, "Cruise off,softhold mode (decelCruise)")
        elif self._cruise_ready:
          self._paddle_decel_active = True
          pass
        elif not CC.enabled:
          v_cruise_kph = max(self.v_ego_kph_set, self._cruise_speed_min)
        elif self.v_ego_kph_set > v_cruise_kph + 2 and self._cruise_button_mode in [2, 3]:
          v_cruise_kph = max(self.v_ego_kph_set, self._cruise_speed_min)
        elif self._cruise_button_mode in [0, 1]:
          v_cruise_kph = button_kph
        elif self.v_ego_kph_set < 1.0:
          self.carrot_cruise_active = True
        elif self.v_ego_kph_set > self._cruise_speed_min and v_cruise_kph > self.v_ego_kph_set:
          v_cruise_kph = self.v_ego_kph_set
        else:
          #self._cruise_control(-2, -1, "Cruise off (decelCruise)")
          self.carrot_cruise_active = True
          #self.events.append(EventName.audioPrompt)
        self._v_cruise_kph_at_brake = 0
        self._cruise_speed_initialized = True

      elif button_type == ButtonType.gapAdjustCruise:
        longitudinalPersonalityMax = supported_gap_levels(self.params.get("LongitudinalPersonalityMax"))
        gap_levels = cruise_gap_levels(self.params.get("CruiseGapLevels"), longitudinalPersonalityMax)
        if not self.CP.openpilotLongitudinalControl:
          gap_levels = longitudinalPersonalityMax
        if CS.pcmCruiseGap == 0 or gap_levels < longitudinalPersonalityMax:
          personality = next_gap_personality(self.params.get('LongitudinalPersonality'), gap_levels)
        else:
          personality = int(np.clip(CS.pcmCruiseGap - 1, 0, longitudinalPersonalityMax - 1))
        self.params.put_nonblocking('LongitudinalPersonality', personality)
        #self.events.append(EventName.personalityChanged)
      elif button_type == ButtonType.lfaButton:
        if self._lfa_button_mode == 0:
          self._lat_enabled = not self._lat_enabled
          self._add_log("Lateral " + "enabled" if self._lat_enabled else "disabled")
        elif self._lfa_button_mode == 2:
          self.carrot_cruise_active = True
        else:
          if False: #CC.enabled and self._paddle_decel_active:  # 수정필요...
            self._paddle_decel_active = False
          else:          
            self._paddle_decel_active = True
      elif button_type == ButtonType.cancel:
        self._paddle_decel_active = False
        if self._cancel_button_mode in [1]:
          self._lat_enabled = False
          self._add_log("Lateral " + "enabled" if self._lat_enabled else "disabled")
        self._cruise_cancel_state = True
        #self._v_cruise_kph_at_brake = 0
    else:
      if button_type == ButtonType.accelCruise:
        v_cruise_kph = button_kph
        self._v_cruise_kph_at_brake = 0
      elif button_type == ButtonType.decelCruise:
        self._pause_auto_speed_up = True
        v_cruise_kph = button_kph
        self._v_cruise_kph_at_brake = 0
      elif button_type == ButtonType.gapAdjustCruise:
        self.params.put_nonblocking("MyDrivingMode", self.params.get("MyDrivingMode") % 4 + 1) # 1,2,3,4 (1:eco, 2:safe, 3:normal, 4:high speed)
      elif button_type == ButtonType.lfaButton:
        useLaneLineSpeed = max(1, self.useLaneLineSpeed)
        self.useLaneLineSpeedApply = useLaneLineSpeed if self.useLaneLineSpeedApply == 0 else 0

      elif button_type == ButtonType.cancel:
        self._cruise_cancel_state = True
        self._lat_enabled = False
        self._paddle_decel_active = False
        #self.params.put_bool_nonblocking("ExperimentalMode", not self.params.get_bool("ExperimentalMode"))
        self._add_log("Lateral " + "enabled" if self._lat_enabled else "disabled")

    if self._paddle_mode > 0 and button_type in [ButtonType.paddleLeft, ButtonType.paddleRight]:  # paddle button
      if self._paddle_mode == 3:
        self.carrot_cruise_active = True
      else:
        self._cruise_control(-2, -1, "Cruise off & Ready (paddle)")
        if self._paddle_mode == 2:
          self._paddle_decel_active = True
    elif self._paddle_decel_active:
      if not CC.enabled:
        self._cruise_control(1, -1, "Cruise on (paddle decel)")

    v_cruise_kph = self._update_cruise_state(CS, CC, v_cruise_kph)
    return v_cruise_kph

  ## desiredSpeed :
  #   leadCar_distance, leadCar_speed, leadCar_accel,
  #   v_ego, tbt_distance, tbt_speed,
  #   nRoadLimitSpeed, vTurnSpeed
  #   gasPressed, brakePressed, standstill
  def _v_cruise_desired(self, CS, v_cruise_kph):
    if self._cruise_button_mode == 3:
      for speed in self._cruise_speed_table:
        if v_cruise_kph < speed:
          v_cruise_kph = speed
          break
      else:
        v_cruise_kph = ((v_cruise_kph // self._cruise_speed_unit) + 1) * self._cruise_speed_unit

    elif v_cruise_kph < 30: #self.nRoadLimitSpeed:
      v_cruise_kph = 30 #self.nRoadLimitSpeed
    else:
      for speed in range (40, 160, self._cruise_speed_unit):
        if v_cruise_kph < speed:
          v_cruise_kph = speed
          break
    return v_cruise_kph

  def _auto_speed_up(self, v_cruise_kph):
    #if self._pause_auto_speed_up:
    #  return v_cruise_kph
    if not self._pause_auto_speed_up and self.applyModelSpeed != 0.0:
      model_kph = self.model_v_kph * abs(self.applyModelSpeed)
      apply_speed = min(model_kph, self.nRoadLimitSpeed * 1.1)

      if self.applyModelSpeed < 0.0:
        v_cruise_kph = min(model_kph, apply_speed)
      elif v_cruise_kph < apply_speed:
        v_cruise_kph = apply_speed

    road_limit_kph = self.nRoadLimitSpeed * self.autoSpeedUptoRoadSpeedLimit
    if road_limit_kph < 1.0:
      return v_cruise_kph

    if self.autoRoadSpeedLimitOffset > 0:
      self._v_cruise_kph_at_brake = self.nRoadLimitSpeed + self.autoRoadSpeedLimitOffset

    if not self._pause_auto_speed_up and self.v_lead_kph + 5 > v_cruise_kph and v_cruise_kph < road_limit_kph and self.d_rel < 60:
      v_cruise_kph = min(v_cruise_kph + 5, road_limit_kph)
    elif self.autoRoadSpeedAdjust < 0 and self.nRoadLimitSpeed != self.nRoadLimitSpeed_last:  # 도로제한속도가 바뀌면, 바뀐속도로 속도를 바꿈.
      if self.autoRoadSpeedLimitOffset < 0:
        v_cruise_kph = self.nRoadLimitSpeed * self.autoNaviSpeedSafetyFactor
      else:
        v_cruise_kph = self.nRoadLimitSpeed + self.autoRoadSpeedLimitOffset
    elif self.nRoadLimitSpeed < self.nRoadLimitSpeed_last and self.autoRoadSpeedAdjust > 0:
      new_road_limit_kph = self.nRoadLimitSpeed * self.autoRoadSpeedAdjust + v_cruise_kph * (1 - self.autoRoadSpeedAdjust)
      self._add_log(f"AutoSpeed change {v_cruise_kph} -> {new_road_limit_kph:.1f}")
      v_cruise_kph = min(v_cruise_kph, new_road_limit_kph)
    self.road_limit_kph = road_limit_kph
    self.nRoadLimitSpeed_last = self.nRoadLimitSpeed
    return v_cruise_kph

  def _cruise_control(self, enable, cancel_timer, reason, allow_cancel_state=False):
    if enable > 0 and not self._cruise_available:
      self._activate_cruise = 0
      self._add_log(reason + " > Cruise unavailable")
      return
    if enable > 0 and self._steering_interlock_active:
      self._activate_cruise = 0
      self._add_log(reason + " > Steering angle interlock active")
      return
    if enable > 0 and self._hold_interlock_active:
      self._activate_cruise = 0
      self._add_log(reason + " > Brake hold interlock active")
      return
    if self._cruise_cancel_state and not allow_cancel_state:
      self._add_log(reason + " > Cancel state")
    elif enable > 0 and self._cancel_timer > 0 and cancel_timer >= 0:
      enable = 0
      self._add_log(reason + " > Canceled")
    else:
      if self.autoCruiseControl == 0 and enable != 0:
        enable = 0
        self._soft_hold_active = 0
        return
      if self.autoCruiseControl_cancel_timer > 0 and enable != 0:
        self._add_log(reason + " > timer Canceled")
        enable = 0
        self._soft_hold_active = 0
        return
      self._activate_cruise = enable
      self._cancel_timer = int(cancel_timer / 0.01)   # DT_CTRL: 0.01
      self._add_log(reason)

  def _check_safe_stop(self, CS, safe_distance = 3):
    v_ego = CS.vEgo
    decel_rate = 1.5
    d_stop_ego = (v_ego ** 2) / (2 * decel_rate)
    d_stop_rel = (self.v_rel ** 2) / (2 * decel_rate)

    d_final = self.d_rel - d_stop_ego - d_stop_rel

    if d_final >= safe_distance:
      return True, d_final
    else:
      return False, d_final

  def _engage_soft_hold(self):
    self._soft_hold_active = 2
    self._cruise_control(1, -1, "Cruise on (soft hold)", allow_cancel_state=self.soft_hold_on_cancel)

  def _update_cruise_state(self, CS, CC, v_cruise_kph):
    if not CC.enabled:
      #self._pause_auto_speed_up = False
      if self._brake_pressed_count == -1 and self._soft_hold_active > 0:
        #self.autoCruiseControl_cancel_timer = 0
        self._engage_soft_hold()
      # GM: autoResume
      elif self.params.get_bool("ActivateCruiseAfterBrake"):
        self.params.put_bool_nonblocking("ActivateCruiseAfterBrake", False)
        self._cruise_control(1, -1, "Cruise on (brake)")
      elif self.v_cruise_kph < self.v_ego_kph_set:
        self.v_cruise_kph = self.v_ego_kph_set

    if self._soft_hold_active > 0:
      #self.events.append(EventName.softHold)
      #self._cruise_cancel_state = False
      pass

    if not self.disengage_on_accelerator and self._gas_tok and self.v_ego_kph_set >= self.autoGasTokSpeed:
      if not CC.enabled:
        #self._cruise_cancel_state = False
        self._cruise_control(1, -1, "Cruise on (gas tok)")
        if self.v_ego_kph_set > v_cruise_kph:
          v_cruise_kph = self.v_ego_kph_set
      else:
        v_cruise_kph = self._v_cruise_desired(CS, v_cruise_kph)
    elif self._gas_pressed_count == -1:
      if 0 < self.d_rel < CS.vEgo * 0.8:
        if CS.vEgo < 1.0:
          self._cruise_control(1, -1 if self.aTarget > 0.0 else 0, "Cruise on (safe speed)")
        else:
          self._cruise_control(-1, 0, "Cruise off (lead car too close)")
      elif self.v_ego_kph_set < self.autoGasCancelSpeed:
        self._cruise_control(-1, 0, "Cruise off (gas speed)")
      elif self.xState == 3:
        v_cruise_kph = min(self.v_ego_kph_set, v_cruise_kph)
        self._cruise_control(-1, 3, "Cruise off (traffic sign)")
      elif CS.leftBlinker or CS.rightBlinker:
        pass
      elif not self.disengage_on_accelerator and self.v_ego_kph_set >= self.autoGasTokSpeed and not CC.enabled:
        v_cruise_kph = min(self.v_ego_kph_set, v_cruise_kph)
        self._cruise_control(1, -1 if self.aTarget > 0.0 else 0, "Cruise on (gas pressed)")
    elif self._brake_pressed_count == -1 and self._soft_hold_active == 0:
      if CS.leftBlinker or CS.rightBlinker:
        pass
      elif self.v_ego_kph_set > self.autoGasTokSpeed:
        v_cruise_kph = self.v_ego_kph_set
        self._cruise_control(1, -1 if self.aTarget > 0.0 else 0, "Cruise on (speed)")
      elif abs(CS.steeringAngleDeg) < 20:
        if self.xState in [3, 5]:
          if self.xState == 3:  # 감속중
            v_cruise_kph = self.v_ego_kph_set
          self._cruise_control(1, 0, "Cruise on (traffic sign)")
        elif 0 < self.d_rel < 20: 
          # v_cruise_kph = self.v_ego_kph_set # 전방에 차가 가까이 있을때, 기존속도 유지
          self._cruise_control(1, -1 if self.v_ego_kph_set < 1 else 0, "Cruise on (lead car)")

    elif self._brake_pressed_count < 0 and self._gas_pressed_count < 0:
      if not CC.enabled:
        if self.d_rel > 0 and CS.vEgo > 0.02:
          safe_state, safe_dist = self._check_safe_stop(CS, 4)
          if abs(CS.steeringAngleDeg) > 70:
            pass
          elif not safe_state:
            self._cruise_control(1, -1, "Cruise on (fcw)")
          elif self.d_rel < self.cruiseOnDist:
            self._cruise_control(1, 0, "Cruise on (fcw dist)")
          else:
            self._add_log(f"leadCar d={self.d_rel:.1f},v={self.v_rel:.1f},{CS.vEgo:.1f}, {safe_dist:.1f}")
            #self.events.append(EventName.stopStop)
        if CS.leftBlinker or CS.rightBlinker:
          pass
        else:
          if self.desiredSpeed < self.v_ego_kph_set:
            self._cruise_control(1, -1, "Cruise on (desired speed)")
          if self._cruise_ready:
            if self.xState in [3]:
              self._cruise_control(1, 0, "Cruise on (traffic sign)")
            elif self.d_rel > 0:
              self._cruise_control(1, 0, "Cruise on (lead car)")
      elif self._paddle_decel_active:
        if self.xState in [3]:
          self._paddle_decel_active = False
          v_cruise_kph = self.v_ego_kph_set
        elif self.d_rel > 0:
          self._paddle_decel_active = False
          v_cruise_kph = self.v_ego_kph_set
          

    if self._gas_pressed_count > self._gas_tok_timer:
      if CS.aEgo < -0.5:
        self._cruise_control(-1, 5.0, "Cruise off (gas pressed while braking)")
      if self.v_ego_kph_set > v_cruise_kph and self.autoGasSyncSpeed:
        v_cruise_kph = self.v_ego_kph_set

    if self._gas_pressed_count == 1 or CS.vEgo < 0.1:
      self._pause_auto_speed_up = False
      if self._gas_pressed_count == 1 and CS.vEgo < 0.1:
        self._cruise_control(-1, -1, "Cruise off (gasPressed)")
    elif self._brake_pressed_count > 0:
      self._pause_auto_speed_up = True

    return self._auto_speed_up(v_cruise_kph)

  def _prepare_brake_gas(self, CS, CC):
    if CS.gasPressed:
      gas_pressed_start = self._gas_pressed_count <= 0
      cancel_soft_hold = gas_pressed_start and self._soft_hold_active > 0 and self._cruise_cancel_state
      self._paddle_decel_active = False
      self._gas_pressed_count = max(1, self._gas_pressed_count + 1)
      self._gas_pressed_count_last = self._gas_pressed_count
      self._gas_pressed_value = 1.0
      self._gas_tok = False
      self._soft_hold_active = 0
      if cancel_soft_hold:
        self._cruise_ready = False
        self.carrot_cruise_active = False
        self._cruise_control(-1, -1, "Cruise off (cancel soft hold released)", allow_cancel_state=True)
      elif gas_pressed_start and self.disengage_on_accelerator:
        self._cruise_ready = False
        self.carrot_cruise_active = False
        self._cruise_control(-1, 0, "Cruise off (gas pressed)")
    else:
      self._gas_tok = True if 0 < self._gas_pressed_count < self._gas_tok_timer else False
      self._gas_pressed_count = min(-1, self._gas_pressed_count - 1)
      if self._gas_pressed_count < -1:
        self._gas_pressed_count_last = 0
        self._gas_tok = False

    if CS.brakePressed:
      self._cruise_ready = False
      self._paddle_decel_active = False
      self._brake_pressed_count = max(1, self._brake_pressed_count + 1)
      if self._brake_pressed_count == 1 and self.enabled_last:
        self._v_cruise_kph_at_brake = self.v_cruise_kph
        self._add_log(f"{self.v_cruise_kph} Cruise speed at brake")
      soft_hold_available = CS.cruiseState.available and self.autoCruiseControl != 0 and not self.CP.pcmCruise and \
                            self.autoCruiseControl_cancel_timer == 0 and \
                            (not self._cruise_cancel_state or self.soft_hold_on_cancel)
      self._soft_hold_count = self._soft_hold_count + 1 if soft_hold_available and CS.vEgo < 0.1 and CS.gearShifter == GearShifter.drive else 0
      if not soft_hold_available:
        self._soft_hold_active = 0
      else:
        self._soft_hold_active = 1 if self._soft_hold_count > 60 else 0
    else:
      self._soft_hold_count = 0
      self._brake_pressed_count = min(-1, self._brake_pressed_count - 1)
