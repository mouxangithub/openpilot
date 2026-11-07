"""Unit tests for headless WebUI helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class HeadlessUtilTest(unittest.TestCase):
  def test_dev_pc_not_headless(self):
    from webui.server.bridge.headless_util import is_headless_mode

    with patch.dict("os.environ", {"WEBUI_DEV_PC": "1"}, clear=False):
      self.assertFalse(is_headless_mode())


class SunnylinkTierParseTest(unittest.TestCase):
  def test_empty_returns_defaults(self):
    from webui.server.bridge.webui_bg_services import sunnylink_tier_from_params

    out = sunnylink_tier_from_params()
    self.assertIn("tier", out)
    self.assertIn("is_paired", out)


class SunnylinkPanelWatchTest(unittest.TestCase):
  def test_watch_refcount(self):
    from webui.server.bridge import webui_bg_services as bg

    bg._sunnylink_watchers = 0
    bg.sunnylink_panel_watch(1)
    self.assertTrue(bg.is_sunnylink_panel_watched())
    bg.sunnylink_panel_watch(-1)
    self.assertFalse(bg.is_sunnylink_panel_watched())


class AlertHeightTest(unittest.TestCase):
  def test_mid_height_without_gui(self):
    from webui.server.bridge.state_api import _estimate_alert_height

    h = _estimate_alert_height("mid", "Test alert", "Secondary line")
    self.assertGreater(h, 0)


class StartupBlockersTest(unittest.TestCase):
  def test_driver_view_blocks_when_enabled(self):
    from webui.server.bridge.startup_blockers import evaluate_startup_gates

    class FakeParams:
      def get_bool(self, key):
        return key == "IsDriverViewEnabled"

      def get(self, key):
        return None

    gates = evaluate_startup_gates(FakeParams(), None)
    self.assertFalse(gates["startup"]["not_driver_view"])

  def test_blocker_messages_have_entries(self):
    from webui.server.bridge.startup_blockers import BLOCKER_MESSAGES, evaluate_startup_gates

    class FakeParams:
      def get_bool(self, key):
        return False

      def get(self, key):
        return None

    gates = evaluate_startup_gates(FakeParams(), None)
    for key in gates["startup"]:
      if key in BLOCKER_MESSAGES:
        self.assertTrue(BLOCKER_MESSAGES[key])


class OffroadGuardTest(unittest.TestCase):
  def test_require_offroad_when_onroad(self):
    from webui.server.bridge import offroad_guard as og

    with patch.object(og, "device_is_onroad", return_value=True):
      out = og.require_offroad()
    self.assertIsNotNone(out)
    self.assertFalse(out["ok"])
    self.assertEqual(out["error"], "only_available_offroad")

  def test_require_offroad_when_offroad(self):
    from webui.server.bridge import offroad_guard as og

    with patch.object(og, "device_is_onroad", return_value=False):
      self.assertIsNone(og.require_offroad())


if __name__ == "__main__":
  unittest.main()
