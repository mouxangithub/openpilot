#!/usr/bin/env python3
"""StarPilot stop/depart policy: vision-lead approach caps, close-stop hold
floors, and standstill lead-depart release, ported from StarPilot's planner
(MIT) as a self-contained module.

Scope notes (this fork):
- Lead presence: sp's log.capnp names the flag `present` (StarPilot renamed it
  to `status`); every check goes through `_lead_present` which reads both.
- `desired_follow_distance` is StarPilot's three-argument shape; here it is
  bridged onto sp's `long_mpc` five-argument version with the same pure
  fallback as lead_follow_policy.
- Channels that only exist in StarPilot (starpilotPlan.forcingStop / redLight /
  stopSignConfirmed / toggles) are provided by the caller and default to False
  on this fork. Depart safety still vetoes through the off-center radar/model
  conflict check.
- E2E/experimental handoff, model launch, manual stop resume and panic windows
  are StarPilot e2e-stack features without an sp foundation and are not ported;
  the MPC-level plan is never touched — this policy only shapes the final
  output a_target / should_stop after arbitration.
- Compared with StarPilot, this stage runs after the follow-smoothing hook
  (sp applies lead_follow_policy first); the cap/floor ordering inside this
  stage keeps the StarPilot sequence.
"""

import time
from dataclasses import dataclass, field

import numpy as np

from openpilot.selfdrive.controls.lib.lead_follow_policy import _desired_follow_distance as desired_follow_distance
from openpilot.selfdrive.controls.lib.longitudinal_vehicle_tunes import (
  get_honda_accord_stop_go_accel_cap,
  get_honda_accord_stop_go_accel_rise_rate,
  get_standstill_gap_settle_max_extra_gap,
  get_standstill_stopped_lead_guard_distance_margin,
  get_standstill_stopped_lead_guard_max_ego_speed,
  get_standstill_stopped_lead_guard_max_lead_speed,
  get_toyota_rav4_tss2_lead_creep_tune,
  get_toyota_rav4_tss2_lead_departure_tune,
  get_untracked_slow_lead_decel_scale,
  get_vision_low_speed_stop_buffer_lead_speed_limits,
)

STOP_DISTANCE_FALLBACK = 6.0

STANDSTILL_LEAD_NUDGE_ACCEL = 0.05
STANDSTILL_LEAD_NUDGE_MIN_SPEED = 0.0
STANDSTILL_LEAD_NUDGE_MIN_LEAD_ACCEL = 0.2
STANDSTILL_LEAD_DEPART_MIN_ACCEL = 0.35
STANDSTILL_LEAD_DEPART_MAX_EGO_SPEED = 1.5
STANDSTILL_LEAD_DEPART_MIN_LEAD_SPEED = 0.6
STANDSTILL_LEAD_DEPART_MIN_GAP_MARGIN = 0.8
STANDSTILL_LEAD_DEPART_MIN_MODEL_ACCEL = 0.08
STANDSTILL_LEAD_CREEP_RELEASE_MIN_ACCEL = 0.18
STANDSTILL_LEAD_CREEP_RELEASE_CONFIRM_TIME = 0.30
STANDSTILL_LEAD_CREEP_RELEASE_MIN_LEAD_SPEED = 0.25
STANDSTILL_LEAD_CREEP_RELEASE_MIN_LEAD_ACCEL = 0.08
STANDSTILL_LEAD_CREEP_RELEASE_MIN_GAP_MARGIN = 0.1
RADAR_STANDSTILL_GAP_SETTLE_ACCEL = 0.18
LEAD_DEPART_CONFIDENT_CONFIRM_TIME = 0.35
LEAD_DEPART_RELEASE_HOLD_TIME = 1.5
LEAD_DEPART_RELEASE_HOLD_CONFIRM_TIME = 0.15
STANDSTILL_STOPPED_LEAD_GUARD_MAX_EGO_SPEED = 0.5
STANDSTILL_STOPPED_LEAD_GUARD_MAX_LEAD_SPEED = 0.45
STANDSTILL_STOPPED_LEAD_GUARD_MAX_LEAD_DELTA = 0.50
STANDSTILL_STOPPED_LEAD_GUARD_MIN_MODEL_PROB = 0.95
STANDSTILL_STOPPED_LEAD_GUARD_MAX_LATERAL_OFFSET = 1.75
STANDSTILL_STOPPED_LEAD_GUARD_MIN_DISTANCE = 3.0
STANDSTILL_STOPPED_LEAD_GUARD_DISTANCE_MARGIN = 3.0
STANDSTILL_STOPPED_LEAD_GUARD_MIN_BRAKE = 0.16
STANDSTILL_STOPPED_LEAD_GUARD_MAX_BRAKE = 0.26
LEAD_DEPART_ACCEL_HOLD_TIME = 1.2
LEAD_DEPART_ACCEL_HOLD_MAX_EGO_SPEED = 2.0
CLOSE_LEAD_BRAKE_CAP_MAX_TTC = 25.0
INSIDE_GAP_CLOSING_MIN_EGO_SPEED = 8.0
INSIDE_GAP_CLOSING_MIN_LEAD_SPEED = 5.0
INSIDE_GAP_CLOSING_MIN_SPEED = 0.5
INSIDE_GAP_CLOSING_FULL_SPEED = 2.5
INSIDE_GAP_CLOSING_MIN_DEFICIT = 3.0
INSIDE_GAP_CLOSING_DEFICIT_RATIO = 0.15
INSIDE_GAP_CLOSING_BRAKE_DEFICIT_RATIO = 0.25
INSIDE_GAP_CLOSING_BRAKE_MIN_SPEED = 1.0
INSIDE_GAP_CLOSING_MAX_DECEL = 0.65
INSIDE_GAP_CLOSING_MAX_LATERAL_OFFSET = 1.75
INSIDE_GAP_CLOSING_VISION_MIN_MODEL_PROB = 0.95
VISION_LEAD_APPROACH_MIN_CLOSING_SPEED = 2.0
VISION_LEAD_APPROACH_TRIGGER_TIME = 4.5
VISION_LEAD_APPROACH_FULL_TIME = 1.0
VISION_LEAD_APPROACH_TIGHT_BUFFER = 2.0
VISION_LEAD_APPROACH_MAX_DECEL = 0.80
VISION_LEAD_APPROACH_MIN_DECEL = 0.15
VISION_LEAD_APPROACH_MIN_MODEL_PROB = 0.85
VISION_LEAD_APPROACH_FULL_MODEL_PROB = 0.98
VISION_LEAD_APPROACH_DEFICIT_MAX_DECEL = 1.30
VISION_LEAD_APPROACH_DEFICIT_BUFFER_MIN = 3.0
VISION_LEAD_APPROACH_DEFICIT_BUFFER_GAIN = 0.20
VISION_LEAD_APPROACH_BRAKING_DEFICIT_MIN = 0.75
VISION_LEAD_APPROACH_BRAKING_MIN_LEAD_BRAKE = 0.45
VISION_LEAD_APPROACH_BRAKING_FULL_LEAD_BRAKE = 1.20
VISION_LEAD_APPROACH_BRAKING_FLOOR_MIN_DECEL = 1.30
VISION_LEAD_APPROACH_BRAKING_FLOOR_MAX_DECEL = 1.75
VISION_LEAD_APPROACH_CONFIRM_TIME = 0.25
VISION_LEAD_APPROACH_CONFIRM_BYPASS_DECEL = 1.0
VISION_LEAD_APPROACH_CONFIRM_BYPASS_CLOSING_SPEED = 4.0
VISION_LEAD_APPROACH_CONFIRM_BYPASS_LEAD_BRAKE = 0.20
VISION_LEAD_APPROACH_CONFIRM_BYPASS_DISTANCE_MIN = 28.0
VISION_LEAD_APPROACH_CONFIRM_BYPASS_DISTANCE_TIME = 0.85
VISION_UNTRACKED_SLOW_LEAD_MIN_MODEL_PROB = 0.9
VISION_UNTRACKED_SLOW_LEAD_FULL_MODEL_PROB = 0.97
VISION_UNTRACKED_SLOW_LEAD_MIN_CLOSING_SPEED = 3.0
VISION_UNTRACKED_SLOW_LEAD_MIN_CLOSING_RATIO = 0.16
VISION_UNTRACKED_SLOW_LEAD_FULL_CLOSING_RATIO = 0.24
VISION_UNTRACKED_SLOW_LEAD_TRIGGER_TTC = 16.0
VISION_UNTRACKED_SLOW_LEAD_FULL_TTC = 8.0
VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_MODEL_PROB = 0.95
VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_CLOSING_SPEED = 2.0
VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_CLOSING_RATIO = 0.12
VISION_UNTRACKED_SLOW_LEAD_EARLY_TRIGGER_TTC = 24.0
VISION_UNTRACKED_SLOW_LEAD_NEAR_MAX_DISTANCE = 45.0
VISION_UNTRACKED_SLOW_LEAD_NEAR_MIN_MODEL_PROB = 0.90
VISION_UNTRACKED_SLOW_LEAD_NEAR_MIN_CLOSING_RATIO = 0.09
VISION_UNTRACKED_SLOW_LEAD_RELAXED_ENTRY_MAX_LATERAL_OFFSET = 1.2
VISION_UNTRACKED_SLOW_LEAD_MAX_DISTANCE_TIME = 4.4
VISION_UNTRACKED_SLOW_LEAD_MIN_DISTANCE = 80.0
VISION_UNTRACKED_SLOW_LEAD_MAX_DISTANCE = 120.0
VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_DISTANCE_TIME = 5.7
VISION_UNTRACKED_SLOW_LEAD_MAX_DECEL = 0.85
VISION_UNTRACKED_SLOW_LEAD_MIN_DECEL = 0.1
VISION_UNTRACKED_SLOW_LEAD_RELAXED_MODEL_PROB = 0.68
VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_LEAD_SPEED = 8.0
VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_TTC = 10.0
VISION_UNTRACKED_SLOW_LEAD_RELAXED_MIN_CLOSING_SPEED = 10.0
VISION_UNTRACKED_SLOW_LEAD_RELAXED_FULL_CLOSING_SPEED = 16.0
VISION_UNTRACKED_SLOW_LEAD_CONFIRM_TIME = 0.30
VISION_UNTRACKED_SLOW_LEAD_IMMEDIATE_DECEL = 0.55
VISION_UNTRACKED_SLOW_LEAD_IMMEDIATE_DISTANCE = 45.0
VISION_UNTRACKED_SLOW_LEAD_IMMEDIATE_LEAD_BRAKE = 0.10
VISION_UNTRACKED_APPROACH_LIFT_MIN_EGO_SPEED = 18.0
VISION_UNTRACKED_APPROACH_LIFT_MIN_MODEL_PROB = 0.95
VISION_UNTRACKED_APPROACH_LIFT_MAX_LATERAL_OFFSET = 1.2
VISION_UNTRACKED_APPROACH_LIFT_MIN_CLOSING_SPEED = 0.75
VISION_UNTRACKED_APPROACH_LIFT_MAX_DISTANCE = 130.0
VISION_UNTRACKED_APPROACH_LIFT_MIN_GAP_EXCESS = 6.0
VISION_UNTRACKED_APPROACH_LIFT_TRIGGER_TIME = 20.0
VISION_UNTRACKED_APPROACH_LIFT_FULL_TIME = 6.0
VISION_UNTRACKED_APPROACH_LIFT_MAX_ACCEL = 0.22
VISION_UNTRACKED_APPROACH_LIFT_CONFIRM_TIME = 0.30
VISION_UNTRACKED_APPROACH_LIFT_HOLD_TIME = 0.75
VISION_UNTRACKED_APPROACH_LIFT_RATE_DOWN = 0.35
VISION_UNTRACKED_APPROACH_LIFT_RATE_UP = 0.25
VISION_SLOW_LEAD_MAX_SPEED = 5.0
VISION_SLOW_LEAD_MIN_CLOSING_SPEED = 1.5
VISION_SLOW_LEAD_TRIGGER_TTC = 4.5
VISION_SLOW_LEAD_FULL_TTC = 2.0
VISION_SLOW_LEAD_MAX_DECEL = 1.2
VISION_SLOW_LEAD_MIN_DECEL = 0.18
VISION_SLOW_LEAD_MIN_MODEL_PROB = 0.9
LEAD_APPROACH_TFOLLOW_TRIGGER_TIME = 4.5
LEAD_APPROACH_TFOLLOW_FULL_TIME = 1.5
LEAD_APPROACH_TFOLLOW_MAX_DELTA = 0.162
LEAD_APPROACH_TFOLLOW_MAX_CLOSING_SPEED = 6.0
LEAD_APPROACH_TFOLLOW_MAX_LEAD_BRAKE = 2.5
LEAD_APPROACH_TFOLLOW_MIN_CLOSING_SPEED = 0.75
LEAD_APPROACH_TFOLLOW_MIN_LEAD_BRAKE = 0.2
LEAD_APPROACH_TFOLLOW_WINDOW_MIN = 6.0
LEAD_APPROACH_TFOLLOW_WINDOW_GAIN = 0.35
LEAD_APPROACH_TFOLLOW_RATE_UP = 1.0
LEAD_APPROACH_TFOLLOW_RATE_DOWN = 0.60
VISION_LEAD_TFOLLOW_MAX_EXTRA_DELTA = 0.216
VISION_LEAD_TFOLLOW_SLOW_LEAD_SPEED = 20.0
VISION_LEAD_TFOLLOW_GAP_BUFFER_MIN = 8.0
VISION_LEAD_TFOLLOW_GAP_BUFFER_GAIN = 0.35
VISION_LOW_SPEED_STOP_BUFFER_MAX_EGO_SPEED = 6.5
VISION_LOW_SPEED_STOP_BUFFER_MAX_LEAD_SPEED = 3.25
VISION_LOW_SPEED_STOP_BUFFER_HOLD_MAX_LEAD_SPEED = 4.0
VISION_LOW_SPEED_STOP_BUFFER_MIN_MODEL_PROB = 0.9
VISION_LOW_SPEED_STOP_BUFFER_MIN_CLOSING_SPEED = 0.35
VISION_LOW_SPEED_STOP_BUFFER_MIN_HOLD_REL_SPEED = -0.2
VISION_LOW_SPEED_STOP_BUFFER_BASE = 3.8
VISION_LOW_SPEED_STOP_BUFFER_EGO_GAIN = 0.80
VISION_LOW_SPEED_STOP_BUFFER_LEAD_GAIN = 0.25
VISION_LOW_SPEED_STOP_BUFFER_RELEASE_MARGIN = 0.9
VISION_LOW_SPEED_STOP_BUFFER_HOLD_TIME = 0.8
VISION_LOW_SPEED_STOP_BUFFER_MIN_BRAKE = 1.25
VISION_LOW_SPEED_STOP_BUFFER_BRAKE_GAIN = 0.25
VISION_CLOSE_STOP_HOLD_MAX_EGO_SPEED = 0.75
VISION_CLOSE_STOP_HOLD_MAX_LEAD_SPEED = 0.8
VISION_CLOSE_STOP_HOLD_MAX_DISTANCE = 3.5
VISION_CLOSE_STOP_HOLD_MIN_MODEL_PROB = 0.95
VISION_CLOSE_SETTLE_MAX_EGO_SPEED = 0.75
VISION_CLOSE_SETTLE_MAX_LEAD_SPEED = 2.75
VISION_CLOSE_SETTLE_MAX_DISTANCE = 4.2
VISION_CLOSE_STOP_HOLD_MIN_BRAKE = 0.20
VISION_CLOSE_STOP_HOLD_MAX_BRAKE = 0.36
VISION_CLOSE_SETTLE_MAX_LEAD_DELTA = 2.6
VISION_CLOSE_SETTLE_MIN_BRAKE = 0.16
VISION_CLOSE_SETTLE_MAX_BRAKE = 0.30
VISION_CLOSE_FINAL_GUARD_MAX_EGO_SPEED = 0.5
VISION_CLOSE_FINAL_GUARD_MAX_LEAD_SPEED = 2.75
VISION_CLOSE_FINAL_GUARD_MAX_DISTANCE = 4.5
VISION_CLOSE_FINAL_GUARD_MIN_BRAKE = 0.18
VISION_CLOSE_FINAL_GUARD_MAX_BRAKE = 0.28
VISION_CLOSE_RELEASE_HOLD_MAX_EGO_SPEED = 2.5
VISION_CLOSE_RELEASE_HOLD_MAX_LEAD_SPEED = 3.5
VISION_CLOSE_RELEASE_HOLD_MAX_DISTANCE = 4.2
VISION_CLOSE_RELEASE_HOLD_MIN_MODEL_PROB = 0.98
VISION_CLOSE_RELEASE_HOLD_MIN_LEAD_DELTA = -0.1
VISION_CLOSE_RELEASE_HOLD_MAX_LEAD_DELTA = 1.5
VISION_CLOSE_RELEASE_HOLD_MIN_BRAKE = 0.18
VISION_CLOSE_RELEASE_HOLD_MAX_BRAKE = 0.40
POST_DEPARTURE_FOLLOW_SETTLE_LATCH_TIME = 75.0
POST_DEPARTURE_FOLLOW_SETTLE_MIN_SPEED = 8.0
POST_DEPARTURE_FOLLOW_SETTLE_MAX_ARM_SPEED = 16.0
POST_DEPARTURE_FOLLOW_SETTLE_MIN_MODEL_PROB = 0.9
POST_DEPARTURE_FOLLOW_SETTLE_MAX_LATERAL_OFFSET = 1.15
POST_DEPARTURE_FOLLOW_SETTLE_MAX_CLOSING_SPEED = 0.8
POST_DEPARTURE_FOLLOW_SETTLE_MAX_LEAD_BRAKE = 0.10
POST_DEPARTURE_FOLLOW_SETTLE_ARM_MIN_LEAD_DELTA = -0.10
POST_DEPARTURE_FOLLOW_SETTLE_ARM_MIN_LEAD_ACCEL = 0.20
POST_DEPARTURE_FOLLOW_SETTLE_ARM_MIN_HEADWAY_MARGIN = 0.08
POST_DEPARTURE_FOLLOW_SETTLE_COMPLETE_HEADWAY_MARGIN = 0.05
RADAR_STANDSTILL_GAP_SETTLE_CONFIRM_TIME = 0.50
RADAR_STANDSTILL_GAP_SETTLE_ENTRY_MARGIN = 0.60
RADAR_STANDSTILL_GAP_SETTLE_EXIT_MARGIN = 0.15
RADAR_STANDSTILL_GAP_SETTLE_MAX_EXTRA_GAP = 1.5
RADAR_STANDSTILL_GAP_SETTLE_MAX_EGO_SPEED = 0.45
RADAR_STANDSTILL_GAP_SETTLE_MAX_LEAD_SPEED = 0.15
RADAR_STANDSTILL_GAP_SETTLE_MAX_LATERAL_OFFSET = 1.0
LEAD_DEPART_CONFIDENT_MIN_GAP = 3.75
LEAD_DEPART_CONFIDENT_MAX_GAP = 5.25
LEAD_DEPART_CONFIDENT_MIN_LEAD_SPEED = 0.3
LEAD_DEPART_CONFIDENT_MIN_LEAD_DELTA = 0.25
LEAD_DEPART_CONFIDENT_MIN_LEAD_ACCEL = 0.2
LEAD_DEPART_RELEASE_HOLD_MIN_DISTANCE = 3.0
LEAD_DEPART_RELEASE_HOLD_MIN_LEAD_SPEED = 0.55
LEAD_DEPART_RELEASE_HOLD_MIN_LEAD_DELTA = 0.25
LEAD_DEPART_RELEASE_HOLD_MAX_LEAD_BRAKE = 0.15
LEAD_DEPART_RELEASE_HOLD_MIN_MODEL_PROB = 0.95
LEAD_DEPART_RELEASE_HOLD_MAX_LATERAL_OFFSET = 1.0
LEAD_DEPART_RELEASE_HOLD_CONFLICT_SPEED = 0.25
LEAD_DEPART_RELEASE_HOLD_CONFLICT_DISTANCE_MARGIN = 3.0
LEAD_DEPART_ACCEL_HOLD_MIN_LEAD_SPEED = 0.6
LEAD_DEPART_ACCEL_HOLD_MIN_LEAD_DELTA = 0.5
LEAD_DEPART_ACCEL_HOLD_MIN_GAP = 3.5
LEAD_DEPART_ACCEL_HOLD_FULL_GAP = 6.0
LEAD_DEPART_ACCEL_HOLD_FULL_LEAD_SPEED = 2.2
LEAD_DEPART_ACCEL_HOLD_MIN_MODEL_PROB = 0.85
LEAD_DEPART_ACCEL_HOLD_MIN_MODEL_ACCEL = 0.12
LEAD_DEPART_ACCEL_HOLD_MAX_LEAD_BRAKE = 0.2
LEAD_DEPART_ACCEL_HOLD_MIN_ACCEL = 0.25
LEAD_DEPART_ACCEL_HOLD_MAX_ACCEL = 0.55
LEAD_DEPART_ACCEL_ASSIST = 0.10
LEAD_DEPART_ACCEL_HOLD_REUSE_MIN_GAP = 3.75
LEAD_DEPART_ACCEL_HOLD_REUSE_MAX_CLOSING_SPEED = 0.45
LEAD_DEPART_ACCEL_HOLD_REUSE_MAX_LEAD_BRAKE = 0.2
LEAD_DEPART_ACCEL_HOLD_REUSE_MIN_HEADWAY_MARGIN = 0.10
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_EGO_SPEED = 4.5
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_DISTANCE = 4.0
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_DISTANCE = 18.0
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_SPEED = 4.0
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LATERAL_OFFSET = 1.75
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_MODEL_PROB = 0.9
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_LEAD_DELTA = -0.5
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_DELTA = 0.75
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_LEAD_ACCEL = -0.4
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_ACCEL = 0.25
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_ACCEL = 0.08
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_ACCEL = 0.22
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MAX_EGO_SPEED = 1.25
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_GAP = 4.0
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_LEAD_SPEED = 1.2
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_LEAD_DELTA = 0.8
LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_LEAD_ACCEL = 0.5
RADAR_DEPART_CONFLICT_MAX_EGO_SPEED = 1.6
RADAR_DEPART_CONFLICT_MIN_RADAR_LATERAL = 1.5
RADAR_DEPART_CONFLICT_MAX_RADAR_DISTANCE = 18.0
RADAR_DEPART_CONFLICT_MIN_MODEL_PROB = 0.95
RADAR_DEPART_CONFLICT_MAX_MODEL_DISTANCE = 18.0
RADAR_DEPART_CONFLICT_MAX_MODEL_LATERAL = 0.9
RADAR_DEPART_CONFLICT_MAX_MODEL_LEAD_SPEED = 2.0
RADAR_DEPART_CONFLICT_MAX_DISTANCE_MISMATCH = 4.0


def _lead_present(lead) -> bool:
  # This fork's log.capnp names the flag `present`; StarPilot's uses `status`.
  return bool(getattr(lead, "present", False) or getattr(lead, "status", False))


def _stop_distance():
  try:
    from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import STOP_DISTANCE
    return float(STOP_DISTANCE)
  except ImportError:
    return STOP_DISTANCE_FALLBACK


@dataclass
class StopDepartContext:
  """Per-frame inputs the caller derives from sm / planner state."""
  CP: object
  dt: float
  lead_one: object
  lead_two: object
  v_ego: float
  standstill: bool
  brake_pressed: bool
  gas_pressed: bool
  long_control_stopping: bool
  active: bool                 # lead control allowed this frame (enabled, not force-decel)
  tracking: bool               # MPC selected a lead source
  t_follow: float              # base t_follow (carrot or mpc default)
  a_target: float              # post-arbitration, post-follow-smoothing target
  should_stop: bool
  output_accel_min: float
  model_desired_accel: float
  model_should_stop: bool
  model_data: object = None    # modelV2 (for the off-center radar depart veto)
  source: str = "lead0"        # MPC lead source ("lead0"/"lead1"/"cruise"/"e2e")
  forcing_stop: bool = False   # StarPilot-only channels; False on this fork
  red_light: bool = False
  stop_sign_confirmed: bool = False


@dataclass
class StopDepartResult:
  a_target: float
  should_stop: bool
  effective_t_follow: float
  post_departure: bool = False
  blocked: bool = False
  notes: dict = field(default_factory=dict)


class LeadStopDepartPolicy:
  """Stateful stop/depart output shaping (caps never add acceleration except
  the explicitly gated standstill depart releases, which mirror StarPilot)."""

  def __init__(self, CP, dt):
    self.CP = CP
    self.dt = dt
    self.untracked_slow_lead_decel_scale = get_untracked_slow_lead_decel_scale(CP)
    self.effective_t_follow = None
    self.vision_low_speed_stop_hold_until = 0.0
    self.vision_lead_approach_confirm_t = 0.0
    self.untracked_slow_lead_confirm_t = 0.0
    self.untracked_vision_approach_lift_confirm_t = 0.0
    self.untracked_vision_approach_lift_cap = None
    self.untracked_vision_approach_lift_target = None
    self.untracked_vision_approach_lift_hold_until = 0.0
    self.confident_lead_depart_elapsed = 0.0
    self.slow_creep_lead_depart_elapsed = 0.0
    self.lead_depart_release_candidate_elapsed = 0.0
    self.lead_depart_release_pending = False
    self.lead_depart_release_hold_remaining = 0.0
    self.radar_standstill_gap_settle_elapsed = 0.0
    self.radar_standstill_gap_settle_active = False
    self.lead_depart_accel_hold_until = 0.0
    self.lead_depart_accel_hold_floor = None
    self.post_departure_follow_settle_until = 0.0
    self.lead_depart_accel_hold_reused = False

  # ------------------------------------------------------------------
  # t_follow shaping
  # ------------------------------------------------------------------
  def get_dynamic_t_follow(self, base_t_follow, lead, v_ego):
    base_t_follow = float(base_t_follow)
    target_t_follow = base_t_follow

    if lead is not None and _lead_present(lead):
      lead_prob = float(getattr(lead, "modelProb", 1.0 if bool(getattr(lead, "radar", False)) else 0.0))
      if bool(getattr(lead, "radar", False)) or lead_prob >= VISION_LEAD_APPROACH_MIN_MODEL_PROB:
        lead_brake = max(0.0, -float(lead.aLeadK))
        closing_speed = max(0.0, v_ego - lead.vLead)
        if closing_speed >= LEAD_APPROACH_TFOLLOW_MIN_CLOSING_SPEED or lead_brake >= LEAD_APPROACH_TFOLLOW_MIN_LEAD_BRAKE:
          desired_gap = float(desired_follow_distance(v_ego, lead.vLead, base_t_follow))
          approach_window = max(LEAD_APPROACH_TFOLLOW_WINDOW_MIN, LEAD_APPROACH_TFOLLOW_WINDOW_GAIN * float(v_ego))
          if float(lead.dRel) <= desired_gap + approach_window:
            reaction_t = max(self.CP.longitudinalActuatorDelay, self.dt)
            projected_closing_speed = closing_speed + 0.5 * lead_brake * reaction_t
            gap_to_follow = max(float(lead.dRel) - desired_gap, 0.0)
            time_to_follow = gap_to_follow / max(projected_closing_speed, 0.1)
            time_factor = float(np.clip((LEAD_APPROACH_TFOLLOW_TRIGGER_TIME - time_to_follow) /
                                        (LEAD_APPROACH_TFOLLOW_TRIGGER_TIME - LEAD_APPROACH_TFOLLOW_FULL_TIME), 0.0, 1.0))
            closing_factor = float(np.clip(closing_speed / LEAD_APPROACH_TFOLLOW_MAX_CLOSING_SPEED, 0.0, 1.0))
            brake_factor = float(np.clip(lead_brake / LEAD_APPROACH_TFOLLOW_MAX_LEAD_BRAKE, 0.0, 1.0))
            target_delta = LEAD_APPROACH_TFOLLOW_MAX_DELTA * np.clip(
              0.55 * time_factor + 0.25 * closing_factor + 0.20 * brake_factor, 0.0, 1.0)
            if not bool(getattr(lead, "radar", False)):
              gap_deficit = max(desired_gap - float(lead.dRel), 0.0)
              gap_buffer = max(VISION_LEAD_TFOLLOW_GAP_BUFFER_MIN,
                               VISION_LEAD_TFOLLOW_GAP_BUFFER_GAIN * float(v_ego))
              gap_factor = float(np.clip(gap_deficit / gap_buffer, 0.0, 1.0))
              slow_lead_factor = float(np.clip((VISION_LEAD_TFOLLOW_SLOW_LEAD_SPEED - float(lead.vLead)) /
                                               VISION_LEAD_TFOLLOW_SLOW_LEAD_SPEED, 0.0, 1.0))
              vision_extra = VISION_LEAD_TFOLLOW_MAX_EXTRA_DELTA * np.clip(
                0.40 * time_factor + 0.30 * gap_factor + 0.20 * slow_lead_factor + 0.10 * closing_factor,
                0.0, 1.0)
              target_delta += vision_extra
            target_t_follow = base_t_follow + float(target_delta)

    if self.effective_t_follow is None:
      self.effective_t_follow = base_t_follow

    rate = LEAD_APPROACH_TFOLLOW_RATE_UP if target_t_follow > self.effective_t_follow else LEAD_APPROACH_TFOLLOW_RATE_DOWN
    step = rate * self.dt
    self.effective_t_follow = float(np.clip(target_t_follow, self.effective_t_follow - step, self.effective_t_follow + step))
    self.effective_t_follow = max(base_t_follow, self.effective_t_follow)
    return self.effective_t_follow

  # ------------------------------------------------------------------
  # Brake caps (vision + close lead)
  # ------------------------------------------------------------------
  def get_close_lead_brake_cap(self, lead, v_ego, accel_min):
    if lead is None or not _lead_present(lead):
      return None

    lead_brake = max(0.0, -float(lead.aLeadK))
    reaction_t = max(self.CP.longitudinalActuatorDelay, self.dt)
    closing_speed = max(0.0, v_ego - lead.vLead)
    projected_closing_speed = closing_speed + lead_brake * reaction_t
    if projected_closing_speed < 0.1 and lead_brake < 0.5:
      return None

    target_gap = float(np.clip(2.0 + 0.2 * v_ego, 2.0, 6.0))
    delay_buffer = projected_closing_speed * reaction_t
    available_gap = max(float(lead.dRel) - target_gap - delay_buffer, 0.5)
    projected_ttc = available_gap / max(projected_closing_speed, 0.1)
    if projected_ttc > CLOSE_LEAD_BRAKE_CAP_MAX_TTC:
      return None
    required_decel = (projected_closing_speed ** 2) / (2.0 * available_gap) + 0.7 * lead_brake
    if required_decel < 0.2:
      return None

    return max(accel_min, -required_decel)

  @staticmethod
  def get_inside_gap_closing_lead_accel_cap(lead, v_ego, accel_min, t_follow):
    if lead is None or not _lead_present(lead):
      return None

    ego_speed = float(v_ego)
    lead_speed = max(float(getattr(lead, "vLead", 0.0)), 0.0)
    if ego_speed < INSIDE_GAP_CLOSING_MIN_EGO_SPEED or lead_speed < INSIDE_GAP_CLOSING_MIN_LEAD_SPEED:
      return None
    if abs(float(getattr(lead, "yRel", 0.0))) > INSIDE_GAP_CLOSING_MAX_LATERAL_OFFSET:
      return None

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < INSIDE_GAP_CLOSING_VISION_MIN_MODEL_PROB:
      return None

    closing_speed = ego_speed - lead_speed
    if closing_speed < INSIDE_GAP_CLOSING_MIN_SPEED:
      return None

    desired_gap = float(desired_follow_distance(ego_speed, lead_speed, float(t_follow)))
    gap_deficit = desired_gap - float(lead.dRel)
    trigger_deficit = max(INSIDE_GAP_CLOSING_MIN_DEFICIT,
                          INSIDE_GAP_CLOSING_DEFICIT_RATIO * desired_gap)
    if gap_deficit <= trigger_deficit:
      return None

    brake_deficit = INSIDE_GAP_CLOSING_BRAKE_DEFICIT_RATIO * desired_gap
    deficit_factor = float(np.clip(
      (gap_deficit - brake_deficit) / max(brake_deficit, 1.0),
      0.0,
      1.0,
    ))
    closing_factor = float(np.clip(
      (closing_speed - INSIDE_GAP_CLOSING_BRAKE_MIN_SPEED) /
      (INSIDE_GAP_CLOSING_FULL_SPEED - INSIDE_GAP_CLOSING_BRAKE_MIN_SPEED),
      0.0,
      1.0,
    ))
    required_decel = 0.45 * deficit_factor + 0.20 * closing_factor
    required_decel = min(required_decel, INSIDE_GAP_CLOSING_MAX_DECEL)
    return max(float(accel_min), -required_decel)

  def get_vision_lead_approach_cap(self, lead, v_ego, accel_min, t_follow):
    if lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    if lead_prob < VISION_LEAD_APPROACH_MIN_MODEL_PROB:
      return None

    lead_brake = max(0.0, -float(lead.aLeadK))
    reaction_t = max(self.CP.longitudinalActuatorDelay, self.dt)
    closing_speed = max(0.0, v_ego - lead.vLead)
    projected_closing_speed = closing_speed + lead_brake * reaction_t
    if projected_closing_speed < VISION_LEAD_APPROACH_MIN_CLOSING_SPEED:
      return None

    tight_follow_gap = float(t_follow * v_ego + VISION_LEAD_APPROACH_TIGHT_BUFFER)
    gap_to_tight_follow = float(lead.dRel) - tight_follow_gap
    time_to_tight_follow = gap_to_tight_follow / max(projected_closing_speed, 0.1)
    if time_to_tight_follow > VISION_LEAD_APPROACH_TRIGGER_TIME:
      return None

    desired_gap = float(desired_follow_distance(v_ego, lead.vLead, t_follow))
    if float(lead.dRel) > desired_gap + VISION_LEAD_APPROACH_TIGHT_BUFFER:
      return None

    time_factor = float(np.clip((VISION_LEAD_APPROACH_TRIGGER_TIME - time_to_tight_follow) /
                                (VISION_LEAD_APPROACH_TRIGGER_TIME - VISION_LEAD_APPROACH_FULL_TIME), 0.0, 1.0))
    prob_factor = float(np.clip((lead_prob - VISION_LEAD_APPROACH_MIN_MODEL_PROB) /
                                (VISION_LEAD_APPROACH_FULL_MODEL_PROB - VISION_LEAD_APPROACH_MIN_MODEL_PROB), 0.0, 1.0))
    closing_factor = float(np.clip(projected_closing_speed / (VISION_LEAD_APPROACH_MIN_CLOSING_SPEED + 2.5), 0.0, 1.0))
    tight_follow_deficit = max(tight_follow_gap - float(lead.dRel), 0.0)
    tight_follow_buffer = max(VISION_LEAD_APPROACH_DEFICIT_BUFFER_MIN,
                              VISION_LEAD_APPROACH_DEFICIT_BUFFER_GAIN * float(v_ego) + 1.0)
    deficit_factor = float(np.clip(tight_follow_deficit / tight_follow_buffer, 0.0, 1.0))

    approach_decel = VISION_LEAD_APPROACH_MAX_DECEL * time_factor * (0.45 + 0.55 * prob_factor)
    approach_decel *= 0.6 + 0.4 * closing_factor
    deficit_decel = VISION_LEAD_APPROACH_DEFICIT_MAX_DECEL * deficit_factor * prob_factor
    deficit_decel *= 0.5 + 0.5 * closing_factor
    approach_decel = max(approach_decel, deficit_decel)

    # If a tracked vision lead is already far inside the tight-follow window and
    # it is actively braking, don't stay stuck at the softer comfort cap.
    if deficit_factor >= VISION_LEAD_APPROACH_BRAKING_DEFICIT_MIN and lead_brake >= VISION_LEAD_APPROACH_BRAKING_MIN_LEAD_BRAKE:
      braking_floor = float(np.interp(
        lead_brake,
        [VISION_LEAD_APPROACH_BRAKING_MIN_LEAD_BRAKE, VISION_LEAD_APPROACH_BRAKING_FULL_LEAD_BRAKE],
        [VISION_LEAD_APPROACH_BRAKING_FLOOR_MIN_DECEL, VISION_LEAD_APPROACH_BRAKING_FLOOR_MAX_DECEL],
      ))
      braking_floor *= 0.85 + 0.15 * max(closing_factor, prob_factor)
      approach_decel = max(approach_decel, braking_floor)

    if approach_decel < VISION_LEAD_APPROACH_MIN_DECEL:
      return None

    return max(accel_min, -approach_decel)

  def get_vision_untracked_slow_lead_cap(self, lead, v_ego, accel_min):
    if lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))

    lead_brake = max(0.0, -float(lead.aLeadK))
    reaction_t = max(self.CP.longitudinalActuatorDelay, self.dt)
    closing_speed = max(0.0, v_ego - lead.vLead)
    projected_closing_speed = closing_speed + lead_brake * reaction_t
    closing_ratio = projected_closing_speed / max(float(v_ego), 0.1)
    projected_ttc = float(lead.dRel) / max(projected_closing_speed, 0.1)

    standard_entry = bool(
      projected_closing_speed >= VISION_UNTRACKED_SLOW_LEAD_MIN_CLOSING_SPEED and
      closing_ratio >= VISION_UNTRACKED_SLOW_LEAD_MIN_CLOSING_RATIO and
      projected_ttc <= VISION_UNTRACKED_SLOW_LEAD_TRIGGER_TTC
    )
    centered_relaxed_entry = (
      abs(float(getattr(lead, "yRel", 0.0))) <= VISION_UNTRACKED_SLOW_LEAD_RELAXED_ENTRY_MAX_LATERAL_OFFSET
    )
    high_confidence_early_entry = bool(
      centered_relaxed_entry and
      lead_prob + 1e-6 >= VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_MODEL_PROB and
      projected_closing_speed >= VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_CLOSING_SPEED and
      closing_ratio >= VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_CLOSING_RATIO and
      projected_ttc <= VISION_UNTRACKED_SLOW_LEAD_EARLY_TRIGGER_TTC
    )
    near_early_entry = bool(
      centered_relaxed_entry and
      float(lead.dRel) <= VISION_UNTRACKED_SLOW_LEAD_NEAR_MAX_DISTANCE and
      lead_prob + 1e-6 >= VISION_UNTRACKED_SLOW_LEAD_NEAR_MIN_MODEL_PROB and
      projected_closing_speed >= VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_CLOSING_SPEED and
      closing_ratio >= VISION_UNTRACKED_SLOW_LEAD_NEAR_MIN_CLOSING_RATIO and
      projected_ttc <= VISION_UNTRACKED_SLOW_LEAD_EARLY_TRIGGER_TTC
    )
    if not (standard_entry or high_confidence_early_entry or near_early_entry):
      return None

    trigger_ttc = VISION_UNTRACKED_SLOW_LEAD_TRIGGER_TTC
    min_closing_ratio = VISION_UNTRACKED_SLOW_LEAD_MIN_CLOSING_RATIO
    if high_confidence_early_entry:
      trigger_ttc = VISION_UNTRACKED_SLOW_LEAD_EARLY_TRIGGER_TTC
      min_closing_ratio = VISION_UNTRACKED_SLOW_LEAD_EARLY_MIN_CLOSING_RATIO
    if near_early_entry:
      trigger_ttc = VISION_UNTRACKED_SLOW_LEAD_EARLY_TRIGGER_TTC
      min_closing_ratio = VISION_UNTRACKED_SLOW_LEAD_NEAR_MIN_CLOSING_RATIO

    min_model_prob = VISION_UNTRACKED_SLOW_LEAD_MIN_MODEL_PROB
    max_distance_time = VISION_UNTRACKED_SLOW_LEAD_MAX_DISTANCE_TIME
    if float(lead.vLead) <= VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_LEAD_SPEED and \
        projected_ttc <= VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_TTC:
      closing_relax = float(np.clip((projected_closing_speed - VISION_UNTRACKED_SLOW_LEAD_RELAXED_MIN_CLOSING_SPEED) /
                                    (VISION_UNTRACKED_SLOW_LEAD_RELAXED_FULL_CLOSING_SPEED -
                                     VISION_UNTRACKED_SLOW_LEAD_RELAXED_MIN_CLOSING_SPEED), 0.0, 1.0))
      ttc_relax = float(np.clip((VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_TTC - projected_ttc) /
                                (VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_TTC -
                                 VISION_UNTRACKED_SLOW_LEAD_FULL_TTC), 0.0, 1.0))
      relax_factor = closing_relax * ttc_relax
      min_model_prob = float(np.interp(relax_factor, [0.0, 1.0],
                                       [VISION_UNTRACKED_SLOW_LEAD_MIN_MODEL_PROB,
                                        VISION_UNTRACKED_SLOW_LEAD_RELAXED_MODEL_PROB]))
      max_distance_time = float(np.interp(relax_factor, [0.0, 1.0],
                                          [VISION_UNTRACKED_SLOW_LEAD_MAX_DISTANCE_TIME,
                                           VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_DISTANCE_TIME]))

    max_distance = float(np.clip(max_distance_time * v_ego,
                                 VISION_UNTRACKED_SLOW_LEAD_MIN_DISTANCE,
                                 VISION_UNTRACKED_SLOW_LEAD_MAX_DISTANCE))
    if float(lead.dRel) > max_distance:
      return None

    if lead_prob + 1e-6 < min_model_prob:
      return None

    time_factor = float(np.clip((trigger_ttc - projected_ttc) /
                                (trigger_ttc - VISION_UNTRACKED_SLOW_LEAD_FULL_TTC),
                                0.0, 1.0))
    prob_factor = float(np.clip((lead_prob - min_model_prob) /
                                (VISION_UNTRACKED_SLOW_LEAD_FULL_MODEL_PROB - min_model_prob),
                                0.0, 1.0))
    closing_factor = float(np.clip((closing_ratio - min_closing_ratio) /
                                   (VISION_UNTRACKED_SLOW_LEAD_FULL_CLOSING_RATIO - min_closing_ratio),
                                   0.0, 1.0))
    approach_decel = VISION_UNTRACKED_SLOW_LEAD_MAX_DECEL * self.untracked_slow_lead_decel_scale * np.clip(
      0.5 * time_factor + 0.3 * prob_factor + 0.2 * closing_factor, 0.0, 1.0)
    if approach_decel < VISION_UNTRACKED_SLOW_LEAD_MIN_DECEL:
      return None

    return max(accel_min, -approach_decel)

  @staticmethod
  def get_vision_untracked_approach_lift_cap(lead, v_ego, t_follow):
    """Trim throttle before a confident vision lead reaches the tracking window."""
    if lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None
    if float(v_ego) < VISION_UNTRACKED_APPROACH_LIFT_MIN_EGO_SPEED:
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    if lead_prob < VISION_UNTRACKED_APPROACH_LIFT_MIN_MODEL_PROB:
      return None
    if abs(float(getattr(lead, "yRel", 0.0))) > VISION_UNTRACKED_APPROACH_LIFT_MAX_LATERAL_OFFSET:
      return None
    if float(lead.dRel) > VISION_UNTRACKED_APPROACH_LIFT_MAX_DISTANCE:
      return None

    closing_speed = float(v_ego) - float(lead.vLead)
    if closing_speed < VISION_UNTRACKED_APPROACH_LIFT_MIN_CLOSING_SPEED:
      return None

    desired_gap = float(desired_follow_distance(v_ego, lead.vLead, t_follow))
    gap_excess = float(lead.dRel) - desired_gap
    if gap_excess < VISION_UNTRACKED_APPROACH_LIFT_MIN_GAP_EXCESS:
      return 0.0

    time_to_desired_gap = gap_excess / max(closing_speed, 0.1)
    if time_to_desired_gap > VISION_UNTRACKED_APPROACH_LIFT_TRIGGER_TIME:
      return None

    # This path only removes positive acceleration. Braking remains exclusively
    # owned by lead tracking and the existing close-lead safety caps.
    return float(np.interp(
      time_to_desired_gap,
      [VISION_UNTRACKED_APPROACH_LIFT_FULL_TIME, VISION_UNTRACKED_APPROACH_LIFT_TRIGGER_TIME],
      [0.0, VISION_UNTRACKED_APPROACH_LIFT_MAX_ACCEL],
    ))

  def update_vision_untracked_approach_lift_cap(self, raw_cap, output_a_target, prev_output_a_target,
                                                now_t, untracked):
    if untracked and raw_cap is not None:
      if self.untracked_vision_approach_lift_cap is None:
        self.untracked_vision_approach_lift_confirm_t = min(
          self.untracked_vision_approach_lift_confirm_t + self.dt,
          VISION_UNTRACKED_APPROACH_LIFT_CONFIRM_TIME,
        )
        if self.untracked_vision_approach_lift_confirm_t >= VISION_UNTRACKED_APPROACH_LIFT_CONFIRM_TIME:
          self.untracked_vision_approach_lift_cap = float(prev_output_a_target)
      if self.untracked_vision_approach_lift_cap is not None:
        self.untracked_vision_approach_lift_target = float(raw_cap)
        self.untracked_vision_approach_lift_hold_until = now_t + VISION_UNTRACKED_APPROACH_LIFT_HOLD_TIME
    elif self.untracked_vision_approach_lift_cap is None:
      self.untracked_vision_approach_lift_confirm_t = 0.0

    active_cap = self.untracked_vision_approach_lift_cap
    if active_cap is None:
      return None

    holding = untracked and now_t < self.untracked_vision_approach_lift_hold_until
    target = self.untracked_vision_approach_lift_target if holding else float(output_a_target)
    if target is None:
      target = float(output_a_target)

    lower = active_cap - VISION_UNTRACKED_APPROACH_LIFT_RATE_DOWN * self.dt
    upper = active_cap + VISION_UNTRACKED_APPROACH_LIFT_RATE_UP * self.dt
    active_cap = float(np.clip(target, lower, upper))
    self.untracked_vision_approach_lift_cap = active_cap

    if not holding and active_cap >= float(output_a_target) - 1e-6:
      self.untracked_vision_approach_lift_confirm_t = 0.0
      self.untracked_vision_approach_lift_cap = None
      self.untracked_vision_approach_lift_target = None
      self.untracked_vision_approach_lift_hold_until = 0.0
      return None

    return active_cap

  def get_vision_slow_stopped_lead_cap(self, lead, v_ego, accel_min, t_follow):
    if lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    if lead_prob < VISION_SLOW_LEAD_MIN_MODEL_PROB or float(lead.vLead) > VISION_SLOW_LEAD_MAX_SPEED:
      return None

    lead_brake = max(0.0, -float(lead.aLeadK))
    reaction_t = max(self.CP.longitudinalActuatorDelay, self.dt)
    closing_speed = max(0.0, v_ego - lead.vLead)
    projected_closing_speed = closing_speed + lead_brake * reaction_t
    if projected_closing_speed < VISION_SLOW_LEAD_MIN_CLOSING_SPEED:
      return None

    stop_gap = float(max(_stop_distance() + 1.0, 2.5 + 0.15 * max(float(lead.vLead), 0.0)))
    delay_buffer = projected_closing_speed * reaction_t
    available_gap = max(float(lead.dRel) - stop_gap - delay_buffer, 0.5)
    projected_ttc = available_gap / max(projected_closing_speed, 0.1)
    if projected_ttc > VISION_SLOW_LEAD_TRIGGER_TTC:
      return None

    time_factor = float(np.clip((VISION_SLOW_LEAD_TRIGGER_TTC - projected_ttc) /
                                (VISION_SLOW_LEAD_TRIGGER_TTC - VISION_SLOW_LEAD_FULL_TTC), 0.0, 1.0))
    prob_factor = float(np.clip((lead_prob - VISION_SLOW_LEAD_MIN_MODEL_PROB) /
                                (VISION_LEAD_APPROACH_FULL_MODEL_PROB - VISION_SLOW_LEAD_MIN_MODEL_PROB), 0.0, 1.0))
    speed_factor = float(np.clip((VISION_SLOW_LEAD_MAX_SPEED - max(float(lead.vLead), 0.0)) /
                                 VISION_SLOW_LEAD_MAX_SPEED, 0.0, 1.0))
    required_decel = (projected_closing_speed ** 2) / (2.0 * available_gap)
    decel_scale = 0.45 + 0.35 * time_factor + 0.20 * speed_factor
    approach_decel = min(VISION_SLOW_LEAD_MAX_DECEL, required_decel * decel_scale)
    approach_decel *= 0.65 + 0.35 * prob_factor
    if approach_decel < VISION_SLOW_LEAD_MIN_DECEL:
      return None

    return max(accel_min, -approach_decel)

  def tracked_vision_lead_approach_needs_immediate_brake(self, lead, v_ego, approach_cap):
    lead_brake = max(0.0, -float(getattr(lead, "aLeadK", 0.0)))
    reaction_t = max(self.CP.longitudinalActuatorDelay, self.dt)
    projected_closing_speed = max(0.0, v_ego - float(lead.vLead)) + lead_brake * reaction_t
    bypass_distance = max(VISION_LEAD_APPROACH_CONFIRM_BYPASS_DISTANCE_MIN,
                          VISION_LEAD_APPROACH_CONFIRM_BYPASS_DISTANCE_TIME * float(v_ego))
    return (
      approach_cap <= -VISION_LEAD_APPROACH_CONFIRM_BYPASS_DECEL or
      projected_closing_speed >= VISION_LEAD_APPROACH_CONFIRM_BYPASS_CLOSING_SPEED or
      lead_brake >= VISION_LEAD_APPROACH_CONFIRM_BYPASS_LEAD_BRAKE or
      float(lead.dRel) <= bypass_distance
    )

  def get_vision_low_speed_stop_buffer_cap(self, lead, v_ego, accel_min):
    if lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None, False

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    if lead_prob < VISION_LOW_SPEED_STOP_BUFFER_MIN_MODEL_PROB:
      return None, False

    lead_speed = max(float(lead.vLead), 0.0)
    relative_speed = float(v_ego) - lead_speed
    max_lead_speed, hold_max_lead_speed = get_vision_low_speed_stop_buffer_lead_speed_limits(
      self.CP,
      VISION_LOW_SPEED_STOP_BUFFER_MAX_LEAD_SPEED,
      VISION_LOW_SPEED_STOP_BUFFER_HOLD_MAX_LEAD_SPEED,
    )
    closing_speed = max(0.0, v_ego - lead_speed)
    entry_context = (
      v_ego <= VISION_LOW_SPEED_STOP_BUFFER_MAX_EGO_SPEED and
      lead_speed <= max_lead_speed and
      closing_speed >= VISION_LOW_SPEED_STOP_BUFFER_MIN_CLOSING_SPEED
    )
    hold_context = (
      v_ego <= VISION_LOW_SPEED_STOP_BUFFER_MAX_EGO_SPEED and
      lead_speed <= hold_max_lead_speed and
      relative_speed >= VISION_LOW_SPEED_STOP_BUFFER_MIN_HOLD_REL_SPEED
    )

    now_t = time.monotonic()
    entry_buffer = max(3.2, VISION_LOW_SPEED_STOP_BUFFER_BASE +
                       VISION_LOW_SPEED_STOP_BUFFER_EGO_GAIN * float(v_ego) +
                       VISION_LOW_SPEED_STOP_BUFFER_LEAD_GAIN * lead_speed)
    release_buffer = entry_buffer + VISION_LOW_SPEED_STOP_BUFFER_RELEASE_MARGIN
    if entry_context and float(lead.dRel) <= entry_buffer:
      self.vision_low_speed_stop_hold_until = now_t + VISION_LOW_SPEED_STOP_BUFFER_HOLD_TIME

    latched = now_t < self.vision_low_speed_stop_hold_until
    active = bool(
      (entry_context and float(lead.dRel) <= entry_buffer) or
      (latched and hold_context and float(lead.dRel) <= release_buffer)
    )
    if not active:
      return None, False

    min_stop_brake = VISION_LOW_SPEED_STOP_BUFFER_MIN_BRAKE + VISION_LOW_SPEED_STOP_BUFFER_BRAKE_GAIN * float(v_ego)
    return max(accel_min, -min_stop_brake), True

  def get_vision_close_stop_hold_cap(self, lead, v_ego, accel_min, should_stop):
    if not should_stop or lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    if lead_prob < VISION_CLOSE_STOP_HOLD_MIN_MODEL_PROB:
      return None

    lead_speed = max(float(lead.vLead), 0.0)
    near_standstill_settle = bool(
      float(v_ego) <= VISION_CLOSE_SETTLE_MAX_EGO_SPEED and
      lead_speed <= VISION_CLOSE_SETTLE_MAX_LEAD_SPEED and
      float(lead.dRel) <= VISION_CLOSE_SETTLE_MAX_DISTANCE
    )
    max_lead_speed = VISION_CLOSE_SETTLE_MAX_LEAD_SPEED if near_standstill_settle else VISION_CLOSE_STOP_HOLD_MAX_LEAD_SPEED
    max_distance = VISION_CLOSE_SETTLE_MAX_DISTANCE if near_standstill_settle else VISION_CLOSE_STOP_HOLD_MAX_DISTANCE
    if (
      float(v_ego) > VISION_CLOSE_STOP_HOLD_MAX_EGO_SPEED or
      lead_speed > max_lead_speed or
      float(lead.dRel) > max_distance
    ):
      return None

    distance_factor = float(np.clip((max_distance - float(lead.dRel)) /
                                    max(max_distance - 1.8, 0.1), 0.0, 1.0))
    speed_factor = float(np.clip(float(v_ego) / max(VISION_CLOSE_STOP_HOLD_MAX_EGO_SPEED, 0.1), 0.0, 1.0))
    hold_brake = VISION_CLOSE_STOP_HOLD_MIN_BRAKE + 0.08 * distance_factor + 0.08 * speed_factor
    if near_standstill_settle:
      settle_brake = VISION_CLOSE_SETTLE_MIN_BRAKE + 0.10 * distance_factor + 0.04 * speed_factor
      hold_brake = max(hold_brake, settle_brake)
    hold_brake = float(np.clip(hold_brake, VISION_CLOSE_STOP_HOLD_MIN_BRAKE, VISION_CLOSE_STOP_HOLD_MAX_BRAKE))
    brake_floor = -hold_brake
    return brake_floor if accel_min >= 0.0 else max(accel_min, brake_floor)

  def get_vision_close_release_hold_cap(self, lead, v_ego, accel_min, should_stop):
    if should_stop or lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    if lead_prob < VISION_CLOSE_RELEASE_HOLD_MIN_MODEL_PROB:
      return None

    lead_speed = max(float(lead.vLead), 0.0)
    lead_delta = lead_speed - float(v_ego)
    near_standstill_settle = bool(
      float(v_ego) <= VISION_CLOSE_SETTLE_MAX_EGO_SPEED and
      lead_speed <= VISION_CLOSE_SETTLE_MAX_LEAD_SPEED and
      float(lead.dRel) <= VISION_CLOSE_SETTLE_MAX_DISTANCE and
      lead_delta <= VISION_CLOSE_SETTLE_MAX_LEAD_DELTA
    )
    max_lead_speed = VISION_CLOSE_SETTLE_MAX_LEAD_SPEED if near_standstill_settle else VISION_CLOSE_RELEASE_HOLD_MAX_LEAD_SPEED
    max_distance = VISION_CLOSE_SETTLE_MAX_DISTANCE if near_standstill_settle else VISION_CLOSE_RELEASE_HOLD_MAX_DISTANCE
    max_lead_delta = VISION_CLOSE_SETTLE_MAX_LEAD_DELTA if near_standstill_settle else VISION_CLOSE_RELEASE_HOLD_MAX_LEAD_DELTA
    if (
      float(v_ego) > VISION_CLOSE_RELEASE_HOLD_MAX_EGO_SPEED or
      lead_speed > max_lead_speed or
      float(lead.dRel) > max_distance or
      lead_delta < VISION_CLOSE_RELEASE_HOLD_MIN_LEAD_DELTA or
      lead_delta > max_lead_delta
    ):
      return None

    distance_factor = float(np.clip((max_distance - float(lead.dRel)) /
                                    max(max_distance - 2.8, 0.1), 0.0, 1.0))
    speed_factor = float(np.clip(float(v_ego) / max(VISION_CLOSE_RELEASE_HOLD_MAX_EGO_SPEED, 0.1), 0.0, 1.0))
    delta_factor = float(np.clip((max_lead_delta - lead_delta) /
                                 max(max_lead_delta - VISION_CLOSE_RELEASE_HOLD_MIN_LEAD_DELTA, 0.1),
                                 0.0, 1.0))
    hold_brake = VISION_CLOSE_RELEASE_HOLD_MIN_BRAKE + 0.12 * distance_factor + 0.06 * speed_factor + 0.04 * delta_factor
    if near_standstill_settle:
      settle_brake = VISION_CLOSE_SETTLE_MIN_BRAKE + 0.08 * distance_factor + 0.02 * delta_factor
      hold_brake = max(hold_brake, settle_brake)
    hold_brake = float(np.clip(hold_brake, VISION_CLOSE_RELEASE_HOLD_MIN_BRAKE, VISION_CLOSE_RELEASE_HOLD_MAX_BRAKE))
    brake_floor = -hold_brake
    return brake_floor if accel_min >= 0.0 else max(accel_min, brake_floor)

  def get_vision_close_settle_cap(self, lead, v_ego, accel_min, stop_guard_active):
    if lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    if lead_prob < VISION_CLOSE_STOP_HOLD_MIN_MODEL_PROB:
      return None

    lead_speed = max(float(lead.vLead), 0.0)
    lead_delta = lead_speed - float(v_ego)
    if (
      float(v_ego) > VISION_CLOSE_SETTLE_MAX_EGO_SPEED or
      lead_speed > VISION_CLOSE_SETTLE_MAX_LEAD_SPEED or
      float(lead.dRel) > VISION_CLOSE_SETTLE_MAX_DISTANCE or
      lead_delta > VISION_CLOSE_SETTLE_MAX_LEAD_DELTA
    ):
      return None

    if not stop_guard_active and lead_delta < 0.0:
      return None

    distance_factor = float(np.clip((VISION_CLOSE_SETTLE_MAX_DISTANCE - float(lead.dRel)) /
                                    max(VISION_CLOSE_SETTLE_MAX_DISTANCE - 2.8, 0.1), 0.0, 1.0))
    delta_factor = float(np.clip((VISION_CLOSE_SETTLE_MAX_LEAD_DELTA - lead_delta) /
                                 max(VISION_CLOSE_SETTLE_MAX_LEAD_DELTA, 0.1), 0.0, 1.0))
    hold_brake = VISION_CLOSE_SETTLE_MIN_BRAKE + 0.10 * distance_factor + 0.04 * delta_factor
    hold_brake = float(np.clip(hold_brake, VISION_CLOSE_SETTLE_MIN_BRAKE, VISION_CLOSE_SETTLE_MAX_BRAKE))
    brake_floor = -hold_brake
    return brake_floor if accel_min >= 0.0 else max(accel_min, brake_floor)

  def get_vision_close_final_guard_cap(self, lead, v_ego, accel_min):
    if lead is None or not _lead_present(lead) or bool(getattr(lead, "radar", False)):
      return None

    lead_prob = float(getattr(lead, "modelProb", 0.0))
    lead_speed = max(float(lead.vLead), 0.0)
    if (
      lead_prob < VISION_CLOSE_STOP_HOLD_MIN_MODEL_PROB or
      float(v_ego) > VISION_CLOSE_FINAL_GUARD_MAX_EGO_SPEED or
      lead_speed > VISION_CLOSE_FINAL_GUARD_MAX_LEAD_SPEED or
      float(lead.dRel) > VISION_CLOSE_FINAL_GUARD_MAX_DISTANCE
    ):
      return None

    distance_factor = float(np.clip((VISION_CLOSE_FINAL_GUARD_MAX_DISTANCE - float(lead.dRel)) /
                                    max(VISION_CLOSE_FINAL_GUARD_MAX_DISTANCE - 2.8, 0.1), 0.0, 1.0))
    hold_brake = VISION_CLOSE_FINAL_GUARD_MIN_BRAKE + 0.10 * distance_factor
    hold_brake = float(np.clip(hold_brake, VISION_CLOSE_FINAL_GUARD_MIN_BRAKE, VISION_CLOSE_FINAL_GUARD_MAX_BRAKE))
    brake_floor = -hold_brake
    return brake_floor if accel_min >= 0.0 else max(accel_min, brake_floor)

  # ------------------------------------------------------------------
  # Depart / standstill release
  # ------------------------------------------------------------------
  def is_confident_lead_depart(self, lead, v_ego):
    if lead is None or not _lead_present(lead):
      return False

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < LEAD_DEPART_ACCEL_HOLD_MIN_MODEL_PROB:
      return False

    lead_speed = max(float(lead.vLead), 0.0)
    lead_delta = lead_speed - float(v_ego)
    lead_accel = float(getattr(lead, "aLeadK", 0.0))
    return bool(
      float(lead.dRel) >= LEAD_DEPART_CONFIDENT_MIN_GAP and
      float(lead.dRel) <= LEAD_DEPART_CONFIDENT_MAX_GAP and
      lead_speed >= LEAD_DEPART_CONFIDENT_MIN_LEAD_SPEED and
      lead_delta >= LEAD_DEPART_CONFIDENT_MIN_LEAD_DELTA and
      lead_accel >= LEAD_DEPART_CONFIDENT_MIN_LEAD_ACCEL
    )

  def is_slow_creep_lead_depart(self, lead, v_ego, standstill_nudge_gap):
    if lead is None or not _lead_present(lead):
      return False

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < STANDSTILL_STOPPED_LEAD_GUARD_MIN_MODEL_PROB:
      return False

    if abs(float(getattr(lead, "yRel", 0.0))) > STANDSTILL_STOPPED_LEAD_GUARD_MAX_LATERAL_OFFSET:
      return False

    lead_gap = float(getattr(lead, "dRel", 0.0))
    lead_speed = max(float(getattr(lead, "vLead", 0.0)), 0.0)
    lead_accel = float(getattr(lead, "aLeadK", 0.0))
    creep_tune = get_toyota_rav4_tss2_lead_creep_tune(self.CP)
    min_lead_speed, min_lead_accel = (
      (STANDSTILL_LEAD_CREEP_RELEASE_MIN_LEAD_SPEED, STANDSTILL_LEAD_CREEP_RELEASE_MIN_LEAD_ACCEL)
      if creep_tune is None else creep_tune
    )
    return bool(
      float(v_ego) <= STANDSTILL_LEAD_DEPART_MAX_EGO_SPEED and
      lead_gap >= standstill_nudge_gap + STANDSTILL_LEAD_CREEP_RELEASE_MIN_GAP_MARGIN and
      lead_speed >= min_lead_speed and
      lead_accel >= min_lead_accel
    )

  def get_safe_depart_release_hold_lead(self, v_ego):
    credible_leads = [
      lead for lead in (self.ctx_lead_one, self.ctx_lead_two)
      if lead is not None and
      _lead_present(lead) and
      (bool(getattr(lead, "radar", False)) or
       float(getattr(lead, "modelProb", 0.0)) >= LEAD_DEPART_RELEASE_HOLD_MIN_MODEL_PROB) and
      abs(float(getattr(lead, "yRel", 0.0))) <= LEAD_DEPART_RELEASE_HOLD_MAX_LATERAL_OFFSET
    ]
    moving_leads = [
      lead for lead in credible_leads
      if float(getattr(lead, "dRel", 0.0)) >= LEAD_DEPART_RELEASE_HOLD_MIN_DISTANCE and
      float(getattr(lead, "vLead", 0.0)) >= LEAD_DEPART_RELEASE_HOLD_MIN_LEAD_SPEED and
      float(getattr(lead, "vLead", 0.0)) - float(v_ego) >= LEAD_DEPART_RELEASE_HOLD_MIN_LEAD_DELTA and
      max(0.0, -float(getattr(lead, "aLeadK", 0.0))) <= LEAD_DEPART_RELEASE_HOLD_MAX_LEAD_BRAKE
    ]
    if not moving_leads:
      return None

    selected_lead = min(moving_leads, key=lambda lead: float(lead.dRel))
    stopped_conflict = any(
      lead is not selected_lead and
      float(getattr(lead, "dRel", float("inf"))) <= float(selected_lead.dRel) + LEAD_DEPART_RELEASE_HOLD_CONFLICT_DISTANCE_MARGIN and
      float(getattr(lead, "vLead", 0.0)) < LEAD_DEPART_RELEASE_HOLD_CONFLICT_SPEED
      for lead in credible_leads
    )
    return None if stopped_conflict else selected_lead

  def get_lead_depart_accel_floor(self, lead, v_ego, model_desired_accel):
    if lead is None or not _lead_present(lead):
      return None

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < LEAD_DEPART_ACCEL_HOLD_MIN_MODEL_PROB:
      return None

    lead_speed = max(float(lead.vLead), 0.0)
    lead_brake = max(0.0, -float(getattr(lead, "aLeadK", 0.0)))
    lead_delta = lead_speed - float(v_ego)
    confident_depart = self.is_confident_lead_depart(lead, v_ego)
    min_lead_speed = LEAD_DEPART_CONFIDENT_MIN_LEAD_SPEED if confident_depart else LEAD_DEPART_ACCEL_HOLD_MIN_LEAD_SPEED
    min_lead_delta = LEAD_DEPART_CONFIDENT_MIN_LEAD_DELTA if confident_depart else LEAD_DEPART_ACCEL_HOLD_MIN_LEAD_DELTA
    min_gap = LEAD_DEPART_CONFIDENT_MIN_GAP if confident_depart else LEAD_DEPART_ACCEL_HOLD_MIN_GAP
    min_model_accel = 0.0 if confident_depart else LEAD_DEPART_ACCEL_HOLD_MIN_MODEL_ACCEL
    if (
      float(v_ego) > LEAD_DEPART_ACCEL_HOLD_MAX_EGO_SPEED or
      lead_speed < min_lead_speed or
      lead_delta < min_lead_delta or
      float(lead.dRel) < min_gap or
      lead_brake > LEAD_DEPART_ACCEL_HOLD_MAX_LEAD_BRAKE or
      float(model_desired_accel) < min_model_accel
    ):
      return None

    gap_factor = float(np.clip((float(lead.dRel) - LEAD_DEPART_ACCEL_HOLD_MIN_GAP) /
                               max(LEAD_DEPART_ACCEL_HOLD_FULL_GAP - LEAD_DEPART_ACCEL_HOLD_MIN_GAP, 0.1), 0.0, 1.0))
    lead_factor = float(np.clip((lead_speed - LEAD_DEPART_ACCEL_HOLD_MIN_LEAD_SPEED) /
                                max(LEAD_DEPART_ACCEL_HOLD_FULL_LEAD_SPEED - LEAD_DEPART_ACCEL_HOLD_MIN_LEAD_SPEED, 0.1), 0.0, 1.0))
    departure_tune = get_toyota_rav4_tss2_lead_departure_tune(self.CP)
    if departure_tune is None:
      departure_tune = (LEAD_DEPART_ACCEL_HOLD_MAX_ACCEL, LEAD_DEPART_ACCEL_ASSIST)
    max_accel = departure_tune[0]
    assist = departure_tune[1]
    accel_cap = LEAD_DEPART_ACCEL_HOLD_MIN_ACCEL + (max_accel - LEAD_DEPART_ACCEL_HOLD_MIN_ACCEL) * np.clip(
      0.55 * lead_factor + 0.45 * gap_factor, 0.0, 1.0)
    assisted_model_accel = float(model_desired_accel) + assist
    return min(accel_cap, max(assisted_model_accel, LEAD_DEPART_ACCEL_HOLD_MIN_ACCEL))

  def get_reusable_lead_depart_accel_floor(self, lead, v_ego, t_follow):
    if self.lead_depart_accel_hold_floor is None or lead is None or not _lead_present(lead):
      return None

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < LEAD_DEPART_ACCEL_HOLD_MIN_MODEL_PROB:
      return None

    if abs(float(getattr(lead, "yRel", 0.0))) > STANDSTILL_STOPPED_LEAD_GUARD_MAX_LATERAL_OFFSET:
      return None

    d_rel = float(getattr(lead, "dRel", 0.0))
    if d_rel < LEAD_DEPART_ACCEL_HOLD_REUSE_MIN_GAP:
      return None

    lead_brake = max(0.0, -float(getattr(lead, "aLeadK", 0.0)))
    if lead_brake > LEAD_DEPART_ACCEL_HOLD_REUSE_MAX_LEAD_BRAKE:
      return None

    closing_speed = max(float(v_ego) - float(getattr(lead, "vLead", 0.0)), 0.0)
    if closing_speed > LEAD_DEPART_ACCEL_HOLD_REUSE_MAX_CLOSING_SPEED:
      return None

    actual_headway = d_rel / max(float(v_ego), 1e-3)
    headway_margin = actual_headway - float(t_follow)
    if headway_margin < LEAD_DEPART_ACCEL_HOLD_REUSE_MIN_HEADWAY_MARGIN:
      return None

    return float(self.lead_depart_accel_hold_floor)

  def get_low_speed_weak_lead_accel_cap(self, lead, v_ego):
    if lead is None or not _lead_present(lead):
      return None

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_MODEL_PROB:
      return None

    d_rel = float(getattr(lead, "dRel", 0.0))
    lead_speed = max(float(getattr(lead, "vLead", 0.0)), 0.0)
    lead_delta = lead_speed - float(v_ego)
    lead_accel = float(getattr(lead, "aLeadK", 0.0))
    lead_lateral = abs(float(getattr(lead, "yRel", 0.0)))
    if (
      float(v_ego) > LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_EGO_SPEED or
      d_rel > LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_DISTANCE or
      lead_speed > LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_SPEED or
      lead_lateral > LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LATERAL_OFFSET or
      lead_delta > LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_DELTA or
      lead_accel > LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_ACCEL
    ):
      return None

    if (
      float(v_ego) <= LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MAX_EGO_SPEED and
      d_rel >= LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_GAP and
      lead_speed >= LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_LEAD_SPEED and
      lead_delta >= LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_LEAD_DELTA and
      lead_accel >= LOW_SPEED_WEAK_LEAD_ACCEL_CAP_STRONG_DEPART_MIN_LEAD_ACCEL
    ):
      return None

    distance_factor = float(np.clip(
      (d_rel - LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_DISTANCE) /
      max(LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_DISTANCE - LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_DISTANCE, 0.1),
      0.0, 1.0,
    ))
    delta_factor = float(np.clip(
      (lead_delta - LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_LEAD_DELTA) /
      max(LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_DELTA - LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_LEAD_DELTA, 0.1),
      0.0, 1.0,
    ))
    accel_factor = float(np.clip(
      (lead_accel - LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_LEAD_ACCEL) /
      max(LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_LEAD_ACCEL - LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_LEAD_ACCEL, 0.1),
      0.0, 1.0,
    ))
    cap_strength = float(np.clip(0.5 * distance_factor + 0.3 * delta_factor + 0.2 * accel_factor, 0.0, 1.0))
    return LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_ACCEL + (
      LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MAX_ACCEL - LOW_SPEED_WEAK_LEAD_ACCEL_CAP_MIN_ACCEL
    ) * cap_strength

  def get_standstill_stopped_lead_guard_cap(self, lead, v_ego, accel_min, stop_distance,
                                            release_ready, confident_depart_ready):
    if lead is None or not _lead_present(lead) or release_ready or confident_depart_ready:
      return None
    max_ego_speed = get_standstill_stopped_lead_guard_max_ego_speed(
      self.CP, STANDSTILL_STOPPED_LEAD_GUARD_MAX_EGO_SPEED,
    )
    if float(v_ego) > max_ego_speed:
      return None

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < STANDSTILL_STOPPED_LEAD_GUARD_MIN_MODEL_PROB:
      return None

    if abs(float(getattr(lead, "yRel", 0.0))) > STANDSTILL_STOPPED_LEAD_GUARD_MAX_LATERAL_OFFSET:
      return None

    lead_speed = max(float(getattr(lead, "vLead", 0.0)), 0.0)
    lead_delta = lead_speed - float(v_ego)
    max_lead_speed = get_standstill_stopped_lead_guard_max_lead_speed(
      self.CP, STANDSTILL_STOPPED_LEAD_GUARD_MAX_LEAD_SPEED,
    )
    max_distance = max(
      STANDSTILL_STOPPED_LEAD_GUARD_MIN_DISTANCE,
      float(stop_distance) + get_standstill_stopped_lead_guard_distance_margin(self.CP),
    )
    if (
      float(getattr(lead, "dRel", float("inf"))) > max_distance or
      lead_speed > max_lead_speed or
      lead_delta > STANDSTILL_STOPPED_LEAD_GUARD_MAX_LEAD_DELTA
    ):
      return None

    distance_factor = float(np.clip((max_distance - float(lead.dRel)) /
                                    max(max_distance - STANDSTILL_STOPPED_LEAD_GUARD_MIN_DISTANCE, 0.1),
                                    0.0, 1.0))
    speed_factor = float(np.clip(lead_speed / max(max_lead_speed, 0.1), 0.0, 1.0))
    delta_factor = float(np.clip((STANDSTILL_STOPPED_LEAD_GUARD_MAX_LEAD_DELTA - lead_delta) /
                                 max(STANDSTILL_STOPPED_LEAD_GUARD_MAX_LEAD_DELTA, 0.1),
                                 0.0, 1.0))
    hold_brake = STANDSTILL_STOPPED_LEAD_GUARD_MIN_BRAKE + 0.06 * distance_factor + 0.02 * speed_factor + 0.02 * delta_factor
    hold_brake = float(np.clip(
      hold_brake,
      STANDSTILL_STOPPED_LEAD_GUARD_MIN_BRAKE,
      STANDSTILL_STOPPED_LEAD_GUARD_MAX_BRAKE,
    ))
    brake_floor = -hold_brake
    return brake_floor if accel_min >= 0.0 else max(accel_min, brake_floor)

  def post_departure_follow_settle_active(self, lead, v_ego, t_follow):
    if lead is None or not _lead_present(lead):
      return False
    if float(v_ego) < POST_DEPARTURE_FOLLOW_SETTLE_MIN_SPEED:
      return False

    lead_radar = bool(getattr(lead, "radar", False))
    lead_prob = float(getattr(lead, "modelProb", 1.0 if lead_radar else 0.0))
    if not lead_radar and lead_prob < POST_DEPARTURE_FOLLOW_SETTLE_MIN_MODEL_PROB:
      return False

    if abs(float(getattr(lead, "yRel", 0.0))) > POST_DEPARTURE_FOLLOW_SETTLE_MAX_LATERAL_OFFSET:
      return False

    actual_headway = float(lead.dRel) / max(float(v_ego), 1e-3)
    headway_margin = actual_headway - float(t_follow)
    lead_brake = max(0.0, -float(getattr(lead, "aLeadK", 0.0)))
    closing_speed = max(float(v_ego) - float(lead.vLead), 0.0)
    now = time.monotonic()
    if now > self.post_departure_follow_settle_until:
      self.post_departure_follow_settle_until = 0.0
      lead_delta = float(lead.vLead) - float(v_ego)
      lead_accel = float(getattr(lead, "aLeadK", 0.0))
      # Rolling launches can miss the standstill release edge that normally arms
      # this latch. Confirm the same safe pull-away state from lead motion instead.
      rolling_departure = (
        float(v_ego) <= POST_DEPARTURE_FOLLOW_SETTLE_MAX_ARM_SPEED and
        lead_delta >= POST_DEPARTURE_FOLLOW_SETTLE_ARM_MIN_LEAD_DELTA and
        lead_accel >= POST_DEPARTURE_FOLLOW_SETTLE_ARM_MIN_LEAD_ACCEL and
        headway_margin >= POST_DEPARTURE_FOLLOW_SETTLE_ARM_MIN_HEADWAY_MARGIN
      )
      if not rolling_departure:
        return False
      self.post_departure_follow_settle_until = now + POST_DEPARTURE_FOLLOW_SETTLE_LATCH_TIME

    if (
      headway_margin <= POST_DEPARTURE_FOLLOW_SETTLE_COMPLETE_HEADWAY_MARGIN or
      lead_brake > POST_DEPARTURE_FOLLOW_SETTLE_MAX_LEAD_BRAKE or
      closing_speed > POST_DEPARTURE_FOLLOW_SETTLE_MAX_CLOSING_SPEED
    ):
      self.post_departure_follow_settle_until = 0.0
      return False

    return True

  @staticmethod
  def is_radar_standstill_gap_settle_candidate(lead, v_ego, target_gap, active=False,
                                               allow_vision=False, max_extra_gap=RADAR_STANDSTILL_GAP_SETTLE_MAX_EXTRA_GAP):
    if lead is None or not _lead_present(lead) or (not bool(getattr(lead, "radar", False)) and not allow_vision):
      return False
    if float(v_ego) > RADAR_STANDSTILL_GAP_SETTLE_MAX_EGO_SPEED:
      return False
    if abs(float(getattr(lead, "yRel", 0.0))) > RADAR_STANDSTILL_GAP_SETTLE_MAX_LATERAL_OFFSET:
      return False
    if abs(float(getattr(lead, "vLead", 0.0))) > RADAR_STANDSTILL_GAP_SETTLE_MAX_LEAD_SPEED:
      return False
    if allow_vision and (
      bool(getattr(lead, "radar", False)) or
      float(getattr(lead, "modelProb", 0.0)) < 0.99
    ):
      return False

    lead_gap = float(getattr(lead, "dRel", 0.0))
    min_margin = RADAR_STANDSTILL_GAP_SETTLE_EXIT_MARGIN if active else RADAR_STANDSTILL_GAP_SETTLE_ENTRY_MARGIN
    return bool(
      lead_gap > target_gap + min_margin and
      lead_gap <= target_gap + float(max_extra_gap)
    )

  def update_radar_standstill_gap_settle(self, ctx, target_gap, allow_vision=False, max_extra_gap=None):
    vetoed = bool(
      ctx.brake_pressed or
      ctx.gas_pressed or
      ctx.forcing_stop or
      ctx.red_light
    )
    candidates = [
      lead for lead in (ctx.lead_one, ctx.lead_two)
      if self.is_radar_standstill_gap_settle_candidate(
        lead,
        float(ctx.v_ego),
        target_gap,
        active=self.radar_standstill_gap_settle_active,
        allow_vision=allow_vision,
        max_extra_gap=(RADAR_STANDSTILL_GAP_SETTLE_MAX_EXTRA_GAP if max_extra_gap is None else max_extra_gap),
      )
    ]

    if vetoed or not candidates:
      self.radar_standstill_gap_settle_elapsed = 0.0
      self.radar_standstill_gap_settle_active = False
      return False

    if self.radar_standstill_gap_settle_active:
      return True

    if not ctx.standstill:
      self.radar_standstill_gap_settle_elapsed = 0.0
      return False

    self.radar_standstill_gap_settle_elapsed = min(
      RADAR_STANDSTILL_GAP_SETTLE_CONFIRM_TIME,
      self.radar_standstill_gap_settle_elapsed + self.dt,
    )
    self.radar_standstill_gap_settle_active = (
      self.radar_standstill_gap_settle_elapsed + 1e-6 >= RADAR_STANDSTILL_GAP_SETTLE_CONFIRM_TIME
    )
    return self.radar_standstill_gap_settle_active

  # ------------------------------------------------------------------
  # Depart safety veto (off-center radar vs centered model lead)
  # ------------------------------------------------------------------
  @staticmethod
  def get_centered_model_lead(model_data):
    if model_data is None:
      return None
    try:
      leads = model_data.leadsV3
    except Exception:
      return None

    best_candidate = None
    for i in range(3):
      try:
        lead = leads[i]
        prob = float(lead.prob)
        x = float(lead.x[0])
        y = float(lead.y[0])
        v = float(lead.v[0])
      except Exception:
        continue

      if (
        prob < RADAR_DEPART_CONFLICT_MIN_MODEL_PROB or
        x <= 0.0 or
        x > RADAR_DEPART_CONFLICT_MAX_MODEL_DISTANCE or
        abs(y) > RADAR_DEPART_CONFLICT_MAX_MODEL_LATERAL or
        max(v, 0.0) > RADAR_DEPART_CONFLICT_MAX_MODEL_LEAD_SPEED
      ):
        continue

      if best_candidate is None or x < best_candidate[0]:
        best_candidate = (x, y, v, prob)

    return best_candidate

  def has_offcenter_radar_depart_conflict(self, ctx):
    if float(getattr(ctx, "v_ego", 0.0)) > RADAR_DEPART_CONFLICT_MAX_EGO_SPEED:
      return False

    centered_model_lead = self.get_centered_model_lead(ctx.model_data)
    if centered_model_lead is None:
      return False

    centered_model_dist = float(centered_model_lead[0])
    for lead in (ctx.lead_one, ctx.lead_two):
      if not _lead_present(lead) or not bool(getattr(lead, "radar", False)):
        continue

      lead_dist = float(getattr(lead, "dRel", 0.0))
      if lead_dist <= 0.0 or lead_dist > RADAR_DEPART_CONFLICT_MAX_RADAR_DISTANCE:
        continue
      if abs(float(getattr(lead, "yRel", 0.0))) < RADAR_DEPART_CONFLICT_MIN_RADAR_LATERAL:
        continue
      if abs(lead_dist - centered_model_dist) > RADAR_DEPART_CONFLICT_MAX_DISTANCE_MISMATCH:
        continue

      return True

    return False

  # ------------------------------------------------------------------
  # Per-vehicle stop&go smoothing (Accord)
  # ------------------------------------------------------------------
  def get_honda_accord_stop_go_accel_target(self, lead, v_ego, previous_target, target, blocked):
    """Smooth the Accord's low-speed lead launch without touching braking targets."""
    if blocked or target <= 0.0:
      return float(target)

    cap = get_honda_accord_stop_go_accel_cap(self.CP, lead, v_ego)
    if cap is None:
      return float(target)

    limited_target = min(float(target), cap)
    if limited_target > float(previous_target):
      rise_rate = get_honda_accord_stop_go_accel_rise_rate(self.CP)
      if rise_rate > 0.0:
        limited_target = min(
          limited_target,
          max(0.0, float(previous_target) + rise_rate * self.dt),
        )
    return float(limited_target)

  # ------------------------------------------------------------------
  # Orchestration (StarPilot output-stage sequence)
  # ------------------------------------------------------------------
  def apply(self, ctx: StopDepartContext) -> StopDepartResult:
    self.ctx_lead_one, self.ctx_lead_two = ctx.lead_one, ctx.lead_two
    now_t = time.monotonic()
    v_ego = float(ctx.v_ego)
    a_target = float(ctx.a_target)
    accel_min = float(ctx.output_accel_min)
    effective_t_follow = self.get_dynamic_t_follow(
      ctx.t_follow, ctx.lead_one if ctx.tracking else None, v_ego)
    should_stop = bool(ctx.should_stop)

    depart_safety_veto = self.has_offcenter_radar_depart_conflict(ctx)
    standstill_nudge_gap = _stop_distance() - 0.5
    notes: dict = {}

    # 1. Pre-tracking vision caps (untracked slow lead, confirm-gated).
    pretracking_vision_caps = []
    for lead in (ctx.lead_one, ctx.lead_two):
      if _lead_present(lead) and not bool(getattr(lead, "radar", False)):
        pretracking_cap = self.get_vision_untracked_slow_lead_cap(lead, v_ego, accel_min)
        if pretracking_cap is not None:
          pretracking_vision_caps.append((pretracking_cap, lead))

    if pretracking_vision_caps:
      pretracking_vision_cap, pretracking_vision_lead = min(pretracking_vision_caps, key=lambda cap_and_lead: cap_and_lead[0])
      lead_brake = max(0.0, -float(getattr(pretracking_vision_lead, "aLeadK", 0.0)))
      immediate_pretracking_cap = (
        pretracking_vision_cap <= -VISION_UNTRACKED_SLOW_LEAD_IMMEDIATE_DECEL or
        float(getattr(pretracking_vision_lead, "dRel", float("inf"))) <= VISION_UNTRACKED_SLOW_LEAD_IMMEDIATE_DISTANCE or
        lead_brake >= VISION_UNTRACKED_SLOW_LEAD_IMMEDIATE_LEAD_BRAKE or
        float(getattr(pretracking_vision_lead, "vLead", float("inf"))) <= VISION_UNTRACKED_SLOW_LEAD_RELAXED_MAX_LEAD_SPEED
      )

      if immediate_pretracking_cap:
        self.untracked_slow_lead_confirm_t = VISION_UNTRACKED_SLOW_LEAD_CONFIRM_TIME
      else:
        self.untracked_slow_lead_confirm_t = min(
          self.untracked_slow_lead_confirm_t + self.dt,
          VISION_UNTRACKED_SLOW_LEAD_CONFIRM_TIME,
        )

      if self.untracked_slow_lead_confirm_t >= VISION_UNTRACKED_SLOW_LEAD_CONFIRM_TIME:
        a_target = min(a_target, pretracking_vision_cap)
        notes["pretracking_cap"] = pretracking_vision_cap
    else:
      self.untracked_slow_lead_confirm_t = 0.0

    # 2. Approach lift (throttle trim before the vision lead is tracked).
    lift_caps = [
      cap for cap in (
        self.get_vision_untracked_approach_lift_cap(ctx.lead_one, v_ego, effective_t_follow),
        self.get_vision_untracked_approach_lift_cap(ctx.lead_two, v_ego, effective_t_follow),
      ) if cap is not None
    ]
    raw_approach_lift_cap = min(lift_caps) if lift_caps else None
    approach_lift_cap = self.update_vision_untracked_approach_lift_cap(
      raw_approach_lift_cap, a_target, a_target, now_t, not ctx.tracking)
    if approach_lift_cap is not None:
      a_target = min(a_target, approach_lift_cap)
      notes["approach_lift_cap"] = approach_lift_cap

    # 3. Close-lead brake caps + tracked vision approach (confirm-gated).
    close_lead_caps = []
    tracked_vision_approach_caps = []
    vision_low_speed_stop_active = False
    if ctx.active:
      for lead in (ctx.lead_one, ctx.lead_two):
        cap = self.get_close_lead_brake_cap(lead, v_ego, accel_min)
        if cap is not None:
          close_lead_caps.append(cap)
        slow_stop_cap = self.get_vision_slow_stopped_lead_cap(lead, v_ego, accel_min, effective_t_follow)
        if slow_stop_cap is not None:
          close_lead_caps.append(slow_stop_cap)
        approach_cap = self.get_vision_lead_approach_cap(lead, v_ego, accel_min, effective_t_follow)
        if approach_cap is not None:
          tracked_vision_approach_caps.append((
            approach_cap,
            self.tracked_vision_lead_approach_needs_immediate_brake(lead, v_ego, approach_cap),
          ))
        low_speed_stop_cap, low_speed_stop_active = self.get_vision_low_speed_stop_buffer_cap(lead, v_ego, accel_min)
        if low_speed_stop_cap is not None:
          close_lead_caps.append(low_speed_stop_cap)
        vision_low_speed_stop_active |= low_speed_stop_active
    if tracked_vision_approach_caps:
      if any(immediate for _, immediate in tracked_vision_approach_caps):
        self.vision_lead_approach_confirm_t = VISION_LEAD_APPROACH_CONFIRM_TIME
      else:
        self.vision_lead_approach_confirm_t = min(
          self.vision_lead_approach_confirm_t + self.dt,
          VISION_LEAD_APPROACH_CONFIRM_TIME,
        )

      if self.vision_lead_approach_confirm_t >= VISION_LEAD_APPROACH_CONFIRM_TIME:
        close_lead_caps.append(min(cap for cap, _ in tracked_vision_approach_caps))
    else:
      self.vision_lead_approach_confirm_t = 0.0
    if close_lead_caps:
      close_lead_brake_cap = min(close_lead_caps)
      a_target = min(a_target, close_lead_brake_cap)
      notes["close_brake_cap"] = close_lead_brake_cap

    # 4. Standstill depart detection / latches.
    moving_leads = [lead for lead in (ctx.lead_one, ctx.lead_two)
                    if _lead_present(lead) and
                    lead.vLead > STANDSTILL_LEAD_NUDGE_MIN_SPEED and lead.dRel >= standstill_nudge_gap]
    accelerating_nudge_lead = any(
      _lead_present(lead) and
      float(getattr(lead, "vLead", 0.0)) > STANDSTILL_LEAD_NUDGE_MIN_SPEED and
      float(getattr(lead, "aLeadK", 0.0)) >= STANDSTILL_LEAD_NUDGE_MIN_LEAD_ACCEL and
      float(getattr(lead, "dRel", 0.0)) >= standstill_nudge_gap
      for lead in (ctx.lead_one, ctx.lead_two)
    )
    confident_depart_detected = any(self.is_confident_lead_depart(lead, v_ego)
                                    for lead in (ctx.lead_one, ctx.lead_two))
    lead_depart_ready = any(
      _lead_present(lead) and
      lead.vLead >= STANDSTILL_LEAD_DEPART_MIN_LEAD_SPEED and
      lead.dRel >= standstill_nudge_gap + STANDSTILL_LEAD_DEPART_MIN_GAP_MARGIN
      for lead in (ctx.lead_one, ctx.lead_two)
    )
    safe_depart_release_hold_lead = self.get_safe_depart_release_hold_lead(v_ego)
    depart_release_hold_context = bool(
      ctx.active and
      v_ego <= STANDSTILL_LEAD_DEPART_MAX_EGO_SPEED and
      not depart_safety_veto and
      not ctx.brake_pressed and
      not ctx.forcing_stop and
      not ctx.red_light and
      safe_depart_release_hold_lead is not None
    )
    if depart_release_hold_context:
      self.lead_depart_release_candidate_elapsed = min(
        LEAD_DEPART_RELEASE_HOLD_CONFIRM_TIME,
        self.lead_depart_release_candidate_elapsed + self.dt,
      )
    else:
      self.lead_depart_release_candidate_elapsed = 0.0
      self.lead_depart_release_pending = False
      self.lead_depart_release_hold_remaining = 0.0

    if self.lead_depart_release_hold_remaining > 0.0:
      self.lead_depart_release_hold_remaining = max(0.0, self.lead_depart_release_hold_remaining - self.dt)
    depart_release_hold_active = bool(depart_release_hold_context and self.lead_depart_release_hold_remaining > 0.0)

    if (
      ctx.active and ctx.standstill and
      not depart_safety_veto and
      not ctx.forcing_stop and not ctx.red_light and
      confident_depart_detected
    ):
      self.confident_lead_depart_elapsed = min(
        LEAD_DEPART_CONFIDENT_CONFIRM_TIME,
        self.confident_lead_depart_elapsed + self.dt,
      )
    else:
      self.confident_lead_depart_elapsed = 0.0
    confident_depart_ready = (
      confident_depart_detected and
      self.confident_lead_depart_elapsed >= LEAD_DEPART_CONFIDENT_CONFIRM_TIME
    )
    slow_creep_depart_detected = any(
      self.is_slow_creep_lead_depart(lead, v_ego, standstill_nudge_gap)
      for lead in (ctx.lead_one, ctx.lead_two)
    )
    if (
      ctx.active and ctx.standstill and
      not depart_safety_veto and
      not ctx.forcing_stop and not ctx.red_light and
      slow_creep_depart_detected
    ):
      self.slow_creep_lead_depart_elapsed = min(
        STANDSTILL_LEAD_CREEP_RELEASE_CONFIRM_TIME,
        self.slow_creep_lead_depart_elapsed + self.dt,
      )
    else:
      self.slow_creep_lead_depart_elapsed = 0.0
    slow_creep_depart_ready = (
      slow_creep_depart_detected and
      self.slow_creep_lead_depart_elapsed >= STANDSTILL_LEAD_CREEP_RELEASE_CONFIRM_TIME
    )

    radar_gap_settle_active = False
    max_extra_gap = get_standstill_gap_settle_max_extra_gap(ctx.CP)
    radar_gap_settle_active = self.update_radar_standstill_gap_settle(
      ctx, standstill_nudge_gap, allow_vision=False, max_extra_gap=max_extra_gap)

    # 5. Stopped-lead guard (standstill hold floor) before depart releases.
    standstill_stopped_lead_guard_cap = None
    standstill_guard_lead_present = any(_lead_present(lead) for lead in (ctx.lead_one, ctx.lead_two))
    if standstill_guard_lead_present and (ctx.standstill or v_ego <= STANDSTILL_STOPPED_LEAD_GUARD_MAX_EGO_SPEED):
      release_ready = bool(
        lead_depart_ready or confident_depart_ready or slow_creep_depart_ready or
        radar_gap_settle_active or depart_release_hold_active
      )
      standstill_stopped_lead_guard_caps = [
        cap for cap in (
          self.get_standstill_stopped_lead_guard_cap(
            ctx.lead_one, v_ego, accel_min, standstill_nudge_gap, release_ready, confident_depart_ready),
          self.get_standstill_stopped_lead_guard_cap(
            ctx.lead_two, v_ego, accel_min, standstill_nudge_gap, release_ready, confident_depart_ready),
        ) if cap is not None
      ]
      if standstill_stopped_lead_guard_caps:
        standstill_stopped_lead_guard_cap = min(standstill_stopped_lead_guard_caps)
        should_stop = True

    # 6. Depart releases (nudge / confirmed / creep / release hold / gap settle).
    if ctx.active and ctx.standstill and moving_leads and not depart_safety_veto:
      a_target = max(a_target, STANDSTILL_LEAD_NUDGE_ACCEL)

    if (
      ctx.active and ctx.standstill and
      (confident_depart_ready or lead_depart_ready or slow_creep_depart_ready) and
      not depart_safety_veto and
      not ctx.forcing_stop and not ctx.red_light and
      (confident_depart_ready or slow_creep_depart_ready or
       float(ctx.model_desired_accel) >= STANDSTILL_LEAD_DEPART_MIN_MODEL_ACCEL)
    ):
      vision_low_speed_stop_active = False
      should_stop = False
      depart_min_accel = STANDSTILL_LEAD_DEPART_MIN_ACCEL
      if slow_creep_depart_ready and not (confident_depart_ready or lead_depart_ready):
        depart_min_accel = STANDSTILL_LEAD_CREEP_RELEASE_MIN_ACCEL
      a_target = max(a_target, depart_min_accel)
      self.post_departure_follow_settle_until = now_t + POST_DEPARTURE_FOLLOW_SETTLE_LATCH_TIME

    if depart_release_hold_context and bool(ctx.should_stop) and not bool(should_stop):
      self.lead_depart_release_pending = True
    if (
      depart_release_hold_context and
      self.lead_depart_release_pending and
      not bool(should_stop) and
      self.lead_depart_release_candidate_elapsed >= LEAD_DEPART_RELEASE_HOLD_CONFIRM_TIME
    ):
      self.lead_depart_release_hold_remaining = LEAD_DEPART_RELEASE_HOLD_TIME
      self.lead_depart_release_pending = False
      depart_release_hold_active = True
    elif bool(should_stop) and self.lead_depart_release_hold_remaining <= 0.0:
      self.lead_depart_release_pending = False

    if depart_release_hold_active:
      vision_low_speed_stop_active = False
      should_stop = False
      self.post_departure_follow_settle_until = now_t + POST_DEPARTURE_FOLLOW_SETTLE_LATCH_TIME

    if ctx.active and lead_depart_ready and not depart_safety_veto and not should_stop and v_ego <= STANDSTILL_LEAD_DEPART_MAX_EGO_SPEED:
      a_target = max(a_target, STANDSTILL_LEAD_DEPART_MIN_ACCEL)
      self.post_departure_follow_settle_until = now_t + POST_DEPARTURE_FOLLOW_SETTLE_LATCH_TIME

    if radar_gap_settle_active:
      vision_low_speed_stop_active = False
      should_stop = False
      a_target = RADAR_STANDSTILL_GAP_SETTLE_ACCEL

    # 7. Depart accel hold floor (carry a release through the first meters).
    if depart_safety_veto or should_stop or ctx.forcing_stop or ctx.red_light:
      self.lead_depart_accel_hold_until = 0.0
      self.lead_depart_accel_hold_floor = None

    lead_depart_accel_floor = None
    self.lead_depart_accel_hold_reused = False
    if ctx.active and not should_stop and not depart_safety_veto:
      lead_depart_accel_floors = [
        floor for floor in (
          self.get_lead_depart_accel_floor(ctx.lead_one, v_ego, ctx.model_desired_accel),
          self.get_lead_depart_accel_floor(ctx.lead_two, v_ego, ctx.model_desired_accel),
        ) if floor is not None
      ]
      if lead_depart_accel_floors:
        lead_depart_accel_floor = max(lead_depart_accel_floors)
        self.lead_depart_accel_hold_floor = lead_depart_accel_floor
        if ctx.standstill:
          self.lead_depart_accel_hold_until = now_t + LEAD_DEPART_ACCEL_HOLD_TIME
      elif self.lead_depart_accel_hold_floor is not None and now_t < self.lead_depart_accel_hold_until:
        reusable_hold_floors = [
          floor for floor in (
            self.get_reusable_lead_depart_accel_floor(ctx.lead_one, v_ego, effective_t_follow),
            self.get_reusable_lead_depart_accel_floor(ctx.lead_two, v_ego, effective_t_follow),
          ) if floor is not None
        ]
        if reusable_hold_floors:
          lead_depart_accel_floor = max(reusable_hold_floors)
          self.lead_depart_accel_hold_reused = True
        else:
          self.lead_depart_accel_hold_floor = None
      elif now_t >= self.lead_depart_accel_hold_until:
        self.lead_depart_accel_hold_floor = None

    lead_depart_accel_hold_active = (
      lead_depart_accel_floor is not None and
      now_t < self.lead_depart_accel_hold_until and
      v_ego <= LEAD_DEPART_ACCEL_HOLD_MAX_EGO_SPEED
    )

    # 8. Weak-lead throttle cap at low speed.
    low_speed_weak_lead_accel_cap = None
    if not should_stop:
      low_speed_weak_lead_accel_caps = [
        cap for cap in (
          self.get_low_speed_weak_lead_accel_cap(ctx.lead_one, v_ego),
          self.get_low_speed_weak_lead_accel_cap(ctx.lead_two, v_ego),
        ) if cap is not None
      ]
      if low_speed_weak_lead_accel_caps:
        low_speed_weak_lead_accel_cap = min(low_speed_weak_lead_accel_caps)

    # 9. Close-stop hold / settle / final guard / release hold caps.
    close_stop_active = bool(should_stop or vision_low_speed_stop_active)

    close_stop_hold_cap = None
    if ctx.active and close_stop_active:
      close_stop_hold_caps = [
        cap for cap in (
          self.get_vision_close_stop_hold_cap(ctx.lead_one, v_ego, accel_min, close_stop_active),
          self.get_vision_close_stop_hold_cap(ctx.lead_two, v_ego, accel_min, close_stop_active),
        ) if cap is not None
      ]
      if close_stop_hold_caps:
        close_stop_hold_cap = min(close_stop_hold_caps)

    close_release_hold_cap = None
    if ctx.active and not close_stop_active:
      close_release_hold_caps = [
        cap for cap in (
          self.get_vision_close_release_hold_cap(ctx.lead_one, v_ego, accel_min, close_stop_active),
          self.get_vision_close_release_hold_cap(ctx.lead_two, v_ego, accel_min, close_stop_active),
        ) if cap is not None
      ]
      if close_release_hold_caps:
        close_release_hold_cap = min(close_release_hold_caps)

    close_settle_guard_active = bool(
      should_stop or
      vision_low_speed_stop_active or
      ctx.long_control_stopping
    )
    close_settle_cap = None
    if ctx.active:
      close_settle_caps = [
        cap for cap in (
          self.get_vision_close_settle_cap(ctx.lead_one, v_ego, accel_min, close_settle_guard_active),
          self.get_vision_close_settle_cap(ctx.lead_two, v_ego, accel_min, close_settle_guard_active),
        ) if cap is not None
      ]
      if close_settle_caps:
        close_settle_cap = min(close_settle_caps)

    close_final_guard_cap = None
    if ctx.active:
      close_final_guard_caps = [
        cap for cap in (
          self.get_vision_close_final_guard_cap(ctx.lead_one, v_ego, accel_min),
          self.get_vision_close_final_guard_cap(ctx.lead_two, v_ego, accel_min),
        ) if cap is not None
      ]
      if close_final_guard_caps:
        close_final_guard_cap = min(close_final_guard_caps)

    # 10. Final ordering (StarPilot: guard caps are mins after smoothing; the
    # depart accel floor is a max after them; the weak-lead cap a final min).
    if close_stop_hold_cap is not None:
      a_target = min(a_target, close_stop_hold_cap)

    if standstill_stopped_lead_guard_cap is not None:
      a_target = min(a_target, standstill_stopped_lead_guard_cap)

    if close_settle_cap is not None:
      a_target = min(a_target, close_settle_cap)

    if close_final_guard_cap is not None:
      a_target = min(a_target, close_final_guard_cap)

    if close_release_hold_cap is not None:
      a_target = min(a_target, close_release_hold_cap)

    if depart_safety_veto:
      a_target = min(a_target, 0.0)
      if ctx.standstill:
        should_stop = True

    if lead_depart_accel_hold_active:
      a_target = max(a_target, lead_depart_accel_floor)

    if low_speed_weak_lead_accel_cap is not None and not (lead_depart_accel_hold_active and self.lead_depart_accel_hold_reused):
      a_target = min(a_target, low_speed_weak_lead_accel_cap)

    if (
      ctx.active and
      (ctx.standstill or v_ego <= STANDSTILL_STOPPED_LEAD_GUARD_MAX_EGO_SPEED) and
      should_stop and
      accelerating_nudge_lead and
      not depart_safety_veto
    ):
      a_target = max(a_target, STANDSTILL_LEAD_NUDGE_ACCEL)

    # 11. Post-departure follow settle latch (report + per-vehicle restop hook).
    policy_lead = ctx.lead_two if getattr(ctx, "source", None) == "lead1" else ctx.lead_one
    post_departure_active = self.post_departure_follow_settle_active(
      policy_lead, v_ego, effective_t_follow)

    notes.update({
      "close_stop_hold": close_stop_hold_cap,
      "close_release_hold": close_release_hold_cap,
      "close_settle": close_settle_cap,
      "close_final_guard": close_final_guard_cap,
      "standstill_guard": standstill_stopped_lead_guard_cap,
      "depart_floor": lead_depart_accel_floor,
      "weak_cap": low_speed_weak_lead_accel_cap,
      "veto": depart_safety_veto,
    })
    return StopDepartResult(
      a_target=a_target,
      should_stop=should_stop,
      effective_t_follow=effective_t_follow,
      post_departure=post_departure_active,
      blocked=bool(should_stop or vision_low_speed_stop_active or close_lead_caps),
      notes=notes,
    )
