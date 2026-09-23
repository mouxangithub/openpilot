#!/usr/bin/env python3
"""Unit tests for the acceleration controller stub."""
from __future__ import annotations

import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.accel_controller.accel_controller import AccelController


class TestAccelController(unittest.TestCase):
  def test_stub_is_disabled(self) -> None:
    controller = AccelController()
    controller.update()
    self.assertFalse(controller.is_enabled())
    self.assertEqual(controller.profile, 0)


if __name__ == "__main__":
  unittest.main()
