"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

import math
import time

import numpy as np

from openpilot.cereal import messaging, custom, log
from opendbc.car import structs
from opendbc.car.interfaces import ACCEL_MAX, ACCEL_MIN
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.car.cruise import V_CRUISE_MAX
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N, get_accel_from_plan
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.selfdrive.controls.lib.accel_controller.accel_controller import AccelController
from openpilot.sunnypilot.selfdrive.controls.lib.turn_accel import get_future_curvature, limit_accel_in_turns
from openpilot.sunnypilot.selfdrive.controls.lib.cutin_predecel import get_cutin_predecel_accel_limit
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_preview import (
  apply_preview_target, clip_preview_offset, get_lead_preview_request, rate_limit_preview,
)
from openpilot.sunnypilot.selfdrive.controls.lib.dec.dec import DynamicExperimentalController
from openpilot.sunnypilot.selfdrive.controls.lib.e2e_lead_gap.controller import E2ELeadGapController
from openpilot.sunnypilot.selfdrive.controls.lib.e2e_set_speed.controller import E2ESetSpeedController
from openpilot.sunnypilot.selfdrive.controls.lib.e2e_alerts_helper import E2EAlertsHelper
from openpilot.sunnypilot.selfdrive.controls.lib.lead_forecast.forecast import LeadForecast
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.zoompilot import make_smart_cruise_control
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_assist import SpeedLimitAssist
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.assist_mirror import SpeedLimitAssistMirror
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.helpers import pcm_machine_owns_sla
from openpilot.sunnypilot.selfdrive.car.intelligent_cruise_button_management.icbm_latch import icbm_active
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_assist_zp import SpeedLimitAssistZP
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import SpeedLimitResolver
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP
from openpilot.sunnypilot.models.helpers import get_active_bundle
from openpilot.sunnypilot.selfdrive.controls.lib.carrot_longitudinal_source import CarrotLongitudinalSource
from openpilot.sunnypilot.selfdrive.controls.lib.traffic_light_fusion import (
  TrafficLightFusion, FusedState, FusedSource,
)
from openpilot.sunnypilot.carrot.config import UnifiedParams

DecState = custom.LongitudinalPlanSP.DynamicExperimentalControl.DynamicExperimentalControlState
LongitudinalPlanSource = custom.LongitudinalPlanSP.LongitudinalPlanSource
CONTROL_N_T_IDX = ModelConstants.T_IDXS[:CONTROL_N]
MpcPlanSource = log.LongitudinalPlan.LongitudinalPlanSource
TrafficLightState = custom.LongitudinalPlanSP.TrafficLightState

# Map the fusion module's internal enums onto the cereal TrafficLightState enum.
_TRAFFIC_LIGHT_STATE_MAP = {
  FusedState.UNKNOWN: TrafficLightState.State.unknown,
  FusedState.RED: TrafficLightState.State.red,
  FusedState.GREEN: TrafficLightState.State.green,
  FusedState.RED_CONFIRMED: TrafficLightState.State.redConfirmed,
  FusedState.GREEN_CONFIRMED: TrafficLightState.State.greenConfirmed,
}
_TRAFFIC_LIGHT_SOURCE_MAP = {
  FusedSource.NONE: TrafficLightState.Source.none,
  FusedSource.CARROT: TrafficLightState.Source.carrot,
  FusedSource.VISION: TrafficLightState.Source.vision,
  FusedSource.FUSED: TrafficLightState.Source.fused,
}
# NOTE: FusedSource.AMAP / TrafficLightState.Source.amap are kept in their
# respective enums for cereal ordinal compatibility, but no live Amap Web source
# exists any more.

E2E_BRAKE_HOLD_ACCEL = -0.2  # m/s^2


class LongitudinalPlannerSP:
  # set by the host planner before the e2e candidate is built
  CP: structs.CarParams
  allow_throttle: bool
  fcw: bool
  a_cruise: float
  v_desired_trajectory: np.ndarray
  a_desired_trajectory: np.ndarray
  # combined lateral budget used by carrot turn-accel (m/s^2)
  TURN_A_LAT_MAX: float = 3.0

  def __init__(self, CP: structs.CarParams, CP_SP: structs.CarParamsSP, mpc):
    self.accel_controller = AccelController()
    self.accel_controller_active = False
    self.lead_one = None
    self.events_sp = EventsSP()
    self.dec = DynamicExperimentalController(CP, mpc)
    self.e2e_set_speed = E2ESetSpeedController()
    self.e2e_lead_gap = E2ELeadGapController()
    self.a_e2e = 0.  # the e2e candidate both lifts produced, for the floor's count of added speed
    self.lead_forecast = LeadForecast()
    self.lead_forecast.install(mpc)
    self.scc = make_smart_cruise_control(CP)
    self.CP = CP
    self.CP_SP = CP_SP
    self.resolver = SpeedLimitResolver(CP)
    # cars whose setpoint only the driver can move run the SLA machine here; everywhere
    # else it runs in card (the cruise arbiter, next to the buttons and the setpoint) and
    # gets mirrored (speed_limit.helpers.pcm_machine_owns_sla). On Mazda alpha long the owner
    # follows card's ICBM decision, which only moves between engagements.
    self.sla_machine = SpeedLimitAssistZP(CP, CP_SP) if pcm_machine_owns_sla(CP, icbm_active=False) else None
    self.sla_mirror = SpeedLimitAssistMirror(CP, CP_SP)
    self.sla = self._sla_owner(not CP_SP.pcmCruiseSpeed)
    self.scc_actionable = CP.openpilotLongitudinalControl or not CP_SP.pcmCruiseSpeed
    self.generation = int(model_bundle.generation) if (model_bundle := get_active_bundle()) else None
    self.source = LongitudinalPlanSource.cruise
    self.e2e_alerts_helper = E2EAlertsHelper()

    self.output_v_target = 0.
    self.output_a_target = 0.
    self.seed_fault_logged = False

    # Carrot longitudinal source + traffic-light fusion (gated by killswitches;
    # both default OFF so stock behavior is untouched unless explicitly enabled).
    self._params = UnifiedParams()
    self.carrot_source = CarrotLongitudinalSource()
    self.traffic_fusion = TrafficLightFusion()
    self._carrot_enabled = self._params.get_bool("CarrotLongitudinalSourceEnabled")
    self._fusion_enabled = self._params.get_bool("CarrotTrafficLightFusionEnabled")
    self._turn_accel_enabled = self._params.get_bool("CarrotTurnAccelEnabled")
    self._cutin_predecel_enabled = self._params.get_bool("CarrotCutinPredecelEnabled")
    self._lead_preview_enabled = self._params.get_bool("CarrotLeadPreviewEnabled")
    self._lead_preview = 0.0
    self._lead_preview_accel = 0.0
    self._param_count = 0
    self.carrot_should_stop = False
    # Experimental moving-red pipeline. Observation-only until mode 2 is
    # wired: it reads modeld's tmpfs observations and logs a shadow summary,
    # never touching v/a targets or should_stop.
    from openpilot.sunnypilot.carrot.signal_shadow import SignalShadowObserver
    self.signal_shadow = SignalShadowObserver()
    self._signal_shadow_last_log = -1.0
    # Geometric red pre-deceleration execution (experimental). The cap decays
    # the commanded accel toward a gentle braking target; it is only ever
    # applied when SignalAssistMode == 2 (see apply_signal_prepare), so at the
    # default mode this state machine does nothing.
    from openpilot.sunnypilot.carrot.signal_stop_prepare import PrepareAccel
    self._signal_prepare_accel = PrepareAccel()
    self._signal_prepare_time = None
    self._signal_prepare_previous = None

  def is_e2e(self, sm: messaging.SubMaster) -> bool:
    experimental_mode = sm['selfdriveState'].experimentalMode
    if not experimental_mode:
      return False

    if not self.dec.active() or self.dec.mode() == "blended":
      return True

    if self.mpc.source == MpcPlanSource.e2e and sm['modelV2'].action.desiredAcceleration < E2E_BRAKE_HOLD_ACCEL:
      return True

    return False

  def get_max_accel_override(self, v_ego: float, engine_off: bool = False, lead=None) -> float | None:
    if not self.accel_controller.is_enabled():
      return None

    # the eco lead pull-away boost needs the lead; the stock planner does not pass it, so update() keeps it
    return self.accel_controller.get_max_accel(v_ego, engine_off, lead if lead is not None else self.lead_one)

  def get_carrot_max_accel(self, sm: messaging.SubMaster, v_ego: float, v_cruise: float) -> float | None:
    """Optional positive-accel cap from carrot (turn curvature + cut-in risk).
    Off by default; each contributor only ever lowers the cap. Returns the
    tightest of the enabled contributors, or None when all are off."""
    cap = None
    if self._turn_accel_enabled:
      try:
        model = sm['modelV2']
        controls = sm['controlsState']
        curvature = get_future_curvature(model, controls.desiredCurvature)
        capped = limit_accel_in_turns(
          v_ego, curvature, [ACCEL_MIN, ACCEL_MAX], self.TURN_A_LAT_MAX,
          model_msg=model, v_cruise=v_cruise, current_curvature=controls.curvature,
        )
        cap = float(capped[1])
      except (AttributeError, KeyError, TypeError, ValueError, IndexError):
        pass
    if self._cutin_predecel_enabled:
      try:
        limit = get_cutin_predecel_accel_limit(sm['radarState'])
        if limit is not None:
          cap = limit if cap is None else min(cap, limit)
      except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return cap

  def get_cruise_target_override(self, v_ego: float, v_target: float, force_decel: bool, accel_coast: float | None = None) -> float:
    if not self.accel_controller.is_enabled() or force_decel or self.source != LongitudinalPlanSource.cruise:
      return v_target

    return self.accel_controller.get_cruise_target(v_ego, v_target, accel_coast)

  def is_accel_controller_active(self, force_decel: bool) -> bool:
    return bool(self.accel_controller.is_enabled() and not force_decel and
                self.mpc.source == MpcPlanSource.cruise)

  def _has_valid_selected_lead(self, sm: messaging.SubMaster, source: MpcPlanSource) -> bool:
    radar_valid = sm.valid.get('radarState', False) and getattr(sm, 'alive', {}).get('radarState', False)
    return radar_valid and ((source == MpcPlanSource.lead0 and sm['radarState'].leadOne.present) or
                            (source == MpcPlanSource.lead1 and sm['radarState'].leadTwo.present))

  def arbitrate_cruise_candidate(self, sm: messaging.SubMaster, gated: float, ungated: float,
                                 mpc_accel: float, mpc_source: MpcPlanSource, *, allow_throttle: bool,
                                 e2e: bool, force_decel: bool) -> float:
    finite = all(math.isfinite(value) for value in (gated, ungated, mpc_accel))
    coast_gate_changed_source = gated < mpc_accel <= ungated
    if (finite and not allow_throttle and not e2e and not force_decel
        and self._has_valid_selected_lead(sm, mpc_source) and coast_gate_changed_source):
      return ungated

    return gated

  def _sla_owner(self, icbm: bool):
    # the machine exists only on pcm openpilot-long cars, where it owns SLA while ICBM is passive
    return self.sla_machine if self.sla_machine is not None and not icbm else self.sla_mirror

  def update_targets(self, sm: messaging.SubMaster, v_ego: float, a_ego: float, v_cruise: float) -> tuple[float, float]:
    CS = sm['carState']
    v_cruise_cluster_kph = min(CS.vCruiseCluster, V_CRUISE_MAX)
    v_cruise_cluster = v_cruise_cluster_kph * CV.KPH_TO_MS

    long_enabled = sm['carControl'].enabled
    long_override = sm['carControl'].cruiseControl.override

    # Staggered killswitch refresh so enable/disable takes effect within ~5 s.
    self._param_count += 1
    if self._param_count % 100 == 0:
      self._carrot_enabled = self._params.get_bool("CarrotLongitudinalSourceEnabled")
      self._fusion_enabled = self._params.get_bool("CarrotTrafficLightFusionEnabled")

    # Smart Cruise Control
    # SCC has nothing to act through without openpilot long or ICBM, the same condition
    # controlsd gates longActive on. Its params outlive that, so gate it here.
    icbm = icbm_active(sm['carStateSP'], self.CP_SP)
    scc_actionable = self.CP.openpilotLongitudinalControl or icbm
    self.scc.update(sm, long_enabled and scc_actionable, long_override, v_ego, a_ego, v_cruise)

    # Speed Limit Resolver
    self.resolver.update(v_ego, sm)

    # Speed Limit Assist
    sla = self._sla_owner(icbm)
    if sla is not self.sla:
      sla.reset()
      self.sla = sla
    self.sla_mirror.session = sm['carStateSP'].zoompilot.cruiseSession
    has_speed_limit = self.resolver.speed_limit_valid or self.resolver.speed_limit_last_valid
    self.sla.update(long_enabled, long_override, v_ego, a_ego, v_cruise_cluster, self.resolver.speed_limit,
                    self.resolver.speed_limit_final_last, has_speed_limit, self.resolver.distance, self.events_sp)

    self.targets = {
      LongitudinalPlanSource.cruise: (v_cruise, a_ego),
      LongitudinalPlanSource.sccVision: (self.scc.vision.output_v_target, self.scc.vision.output_a_target),
      LongitudinalPlanSource.sccMap: (self.scc.map.output_v_target, self.scc.map.output_a_target),
      LongitudinalPlanSource.speedLimitAssist: (self.sla.output_v_target, self.sla.output_a_target),
    }

    # Carrot longitudinal source (gated by CarrotLongitudinalSourceEnabled; default OFF).
    self.carrot_should_stop = False
    self.carrot_source_active = False
    self.carrot_t_follow = 0.0
    self.carrot_jerk_factor = 0.0
    self.carrot_comfort_brake = 0.0
    self.carrot_stop_distance_margin = 0.0
    self.carrot_traffic_stop_offset = 0.0
    self.carrot_traffic_stop_adjust = 0.0
    self.carrot_lane_change_active = False
    self.carrot_lane_change_gap = None
    self.carrot_dynamic_t_follow_lc = 1.0
    if self._carrot_enabled:
      mpc_mode = self.dec.mode() if self.dec.active() else "acc"
      self.carrot_source.update(sm, v_cruise * CV.MS_TO_KPH, mpc_mode)
      # Carrot as a 5th speed source: its curve-speed / driving-mode target can
      # only ever slow the car below the user-set cruise, never command more
      # speed (clamped to v_cruise), and only on a fresh packet (the adapter's
      # 2 s killswitch). A non-finite value is ignored rather than poisoning min().
      if self.carrot_source.active and math.isfinite(self.carrot_source.v_target):
        carrot_v = min(v_cruise, max(0.0, float(self.carrot_source.v_target)))
        self.targets[LongitudinalPlanSource.carrot] = (carrot_v, a_ego)

    self.source = min(self.targets, key=lambda k: self.targets[k][0])
    v_target, a_target = self.targets[self.source]

    # The pair returned here becomes the MPC seed (set_cur_state pins stage 0 to it), and a
    # single NaN in the seed poisons HPIPM's memory past acados_reset: every solve after it
    # fails, the plan stays at zero and the car never resumes. No source may reach the
    # solver with a non-finite target; fall back to what the cruise path would have given.
    if not (math.isfinite(v_target) and math.isfinite(a_target)):
      if not self.seed_fault_logged:
        self.seed_fault_logged = True
        cloudlog.error(f"longitudinal_planner: non-finite target from {self.source}: v={v_target} a={a_target}")
      v_target = v_cruise if math.isfinite(v_cruise) else v_ego
      a_target = a_ego if math.isfinite(a_ego) else 0.
      if not math.isfinite(v_target):
        v_target = 0.
      self.source = LongitudinalPlanSource.cruise

    self.output_v_target, self.output_a_target = v_target, a_target

    # When the carrot source is active and commanding a stop, flag it for MPC
    # stop-line handling (consumed downstream / by the subclass). Carrot no
    # longer competes for the speed *target* (SLA is the single executor of the
    # road-speed-limit value); its longitudinal adapter now only supplies
    # t-follow / lane-change / traffic-stop data to the MPC when active.
    if self.carrot_source.active:
      self.carrot_source_active = True
      self.carrot_t_follow = float(self.carrot_source.t_follow)
      self.carrot_jerk_factor = float(self.carrot_source.jerk_factor)
      self.carrot_comfort_brake = float(self.carrot_source.comfort_brake)
      self.carrot_stop_distance_margin = float(self.carrot_source.stop_distance_margin)
      self.carrot_traffic_stop_offset = float(self.carrot_source.traffic_stop_model_lead_offset)
      self.carrot_traffic_stop_adjust = float(self.carrot_source.traffic_stop_distance_adjust)
      self.carrot_lane_change_active = bool(self.carrot_source.lane_change_active)
      self.carrot_lane_change_gap = self.carrot_source.lane_change_gap
      self.carrot_dynamic_t_follow_lc = float(self.carrot_source.dynamic_t_follow_lc)
      if self.carrot_source.should_stop:
        self.carrot_should_stop = True

    # Traffic-light fusion (gated by CarrotTrafficLightFusionEnabled; default OFF).
    if self._fusion_enabled:
      self.traffic_fusion.update(sm, v_ego)

    # Experimental moving-red shadow: mode 1 observes only (no control effect),
    # mode 2 reserved for actuation in a later change. Runs independent of the
    # carrot longitudinal source and only does file reads + throttled logging.
    # Kept for the publisher below so the HUD ring does not re-read tmpfs.
    shadow = self._signal_shadow_state = self.signal_shadow.update()
    if shadow.mode > 0:
      now_mono = time.monotonic()
      if now_mono - self._signal_shadow_last_log >= 1.0:
        self._signal_shadow_last_log = now_mono
        cloudlog.event("signalShadow", mode=int(shadow.mode),
                       prepare_seen=bool(shadow.prepare_seen), start_seen=bool(shadow.start_seen),
                       prepare_count=int(self.signal_shadow.prepare_count),
                       start_count=int(self.signal_shadow.start_count))

    return self.output_v_target, self.output_a_target

  def apply_lead_preview(self, sm: messaging.SubMaster, action_t: float, output_a_target_mpc: float,
                         reset_state: bool, v_ego: float) -> tuple[float, float]:
    """Carrot lead-deceleration preview (default OFF behind
    CarrotLeadPreviewEnabled). Evaluates the MPC plan at a previewed action
    time while the radar lead is braking, then keeps only a bounded early
    deceleration (apply_preview_target never raises the target). Returns the
    effective (action_t, mpc accel)."""
    if not self._lead_preview_enabled:
      return action_t, output_a_target_mpc
    try:
      cs = sm['carState']
      preview_enabled = (not self.dec.active() and not reset_state
                         and not cs.gasPressed and not cs.brakePressed)
      lead = sm['radarState'].leadOne
      lead_status = (preview_enabled and bool(getattr(lead, 'present', False))
                     and bool(lead.radar) and int(getattr(lead, 'radarTrackId', -1)) >= 0)
      request = get_lead_preview_request(
        self._driving_mode_value(),
        lead_status=lead_status, a_lead=float(lead.aLeadK), a_ego=float(cs.aEgo),
      )
      if preview_enabled:
        requested = rate_limit_preview(request.offset_s, self._lead_preview)
        self._lead_preview = clip_preview_offset(action_t, requested)
        self._lead_preview_accel = request.lead_accel_signal
        previewed = get_accel_from_plan(self.v_desired_trajectory, self.a_desired_trajectory,
                                        CONTROL_N_T_IDX, action_t=action_t + self._lead_preview)
        output_a_target_mpc = apply_preview_target(output_a_target_mpc, previewed,
                                                   self._driving_mode_value())
      else:
        self._lead_preview = 0.0
        self._lead_preview_accel = 0.0
      return action_t + self._lead_preview, output_a_target_mpc
    except (AttributeError, KeyError, TypeError, ValueError, IndexError):
      return action_t, output_a_target_mpc

  def get_signal_assist_action(self, sm: messaging.SubMaster) -> int:
    """Advisory HUD evidence: 0 unknown, 1 red, 2 green, 3 mixed.

    Shadow only. Sourced from modeld's tmpfs observation records (the same
    ones the start guard / prepare runtime consume), never from a control
    decision, so the ring can never imply that the car is acting on it.
    """
    try:
      observer = getattr(self, "signal_shadow", None)
      if observer is None:
        return 0
      # Colour codes are bit flags (1 red | 2 green = 3 mixed), so a stream
      # disagreeing with the other is mixed rather than one winning.
      state = getattr(self, "_signal_shadow_state", None) or observer.update()
      if int(state.mode) <= 0:
        return 0
      return int(getattr(state, "prepare_color", 0)) | int(getattr(state, "start_color", 0))
    except (AttributeError, TypeError, ValueError):
      return 0

  def get_signal_detection_suspended(self) -> bool:
    """True while the carrot planner has parked signal detection (e.g. motorway).

    Display only: the HUD shows the pause ring so a "no light" reading is not
    mistaken for a missed detection.
    """
    try:
      return bool(getattr(self.carrot_source.carrot, "signal_detection_suspended", False))
    except (AttributeError, TypeError, ValueError):
      return False

  def _driving_mode_value(self) -> int:
    """Carrot driving mode as the 1..4 value longitudinal_preview expects.
    Reads the carrot planner when available (it follows the user param),
    else the param directly; any failure means Normal."""
    try:
      mode = getattr(self.carrot_source.carrot, "_my_driving_mode", None)
      if mode is not None:
        return int(getattr(mode, "value", 3))
      return int(self._params.get_int("MyDrivingMode")) or 3
    except Exception:
      return 3

  def apply_signal_prepare(self, sm: messaging.SubMaster, now: float | None = None) -> None:
    """Geometric red-light pre-deceleration cap on the arbitrated accel.

    Experimental and default-OFF: it only ever engages at SignalAssistMode == 2
    with a fresh, active carrot prepare decision, and it can only ever *lower*
    the commanded accel (PrepareAccel returns min(target, cap)). It never
    requests a stop or a departure - the model keeps owning those. At mode < 2
    this resets the cap and returns, so the default device is byte-for-byte
    unaffected.
    """
    from openpilot.sunnypilot.carrot.signal_mode import signal_mode
    from openpilot.sunnypilot.carrot.signal_stop_prepare import prepare_lead_blocked

    now = time.monotonic() if now is None else now
    elapsed = self.dt if self._signal_prepare_time is None else now - self._signal_prepare_time
    self._signal_prepare_time = now

    carrot = self.carrot_source.carrot
    decision = getattr(carrot, "prepare_decision", None)

    cs = sm['carState']
    active = (
      signal_mode() >= 2
      and decision is not None and bool(getattr(decision, "active", False))
      and bool(getattr(carrot, "prepare_control_active", False))
      and not cs.gasPressed and not cs.brakePressed
      and 5 / 3.6 < cs.vEgo < 82 / 3.6
      and getattr(cs, "softHoldActive", 0) == 0
      and 0 < elapsed <= 0.2
      and not self.output_should_stop
      and not self.dec.active()
      and not prepare_lead_blocked(sm['radarState'])
    )
    previous = cs.aEgo if self._signal_prepare_previous is None else self._signal_prepare_previous
    uncapped = self.output_a_target
    self.output_a_target = float(self._signal_prepare_accel.apply(self.output_a_target, previous, elapsed, active))
    self._signal_prepare_previous = self.output_a_target
    if active and self.output_a_target < uncapped:
      # keep the speed target consistent with the gentler deceleration
      self.output_v_target = min(self.output_v_target, max(0.0, cs.vEgo + self.output_a_target * self.dt))

  def update_e2e_target(self, sm: messaging.SubMaster, a_model: float, reset_state: bool, accel_coast: float) -> float:
    """The e2e candidate after the set-speed floor and the follow-distance assist. The host
    planner min()s it against the MPC and cruise candidates; neither assist can raise it above
    the MPC's behind a lead, so the plan never follows closer than long_mpc would."""
    is_e2e, dec_active = self.is_e2e(sm), self.dec.active()
    # lateral acceleration from the measured steering, as the host's cruise candidate computes it
    CS = sm['carState']
    steer_deg = CS.steeringAngleDeg - sm['vehicleParameters'].angleOffsetDeg
    steer_lat_accel = CS.vEgo ** 2 * math.radians(steer_deg) / (self.CP.steerRatio * self.CP.wheelbase)
    # output_v_target is this frame's cruise target after SCC and SLA
    a_e2e = self.e2e_set_speed.update(sm, a_model, self.output_v_target, is_e2e, reset_state, dec_active,
                                      self.allow_throttle, self.fcw, accel_coast, steer_lat_accel)
    # the MPC candidate as the host planner takes it from this frame's solution
    a_mpc = get_accel_from_plan(self.v_desired_trajectory, self.a_desired_trajectory, CONTROL_N_T_IDX,
                                action_t=self.CP.longitudinalActuatorDelay + DT_MDL)
    # a_cruise is last frame's: the host builds this frame's after the e2e candidate
    self.a_e2e = self.e2e_lead_gap.update(sm, a_e2e, float(a_mpc), is_e2e, reset_state, dec_active, self.allow_throttle,
                                          self.fcw, self.a_cruise, steer_lat_accel)
    return self.a_e2e

  def update(self, sm: messaging.SubMaster) -> None:
    self.accel_controller.update()
    self.lead_one = sm['radarState'].leadOne
    self.events_sp.clear()
    # DEC is driven separately through update_dec() by the host (stock
    # LongitudinalPlanner.update calls it), so it is not ticked here - doing
    # both double-updates it and breaks __new__-based tests that bypass
    # __init__ (no self.dec).
    self.lead_forecast.update(sm)
    self.e2e_alerts_helper.update(sm, self.events_sp)

  def update_dec(self, sm: messaging.SubMaster) -> None:
    self.dec.update(sm)

  def publish_longitudinal_plan_sp(self, sm: messaging.SubMaster, pm: messaging.PubMaster) -> None:
    # the host has chosen: tell the set-speed floor how much of the lift reached the car
    self.e2e_set_speed.delivered(float(self.output_a_target), float(self.a_e2e))

    plan_sp_send = messaging.new_message('longitudinalPlanSP')

    plan_sp_send.valid = sm.all_checks(service_list=['carState', 'controlsState'])

    longitudinalPlanSP = plan_sp_send.longitudinalPlanSP
    longitudinalPlanSP.longitudinalPlanSource = self.source
    longitudinalPlanSP.vTarget = float(self.output_v_target)
    longitudinalPlanSP.aTarget = float(self.output_a_target)
    longitudinalPlanSP.events = self.events_sp.to_msg()

    # Dynamic Experimental Control
    dec = longitudinalPlanSP.dec
    dec.state = DecState.blended if self.dec.mode() == 'blended' else DecState.acc
    dec.enabled = self.dec.enabled()
    dec.active = self.dec.active()
    dec.decelIntent = float(self.dec.signals.decel_intent)
    dec.curveDetected = bool(self.dec.signals.curve_detected)
    dec.wantBlended = bool(self.dec.want_blended)
    dec.leadVeto = bool(self.dec.lead_veto)

    longitudinalPlanSP.signalAssistAction = int(self.get_signal_assist_action(sm))
    longitudinalPlanSP.signalDetectionSuspended = bool(self.get_signal_detection_suspended())

    accel_controller = longitudinalPlanSP.accelController
    accel_controller.enabled = bool(self.accel_controller.is_enabled())
    accel_controller.active = bool(self.accel_controller_active)
    accel_controller.profile = int(self.accel_controller.profile)

    # Lead forecast: how much of each lead the MPC took from the model's forecast, and the
    # trajectory it got (sunnypilot/selfdrive/controls/lib/lead_forecast)
    leadForecast = longitudinalPlanSP.leadForecast
    for report, weight, inhibit, lead_xv in zip((leadForecast.leadOne, leadForecast.leadTwo), self.lead_forecast.weights,
                                                self.lead_forecast.inhibits, self.lead_forecast.lead_xv, strict=True):
      report.weight = float(weight)
      report.inhibit = inhibit
      if lead_xv is not None:
        report.x = lead_xv[:, 0].tolist()
        report.v = lead_xv[:, 1].tolist()

    # e2e assists: what each added to the model's acceleration and, when nothing, why
    e2eSetSpeed = longitudinalPlanSP.e2eSetSpeed
    e2eSetSpeed.authority = float(self.e2e_set_speed.authority)
    e2eSetSpeed.gain = float(self.e2e_set_speed.gain)
    e2eSetSpeed.floor = float(self.e2e_set_speed.floor)
    e2eSetSpeed.boost = float(self.e2e_set_speed.boost)
    e2eSetSpeed.inhibit = self.e2e_set_speed.inhibit

    e2eLeadGap = longitudinalPlanSP.e2eLeadGap
    e2eLeadGap.authority = float(self.e2e_lead_gap.authority)
    e2eLeadGap.gain = float(self.e2e_lead_gap.gain)
    e2eLeadGap.weight = float(self.e2e_lead_gap.weight)
    e2eLeadGap.gapExcess = float(self.e2e_lead_gap.gap_excess)
    e2eLeadGap.boost = float(self.e2e_lead_gap.boost)
    e2eLeadGap.inhibit = self.e2e_lead_gap.inhibit

    # Smart Cruise Control
    smartCruiseControl = longitudinalPlanSP.smartCruiseControl
    # Vision Control
    sccVision = smartCruiseControl.vision
    sccVision.state = self.scc.vision.state
    sccVision.vTarget = float(self.scc.vision.output_v_target)
    sccVision.aTarget = float(self.scc.vision.output_a_target)
    sccVision.currentLateralAccel = float(self.scc.vision.current_lat_acc)
    sccVision.maxPredictedLateralAccel = float(self.scc.vision.max_pred_lat_acc)
    sccVision.enabled = self.scc.vision.is_enabled
    sccVision.active = self.scc.vision.is_active
    # zoompilot's planner only; 0 tells the ICBM servo there is no lookahead
    sccVision.vAheadMin = float(getattr(self.scc.vision, 'v_ahead_min', 0.))
    # Map Control
    sccMap = smartCruiseControl.map
    sccMap.state = self.scc.map.state
    sccMap.vTarget = float(self.scc.map.output_v_target)
    sccMap.aTarget = float(self.scc.map.output_a_target)
    sccMap.enabled = self.scc.map.is_enabled
    sccMap.active = self.scc.map.is_active

    # Speed Limit
    speedLimit = longitudinalPlanSP.speedLimit
    resolver = speedLimit.resolver
    resolver.speedLimit = float(self.resolver.speed_limit)
    resolver.speedLimitLast = float(self.resolver.speed_limit_last)
    resolver.speedLimitFinal = float(self.resolver.speed_limit_final)
    resolver.speedLimitFinalLast = float(self.resolver.speed_limit_final_last)
    resolver.speedLimitValid = self.resolver.speed_limit_valid
    resolver.speedLimitLastValid = self.resolver.speed_limit_last_valid
    resolver.speedLimitOffset = float(self.resolver.speed_limit_offset)
    resolver.distToSpeedLimit = float(self.resolver.distance)
    resolver.source = self.resolver.source
    assist = speedLimit.assist
    assist.state = self.sla.state
    assist.enabled = self.sla.is_enabled
    assist.active = self.sla.is_active
    assist.vTarget = float(self.sla.output_v_target)
    assist.aTarget = float(self.sla.output_a_target)

    # E2E Alerts
    e2eAlerts = longitudinalPlanSP.e2eAlerts
    e2eAlerts.greenLightAlert = self.e2e_alerts_helper.green_light_alert
    e2eAlerts.leadDepartAlert = self.e2e_alerts_helper.lead_depart_alert

    # Carrot longitudinal source (gated; default OFF). Reflect the planner's
    # raw outputs for shadow-mode logging / debugging.
    if self._carrot_enabled:
      carrot_plan = longitudinalPlanSP.carrot
      carrot_plan.xState = str(self.carrot_source.carrot.x_state)
      carrot_plan.drivingMode = str(self.carrot_source.carrot.driving_mode)
      carrot_plan.vTarget = float(self.carrot_source.v_target)
      carrot_plan.aTarget = float(self.carrot_source.a_target)
      carrot_plan.stopDist = float(self.carrot_source.stop_dist)
      carrot_plan.active = bool(self.carrot_source.active)

    # Traffic-light fusion (gated; default OFF).
    if self._fusion_enabled:
      tl = longitudinalPlanSP.trafficLight
      fused = self.traffic_fusion
      tl.lightState = _TRAFFIC_LIGHT_STATE_MAP[fused.state]
      tl.source = _TRAFFIC_LIGHT_SOURCE_MAP[fused.source]
      tl.confidence = float(fused.confidence)
      tl.distance = float(fused.distance)

    # zoompilot: experimental mode's set-speed floor and follow-distance assist, the model's lead forecast
    zoompilot = longitudinalPlanSP.zoompilot
    self.e2e_set_speed.fill(zoompilot.e2eSetSpeed)
    self.e2e_lead_gap.fill(zoompilot.e2eLeadGap)
    self.lead_forecast.fill(zoompilot.leadForecast)
    # zoompilot's vision planner only; 0 tells the ICBM servo there is no lookahead
    zoompilot.sccVAheadMin = float(getattr(self.scc.vision, 'v_ahead_min', 0.))

    pm.send('longitudinalPlanSP', plan_sp_send)
