#!/usr/bin/env python3
import math
import numpy as np

import openpilot.cereal.messaging as messaging
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX
from openpilot.common.constants import CV
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.selfdrive.controls.lib.accel_boost import AccelBoost
from openpilot.selfdrive.controls.lib.longcontrol import LongCtrlState
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc, LongitudinalPlanSource
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import T_IDXS as T_IDXS_MPC
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import (
  STOP_DISTANCE,
  desired_follow_distance,
)
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N, get_accel_from_plan, should_stop
from openpilot.selfdrive.controls.lib.lead_follow_policy import apply as apply_follow_policy
from openpilot.selfdrive.controls.lib.longitudinal_uncertainty import (
  UncertaintyTracker,
  compute_raw_uncertainty,
  panic_window_flags,
  should_panic_bypass,
)
from openpilot.selfdrive.car.cruise import V_CRUISE_MAX, V_CRUISE_UNSET
from openpilot.common.swaglog import cloudlog

from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlannerSP
from openpilot.sunnypilot.carrot.traffic_stop import (
  get_traffic_stop_distance_adjust, get_traffic_stop_obstacle_distance,
)

A_CRUISE_MAX_VALS = [1.6, 1.2, 0.8, 0.6]
A_CRUISE_MAX_BP = [0., 10.0, 25., 40.]
J_CRUISE_VALS = [1.6, 1.2, 0.8, 0.6]
A_CRUISE_MIN = -1.2
CONTROL_N_T_IDX = ModelConstants.T_IDXS[:CONTROL_N]
ALLOW_THROTTLE_THRESHOLD = 0.4
MIN_ALLOW_THROTTLE_SPEED = 2.5

# Lookup table for turns
_A_TOTAL_MAX_V = [1.7, 3.2]
_A_TOTAL_MAX_BP = [20., 40.]

def get_max_accel(v_ego):
  return np.interp(v_ego, A_CRUISE_MAX_BP, A_CRUISE_MAX_VALS)

def get_coast_accel(pitch):
  return np.sin(pitch) * -5.65 - 0.3  # fitted from data using xx/projects/allow_throttle/compute_coast_accel.py

def get_cruise_accel(e2e, v_cruise, v_ego, a_cruise_prev, angle_steers, CP, dt, accel_coast, allow_throttle,
                      max_accel_override=None, carrot_max_accel=None, weather_accel_scale=1.0):
  if max_accel_override is not None:
    max_accel = max_accel_override
  else:
    max_accel = ACCEL_MAX if e2e else get_max_accel(v_ego)
  if not e2e:
    # StarPilot weather margin: a wet road lowers the acceleration ceiling.
    # The e2e branch is left alone - that path is the end-to-end model's own
    # budget, not the driver's comfort setting.
    if weather_accel_scale != 1.0 and math.isfinite(weather_accel_scale):
      max_accel *= float(weather_accel_scale)
    a_total_max = np.interp(v_ego, _A_TOTAL_MAX_BP, _A_TOTAL_MAX_V)
    a_y = v_ego ** 2 * angle_steers * CV.DEG_TO_RAD / (CP.steerRatio * CP.wheelbase)
    a_x_allowed = math.sqrt(max(a_total_max ** 2 - a_y ** 2, 0.))
    max_accel = min(max_accel, a_x_allowed)
    # Carrot turn-accel / cutin-predecel (optional): tighten further using the
    # *upcoming* model curvature and corner-radar cut-in risk, not just the
    # present steering angle. Only ever lowers the cap.
    if carrot_max_accel is not None and math.isfinite(carrot_max_accel):
      max_accel = min(max_accel, carrot_max_accel)
    if not allow_throttle:
      clipped_accel_coast = max(accel_coast, ACCEL_MIN)
      coast_limit = np.interp(v_ego, [MIN_ALLOW_THROTTLE_SPEED, MIN_ALLOW_THROTTLE_SPEED*2], [max_accel, clipped_accel_coast])
      max_accel = min(max_accel, coast_limit)

  target_accel = np.clip(v_cruise - v_ego, A_CRUISE_MIN, max_accel)
  j_cruise = np.interp(v_ego, A_CRUISE_MAX_BP, J_CRUISE_VALS)
  target_accel = float(np.clip(target_accel, a_cruise_prev - j_cruise * dt, a_cruise_prev + j_cruise * dt))

  return target_accel


from openpilot.sunnypilot.common.param_read import read_bool
from openpilot.sunnypilot.selfdrive.controls.lib.lane_change_close_gap import LaneChangeCloseGap


class LongitudinalPlanner(LongitudinalPlannerSP):
  def __init__(self, CP, CP_SP, init_v=0.0, init_a=0.0, dt=DT_MDL):
    self.CP = CP
    self.mpc = LongitudinalMpc(dt=dt)
    LongitudinalPlannerSP.__init__(self, self.CP, CP_SP, self.mpc)
    self.fcw = False
    self.dt = dt
    self.allow_throttle = True
    self.accel_boost = AccelBoost()
    self._params = Params()
    self._policy_frame = 0
    self.lead_follow_policy_enabled = self._params.get_bool("LeadFollowPolicyEnabled")
    self._stop_depart_frame = 0
    self.lead_stop_depart_enabled = self._params.get_bool("LeadStopDepartPolicyEnabled")
    self._stop_depart_policy = None  # lazy: stateful stop/depart shaper
    # StarPilot uncertainty/panic gate + duplicate guard + model trajectory
    # (all default off; refreshed from params every 20 frames like the above)
    self._uncert_frame = 0
    self.uncertainty_policy_enabled = self._params.get_bool("UncertaintyPanicBypassEnabled")
    self.duplicate_guard_enabled = self._params.get_bool("LeadDuplicateGuardEnabled")
    self.model_lead_enabled = self._params.get_bool("ModelLeadTrajectoryEnabled")
    self._uncert_tracker = None  # lazy: UncertaintyTracker(self.dt)
    # Absolute lane-change headway (default off until the key is registered;
    # read fault-tolerantly so an unregistered key cannot kill the planner).
    self.lane_change_close_gap_enabled = read_bool(self._params, "LaneChangeCloseGapEnabled")
    self._lc_close_gap = LaneChangeCloseGap(dt=dt)

    self.v_desired_filter = FirstOrderFilter(init_v, 2.0, self.dt)
    self.a_cruise = init_a
    self.output_a_target = init_a
    self.output_should_stop = False

    self.v_desired_trajectory = np.zeros(CONTROL_N)
    self.a_desired_trajectory = np.zeros(CONTROL_N)
    self.j_desired_trajectory = np.zeros(CONTROL_N)

  def update(self, sm):
    LongitudinalPlannerSP.update(self, sm)
    self.refresh_weather_offsets()

    if len(sm['carControl'].orientationNED) == 3:
      accel_coast = get_coast_accel(sm['carControl'].orientationNED[1])
    else:
      accel_coast = ACCEL_MAX

    v_ego = sm['carState'].vEgo
    v_cruise_kph = min(sm['carState'].vCruise, V_CRUISE_MAX)
    v_cruise = v_cruise_kph * CV.KPH_TO_MS
    force_decel = sm['controlsState'].forceDecel
    if force_decel:
      v_cruise = 0.0

    long_control_off = sm['controlsState'].longControlState == LongCtrlState.off

    # Reset current state when not engaged, or user is controlling the speed
    reset_state = long_control_off if self.CP.openpilotLongitudinalControl else not sm['selfdriveState'].enabled
    # PCM cruise speed may be updated a few cycles later, check if initialized
    v_cruise_initialized = sm['carState'].vCruise != V_CRUISE_UNSET
    reset_state = reset_state or not v_cruise_initialized

    throttle_probs = sm['modelV2'].meta.disengagePredictions.gasPressProbs
    throttle_prob = throttle_probs[1] if len(throttle_probs) > 1 else 1.0
    self.allow_throttle = throttle_prob > ALLOW_THROTTLE_THRESHOLD or v_ego <= MIN_ALLOW_THROTTLE_SPEED

    steer_angle_without_offset = sm['carState'].steeringAngleDeg - sm['vehicleParameters'].angleOffsetDeg

    if reset_state:
      self.v_desired_filter.x = v_ego
      self.output_a_target = np.clip(sm['carState'].aEgo, ACCEL_MIN, ACCEL_MAX)
      self.a_cruise = self.output_a_target

    # Prevent divergence, smooth in current v_ego
    self.v_desired_filter.x = max(0.0, self.v_desired_filter.update(v_ego))

    # No change cost when user is controlling the speed, or when standstill
    prev_accel_constraint = not (reset_state or sm['carState'].standstill)

    # Get new v_cruise and a_target from Smart Cruise Control and Speed Limit Assist
    v_cruise, self.output_a_target = LongitudinalPlannerSP.update_targets(self, sm, self.v_desired_filter.x,
                                                                          self.output_a_target, v_cruise,
                                                                          reset_state=reset_state)

    self.mpc.set_weights(prev_accel_constraint, personality=sm['selfdriveState'].personality,
                         jerk_factor=self.carrot_jerk_factor if self.carrot_source_active else None)
    self.mpc.set_cur_state(self.v_desired_filter.x, self.output_a_target)

    # The follow time Carrot contributes, scaled by how far the user moved
    # sunnypilot's Longitudinal MPC Tuning value from its default. Carrot supplies
    # the dynamics (speed interpolation, driving-mode factor, deceleration boost);
    # the user's tuning decides the nominal gap. On default params the scale is
    # exactly 1.0, so this is behaviour-preserving; previously Carrot replaced the
    # tuned value outright and the tuning page was ignored while it was active.
    personality = sm['selfdriveState'].personality
    carrot_t_follow = None
    if self.carrot_source_active:
      carrot_t_follow = self.carrot_t_follow * self.mpc.t_follow_user_scale(personality, v_ego)

    # StarPilot weather margin on the follow time. Kept separate from
    # carrot_t_follow: that variable also decides whether the Carrot source
    # is in charge further down, and the weather margin applies to the stock
    # path too. The offset is zero unless the user asked for it.
    weather_t_follow = self.weather_offsets.increase_following_distance

    # The follow time that is actually in effect this frame. The Carrot
    # source takes precedence, then the weather margin on top of whichever
    # base is in use, then the stock personality value.
    base_t_follow = carrot_t_follow if carrot_t_follow is not None else self.mpc.get_t_follow(personality, v_ego)
    effective_t_follow = base_t_follow + weather_t_follow

    # Absolute lane-change headway shortening (default off). While the driver
    # signals out of the lane, ramp toward an absolute headway that can only
    # shorten the gap; blindspot / braking-lead / low-speed gates trip it back.
    if self.lane_change_close_gap_enabled:
      meta = sm['modelV2'].meta
      lead_one = sm['radarState'].leadOne
      effective_t_follow = self._lc_close_gap.update(
        bool(sm['selfdriveState'].enabled), v_ego, bool(sm['carState'].standstill),
        int(meta.laneChangeState), int(meta.laneChangeDirection),
        bool(sm['carState'].leftBlindspot), bool(sm['carState'].rightBlindspot),
        bool(lead_one.status), float(lead_one.aLeadK), effective_t_follow)
    else:
      self._lc_close_gap.reset()

    # CarrotPlanner longitudinal overrides (Option C). Only applied when the
    # carrot source is active, so stock behavior is untouched otherwise. These
    # never change PARAM_DIM or rebuild the acados solver. Stop distance is not
    # among them: it is baked into the solver at codegen, so the planned stop is
    # injected as a virtual obstacle instead (see stop_obstacle_distance below).
    mpc_carrot_kwargs: dict = {}
    if self.carrot_source_active:
      mpc_carrot_kwargs['comfort_brake'] = self.carrot_comfort_brake

      # Inject the planned stop as a virtual obstacle so the MPC brakes toward
      # the CarrotPlanner stop point. Blended against the current lead obstacle
      # so a closer real lead still wins (safety floor preserved).
      if self.carrot_should_stop:
        cruise_obstacle = float(self.mpc.lead_0_obstacle[0]) if self.mpc.lead_0_obstacle is not None else 1000.0
        adjust = get_traffic_stop_distance_adjust(self.carrot_traffic_stop_adjust, v_ego,
                                                 self.carrot_traffic_stop_offset)
        stop_obstacle = get_traffic_stop_obstacle_distance(self.carrot_source.stop_dist, cruise_obstacle, adjust)
        if 0.0 < stop_obstacle < 1e5:
          mpc_carrot_kwargs['stop_obstacle_distance'] = float(stop_obstacle)

      # Lane-change gap credit: permit a bounded ACC departure once the gap is
      # clear. The tracker's own guards gate on confidence / clearance / speed.
      if self.carrot_lane_change_active and self.carrot_lane_change_gap is not None \
              and getattr(self.carrot_lane_change_gap, 'active', False):
        credit = self.carrot_lane_change_gap.credit(
          sm['radarState'].leadOne, T_IDXS_MPC, v_ego, ACCEL_MAX,
          carrot_t_follow, self.carrot_stop_distance_margin, self.carrot_dynamic_t_follow_lc,
        )
        if credit is not None and np.any(credit):
          mpc_carrot_kwargs['lane_change_credit'] = credit

    # Carrot gap/comfort refinements (each default off; only passed when on so
    # the stock solver input is byte-identical while they are disabled).
    if self._gap_recovery_enabled or self._braking_gap_enabled or self._cutout_relief_enabled:
      mpc_carrot_kwargs['reset_state'] = reset_state
      mpc_carrot_kwargs['lead_gap_enabled'] = self._gap_recovery_enabled
      mpc_carrot_kwargs['lead_comfort_enabled'] = self._braking_gap_enabled
      mpc_carrot_kwargs['cutout_relief_enabled'] = self._cutout_relief_enabled
      mpc_carrot_kwargs['lead_accel_response'] = int(getattr(self.carrot_source.carrot, 'leadAccelResponse', 0) or 0)
      mpc_carrot_kwargs['lane_change_active'] = self.carrot_lane_change_active

    # StarPilot uncertainty panic gate (default off). Combines desire entropy
    # + decayed brake-press risk into a scene uncertainty metric; a fast rise
    # or high magnitude while closing on a nearby lead bypasses downstream
    # comfort smoothing this frame. Refresh gates every 20 frames.
    self._uncert_frame += 1
    if self._uncert_frame % 20 == 0:
      self.uncertainty_policy_enabled = self._params.get_bool("UncertaintyPanicBypassEnabled")
      self.duplicate_guard_enabled = self._params.get_bool("LeadDuplicateGuardEnabled")
      self.model_lead_enabled = self._params.get_bool("ModelLeadTrajectoryEnabled")
    panic_bypass = False
    if self.uncertainty_policy_enabled:
      if self._uncert_tracker is None:
        self._uncert_tracker = UncertaintyTracker(self.dt)
      raw_uncertainty = compute_raw_uncertainty(sm['modelV2'].meta)
      uncertainty, _uncertainty_accel, uncert_slope = self._uncert_tracker.update(
        raw_uncertainty, sm.logMonoTime['modelV2'] / 1e9)
      uncert_t_follow = effective_t_follow
      uncert_lead = sm['radarState'].leadOne
      if uncert_lead is not None and uncert_lead.present:
        scene_desired_gap = float(desired_follow_distance(
          v_ego, float(uncert_lead.vLead), self.mpc.comfort_brake, STOP_DISTANCE, uncert_t_follow))
        panic_close_window, _closing_speed, closing_fast = panic_window_flags(uncert_lead, v_ego, scene_desired_gap)
        panic_bypass = should_panic_bypass(uncertainty, uncert_slope, panic_close_window, closing_fast)

    self.mpc.update(sm['radarState'], personality=personality,
                    t_follow=effective_t_follow,
                    model_leads=sm['modelV2'].leadsV3 if self.model_lead_enabled else None,
                    duplicate_guard_enabled=self.duplicate_guard_enabled,
                    panic_bypass=panic_bypass,
                    v_ego=v_ego,
                    **mpc_carrot_kwargs)

    self.v_desired_trajectory = np.interp(CONTROL_N_T_IDX, T_IDXS_MPC, self.mpc.v_solution)
    self.a_desired_trajectory = np.interp(CONTROL_N_T_IDX, T_IDXS_MPC, self.mpc.a_solution)
    self.j_desired_trajectory = np.interp(CONTROL_N_T_IDX, T_IDXS_MPC[:-1], self.mpc.j_solution)

    # TODO counter is only needed because radar is glitchy, remove once radar is gone
    self.fcw = self.mpc.crash_cnt > 2 and not sm['carState'].standstill
    if self.fcw:
      cloudlog.info("FCW triggered")

    # Save starting point for next iteration
    a_prev = self.output_a_target

    action_t =  self.CP.longitudinalActuatorDelay + DT_MDL
    output_a_target_mpc = get_accel_from_plan(self.v_desired_trajectory, self.a_desired_trajectory, CONTROL_N_T_IDX,
                                              action_t=action_t)
    # Carrot lead-deceleration preview (optional, default OFF): evaluate the
    # same MPC plan at a previewed action time when the lead is braking, then
    # apply only a bounded early deceleration. Never adds acceleration.
    action_t, output_a_target_mpc = self.apply_lead_preview(
      sm, action_t, output_a_target_mpc, reset_state, v_ego)
    output_should_stop_mpc = should_stop(v_ego, output_a_target_mpc)
    output_a_target_e2e = sm['modelV2'].action.desiredAcceleration
    output_should_stop_e2e = sm['modelV2'].action.shouldStop

    is_e2e = self.is_e2e(sm)
    output_a_target_e2e, output_should_stop_e2e = LongitudinalPlannerSP.update_e2e_target(
      self, sm, output_a_target_e2e, output_should_stop_e2e, reset_state)

    max_accel_override = self.get_max_accel_override(v_ego, sm['carStateSP'].engineOff)
    carrot_max_accel = self.get_carrot_max_accel(sm, v_ego, v_cruise)
    weather_accel_scale = 1.0 - self.weather_offsets.reduce_acceleration
    v_cruise = self.get_cruise_target_override(v_ego, v_cruise, force_decel, accel_coast if accel_coast < 0.0 else None)
    a_cruise_prev = self.a_cruise
    gated_cruise = get_cruise_accel(is_e2e, v_cruise, v_ego, a_cruise_prev, steer_angle_without_offset,
                                    self.CP, self.dt, accel_coast, self.allow_throttle, max_accel_override,
                                    carrot_max_accel, weather_accel_scale)
    ungated_cruise = get_cruise_accel(is_e2e, v_cruise, v_ego, a_cruise_prev, steer_angle_without_offset,
                                      self.CP, self.dt, accel_coast, True, max_accel_override,
                                      carrot_max_accel, weather_accel_scale)
    self.a_cruise = self.arbitrate_cruise_candidate(
      sm, gated_cruise, ungated_cruise, output_a_target_mpc, self.mpc.source,
      allow_throttle=self.allow_throttle, e2e=is_e2e, force_decel=force_decel,
    )
    cruise_should_stop = should_stop(v_ego, self.a_cruise)

    output_a_target_e2e = self.accel_boost.update(sm, output_a_target_e2e, output_a_target_mpc, self.a_cruise)

    candidates = [(output_a_target_mpc, self.mpc.source, output_should_stop_mpc),
                  (self.a_cruise, LongitudinalPlanSource.cruise, cruise_should_stop)]
    if is_e2e:
      candidates.append((output_a_target_e2e, LongitudinalPlanSource.e2e, output_should_stop_e2e))

    output_a_target, self.mpc.source, _ = min(candidates, key=lambda c: c[0])
    self.output_should_stop = any(should_stop for _, _, should_stop in candidates)
    self.output_a_target = np.clip(output_a_target, ACCEL_MIN, ACCEL_MAX)

    # StarPilot lead_follow_policy: shape only the non-urgent follow output of
    # an MPC-selected lead. Gated (default off) and never applied to e2e,
    # stops, force decel or post-departure handoffs.
    self._policy_frame += 1
    if self._policy_frame % 20 == 0:
      self.lead_follow_policy_enabled = self._params.get_bool("LeadFollowPolicyEnabled")
      self.lane_change_close_gap_enabled = read_bool(self._params, "LaneChangeCloseGapEnabled")
    if self.lead_follow_policy_enabled and self.mpc.source in (LongitudinalPlanSource.lead0, LongitudinalPlanSource.lead1):
      follow_result = apply_follow_policy(
        sm['radarState'].leadOne, sm['radarState'].leadTwo,
        source='lead0' if self.mpc.source == LongitudinalPlanSource.lead0 else 'lead1',
        active=bool(sm['selfdriveState'].enabled), v_ego=v_ego, t_follow=effective_t_follow,
        previous_target=float(a_prev), raw_target=float(self.output_a_target),
        tracking=True, post_departure=False,
        blocked=bool(force_decel or self.output_should_stop), panic_bypass=panic_bypass)
      self.output_a_target = float(np.clip(follow_result.target, ACCEL_MIN, ACCEL_MAX))

    # StarPilot stop/depart policy: vision-lead approach caps, low-speed stop
    # buffer, close-stop hold floors, standstill lead-depart releases. Gated
    # (default off); when off this whole stage is a pass-through and the
    # plan above is untouched.
    self._stop_depart_frame += 1
    if self._stop_depart_frame % 20 == 0:
      self.lead_stop_depart_enabled = self._params.get_bool("LeadStopDepartPolicyEnabled")
    if self.lead_stop_depart_enabled and not force_decel:
      from openpilot.selfdrive.controls.lib.lead_stop_depart_policy import LeadStopDepartPolicy, StopDepartContext
      if self._stop_depart_policy is None:
        self._stop_depart_policy = LeadStopDepartPolicy(self.CP, self.dt)
      stop_ctx = StopDepartContext(
        CP=self.CP, dt=self.dt,
        lead_one=sm['radarState'].leadOne, lead_two=sm['radarState'].leadTwo,
        v_ego=v_ego, standstill=bool(sm['carState'].standstill),
        brake_pressed=bool(sm['carState'].brakePressed), gas_pressed=bool(sm['carState'].gasPressed),
        long_control_stopping=sm['controlsState'].longControlState == LongCtrlState.stopping,
        active=bool(sm['selfdriveState'].enabled),
        tracking=self.mpc.source in (LongitudinalPlanSource.lead0, LongitudinalPlanSource.lead1),
        t_follow=effective_t_follow,
        a_target=float(self.output_a_target), should_stop=bool(self.output_should_stop),
        output_accel_min=float(ACCEL_MIN),
        model_desired_accel=float(sm['modelV2'].action.desiredAcceleration),
        model_should_stop=bool(sm['modelV2'].action.shouldStop),
        model_data=sm['modelV2'],
        source='lead1' if self.mpc.source == LongitudinalPlanSource.lead1 else 'lead0',
      )
      stop_result = self._stop_depart_policy.apply(stop_ctx)
      self.output_a_target = float(np.clip(stop_result.a_target, ACCEL_MIN, ACCEL_MAX))
      self.output_should_stop = stop_result.should_stop

    # sunnypilot: geometric red-light pre-deceleration runs after the final
    # arbitration so its gentle cap cannot be overwritten. A no-op unless the
    # SignalAssistMode killswitch is set (the SP subclass owns the gating).
    if hasattr(self, 'apply_signal_prepare'):
      self.apply_signal_prepare(sm)
    self.accel_controller_active = self.is_accel_controller_active(force_decel)

    self.v_desired_filter.x = self.v_desired_filter.x + self.dt * (self.output_a_target + a_prev) / 2.0

  def publish(self, sm, pm):
    plan_send = messaging.new_message('longitudinalPlan')

    plan_send.valid = sm.all_checks()

    longitudinalPlan = plan_send.longitudinalPlan
    longitudinalPlan.modelMonoTime = sm.logMonoTime['modelV2']
    longitudinalPlan.processingDelay = (plan_send.logMonoTime / 1e9) - sm.logMonoTime['modelV2']
    longitudinalPlan.solverExecutionTime = self.mpc.solve_time

    longitudinalPlan.speeds = self.v_desired_trajectory.tolist()
    longitudinalPlan.accels = self.a_desired_trajectory.tolist()
    longitudinalPlan.jerks = self.j_desired_trajectory.tolist()

    longitudinalPlan.hasLead = sm['radarState'].leadOne.present
    longitudinalPlan.longitudinalPlanSource = self.mpc.source
    longitudinalPlan.fcw = self.fcw

    longitudinalPlan.aTarget = float(self.output_a_target)
    longitudinalPlan.accelBoost = float(self.accel_boost.total_boost)
    longitudinalPlan.shouldStop = bool(self.output_should_stop)
    longitudinalPlan.allowBrake = True
    longitudinalPlan.allowThrottle = bool(self.allow_throttle)

    pm.send('longitudinalPlan', plan_send)

    self.publish_longitudinal_plan_sp(sm, pm)
