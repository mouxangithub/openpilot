"""Tests for run_health_check composite tool."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock


class TestHealthCheck(unittest.TestCase):
  def test_engage_scope_ok_when_idle(self):
    from ai.tools.health_check_tools import run_health_check

    state = MagicMock()
    state.to_dict.return_value = {
      "enabled": False,
      "started": False,
      "vEgo": 0,
      "brand": "toyota",
      "alerts": [],
      "events": [],
    }
    reader = MagicMock()
    reader.update.return_value = state
    reader.latest.return_value = {"vehicle": state.to_dict()}

    with unittest.mock.patch("ai.tools.device_health_tools.device_health", return_value={"ok": True, "board": "tici"}):
      with unittest.mock.patch("ai.tools.device_health_tools.panda_status", return_value={"ok": True, "connected": True, "summary": "ok"}):
        params_mod = unittest.mock.MagicMock()
        mock_inst = unittest.mock.MagicMock()
        mock_inst.get.side_effect = lambda k: {
          "IsOffroad": b"1",
          "IsOnroad": b"0",
          "CarParams": b"car",
          "SecOCKey": b"key",
          "OpenpilotEnabledToggle": b"1",
        }.get(k)
        params_mod.Params.return_value = mock_inst
        with unittest.mock.patch.dict("sys.modules", {"openpilot.common.params": params_mod}):
          res = run_health_check(scope="engage", get_state_reader=lambda: reader)

    self.assertTrue(res.get("ok"))
    self.assertIn(res.get("overall"), ("ok", "warn", "fail"))
    names = {c["name"] for c in res.get("checks", [])}
    self.assertIn("engage", names)
    self.assertIn("panda", names)

  def test_guide_ota_returns_steps(self):
    from ai.tools.health_check_tools import guide_ota_update

    with unittest.mock.patch("ai.tools.branch_tools.ota_preflight_checklist", return_value={"ok": True}):
      res = guide_ota_update()
    self.assertTrue(res.get("ok"))
    self.assertTrue(res.get("steps"))


if __name__ == "__main__":
  unittest.main()
