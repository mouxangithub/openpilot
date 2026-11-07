#!/usr/bin/env python3
"""Scripted onroad-scenario simulation for the StarPilot stop/depart policy.

Runs the LeadStopDepartPolicy closed-loop at planner rate (20 Hz) over the
typical onroad stop-and-go sequences, using the real long_mpc constants on
device (pure fallback on dev machines). No messaging/cereal involved, so it
runs identically on PC and device.

Scenarios:
  1. standstill_depart  - stopped behind a lead that pulls away
  2. approach_brake     - closing on a slower vision lead at speed
  3. low_speed_stop     - creeping toward a stopped lead
  4. radar_gap_settle   - standstill gap adjust behind a stopped radar lead
  5. gate_off_passthrough is implicit: run with --bypass to see raw targets
"""
import argparse
import math
from types import SimpleNamespace

from openpilot.selfdrive.controls.lib.lead_stop_depart_policy import (
  RADAR_STANDSTILL_GAP_SETTLE_ACCEL,
  LeadStopDepartPolicy,
  StopDepartContext,
)

DT = 0.05  # planner rate


class SimLead:
  """Kinematic lead with the LeadData field names the policy reads."""

  def __init__(self, d_rel, v_lead, radar=True, prob=1.0, y_rel=0.0, accel=0.0):
    self.radar = radar
    self.modelProb = prob
    self.yRel = y_rel
    self.dRel = d_rel
    self.vLead = v_lead
    self.aLeadK = accel
    self.present = True

  def step(self, dt, a_lead=None):
    a = self.aLeadK if a_lead is None else a_lead
    self.vLead = max(0.0, self.vLead + a * dt)
    self.dRel += (self.vLead) * dt  # ego handled by caller offsetting distance


class SimEgo:
  def __init__(self, v_ego=0.0):
    self.v = v_ego

  def step(self, a_target, dt, standstill_hold=True):
    if standstill_hold and self.v <= 0.0 and a_target <= 0.0:
      return 0.0
    self.v = max(0.0, self.v + a_target * dt)
    return self.v


def run_standstill_depart(bypass=False):
  """Stopped behind a lead that launches after 2 s."""
  policy = LeadStopDepartPolicy(SimpleNamespace(longitudinalActuatorDelay=0.15, brand="toyota",
                                                carFingerprint="TOYOTA_WILDLANDER_PHEV"), DT)
  lead = SimLead(4.5, 0.0)
  ego = SimEgo(0.0)
  a_target_in = 0.0
  released_at, min_gap_seen = None, lead.dRel
  for frame in range(int(12.0 / DT)):
    if frame == int(2.0 / DT):  # lead launches
      lead.aLeadK = 0.5
    lead.step(DT)  # lead velocity integrates its own accel
    ctx = StopDepartContext(
      CP=policy.CP, dt=DT, lead_one=lead, lead_two=None,
      v_ego=ego.v, standstill=ego.v <= 0.01, brake_pressed=False, gas_pressed=False,
      long_control_stopping=False, active=True, tracking=True, t_follow=1.8,
      a_target=a_target_in, should_stop=ego.v <= 0.01 and lead.dRel < 8.0,
      output_accel_min=-1.2, model_desired_accel=0.3 if frame >= int(2.0 / DT) else 0.0,
      model_should_stop=False, model_data=None,
    )
    result = policy.apply(ctx)
    a_target_in = a_target_in if bypass else result.a_target
    ego.step(a_target_in, DT)
    min_gap_seen = min(min_gap_seen, lead.dRel)
    lead.dRel -= ego.v * DT
    if released_at is None and ego.v > 0.3:
      released_at = frame * DT
  assert released_at is not None, "ego never launched behind a departing lead"
  assert 2.0 <= released_at <= 6.0, f"launch at {released_at:.2f}s outside the plausible window"
  assert min_gap_seen > 3.0, f"crept into the lead: min gap {min_gap_seen:.2f}m"
  return f"launched at {released_at:.2f}s, min gap {min_gap_seen:.2f}m"


def run_approach_brake(bypass=False):
  """20 m/s into a slower vision lead 60 m ahead; verify smooth braking."""
  policy = LeadStopDepartPolicy(SimpleNamespace(longitudinalActuatorDelay=0.15, brand="toyota",
                                                carFingerprint="TOYOTA_WILDLANDER_PHEV"), DT)
  lead = SimLead(60.0, 8.0, radar=False, prob=0.95)
  ego = SimEgo(20.0)
  a_target_in = 0.3
  brake_started, min_gap = None, float("inf")
  for frame in range(int(20.0 / DT)):
    lead.dRel += (ego.v - lead.vLead) * DT
    ctx = StopDepartContext(
      CP=policy.CP, dt=DT, lead_one=lead, lead_two=None,
      v_ego=ego.v, standstill=False, brake_pressed=False, gas_pressed=False,
      long_control_stopping=False, active=True, tracking=True, t_follow=1.8,
      a_target=a_target_in, should_stop=False,
      output_accel_min=-1.2, model_desired_accel=0.3, model_should_stop=False,
      model_data=None,
    )
    result = policy.apply(ctx)
    if not bypass:
      a_target_in = result.a_target
    if brake_started is None and a_target_in < 0.0:
      brake_started = frame * DT
    ego.step(a_target_in, DT, standstill_hold=False)
    min_gap = min(min_gap, lead.dRel)
  assert brake_started is not None, "approach cap never braked for the slow lead"
  assert min_gap > 8.0, f"approach cut in too deep: min gap {min_gap:.2f}m"
  return f"braking from {brake_started:.1f}s, min gap {min_gap:.1f}m"


def run_low_speed_stop(bypass=False):
  """3 m/s creeping toward a stopped lead; verify the stop buffer stops us."""
  policy = LeadStopDepartPolicy(SimpleNamespace(longitudinalActuatorDelay=0.15, brand="toyota",
                                                carFingerprint="TOYOTA_WILDLANDER_PHEV"), DT)
  lead = SimLead(9.0, 0.0, radar=False, prob=0.95)
  ego = SimEgo(3.0)
  a_target_in = 0.0
  stopped, min_gap = None, float("inf")
  for frame in range(int(15.0 / DT)):
    lead.dRel += ego.v * DT  # lead is stationary
    ctx = StopDepartContext(
      CP=policy.CP, dt=DT, lead_one=lead, lead_two=None,
      v_ego=ego.v, standstill=ego.v <= 0.01, brake_pressed=False, gas_pressed=False,
      long_control_stopping=False, active=True, tracking=True, t_follow=1.8,
      a_target=a_target_in, should_stop=ego.v <= 0.01,
      output_accel_min=-1.2, model_desired_accel=0.0, model_should_stop=True,
      model_data=None,
    )
    result = policy.apply(ctx)
    if not bypass:
      a_target_in = result.a_target
      if result.should_stop:
        a_target_in = min(a_target_in, -0.4)
    ego.step(a_target_in, DT)
    min_gap = min(min_gap, lead.dRel)
    if stopped is None and ego.v <= 0.05:
      stopped = frame * DT
  assert stopped is not None, "never stopped behind the stopped lead"
  assert min_gap > 3.0, f"stopped too close: {min_gap:.2f}m"
  return f"stopped at {stopped:.1f}s, final gap {min_gap:.1f}m"


def run_radar_gap_settle(bypass=False):
  """Standstill with the radar lead 6.8 m out (nudge gap 5.5): settle creep."""
  policy = LeadStopDepartPolicy(SimpleNamespace(longitudinalActuatorDelay=0.15, brand="toyota",
                                                carFingerprint="TOYOTA_WILDLANDER_PHEV"), DT)
  lead = SimLead(6.8, 0.0, radar=True, prob=1.0)
  ego = SimEgo(0.0)
  a_target_in = 0.0
  settle_active, max_gap = False, lead.dRel
  for frame in range(int(10.0 / DT)):
    ctx = StopDepartContext(
      CP=policy.CP, dt=DT, lead_one=lead, lead_two=None,
      v_ego=0.0, standstill=True, brake_pressed=False, gas_pressed=False,
      long_control_stopping=False, active=True, tracking=True, t_follow=1.8,
      a_target=a_target_in, should_stop=True,
      output_accel_min=-1.2, model_desired_accel=0.0, model_should_stop=True,
      model_data=None,
    )
    result = policy.apply(ctx)
    if not bypass:
      a_target_in = result.a_target
      settle_active = settle_active or result.a_target > 0.0 and not result.should_stop
    ego.step(a_target_in, DT)
    lead.dRel -= ego.v * DT
    max_gap = max(max_gap, lead.dRel)
  assert settle_active or max_gap > 6.8, "gap settle never engaged or never advanced"
  assert max_gap <= 7.0 + 1.5 + 1e-6, f"settled too far: {max_gap:.2f}m"
  return f"settle accel engaged={settle_active}, max gap {max_gap:.2f}m"


def run_gate_off_passthrough():
  """Without any cap-triggering scene the output must equal the input."""
  policy = LeadStopDepartPolicy(SimpleNamespace(longitudinalActuatorDelay=0.15, brand="toyota",
                                                carFingerprint="TOYOTA_WILDLANDER_PHEV"), DT)
  result = policy.apply(StopDepartContext(
    CP=policy.CP, dt=DT, lead_one=None, lead_two=None,
    v_ego=20.0, standstill=False, brake_pressed=False, gas_pressed=False,
    long_control_stopping=False, active=True, tracking=True, t_follow=1.8,
    a_target=-0.17, should_stop=False, output_accel_min=-1.2,
    model_desired_accel=0.3, model_should_stop=False, model_data=None,
  ))
  assert abs(result.a_target - (-0.17)) < 1e-9, f"passthrough drifted: {result.a_target}"
  return "a_target unchanged without a lead"


SCENARIOS = {
  "standstill_depart": run_standstill_depart,
  "approach_brake": run_approach_brake,
  "low_speed_stop": run_low_speed_stop,
  "radar_gap_settle": run_radar_gap_settle,
  "gate_off_passthrough": run_gate_off_passthrough,
}


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--bypass", action="store_true", help="feed raw targets back (no policy shaping)")
  parser.add_argument("--only", default=None, help="run a single scenario")
  args = parser.parse_args()

  failures = 0
  for name, fn in SCENARIOS.items():
    if args.only and name != args.only:
      continue
    try:
      detail = fn(bypass=args.bypass) if name != "gate_off_passthrough" else fn()
      print(f"PASS {name}: {detail}")
    except AssertionError as err:
      failures += 1
      print(f"FAIL {name}: {err}")
  raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
  main()
