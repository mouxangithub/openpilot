#!/usr/bin/env python3
"""Unit tests for the acceleration controller stub."""
from __future__ import annotations

import unittest

from openpilot.common.params import Params
from openpilot.sunnypilot.selfdrive.controls.lib.accel_controller.accel_controller import AccelController, AccelProfile


class TestAccelController(unittest.TestCase):
  def test_stub_is_disabled(self) -> None:
    # Isolate the params so the assertion does not depend on whatever the device
    # happens to have set: the stub is disabled when AccelPersonalityEnabled is off,
    # and the profile falls back to eco (0).
    params = Params()
    params.put_bool("AccelPersonalityEnabled", False, block=True)
    params.put("AccelPersonality", AccelProfile.eco, block=True)
    controller = AccelController()
    controller.update()
    self.assertFalse(controller.is_enabled())
    self.assertEqual(controller.profile, AccelProfile.eco)


if __name__ == "__main__":
  unittest.main()
