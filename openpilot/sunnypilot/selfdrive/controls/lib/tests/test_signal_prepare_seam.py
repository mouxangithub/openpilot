"""Geometric red-light pre-deceleration execution seam (apply_signal_prepare).

Default-OFF and mode-2-gated: these lock that the cap is a no-op at mode<=1,
only ever lowers accel, and is blocked by the cp guard conditions.
"""
import unittest
from unittest.mock import MagicMock, patch

import openpilot.cereal.messaging as messaging
from opendbc.car import structs
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlannerSP


def _make_planner():
  cp = structs.CarParams(brand="mazda", openpilotLongitudinalControl=True, longitudinalActuatorDelay=0.36)
  planner = LongitudinalPlannerSP(cp, structs.CarParamsSP(), MagicMock())
  planner.dt = 0.05
  cs = messaging.new_message('carState').carState
  cs.vEgo = 12.0
  cs.aEgo = 0.0
  cs.gasPressed = False
  cs.brakePressed = False
  radar = messaging.new_message('radarState').radarState
  sm = {'carState': cs, 'radarState': radar}
  return planner, sm


class TestApplySignalPrepare(unittest.TestCase):
  def setUp(self):
    self.planner, self.sm = _make_planner()
    self.planner.output_a_target = 0.0
    self.planner.output_v_target = 20.0
    self.planner.output_should_stop = False

  def _set_decision(self, active=True, control_active=True):
    carrot = self.planner.carrot_source.carrot
    carrot.prepare_decision = MagicMock(active=active)
    carrot.prepare_control_active = control_active

  def test_mode_zero_is_noop(self):
    self._set_decision()
    with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 0):
      self.planner.apply_signal_prepare(self.sm, now=1.0)
    self.assertEqual(self.planner.output_a_target, 0.0)

  def test_mode_one_shadow_does_not_actuate(self):
    self._set_decision()
    with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 1):
      self.planner.apply_signal_prepare(self.sm, now=1.0)
    self.assertEqual(self.planner.output_a_target, 0.0)

  def test_mode_two_lowers_accel_not_raises(self):
    self._set_decision()
    with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 2), \
         patch('openpilot.sunnypilot.carrot.signal_stop_prepare.prepare_lead_blocked', lambda r: False):
      self.planner.apply_signal_prepare(self.sm, now=1.0)
      self.planner.apply_signal_prepare(self.sm, now=1.05)
    # the cap can only pull the command down toward the gentle braking target
    self.assertLessEqual(self.planner.output_a_target, 0.0)

  def test_mode_two_blocked_by_lead(self):
    self._set_decision()
    with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 2), \
         patch('openpilot.sunnypilot.carrot.signal_stop_prepare.prepare_lead_blocked', lambda r: True):
      before = self.planner.output_a_target
      self.planner.apply_signal_prepare(self.sm, now=1.0)
    self.assertEqual(self.planner.output_a_target, before)

  def test_decision_none_is_noop(self):
    carrot = self.planner.carrot_source.carrot
    carrot.prepare_decision = None
    carrot.prepare_control_active = False
    with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 2):
      self.planner.apply_signal_prepare(self.sm, now=1.0)
    self.assertEqual(self.planner.output_a_target, 0.0)

  def test_gas_pressed_blocks(self):
    self._set_decision()
    self.sm['carState'].gasPressed = True
    with patch('openpilot.sunnypilot.carrot.signal_mode.signal_mode', lambda: 2), \
         patch('openpilot.sunnypilot.carrot.signal_stop_prepare.prepare_lead_blocked', lambda r: False):
      self.planner.apply_signal_prepare(self.sm, now=1.0)
    self.assertEqual(self.planner.output_a_target, 0.0)


if __name__ == "__main__":
  unittest.main()
