#!/usr/bin/env python3
from __future__ import annotations
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Unit tests for CarrotControls lat-suspend behaviour.

`lat_suspend_control(CS, latActive)` was replaced by `wants_suspend(CS)`. The old API
returned a possibly-cleared `latActive`, which is how carrot ended up overriding
CC.latActive from controlsd.py *after* the sunnypilot lateral-enable arbitration - a
second, independent gate on the actuator that also ignored CarrotEnabled. The
predicate form forces the decision through ControlsExt.get_lat_active instead, so
these tests exercise the predicate and the master switch.
"""

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
    self.ctrl.enabled = True

  def test_no_suspend_when_steering_small(self):
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=10.0)
    for _ in range(200):
      suspended = self.ctrl.wants_suspend(cs)
    self.assertFalse(suspended)
    self.assertFalse(self.ctrl.lat_suspend_active)

  def test_no_suspend_at_the_default_angle(self):
    """LatSuspendAngleDeg defaults to 300, which no real steering angle reaches.

    This is why folding the check into get_lat_active is behaviour-preserving by
    default: the predicate can only ever return False unless the user lowers it.
    """
    self.ctrl.params.get = lambda key: 300
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=180.0)
    for _ in range(1000):
      self.assertFalse(self.ctrl.wants_suspend(cs))

  def test_suspend_after_delay_at_large_angle(self):
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    for _ in range(99):
      self.assertFalse(self.ctrl.wants_suspend(cs))
    self.assertTrue(self.ctrl.wants_suspend(cs))
    self.assertTrue(self.ctrl.lat_suspend_active)

  def test_suspend_holds_and_resumes(self):
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    for _ in range(110):
      self.ctrl.wants_suspend(cs)
    self.assertTrue(self.ctrl.lat_suspend_active)

    # Still steering hard -> stays suspended.
    self.assertTrue(self.ctrl.wants_suspend(cs))

    # Released but angle still large -> exit angle not met, stays suspended.
    cs = _FakeCS(steering_pressed=False, steering_angle_deg=350.0)
    for _ in range(60):
      self.assertTrue(self.ctrl.wants_suspend(cs))
    self.assertTrue(self.ctrl.lat_suspend_active)

    # Small angle, past hold time -> resumes.
    cs = _FakeCS(steering_pressed=False, steering_angle_deg=10.0)
    for _ in range(60):
      self.assertFalse(self.ctrl.wants_suspend(cs))
    self.assertFalse(self.ctrl.lat_suspend_active)

  def test_timer_resets_when_condition_lost(self):
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    for _ in range(50):
      self.ctrl.wants_suspend(cs)
    self.assertFalse(self.ctrl.lat_suspend_active)

    # Briefly lose the condition.
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=10.0)
    self.ctrl.wants_suspend(cs)

    # Re-entering must wait the full delay again.
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    for _ in range(99):
      self.assertFalse(self.ctrl.wants_suspend(cs))
    self.assertTrue(self.ctrl.wants_suspend(cs))

  def test_master_switch_off_never_suspends(self):
    """CarrotEnabled off must disable this entirely.

    Previously nothing consulted that switch, so carrot kept overriding CC.latActive
    even with carrot turned off.
    """
    self.ctrl.enabled = False
    cs = _FakeCS(steering_pressed=True, steering_angle_deg=350.0)
    for _ in range(1000):
      self.assertFalse(self.ctrl.wants_suspend(cs))
    self.assertFalse(self.ctrl.lat_suspend_active)

  def test_update_params_reads_carrot_enabled(self):
    self.ctrl.params.get_bool = lambda key, *a: key == "CarrotEnabled"
    self.ctrl.update_params()
    self.assertTrue(self.ctrl.enabled)

    self.ctrl.params.get_bool = lambda key, *a: False
    self.ctrl.update_params()
    self.assertFalse(self.ctrl.enabled)

  def test_predicate_never_takes_latActive(self):
    """The point of the rewrite: no in-place latActive fiddling.

    Checked on the signature rather than the source text, because the docstring
    legitimately mentions the name it deliberately no longer touches.
    """
    import inspect

    sig = inspect.signature(CarrotControls.wants_suspend)
    self.assertEqual(list(sig.parameters), ["self", "CS"],
                     f"wants_suspend must only take the car state, got {list(sig.parameters)}")
    # `from __future__ import annotations` keeps annotations as strings.
    self.assertIn(sig.return_annotation, (bool, "bool"),
                  f"wants_suspend must return bool, got {sig.return_annotation!r}")


if __name__ == "__main__":
  unittest.main()
