"""Confirmed stops while openpilot holds the car pause DM assessment.

Ported from cp dm2d stationary_pause_eligible: besides the vehicle's own soft
hold, two openpilot-owned stops qualify - an E2E red-light stop the planner
has settled into, and a stationary lead ahead. Every uncertain input fails
closed.
"""
import unittest
from types import SimpleNamespace as NS

from opendbc.car.structs import car

from openpilot.selfdrive.monitoring.dmonitoringd import (
  SOFT_HOLD_MAX_AGE_S, stationary_pause_eligible,
)

XSTATE_LEAD = 0        # carrot XState.lead
XSTATE_E2E_STOPPED = 5  # carrot XState.e2eStopped
TRAFFIC_RED = 1         # carrot TrafficState.red


def _car_state(**overrides):
  state = {'canValid': True, 'softHoldActive': 0, 'standstill': True, 'gasPressed': False,
           'gearShifter': car.CarState.GearShifter.drive, 'vEgo': 0.0, 'vEgoRaw': 0.0,
           'brakePressed': False, 'leftBlindspot': False, 'rightBlindspot': False}
  state.update(overrides)
  return NS(**state)


def _plan(**overrides):
  plan = {'xState': XSTATE_E2E_STOPPED, 'trafficState': TRAFFIC_RED, 'vTargetNow': 0.0, 'hasLead': False}
  plan.update(overrides)
  return NS(**plan)


def _lead(**overrides):
  lead = {'status': True, 'dRel': 12.0, 'vLead': 0.0}
  lead.update(overrides)
  return NS(**lead)


def _radar(**overrides):
  radar = {'leadOne': _lead(), 'radarErrors': NS(to_dict=dict)}
  radar.update(overrides)
  return NS(**radar)


def _car_control(**overrides):
  actuators = NS(longControlState=car.CarControl.Actuators.LongControlState.stopping)
  cc = NS(longActive=True, actuators=actuators)
  cc.__dict__.update(overrides)
  return cc


class _Sm:
  def __init__(self, car_state=None, plan=None, car_control=None, radar=None,
               state=None, now=10.0, checks=True, services=None):
    self.services = services if services is not None else [
      'carState', 'selfdriveState', 'carControl', 'longitudinalPlan']
    self._checks = checks
    self.data = {
      'carState': car_state if car_state is not None else _car_state(),
      'selfdriveState': state if state is not None else NS(enabled=True, active=True),
      'carControl': car_control if car_control is not None else _car_control(),
      'longitudinalPlan': plan if plan is not None else _plan(),
      'radarState': radar if radar is not None else _radar(),
    }
    self.recv_time = dict.fromkeys(list(self.services) + ['radarState'], now)

  def all_checks(self, service_list=None):
    return self._checks

  def __getitem__(self, key):
    return self.data[key]


class TestStationaryPauseE2EStop(unittest.TestCase):
  def test_e2e_red_light_stop_pauses(self):
    self.assertTrue(stationary_pause_eligible(_Sm(), 10.0))

  def test_soft_hold_still_qualifies_first(self):
    sm = _Sm(_car_state(softHoldActive=1), plan=_plan(xState=XSTATE_LEAD, hasLead=False))
    self.assertTrue(stationary_pause_eligible(sm, 10.0))

  def test_red_light_requires_both_state_and_signal(self):
    for name, plan in (
      ('wrong_xstate', _plan(xState=XSTATE_LEAD, hasLead=False)),
      ('green_signal', _plan(trafficState=2)),
    ):
      with self.subTest(case=name):
        self.assertFalse(stationary_pause_eligible(_Sm(plan=plan), 10.0))

  def test_demo_never_pauses(self):
    self.assertFalse(stationary_pause_eligible(_Sm(), 10.0, demo=True))


class TestStationaryPauseLead(unittest.TestCase):
  def test_stationary_lead_pauses(self):
    plan = _plan(xState=XSTATE_LEAD, hasLead=True, trafficState=0)
    self.assertTrue(stationary_pause_eligible(_Sm(plan=plan), 10.0))

  def test_lead_vetoes(self):
    plan = _plan(xState=XSTATE_LEAD, hasLead=True, trafficState=0)
    for name, radar in (
      ('no_lead', _radar(leadOne=_lead(status=False))),
      ('too_far', _radar(leadOne=_lead(dRel=45.0))),
      ('lead_moving', _radar(leadOne=_lead(vLead=0.5))),
      ('radar_errors', _radar(radarErrors=NS(to_dict=lambda: {'commIssue': True}))),
    ):
      with self.subTest(case=name):
        self.assertFalse(stationary_pause_eligible(_Sm(plan=plan, radar=radar), 10.0))

  def test_lead_distance_boundaries(self):
    plan = _plan(xState=XSTATE_LEAD, hasLead=True, trafficState=0)
    self.assertTrue(stationary_pause_eligible(_Sm(plan=plan, radar=_radar(leadOne=_lead(dRel=40.0))), 10.0))
    self.assertFalse(stationary_pause_eligible(_Sm(plan=plan, radar=_radar(leadOne=_lead(dRel=40.01))), 10.0))


class TestStationaryPauseFailClosed(unittest.TestCase):
  def _plan_variant(self, **overrides):
    return _plan(**overrides)

  def test_uncertain_inputs_fail_closed(self):
    base_plan = _plan(xState=XSTATE_LEAD, hasLead=True, trafficState=0)
    for name, sm in (
      ('invalid_checks', _Sm(plan=base_plan, checks=False)),
      ('not_standstill', _Sm(_car_state(standstill=False), plan=base_plan)),
      ('gas_pressed', _Sm(_car_state(gasPressed=True), plan=base_plan)),
      ('can_invalid', _Sm(_car_state(canValid=False), plan=base_plan)),
      ('reverse_gear', _Sm(_car_state(gearShifter=car.CarState.GearShifter.reverse), plan=base_plan)),
      ('moving', _Sm(_car_state(vEgo=0.5), plan=base_plan)),
      ('not_enabled', _Sm(plan=base_plan, state=NS(enabled=False, active=True))),
      ('not_active', _Sm(plan=base_plan, state=NS(enabled=True, active=False))),
      ('long_not_active', _Sm(plan=base_plan, car_control=_car_control(longActive=False))),
      ('wrong_control_state', _Sm(
        plan=base_plan,
        car_control=_car_control(
          actuators=NS(longControlState=car.CarControl.Actuators.LongControlState.enabled)))),
      ('vtarget_too_high', _Sm(plan=self._plan_variant(vTargetNow=0.5), checks=True)),
      ('vtarget_missing_nan', _Sm(plan=self._plan_variant(vTargetNow=float('nan')))),
    ):
      with self.subTest(case=name):
        self.assertFalse(stationary_pause_eligible(sm, 10.0))

  def test_stale_inputs_fail_closed(self):
    self.assertFalse(stationary_pause_eligible(_Sm(now=10.0), 10.0 - SOFT_HOLD_MAX_AGE_S - 0.01))
    self.assertFalse(stationary_pause_eligible(_Sm(now=10.0), 10.5))  # message from the future
    self.assertTrue(stationary_pause_eligible(_Sm(now=10.0), 10.0 + SOFT_HOLD_MAX_AGE_S))

  def test_minimal_sm_without_plan_fields_fails_closed(self):
    # A minimal SubMaster stand-in without the new fields must not crash.
    sm = _Sm(plan=NS())
    sm.data['carControl'] = NS(longActive=True, actuators=NS())
    self.assertFalse(stationary_pause_eligible(sm, 10.0))


if __name__ == '__main__':
  unittest.main()
