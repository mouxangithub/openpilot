#!/usr/bin/env python3
from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Unit tests for CarrotControls lat-suspend behavior."""

import sys
import types
import unittest
from unittest.mock import MagicMock

# Minimal mocks so the module imports without a compiled capnp runtime.
_common_pkg = types.ModuleType("openpilot.common")
_common_pkg.realtime = types.ModuleType("openpilot.common.realtime")
_common_pkg.realtime.DT_CTRL = 0.01
_common_pkg.params = MagicMock()
_common_pkg.swaglog = MagicMock(cloudlog=MagicMock())
sys.modules["openpilot.common"] = _common_pkg
sys.modules["openpilot.common.realtime"] = _common_pkg.realtime
sys.modules["openpilot.common.params"] = _common_pkg.params
sys.modules["openpilot.common.swaglog"] = _common_pkg.swaglog

from openpilot.sunnypilot.carrot.carrot_controls import CarrotControls


class _FakeCS:
  def __init__(self, steering_pressed: bool = False, steering_angle_deg: float = 0.0):
    self.steeringPressed = steering_pressed
    self.steeringAngleDeg = steering_angle_deg


class TestCarrotControlsLatSuspend(unittest.TestCase):
  def setUp(self):
    self.ctrl = CarrotControls(MagicMock())
    self.ctrl.params = MagicMock()
    self.ctrl.params.get = lambda key: 300  # LatSuspendAngleDeg = 300 degrees

  def test_no_suspend_when_steering_small(self):
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=10.0)
    for _ in range(200):
      active = self.ctrl.lat_suspend_control(cs, True)
    self.assertTrue(active)
    self.assertFalse(self.ctrl.lat_suspend_active)

  def test_suspend_after_delay_at_large_angle(self):
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    active = True
    for _ in range(99):
      active = self.ctrl.lat_suspend_control(cs, True)
    self.assertTrue(active)
    active = self.ctrl.lat_suspend_control(cs, True)
    self.assertFalse(active)
    self.assertTrue(self.ctrl.lat_suspend_active)

  def test_suspend_holds_and_resumes(self):
    # Enter suspend.
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    for _ in range(110):
      self.ctrl.lat_suspend_control(cs, True)
    self.assertTrue(self.ctrl.lat_suspend_active)

    # Stay suspended while still steering hard.
    active = self.ctrl.lat_suspend_control(cs, True)
    self.assertFalse(active)

    # Release steering but stay at large angle -> still suspended (exit angle not met).
    cs = _FakeCS(steering_pressed=False, steering_angle_deg=350.0)
    for _ in range(60):
      active = self.ctrl.lat_suspend_control(cs, True)
    self.assertFalse(active)
    self.assertTrue(self.ctrl.lat_suspend_active)

    # Move to small angle and wait for hold time.
    cs = _FakeCS(steering_pressed=False, steering_angle_deg=10.0)
    for _ in range(60):
      active = self.ctrl.lat_suspend_control(cs, True)
    self.assertTrue(active)
    self.assertFalse(self.ctrl.lat_suspend_active)

  def test_timer_resets_when_condition_lost(self):
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    for _ in range(50):
      self.ctrl.lat_suspend_control(cs, True)
    self.assertFalse(self.ctrl.lat_suspend_active)

    # Briefly lose the condition.
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=10.0)
    self.ctrl.lat_suspend_control(cs, True)

    # Re-enter must wait full delay again.
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    active = True
    for _ in range(99):
      active = self.ctrl.lat_suspend_control(cs, True)
    self.assertTrue(active)
    active = self.ctrl.lat_suspend_control(cs, True)
    self.assertFalse(active)


if __name__ == "__main__":
  unittest.main()
