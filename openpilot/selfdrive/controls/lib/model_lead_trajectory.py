#!/usr/bin/env python3
"""Model-predicted lead trajectory with raw h=0 anchor (StarPilot port).

The model's lead trajectory is a comfort prediction, not the raw safety
measurement. This builder converts it into MPC-ready (x, v) columns by
contributing only future deltas on top of the raw measured anchor:

    x_lead_traj = dRel + (model_x - model_x[0])
    v_lead_traj = vLead + (model_v - model_v[0])

so raw lead source selection and the h=0 safety anchor stay intact. When the
measured lead is already braking hard or the gap is closing fast, the raw
path wins (returns None) so an optimistic model horizon cannot delay the
first braking response.

Pure logic only -- numpy + modeld constants, safe to import on a PC host.
"""
import numpy as np

from openpilot.selfdrive.modeld.constants import ModelConstants

# StarPilot verbatim constants
FCW_MIN_MODEL_PROB = 0.9
FCW_MIN_CLOSING_SPEED = 0.5
FCW_MAX_TTC = 4.0
MODEL_LEAD_TRAJECTORY_MAX_LEAD_BRAKE = 0.5
MODEL_LEAD_TRAJECTORY_MAX_CLOSING_TTC = 7.0

LEAD_T_IDXS_MODEL = np.asarray(ModelConstants.LEAD_T_IDXS, dtype=np.float64)

# Physical brake limit used for the MPC convergence guard. Equals upstream
# ACCEL_MIN (opendbc default); kept as a literal so this module stays free of
# the opendbc.car.interfaces import chain on PC test hosts.
ACCEL_MIN_PHYSICAL = -3.5


def build_model_lead_trajectory(model_lead, radar_lead, v_ego, t_idxs):
  """Build a model-predicted lead path while preserving the raw h=0 anchor.

  model_lead: leadsV3 entry (x/v arrays over LEAD_T_IDXS + prob), or None.
  radar_lead: raw radarState lead for the same track (status/present, dRel,
    vLead, aLeadK), or None.
  t_idxs: MPC horizon time points (long_mpc T_IDXS, shape (N+1,)).
  Returns an (N+1, 2) float array of (x_lead_mpc, v_lead_mpc) or None.
  """
  if model_lead is None or radar_lead is None or not (
    bool(getattr(radar_lead, "present", False)) or bool(getattr(radar_lead, "status", False))
  ):
    return None

  try:
    if float(model_lead.prob) <= 0.5:
      return None
    model_x = np.asarray(model_lead.x, dtype=np.float64)
    model_v = np.asarray(model_lead.v, dtype=np.float64)
  except (AttributeError, TypeError, ValueError):
    return None

  expected_len = len(LEAD_T_IDXS_MODEL)
  if model_x.shape != (expected_len,) or model_v.shape != (expected_len,):
    return None
  if not np.all(np.isfinite(model_x)) or not np.all(np.isfinite(model_v)):
    return None

  raw_d_rel = float(getattr(radar_lead, "dRel", float("nan")))
  raw_v_lead = float(getattr(radar_lead, "vLead", float("nan")))
  if not np.isfinite(raw_d_rel) or not np.isfinite(raw_v_lead):
    return None

  # When the measured lead is already braking or the gap is closing quickly,
  # keep the legacy raw-lead path so an optimistic model horizon cannot delay
  # the first braking response.
  raw_lead_brake = max(0.0, -float(getattr(radar_lead, "aLeadK", 0.0)))
  closing_speed = max(0.0, float(v_ego) - raw_v_lead)
  ttc = raw_d_rel / max(closing_speed, 1e-3) if closing_speed > 0.1 else float("inf")
  if (raw_lead_brake > MODEL_LEAD_TRAJECTORY_MAX_LEAD_BRAKE or
      (closing_speed > 0.75 and ttc < MODEL_LEAD_TRAJECTORY_MAX_CLOSING_TTC)):
    return None

  # The model contributes future deltas only. This preserves raw lead source
  # selection and keeps the current lead distance/speed safety anchor intact.
  x_lead_traj = raw_d_rel + (model_x - model_x[0])
  v_lead_traj = raw_v_lead + (model_v - model_v[0])
  v_lead_traj = np.clip(v_lead_traj, 0.0, 1e8)

  # Match the existing MPC convergence guard using the physical brake limit.
  v_ego = float(v_ego)
  min_x_lead = ((v_ego + v_lead_traj[0]) / 2.0) * (v_ego - v_lead_traj[0]) / (-ACCEL_MIN_PHYSICAL * 2.0)
  x_lead_traj[0] = max(x_lead_traj[0], min_x_lead)

  t_idxs = np.asarray(t_idxs, dtype=np.float64)
  x_lead_mpc = np.maximum.accumulate(np.interp(t_idxs, LEAD_T_IDXS_MODEL, x_lead_traj))
  v_lead_mpc = np.interp(t_idxs, LEAD_T_IDXS_MODEL, v_lead_traj)
  return np.column_stack((x_lead_mpc, v_lead_mpc))


def should_trigger_planner_fcw(lead, v_ego) -> bool:
  """Enhanced planner-FCW gate: closing-speed + TTC windows on top of modelProb."""
  if lead is None or not (bool(getattr(lead, "present", False)) or bool(getattr(lead, "status", False))
                          ) or float(getattr(lead, "modelProb", 0.0)) <= FCW_MIN_MODEL_PROB:
    return False

  closing_speed = max(0.0, float(v_ego) - float(getattr(lead, "vLead", 0.0)))
  if closing_speed < FCW_MIN_CLOSING_SPEED:
    return False

  ttc = max(0.0, float(getattr(lead, "dRel", 0.0))) / max(closing_speed, 1e-3)
  return ttc < FCW_MAX_TTC
