"""Stationary soft hold pauses driver monitoring assessment.

A soft hold is the vehicle's own standstill brake (e.g. waiting at a light).
The driver is expected to look away there, so DM must not count it against
them - but publication must continue at the normal cadence so consumer health
checks still see a fresh packet.
"""
import unittest
from types import SimpleNamespace as NS

from opendbc.car.structs import car

from openpilot.selfdrive.monitoring.dmonitoringd import (
  SOFT_HOLD_MAX_AGE_S, soft_hold_pause_eligible, soft_hold_state_packet,
)


def _car_state(**overrides):
  state = {'canValid': True, 'softHoldActive': 1, 'standstill': True, 'gasPressed': False,
           'gearShifter': car.CarState.GearShifter.drive, 'vEgo': 0.0, 'vEgoRaw': 0.0}
  state.update(overrides)
  return NS(**state)


class _Sm:
  def __init__(self, car_state=None, now=10.0, checks=True, stale_service=None):
    self.services = ['carState', 'selfdriveState']
    self._checks = checks
    self._stale = stale_service
    self.data = {'carState': car_state if car_state is not None else _car_state(),
                 'selfdriveState': NS(enabled=True)}
    self.recv_time = dict.fromkeys(self.services, now)

  def all_checks(self, service_list=None):
    return self._checks

  def __getitem__(self, key):
    return self.data[key]


class TestSoftHoldEligible(unittest.TestCase):
  def test_stationary_soft_hold_pauses(self):
    self.assertTrue(soft_hold_pause_eligible(_Sm(), 10.0))

  def test_demo_never_pauses(self):
    self.assertFalse(soft_hold_pause_eligible(_Sm(), 10.0, demo=True))

  def test_uncertain_inputs_fail_closed(self):
    for name, sm in (
      ('invalid_checks', _Sm(checks=False)),
      ('no_soft_hold', _Sm(_car_state(softHoldActive=0))),
      ('not_standstill', _Sm(_car_state(standstill=False))),
      ('gas_pressed', _Sm(_car_state(gasPressed=True))),
      ('can_invalid', _Sm(_car_state(canValid=False))),
      ('reverse_gear', _Sm(_car_state(gearShifter=car.CarState.GearShifter.reverse))),
      ('moving', _Sm(_car_state(vEgo=0.5))),
      ('raw_moving', _Sm(_car_state(vEgoRaw=0.4))),
      ('nan_speed', _Sm(_car_state(vEgo=float('nan')))),
    ):
      with self.subTest(case=name):
        self.assertFalse(soft_hold_pause_eligible(sm, 10.0))

  def test_low_gear_is_allowed(self):
    self.assertTrue(soft_hold_pause_eligible(_Sm(_car_state(gearShifter=car.CarState.GearShifter.low)), 10.0))

  def test_stale_inputs_fail_closed(self):
    # age in both directions, plus exactly at the boundary
    self.assertFalse(soft_hold_pause_eligible(_Sm(now=10.0), 10.0 - SOFT_HOLD_MAX_AGE_S - 0.01))
    self.assertFalse(soft_hold_pause_eligible(_Sm(now=10.0), 10.5))  # message from the future
    self.assertTrue(soft_hold_pause_eligible(_Sm(now=10.0), 10.0 + SOFT_HOLD_MAX_AGE_S))


class _Monitor:
  """Minimal stand-in exposing only what soft_hold_state_packet touches."""

  def __init__(self):
    self.calls = 0

  def get_state_packet(self, valid=True):
    self.calls += 1
    state = NS(
      lockout=True, alertCountLockoutPercent=50, alertTimeLockoutPercent=60,
      lockoutRecoveryPercent=70, alert3Count=3, noResponseCount=4,
      noResponseForceDecel=True, alwaysOnLockout=True, alertLevel='three',
      isRHD=True, activePolicy='vision',
      visionPolicyState=NS(awarenessPercent=5, awarenessStep=1, isDistracted=True,
                           distractedTypes=NS(pose=True, eye=True, phone=True),
                           faceDetected=True, wheeltouchFallbackPercent=10),
      wheeltouchPolicyState=NS(awarenessPercent=5),
    )
    return NS(driverMonitoringState=state, valid=valid)


class TestSoftHoldPacket(unittest.TestCase):
  def test_packet_carries_no_penalty(self):
    monitor = _Monitor()
    state = soft_hold_state_packet(monitor).driverMonitoringState
    self.assertFalse(state.lockout)
    self.assertEqual(state.alertLevel, 'none')
    self.assertEqual(state.alert3Count, 0)
    self.assertEqual(state.noResponseCount, 0)
    self.assertFalse(state.noResponseForceDecel)
    self.assertFalse(state.alwaysOnLockout)
    self.assertEqual(state.alertCountLockoutPercent, 0)
    self.assertEqual(state.alertTimeLockoutPercent, 0)
    self.assertEqual(state.lockoutRecoveryPercent, 0)

  def test_awareness_and_distraction_are_neutralized(self):
    state = soft_hold_state_packet(_Monitor()).driverMonitoringState
    self.assertEqual(state.visionPolicyState.awarenessPercent, 100)
    self.assertEqual(state.visionPolicyState.awarenessStep, 0)
    self.assertFalse(state.visionPolicyState.isDistracted)
    self.assertFalse(state.visionPolicyState.distractedTypes.pose)
    self.assertFalse(state.visionPolicyState.distractedTypes.eye)
    self.assertFalse(state.visionPolicyState.distractedTypes.phone)

  def test_driver_facing_evidence_is_preserved(self):
    # A pause is not a loss of monitoring: keep what the driver relies on.
    state = soft_hold_state_packet(_Monitor()).driverMonitoringState
    self.assertTrue(state.isRHD)
    self.assertTrue(state.visionPolicyState.faceDetected)
    self.assertEqual(state.activePolicy, 'vision')

  def test_valid_flag_is_propagated(self):
    self.assertTrue(soft_hold_state_packet(_Monitor(), valid=True).valid)
    self.assertFalse(soft_hold_state_packet(_Monitor(), valid=False).valid)


if __name__ == '__main__':
  unittest.main()
