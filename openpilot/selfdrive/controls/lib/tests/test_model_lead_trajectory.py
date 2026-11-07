"""Pure-logic unit tests for the StarPilot model-lead trajectory port.

Covers the raw-anchor future-delta construction, the safety guards (braking
lead, fast closing TTC, non-finite input) and the enhanced planner-FCW gate.
"""
import unittest
from types import SimpleNamespace

import numpy as np

from openpilot.selfdrive.controls.lib.model_lead_trajectory import (
  FCW_MIN_CLOSING_SPEED,
  FCW_MIN_MODEL_PROB,
  MODEL_LEAD_TRAJECTORY_MAX_LEAD_BRAKE,
  build_model_lead_trajectory,
  should_trigger_planner_fcw,
)
from openpilot.selfdrive.modeld.constants import ModelConstants

# MPC horizon (long_mpc T_IDXS): 12 points over 10s
T_IDXS = np.array([10.0 * (i / 12) ** 2 for i in range(13)])
N_LEAD = len(ModelConstants.LEAD_T_IDXS)


def make_model_lead(x0=50.0, v0=20.0, decel=0.0, prob=0.9):
  t = np.asarray(ModelConstants.LEAD_T_IDXS, dtype=np.float64)
  v = v0 + decel * t
  x = x0 + np.cumsum(np.concatenate(([0.0], (v[1:] + v[:-1]) / 2.0 * np.diff(t))))
  return SimpleNamespace(x=x, v=v, prob=prob)


def make_radar(d_rel=50.0, v_lead=20.0, a_lead=0.0, present=True):
  return SimpleNamespace(present=present, status=present, dRel=d_rel, vLead=v_lead, aLeadK=a_lead)


class TestBuildModelLeadTrajectory(unittest.TestCase):
  def test_anchor_preserved(self):
    traj = build_model_lead_trajectory(make_model_lead(x0=60.0, v0=25.0),
                                       make_radar(d_rel=50.0, v_lead=20.0), 20.0, T_IDXS)
    self.assertIsNotNone(traj)
    # h=0 stays on the raw measurement, not the model's absolute prediction
    self.assertAlmostEqual(traj[0, 0], 50.0, places=6)
    self.assertAlmostEqual(traj[0, 1], 20.0, places=6)

  def test_future_delta_only(self):
    model = make_model_lead(x0=60.0, v0=25.0)
    traj = build_model_lead_trajectory(model, make_radar(d_rel=50.0, v_lead=20.0), 20.0, T_IDXS)
    # v trajectory = raw anchor + model deltas
    model_v = np.asarray(model.v)
    expected_v_tail = 20.0 + (model_v[-1] - model_v[0])
    self.assertAlmostEqual(traj[-1, 1], expected_v_tail, places=6)

  def test_monotonic_distance(self):
    traj = build_model_lead_trajectory(make_model_lead(), make_radar(), 20.0, T_IDXS)
    self.assertTrue(np.all(np.diff(traj[:, 0]) >= 0.0))

  def test_braking_radar_lead_returns_none(self):
    model = make_model_lead()
    radar = make_radar(a_lead=-MODEL_LEAD_TRAJECTORY_MAX_LEAD_BRAKE - 0.05)
    self.assertIsNone(build_model_lead_trajectory(model, radar, 20.0, T_IDXS))

  def test_fast_closing_low_ttc_returns_none(self):
    # closing 6 m/s from 30 m -> ttc 5s < 7
    model = make_model_lead()
    radar = make_radar(d_rel=30.0, v_lead=14.0)
    self.assertIsNone(build_model_lead_trajectory(model, radar, 20.0, T_IDXS))

  def test_slow_closing_keeps_model_path(self):
    # closing 0.5 m/s from 50 m -> ttc 100s
    model = make_model_lead()
    radar = make_radar(d_rel=50.0, v_lead=19.5)
    self.assertIsNotNone(build_model_lead_trajectory(model, radar, 20.0, T_IDXS))

  def test_low_prob_returns_none(self):
    self.assertIsNone(build_model_lead_trajectory(
      make_model_lead(prob=0.45), make_radar(), 20.0, T_IDXS))

  def test_inactive_radar_returns_none(self):
    self.assertIsNone(build_model_lead_trajectory(
      make_model_lead(), make_radar(present=False), 20.0, T_IDXS))

  def test_none_inputs_return_none(self):
    self.assertIsNone(build_model_lead_trajectory(None, make_radar(), 20.0, T_IDXS))
    self.assertIsNone(build_model_lead_trajectory(make_model_lead(), None, 20.0, T_IDXS))

  def test_non_finite_model_returns_none(self):
    model = make_model_lead()
    x = np.asarray(model.x).copy()
    x[2] = float("nan")
    model.x = x
    self.assertIsNone(build_model_lead_trajectory(model, make_radar(), 20.0, T_IDXS))

  def test_wrong_length_model_returns_none(self):
    model = make_model_lead()
    model.x = np.zeros(3)
    self.assertIsNone(build_model_lead_trajectory(model, make_radar(), 20.0, T_IDXS))

  def test_output_shape(self):
    traj = build_model_lead_trajectory(make_model_lead(), make_radar(), 20.0, T_IDXS)
    self.assertEqual(traj.shape, (len(T_IDXS), 2))

  def test_min_x_convergence_guard(self):
    # anchor distance below the physical brake guard gets clamped up.
    # Slow closing (0.5 m/s) so the urgent-closing guard stays out of the way.
    v_ego, v_lead = 10.0, 9.5
    traj = build_model_lead_trajectory(
      make_model_lead(x0=0.5, v0=9.5), make_radar(d_rel=0.5, v_lead=9.5), v_ego, T_IDXS)
    self.assertIsNotNone(traj)
    min_x = ((v_ego + v_lead) / 2.0) * (v_ego - v_lead) / 7.0
    self.assertGreaterEqual(traj[0, 0], min_x - 1e-6)


class TestShouldTriggerPlannerFcw(unittest.TestCase):
  def test_triggered_when_closing_fast_close_range(self):
    # prob 0.95, closing 5 m/s, 15 m -> ttc 3s
    lead = SimpleNamespace(present=True, modelProb=0.95, dRel=15.0, vLead=10.0)
    self.assertTrue(should_trigger_planner_fcw(lead, 15.0))

  def test_low_prob_rejected(self):
    lead = SimpleNamespace(present=True, modelProb=FCW_MIN_MODEL_PROB - 0.01, dRel=15.0, vLead=10.0)
    self.assertFalse(should_trigger_planner_fcw(lead, 15.0))

  def test_slow_closing_rejected(self):
    lead = SimpleNamespace(present=True, modelProb=0.95, dRel=15.0, vLead=14.8)
    self.assertFalse(should_trigger_planner_fcw(lead, 15.0))

  def test_far_ttc_rejected(self):
    # closing FCW_MIN_CLOSING_SPEED from far away -> ttc way above window
    lead = SimpleNamespace(present=True, modelProb=0.95,
                           dRel=100.0, vLead=15.0 - FCW_MIN_CLOSING_SPEED)
    self.assertFalse(should_trigger_planner_fcw(lead, 15.0))

  def test_inactive_lead_rejected(self):
    lead = SimpleNamespace(present=False, modelProb=0.95, dRel=15.0, vLead=10.0)
    self.assertFalse(should_trigger_planner_fcw(lead, 15.0))


if __name__ == "__main__":
  unittest.main()
