#!/usr/bin/env python3
import os
import time
import numpy as np
from openpilot.cereal import log
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.following_profile import (
  load_profile_document,
  personality_key,
  t_follow_for_personality,
)
from openpilot.selfdrive.controls.lib.lead_duplicate_policy import (
  DuplicateVisionLeadFilters,
  identical_radar_duplicate_source_hold,
  near_duplicate_lead_source_hysteresis,
)
from openpilot.selfdrive.controls.lib.model_lead_trajectory import (
  build_model_lead_trajectory,
  should_trigger_planner_fcw,
)
# WARNING: imports outside of constants will not trigger a rebuild
from openpilot.selfdrive.modeld.constants import index_function
from openpilot.selfdrive.controls.radard import _LEAD_ACCEL_TAU
from openpilot.common.params import Params
from openpilot.sunnypilot.common.param_read import read_bool, read_str
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_braking_gap import (
  LeadComfortState, braking_gap_reference, comfort_path_has_reserve,
)
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_gap_recovery import (
  LeadGapState, displayed_follow_distance,
)
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_cutout import cutout_obstacle_relief

if __name__ == '__main__':  # generating code
  from acados.acados_template import AcadosModel, AcadosOcp, AcadosOcpSolver
else:
  from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.c_generated_code.acados_ocp_solver_pyx import AcadosOcpSolverCython

from casadi import SX, vertcat

MODEL_NAME = 'long'
LONG_MPC_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(LONG_MPC_DIR, "c_generated_code")
JSON_FILE = os.path.join(LONG_MPC_DIR, "acados_ocp_long.json")

LongitudinalPlanSource = log.LongitudinalPlan.LongitudinalPlanSource
MPC_SOURCES = (LongitudinalPlanSource.lead0, LongitudinalPlanSource.lead1)

X_DIM = 3
U_DIM = 1
PARAM_DIM = 6
COST_E_DIM = 5
COST_DIM = COST_E_DIM + 1
CONSTR_DIM = 4

X_EGO_OBSTACLE_COST = 3.
X_EGO_COST = 0.
V_EGO_COST = 0.
A_EGO_COST = 0.
J_EGO_COST = 5.
A_CHANGE_COST = 200.
DANGER_ZONE_COST = 100.
CRASH_DISTANCE = .25
LEAD_DANGER_FACTOR = 0.75
LIMIT_COST = 1e6
ACADOS_SOLVER_TYPE = 'SQP_RTI'

# Fewer timestamps don't hurt performance and lead to
# much better convergence of the MPC with low iterations
N = 12
MAX_T = 10.0
T_IDXS_LST = [index_function(idx, max_val=MAX_T, max_idx=N) for idx in range(N+1)]

T_IDXS = np.array(T_IDXS_LST)
FCW_IDXS = T_IDXS < 5.0
T_DIFFS = np.diff(T_IDXS, prepend=[0.])

# TODO don't hardcode A_CHANGE_COST idx
# reduce the cost on (a-a_prev) later in the horizon. The taper only depends on
# the fixed horizon times, so interpolate it once instead of every horizon step.
A_CHANGE_FACTORS = np.interp(T_IDXS[:N], [0.0, 1.0, 2.0], [1.0, 1.0, 0.0])


def _read_tuning_float(params, key, default):
  """Best-effort read of a float tuning param; falls back to default (e.g. in tests / no-params env)."""
  try:
    val = params.get(key, return_default=True)
    return float(val) if val is not None else default
  except Exception:
    return default

# COMFORT_BRAKE and STOP_DISTANCE are baked into the compiled acados solver (see gen_long_ocp).
# They are read at module load so a solver rebuild bakes the user's chosen values consistently.
_TUNING_PARAMS = Params()
COMFORT_BRAKE = _read_tuning_float(_TUNING_PARAMS, "LongitudinalMpcTuningComfortBrake", 2.5)
STOP_DISTANCE = _read_tuning_float(_TUNING_PARAMS, "LongitudinalMpcTuningStopDistance", 6.0)
MIN_X_LEAD_FACTOR = 0.5

# Fallbacks for the t-follow tuning params. LongitudinalMpc reads the live values
# into self.t_follow_*; these are the built-in defaults, used to tell "the user
# changed the follow time" apart from "the default is in effect".
T_FOLLOW_DEFAULTS = {
  log.LongitudinalPersonality.relaxed: 1.75,
  log.LongitudinalPersonality.standard: 1.45,
  log.LongitudinalPersonality.aggressive: 1.25,
}

def get_jerk_factor(personality=log.LongitudinalPersonality.standard):
  if personality==log.LongitudinalPersonality.relaxed:
    return 1.0
  elif personality==log.LongitudinalPersonality.standard:
    return 1.0
  elif personality==log.LongitudinalPersonality.aggressive:
    return 0.5
  else:
    raise NotImplementedError("Longitudinal personality not supported")


def get_T_FOLLOW(personality=log.LongitudinalPersonality.standard):
  if personality==log.LongitudinalPersonality.relaxed:
    return 1.75
  elif personality==log.LongitudinalPersonality.standard:
    return 1.45
  elif personality==log.LongitudinalPersonality.aggressive:
    return 1.25
  else:
    raise NotImplementedError("Longitudinal personality not supported")

def get_stopped_equivalence_factor(v_lead, comfort_brake=COMFORT_BRAKE):
  return (v_lead**2) / (2 * comfort_brake)

def get_safe_obstacle_distance(v_ego, t_follow, comfort_brake=COMFORT_BRAKE, stop_distance=STOP_DISTANCE):
  return (v_ego**2) / (2 * comfort_brake) + t_follow * v_ego + stop_distance


def desired_follow_distance(v_ego, v_lead, comfort_brake, stop_distance, t_follow):
  # Carrot gap-recovery display reference. Same shape as the safe obstacle
  # distance minus the lead's stopped-equivalence, so a stopped lead shows the
  # physical stop gap and a moving one shows the time-gap.
  return get_safe_obstacle_distance(v_ego, t_follow, comfort_brake, stop_distance) - get_stopped_equivalence_factor(v_lead, comfort_brake)

def gen_long_model():
  model = AcadosModel()
  model.name = MODEL_NAME

  # states
  x_ego, v_ego, a_ego = SX.sym('x_ego'), SX.sym('v_ego'), SX.sym('a_ego')
  model.x = vertcat(x_ego, v_ego, a_ego)

  # controls
  j_ego = SX.sym('j_ego')
  model.u = vertcat(j_ego)

  # xdot
  x_ego_dot = SX.sym('x_ego_dot')
  v_ego_dot = SX.sym('v_ego_dot')
  a_ego_dot = SX.sym('a_ego_dot')
  model.xdot = vertcat(x_ego_dot, v_ego_dot, a_ego_dot)

  # runtime parameters
  a_min = SX.sym('a_min')
  a_max = SX.sym('a_max')
  x_obstacle = SX.sym('x_obstacle')
  a_prev = SX.sym('a_prev')
  lead_t_follow = SX.sym('lead_t_follow')
  lead_danger_factor = SX.sym('lead_danger_factor')
  model.p = vertcat(a_min, a_max, x_obstacle, a_prev, lead_t_follow, lead_danger_factor)

  # dynamics model
  f_expl = vertcat(v_ego, a_ego, j_ego)
  model.f_impl_expr = model.xdot - f_expl
  model.f_expl_expr = f_expl
  return model

def gen_long_ocp():
  ocp = AcadosOcp()
  ocp.model = gen_long_model()

  Tf = T_IDXS[-1]

  # set dimensions
  ocp.dims.N = N

  # set cost module
  ocp.cost.cost_type = 'NONLINEAR_LS'
  ocp.cost.cost_type_e = 'NONLINEAR_LS'

  QR = np.zeros((COST_DIM, COST_DIM))
  Q = np.zeros((COST_E_DIM, COST_E_DIM))

  ocp.cost.W = QR
  ocp.cost.W_e = Q

  x_ego, v_ego, a_ego = ocp.model.x[0], ocp.model.x[1], ocp.model.x[2]
  j_ego = ocp.model.u[0]

  a_min, a_max = ocp.model.p[0], ocp.model.p[1]
  x_obstacle = ocp.model.p[2]
  a_prev = ocp.model.p[3]
  lead_t_follow = ocp.model.p[4]
  lead_danger_factor = ocp.model.p[5]

  ocp.cost.yref = np.zeros((COST_DIM, ))
  ocp.cost.yref_e = np.zeros((COST_E_DIM, ))

  desired_dist_comfort = get_safe_obstacle_distance(v_ego, lead_t_follow)

  # The main cost in normal operation is how close you are to the "desired" distance
  # from an obstacle at every timestep. This obstacle can be a lead car
  # or other object. In e2e mode we can use x_position targets as a cost
  # instead.
  costs = [((x_obstacle - x_ego) - (desired_dist_comfort)) / (v_ego + 10.),
           x_ego,
           v_ego,
           a_ego,
           a_ego - a_prev,
           j_ego]
  ocp.model.cost_y_expr = vertcat(*costs)
  ocp.model.cost_y_expr_e = vertcat(*costs[:-1])

  # Constraints on speed, acceleration and desired distance to
  # the obstacle, which is treated as a slack constraint so it
  # behaves like an asymmetrical cost.
  constraints = vertcat(v_ego,
                        (a_ego - a_min),
                        (a_max - a_ego),
                        ((x_obstacle - x_ego) - lead_danger_factor * (desired_dist_comfort)) / (v_ego + 10.))
  ocp.model.con_h_expr = constraints
  # The terminal stage needs the same soft constraint, or the solver can
  # overrun it when it is stopped early (ported from StarPilot e75470f2e).
  ocp.model.con_h_expr_e = constraints

  x0 = np.zeros(X_DIM)
  ocp.constraints.x0 = x0
  ocp.parameter_values = np.array([-1.2, 1.2, 0.0, 0.0, get_T_FOLLOW(), LEAD_DANGER_FACTOR])


  # We put all constraint cost weights to 0 and only set them at runtime
  cost_weights = np.zeros(CONSTR_DIM)
  ocp.cost.zl = cost_weights
  ocp.cost.Zl = cost_weights
  ocp.cost.Zu = cost_weights
  ocp.cost.zu = cost_weights
  ocp.cost.zl_e = cost_weights
  ocp.cost.Zl_e = cost_weights
  ocp.cost.Zu_e = cost_weights
  ocp.cost.zu_e = cost_weights

  ocp.constraints.lh = np.zeros(CONSTR_DIM)
  ocp.constraints.uh = 1e4*np.ones(CONSTR_DIM)
  ocp.constraints.idxsh = np.arange(CONSTR_DIM)
  ocp.constraints.lh_e = np.zeros(CONSTR_DIM)
  ocp.constraints.uh_e = 1e4*np.ones(CONSTR_DIM)
  ocp.constraints.idxsh_e = np.arange(CONSTR_DIM)

  # The HPIPM solver can give decent solutions even when it is stopped early
  # Which is critical for our purpose where compute time is strictly bounded
  # We use HPIPM in the SPEED_ABS mode, which ensures fastest runtime. This
  # does not cause issues since the problem is well bounded.
  ocp.solver_options.qp_solver = 'PARTIAL_CONDENSING_HPIPM'
  ocp.solver_options.hessian_approx = 'GAUSS_NEWTON'
  ocp.solver_options.integrator_type = 'ERK'
  ocp.solver_options.nlp_solver_type = ACADOS_SOLVER_TYPE
  ocp.solver_options.qp_solver_cond_N = 1

  # More iterations take too much time and less lead to inaccurate convergence in
  # some situations. Ideally we would run just 1 iteration to ensure fixed runtime.
  ocp.solver_options.qp_solver_iter_max = 10
  ocp.solver_options.qp_tol = 1e-3

  # set prediction horizon
  ocp.solver_options.tf = Tf
  ocp.solver_options.shooting_nodes = T_IDXS

  ocp.code_export_directory = EXPORT_DIR
  return ocp


class LongitudinalMpc:
  def __init__(self, dt=DT_MDL):
    self.dt = dt
    self.solver = AcadosOcpSolverCython(MODEL_NAME, ACADOS_SOLVER_TYPE, N)
    self._read_live_tuning(Params())
    # Dynamic comfort-brake / stop-distance overrides (set per-call by the
    # CarrotPlanner longitudinal source). They default to the module-level
    # values baked at import, so stock behavior is unchanged unless explicitly
    # overridden. NOTE: these do NOT change PARAM_DIM or rebuild the solver.
    self.comfort_brake = COMFORT_BRAKE
    # Carrot lead gap / braking gap state (default off; see update's gap flags).
    # The margins stay all-zero unless a caller opts in, and braking_gap_reference
    # with zero margins reproduces the previous yref[:,0] exactly.
    self.lead_gap_states = (LeadGapState(), LeadGapState())
    self.lead_comfort_states = (LeadComfortState(), LeadComfortState())
    self.lead_gap_margins = np.zeros((N+1, 2))
    self.base_desired_distances = np.zeros(2)
    self.desired_distance = 0.0
    # StarPilot duplicate-vision comfort filters (used only when the planner
    # passes smooth_duplicate_vision=True for a qualified non-urgent pair).
    self.duplicate_lead_filters = DuplicateVisionLeadFilters(self.dt)
    self.reset()
    self.source = LongitudinalPlanSource.cruise

  def _read_live_tuning(self, p: Params):
    # MPC tuning (no solver rebuild needed): cost weights, follow time and lead danger factor.
    self.t_follow_relaxed = _read_tuning_float(p, "LongitudinalMpcTuningTFollowRelaxed", 1.75)
    self.t_follow_standard = _read_tuning_float(p, "LongitudinalMpcTuningTFollowStandard", 1.45)
    self.t_follow_aggressive = _read_tuning_float(p, "LongitudinalMpcTuningTFollowAggressive", 1.25)
    self.x_ego_obstacle_cost = _read_tuning_float(p, "LongitudinalMpcTuningXEgoObstacleCost", X_EGO_OBSTACLE_COST)
    self.j_ego_cost = _read_tuning_float(p, "LongitudinalMpcTuningJEgoCost", J_EGO_COST)
    self.a_change_cost = _read_tuning_float(p, "LongitudinalMpcTuningAChangeCost", A_CHANGE_COST)
    self.danger_zone_cost = _read_tuning_float(p, "LongitudinalMpcTuningDangerZoneCost", DANGER_ZONE_COST)
    self.lead_danger_factor = _read_tuning_float(p, "LongitudinalMpcTuningLeadDangerFactor", LEAD_DANGER_FACTOR)

    # StarPilot speed-dependent following profiles. The document is read once
    # here because Params.get() must stay out of the planning loop; the curve
    # itself is interpolated per frame from this cached copy.
    self.following_profile = None
    if read_bool(p, "LongitudinalFollowingProfileEnabled"):
      raw = read_str(p, "LongitudinalFollowingProfile")
      self.following_profile = load_profile_document(raw) or None

  def get_t_follow(self, personality=log.LongitudinalPersonality.standard, v_ego=None):
    """Follow time for a personality.

    With a speed-dependent profile configured, the value is interpolated at
    the current speed; otherwise the stock per-personality scalar is used.
    The speed is optional so that the callers which have no speed handy (the
    user-scale helper) keep the scalar behaviour.
    """
    if v_ego is not None and self.following_profile:
      key = personality_key(personality)
      if key is not None:
        value = t_follow_for_personality(self.following_profile, key, v_ego)
        if value is not None:
          return value

    if personality == log.LongitudinalPersonality.relaxed:
      return self.t_follow_relaxed
    elif personality == log.LongitudinalPersonality.standard:
      return self.t_follow_standard
    elif personality == log.LongitudinalPersonality.aggressive:
      return self.t_follow_aggressive
    else:
      raise NotImplementedError("Longitudinal personality not supported")

  def leads_are_near_duplicates(self, lead_one, lead_two, v_ego, *, vision_min_speed=None):
    """Expose the duplicate-lead detector for lead_follow_policy and tests."""
    from openpilot.selfdrive.controls.lib.lead_duplicate_policy import leads_are_near_duplicates
    return leads_are_near_duplicates(lead_one, lead_two, v_ego, vision_min_speed=vision_min_speed)

  def t_follow_user_scale(self, personality=log.LongitudinalPersonality.standard, v_ego=None) -> float:
    """How far the follow time moved from its default (1.0 = untouched).

    The Carrot longitudinal source multiplies its own modulated follow time by
    this, so the Longitudinal MPC Tuning entry stays authoritative even while the
    Carrot source is active - without changing behaviour for anyone who has left
    the tuning at its default.

    With a speed-dependent profile configured the baseline is the profile's
    value at the current speed instead of the scalar tuning value, so the
    Carrot path and the stock path end up with the same gap character. The
    ratio is taken against the built-in default, which keeps the meaning of
    the scale identical in both cases.
    """
    default = T_FOLLOW_DEFAULTS.get(personality)
    if not default:
      return 1.0

    if v_ego is not None and self.following_profile:
      key = personality_key(personality)
      if key is not None:
        profile_value = t_follow_for_personality(self.following_profile, key, v_ego)
        if profile_value is not None:
          return profile_value / default

    return self.get_t_follow(personality) / default

  def reset(self):
    self.solver.reset()

    self.x_sol = np.zeros((N+1, X_DIM))
    self.u_sol = np.zeros((N, 1))
    self.v_solution = np.zeros(N+1)
    self.a_solution = np.zeros(N+1)
    self.j_solution = np.zeros(N)
    self.a_prev = np.array(self.a_solution)
    self.yref = np.zeros((N+1, COST_DIM))

    for i in range(N):
      self.solver.cost_set(i, "yref", self.yref[i])
    self.solver.cost_set(N, "yref", self.yref[N][:COST_E_DIM])

    self.params = np.zeros((N+1, PARAM_DIM))
    for i in range(N+1):
      self.solver.set(i, 'x', np.zeros(X_DIM))

    self.last_cloudlog_t = 0
    self.crash_cnt = 0.0
    self.solution_status = 0
    # timers
    self.solve_time = 0.0
    self.x0 = np.zeros(X_DIM)
    self.lead_0_obstacle = None
    self.lead_1_obstacle = None
    if getattr(self, 'duplicate_lead_filters', None) is not None:
      self.duplicate_lead_filters.invalidate()
    if getattr(self, 'lead_gap_states', None) is not None:
      self.lead_gap_margins = np.zeros((N+1, 2))
    self.set_weights()

  def set_cost_weights(self, cost_weights, constraint_cost_weights):
    W = np.asfortranarray(np.diag(cost_weights))
    for i in range(N):
      W[4,4] = cost_weights[4] * A_CHANGE_FACTORS[i]
      self.solver.cost_set(i, 'W', W)
    # Setting the slice without the copy make the array not contiguous,
    # causing issues with the C interface.
    self.solver.cost_set(N, 'W', np.copy(W[:COST_E_DIM, :COST_E_DIM]))

    # Set L2 slack cost on lower bound constraints
    Zl = np.array(constraint_cost_weights)
    for i in range(N+1):
      self.solver.cost_set(i, 'Zl', Zl)

  def set_weights(self, prev_accel_constraint=True, personality=log.LongitudinalPersonality.standard, jerk_factor=None):
    if jerk_factor is None:
      jerk_factor = get_jerk_factor(personality)
    a_change_cost = self.a_change_cost if prev_accel_constraint else 0
    cost_weights = [self.x_ego_obstacle_cost, X_EGO_COST, V_EGO_COST, A_EGO_COST, jerk_factor * a_change_cost, jerk_factor * self.j_ego_cost]
    constraint_cost_weights = [LIMIT_COST, LIMIT_COST, LIMIT_COST, self.danger_zone_cost]
    self.set_cost_weights(cost_weights, constraint_cost_weights)

  def set_cur_state(self, v, a):
    v_prev = self.x0[1]
    self.x0[1] = v
    self.x0[2] = a
    if abs(v_prev - v) > 2.:  # probably only helps if v < v_prev
      for i in range(N+1):
        self.solver.set(i, 'x', self.x0)

  @staticmethod
  def extrapolate_lead(x_lead, v_lead, a_lead, a_lead_tau):
    a_lead_traj = a_lead * np.exp(-a_lead_tau * (T_IDXS**2)/2.)
    v_lead_traj = np.clip(v_lead + np.cumsum(T_DIFFS * a_lead_traj), 0.0, 1e8)
    x_lead_traj = x_lead + np.cumsum(T_DIFFS * v_lead_traj)
    lead_xv = np.column_stack((x_lead_traj, v_lead_traj))
    return lead_xv

  def process_lead(self, lead, lead_index=0, model_lead=None, smooth_duplicate_vision=False):
    v_ego = self.x0[1]
    lead_active = lead is not None and lead.present

    # StarPilot model-lead trajectory: the model contributes future deltas on
    # top of the raw h=0 anchor. Activated only when the planner passes a
    # model_lead (gated by ModelLeadTrajectoryEnabled); otherwise the raw path
    # below runs unchanged.
    if lead_active and model_lead is not None:
      model_lead_xv = build_model_lead_trajectory(model_lead, lead, v_ego, T_IDXS)
      if model_lead_xv is not None:
        # Keep duplicate filters invalidated so leaving this path later
        # cannot introduce a state discontinuity.
        self.duplicate_lead_filters.invalidate(lead_index)
        return model_lead_xv

    if lead_active:
      x_lead = lead.dRel
      v_lead = lead.vLead
      a_lead = lead.aLeadK
      a_lead_tau = lead.aLeadTau
    else:
      # Fake a fast lead car, so mpc can keep running in the same mode
      x_lead = 50.0
      v_lead = v_ego + 10.0
      a_lead = 0.0
      a_lead_tau = _LEAD_ACCEL_TAU

    # MPC will not converge if immediate crash is expected
    # Clip lead distance to what is still possible to brake for
    min_x_lead = MIN_X_LEAD_FACTOR * (v_ego + v_lead) * (v_ego - v_lead) / (-ACCEL_MIN * 2)
    x_lead = np.clip(x_lead, min_x_lead, 1e8)
    v_lead = np.clip(v_lead, 0.0, 1e8)
    a_lead = np.clip(a_lead, -10., 5.)

    # StarPilot duplicate-vision comfort smoothing: only for a qualified
    # non-urgent vision duplicate pair (planner-decided). Ratcheted distance
    # filter lets closers through instantly; outside the scene the filters
    # invalidate so the raw path is preserved bit-for-bit.
    if lead_active and smooth_duplicate_vision and not bool(getattr(lead, "radar", False)):
      x_lead, v_lead, a_lead = self.duplicate_lead_filters.apply(lead_index, float(x_lead), float(v_lead), float(a_lead))
      x_lead = np.clip(x_lead, min_x_lead, 1e8)
      v_lead = np.clip(v_lead, 0.0, 1e8)
      a_lead = np.clip(a_lead, -10., 5.)
    else:
      self.duplicate_lead_filters.invalidate(lead_index)
    lead_xv = self.extrapolate_lead(x_lead, v_lead, a_lead, a_lead_tau)
    return lead_xv

  def update(self, radarstate, personality=log.LongitudinalPersonality.standard, *, t_follow=None, jerk_factor=None,
              comfort_brake=None, stop_obstacle_distance=0.0, lane_change_credit=None,
              reset_state=False, lead_gap_enabled=False, lead_comfort_enabled=False,
              cutout_relief_enabled=False, lead_accel_response=0, lane_change_active=False,
              model_leads=None, duplicate_guard_enabled=False, panic_bypass=False, v_ego=None):
    # StarPilot additions (all default off -> stock path byte-identical):
    # - model_leads: leadsV3 pair; enables the model-trajectory future-delta path
    #   and the enhanced planner-FCW gate (ModelLeadTrajectoryEnabled).
    # - duplicate_guard_enabled: near-duplicate source hysteresis + identical
    #   radar-track source hold (LeadDuplicateGuardEnabled).
    # - panic_bypass: uncertainty panic gate, forces raw lead path for this frame.
    # Carrot gap/comfort refinements (all default off). lead_gap_enabled adds an
    # opening-gap TF margin, lead_comfort_enabled a bounded comfort slack, and
    # cutout_relief_enabled eases the demand for a confirmed cut-out. With every
    # flag off the margins stay zero and braking_gap_reference returns exactly
    # the previous yref[:,0], so the stock solver input is unchanged.
    # Tuning is read once in __init__, never here. Params.get() is a filesystem read that
    # measures 111 us/key on a tizi, and its tail latency is unbounded when loggerd or the
    # uploader are busy -- not something to put in the planning loop. plannerd only runs
    # onroad, so edits made while parked take effect on the next drive.
    # StarPilot speed-dependent following profile: when one is configured the
    # follow time is interpolated at the current speed instead of being a
    # single number per personality. The document itself was read in
    # __init__; only the interpolation happens here.
    t_follow = self.get_t_follow(personality, v_ego) if t_follow is None else float(t_follow)
    if jerk_factor is not None:
      jerk_factor = float(jerk_factor)

    # Optional dynamic override from the CarrotPlanner longitudinal source. This only
    # changes the runtime obstacle-distance math; it does NOT touch PARAM_DIM or
    # rebuild the solver. There is deliberately no stop_distance override: the solver
    # bakes STOP_DISTANCE in at codegen (see gen_long_ocp), so a runtime value could
    # never take effect.
    self.comfort_brake = float(comfort_brake) if comfort_brake is not None else COMFORT_BRAKE

    # StarPilot duplicate-vision comfort smoothing only wires for a qualified
    # non-urgent vision duplicate pair, decided on the raw leads before any
    # filtering. Panic frames bypass it entirely.
    from openpilot.selfdrive.controls.lib.lead_follow_policy import is_nonurgent_duplicate_vision_follow
    smooth_dup_vision = bool(
      duplicate_guard_enabled and not panic_bypass and
      is_nonurgent_duplicate_vision_follow(
        radarstate.leadOne, radarstate.leadTwo, float(self.x0[1]), float(t_follow), self,
      )
    )
    # Panic frames trust raw measurements only: the model trajectory is a
    # comfort prediction and must not delay the braking response.
    model_leads_eff = None if panic_bypass else model_leads

    lead_xv_0 = self.process_lead(radarstate.leadOne, lead_index=0,
                                  model_lead=model_leads_eff[0] if model_leads_eff else None,
                                  smooth_duplicate_vision=smooth_dup_vision)
    lead_xv_1 = self.process_lead(radarstate.leadTwo, lead_index=1,
                                  model_lead=model_leads_eff[1] if model_leads_eff else None,
                                  smooth_duplicate_vision=smooth_dup_vision)

    # To estimate a safe distance from a moving lead, we calculate how much stopping
    # distance that lead needs as a minimum. We can add that to the current distance
    # and then treat that as a stopped car/obstacle at this new distance.
    lead_0_obstacle = lead_xv_0[:,0] + get_stopped_equivalence_factor(lead_xv_0[:,1], self.comfort_brake)
    lead_1_obstacle = lead_xv_1[:,0] + get_stopped_equivalence_factor(lead_xv_1[:,1], self.comfort_brake)

    # Lane-change gap credit: when an active lane change has a confirmed clear gap,
    # the tracker's credit (meters, per horizon) is added to the primary lead
    # obstacle so the MPC may permit a bounded ACC departure. Guards inside
    # LaneChangeGapPlan.credit() already gate on confidence / clearance / speed.
    if lane_change_credit is not None:
      lead_0_obstacle = lead_0_obstacle + np.asarray(lane_change_credit, dtype=float)
    # Carrot cut-out relief (default off): bounded future headway relief for a
    # measured lead predicted to leave the lane. Eases the demand after the
    # predicted clearance; never deletes the obstacle or changes the range.
    elif cutout_relief_enabled and not reset_state and radarstate.leadOne.present:
      lead_0_obstacle = lead_0_obstacle + cutout_obstacle_relief(
        radarstate.leadOne, float(self.x0[1]), T_IDXS, t_follow, STOP_DISTANCE,
      )

    # The MPC source is chosen from the real radar leads only.
    # StarPilot duplicate-lead guard (default off): hysteresis bias keeps the
    # tracked source sticky between near-duplicate leads; an identical radar
    # track holds the source while the two obstacle profiles stay close. The
    # bias folds into the real obstacles (as upstream StarPilot) so the argmin
    # and the solver's min-constraint stay consistent.
    if duplicate_guard_enabled:
      prev_source_str = {LongitudinalPlanSource.lead0: "lead0",
                         LongitudinalPlanSource.lead1: "lead1"}.get(self.source)
      lead0_bias, lead1_bias = near_duplicate_lead_source_hysteresis(
        prev_source_str, radarstate.leadOne, radarstate.leadTwo, float(self.x0[1]))
      lead_0_obstacle = lead_0_obstacle + lead0_bias
      lead_1_obstacle = lead_1_obstacle + lead1_bias

    lead_obstacles = np.column_stack([lead_0_obstacle, lead_1_obstacle])
    candidate = MPC_SOURCES[np.argmin(lead_obstacles[0])]
    sticky = None
    if duplicate_guard_enabled and candidate in (LongitudinalPlanSource.lead0, LongitudinalPlanSource.lead1):
      prev_source_str = {LongitudinalPlanSource.lead0: "lead0",
                         LongitudinalPlanSource.lead1: "lead1"}.get(self.source)
      if prev_source_str is not None:
        sticky = identical_radar_duplicate_source_hold(
          prev_source_str, radarstate.leadOne, radarstate.leadTwo,
          float(lead_obstacles[0, 0]), float(lead_obstacles[0, 1]))
    if sticky == "lead1":
      self.source = LongitudinalPlanSource.lead1
    elif sticky == "lead0":
      self.source = LongitudinalPlanSource.lead0
    else:
      self.source = candidate

    # A virtual stop obstacle (planned stop point) may be injected when the
    # CarrotPlanner is commanding a stop at a known distance. It is folded into
    # the safety floor via the min() over all obstacles.
    obstacles = [lead_0_obstacle, lead_1_obstacle]
    if stop_obstacle_distance and stop_obstacle_distance > 0:
      obstacles.append(np.full(N + 1, float(stop_obstacle_distance)))
    x_obstacles = np.column_stack(obstacles)

    # Expose the per-lead obstacles for upstream stop-obstacle blending.
    self.lead_0_obstacle = lead_0_obstacle
    self.lead_1_obstacle = lead_1_obstacle

    # Carrot gap/comfort margins (default zero). Computed against the previous
    # solution's speed profile; the margins only shift the comfort reference in
    # yref[:,0] and never modify physical obstacles or the danger constraint.
    v_ego_now = float(self.x0[1])
    gap_v = np.maximum(0.0, self.x_sol[:,1] + v_ego_now - self.x_sol[0,1])
    gap_x = np.cumsum(T_DIFFS * np.concatenate(([gap_v[0]], (gap_v[1:] + gap_v[:-1]) * 0.5)))
    self.lead_gap_margins[:] = 0.0
    comfort_reliefs = np.zeros_like(self.lead_gap_margins)
    self.base_desired_distances = np.array([
      desired_follow_distance(v_ego_now, float(lead_xv_0[0,1]), self.comfort_brake, STOP_DISTANCE, t_follow),
      desired_follow_distance(v_ego_now, float(lead_xv_1[0,1]), self.comfort_brake, STOP_DISTANCE, t_follow),
    ])
    for lead_index, (lead, lead_xv) in enumerate(((radarstate.leadOne, lead_xv_0), (radarstate.leadTwo, lead_xv_1))):
      eligible = (lead_gap_enabled and not reset_state and not lane_change_active
                  and lead.present and getattr(lead, 'radar', False))
      if not eligible:
        continue
      physical_gaps = lead_xv[:,0] - gap_x
      desired_distances = desired_follow_distance(
        gap_v, lead_xv[:,1], self.comfort_brake, STOP_DISTANCE, t_follow)
      state = self.lead_gap_states[lead_index]
      state.update(level=lead_accel_response, track_id=int(lead.radarTrackId), enabled=True, dt=self.dt,
                   ego_speed=v_ego_now, lead_speed=float(lead.vLead), relative_speed=float(lead.vRel),
                   distance=float(lead.dRel), desired_distance=float(self.base_desired_distances[lead_index]),
                   base_tf=t_follow, stop_distance=STOP_DISTANCE)
      self.lead_gap_margins[:,lead_index] = state.margins(
        level=lead_accel_response, times=T_IDXS, ego_speeds=gap_v, lead_speeds=lead_xv[:,1], base_tf=t_follow,
        lead_distances=physical_gaps, desired_distances=desired_distances, stop_distance=STOP_DISTANCE)
      if lead_comfort_enabled:
        comfort = self.lead_comfort_states[lead_index]
        comfort.update(enabled=True, track_id=int(lead.radarTrackId), dt=self.dt,
                       distance=float(lead.dRel), relative_speed=float(lead.vRel))
        danger = lead_xv[:,0] + get_stopped_equivalence_factor(lead_xv[:,1], self.comfort_brake) \
                 - gap_x - self.lead_danger_factor * get_safe_obstacle_distance(gap_v, t_follow, self.comfort_brake, STOP_DISTANCE)
        relief = comfort.comfort_relief(dt=self.dt, enabled=self.lead_gap_margins[0,lead_index] <= 0.01,
                                        base_tf=t_follow, ego_speeds=gap_v, lead_speeds=lead_xv[:,1],
                                        lead_accel=float(lead.aLeadK), physical_gaps=physical_gaps,
                                        danger_margins=danger, times=T_IDXS, stop_distance=STOP_DISTANCE)
        self.lead_gap_margins[:,lead_index] -= relief
        comfort_reliefs[:,lead_index] = relief
    self.desired_distance = displayed_follow_distance(
      self.base_desired_distances, np.array([lead_0_obstacle[0], lead_1_obstacle[0]]),
      x_obstacles[0, :2], self.lead_gap_margins[0],
      (radarstate.leadOne.present, radarstate.leadTwo.present))

    self.yref[:,:] = 0.0
    self.yref[:,0] = braking_gap_reference(x_obstacles, self.lead_gap_margins, gap_v)
    for i in range(N):
      self.solver.set(i, "yref", self.yref[i])
    self.solver.set(N, "yref", self.yref[N][:COST_E_DIM])

    self.params[:,0] = ACCEL_MIN
    self.params[:,1] = ACCEL_MAX
    self.params[:,2] = np.min(x_obstacles, axis=1)
    self.params[:,3] = np.copy(self.a_prev)
    self.params[:,4] = t_follow
    self.params[:,5] = self.lead_danger_factor

    self.run()
    # Carrot comfort-slack safety check (only when a comfort relief was applied).
    # The trial trajectory is validated; if it spends the reserve the margins are
    # restored and the solve repeats without slack. Never relaxes a danger edge.
    if np.any(comfort_reliefs) and self.solution_status == 0:
      safe = get_safe_obstacle_distance(self.x_sol[:,1], t_follow, self.comfort_brake, STOP_DISTANCE)
      reserve_ok = all(
        not np.any(comfort_reliefs[:, i]) or comfort_path_has_reserve(
          self.x_sol[:,1], lead_xv[:,0] - self.x_sol[:,0],
          obstacle - self.x_sol[:,0] - self.params[:,5] * safe, T_IDXS, STOP_DISTANCE)
        for i, (lead_xv, obstacle) in enumerate(((lead_xv_0, lead_0_obstacle), (lead_xv_1, lead_1_obstacle)))
      )
      if not reserve_ok:
        self.lead_gap_margins += comfort_reliefs
        self.yref[:,0] = braking_gap_reference(x_obstacles, self.lead_gap_margins, gap_v)
        for i in range(N):
          self.solver.set(i, "yref", self.yref[i])
        self.solver.set(N, "yref", self.yref[N][:COST_E_DIM])
        self.desired_distance = displayed_follow_distance(
          self.base_desired_distances, np.array([lead_0_obstacle[0], lead_1_obstacle[0]]),
          x_obstacles[0, :2], self.lead_gap_margins[0],
          (radarstate.leadOne.present, radarstate.leadTwo.present))
        self.run()

    # Enhanced planner-FCW gate (StarPilot): adds closing-speed + TTC windows
    # on top of modelProb, so a distant or pace-matched lead cannot inflate
    # crash_cnt. Gated with ModelLeadTrajectoryEnabled (same feature family).
    if model_leads is not None:
      fcw_trigger = should_trigger_planner_fcw(radarstate.leadOne, float(self.x0[1]))
    else:
      fcw_trigger = radarstate.leadOne.present and radarstate.leadOne.modelProb > 0.9
    if (np.any(lead_xv_0[FCW_IDXS,0] - self.x_sol[FCW_IDXS,0] < CRASH_DISTANCE) and
            fcw_trigger):
      self.crash_cnt += 1
    else:
      self.crash_cnt = 0

  def run(self):
    for i in range(N+1):
      self.solver.set(i, 'p', self.params[i])
    self.solver.constraints_set(0, "lbx", self.x0)
    self.solver.constraints_set(0, "ubx", self.x0)

    self.solution_status = self.solver.solve()
    self.solve_time = float(self.solver.get_stats('time_tot')[0])

    for i in range(N+1):
      self.x_sol[i] = self.solver.get(i, 'x')
    for i in range(N):
      self.u_sol[i] = self.solver.get(i, 'u')

    self.v_solution = self.x_sol[:,1]
    self.a_solution = self.x_sol[:,2]
    self.j_solution = self.u_sol[:,0]

    self.a_prev = np.interp(T_IDXS + self.dt, T_IDXS, self.a_solution)

    t = time.monotonic()
    if self.solution_status != 0:
      if t > self.last_cloudlog_t + 5.0:
        self.last_cloudlog_t = t
        cloudlog.warning(f"Long mpc reset, solution_status: {self.solution_status}")
      self.reset()


if __name__ == "__main__":
  ocp = gen_long_ocp()
  AcadosOcpSolver.generate(ocp, json_file=JSON_FILE)
