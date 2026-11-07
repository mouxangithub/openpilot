"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Standstill chime gate semantics (E2EAlertsWhenEngaged).

Unittest only (no pytest): this runs on device, where cereal imports.
"""
import unittest

from openpilot.sunnypilot.selfdrive.controls.lib.e2e_alerts_helper import standstill_alert_allowed


class TestStandstillAlertAllowed(unittest.TestCase):
  def test_default_matches_legacy_behaviour(self):
    # (moving, gas_pressed, cc_enabled, recent_moving) -> allowed, with the switch off.
    # This is exactly the pre-E2EAlertsWhenEngaged formula:
    #   not moving and not gas and not cc_enabled and not recent_moving
    legacy_cases = [
      (False, False, False, False, True),
      (False, False, True, False, False),   # longitudinal engaged -> vetoed
      (False, True, False, False, False),   # gas pressed -> vetoed
      (True, False, False, False, False),   # moving -> vetoed
      (False, False, False, True, False),   # recently moved -> vetoed
      (True, True, True, True, False),
    ]
    for moving, gas, enabled, recent, expected in legacy_cases:
      self.assertEqual(
        standstill_alert_allowed(moving, gas, enabled, recent, False),
        expected,
        msg=f"moving={moving} gas={gas} cc_enabled={enabled} recent_moving={recent}",
      )

  def test_when_engaged_relaxes_only_the_engagement_veto(self):
    # ACC holding at a standstill (cc_enabled=True) is now allowed...
    self.assertTrue(standstill_alert_allowed(False, False, True, False, True))
    # ...but every other gate still applies.
    self.assertFalse(standstill_alert_allowed(True, False, True, False, True))
    self.assertFalse(standstill_alert_allowed(False, True, True, False, True))
    self.assertFalse(standstill_alert_allowed(False, False, True, True, True))

  def test_when_engaged_keeps_disengaged_behaviour(self):
    self.assertTrue(standstill_alert_allowed(False, False, False, False, True))
    self.assertFalse(standstill_alert_allowed(True, True, False, False, True))


if __name__ == "__main__":
  unittest.main()
