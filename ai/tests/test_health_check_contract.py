"""Tests for health_check executable actions + standard contract (T-P0.4, T-P1.3)."""
from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401


def _check(name, status, action=None):
  return {"name": name, "status": status, "summary": "x", "details": {}, "action": action}


class TestHealthCheckContract(unittest.TestCase):
  def test_executables_collected_and_deduped(self):
    from ai.tools.domains.platform.health_check_tools import _collect_executables
    checks = [
      _check("panda", "fail", "检查 USB / pandad / c3-dos-panda 技能"),
      _check("secoc", "warn", "启用 secoc-toyota 技能"),
      _check("engage", "ok"),
      # duplicate panda action again
      _check("panda2", "warn", "检查 USB / pandad / c3-dos-panda 技能"),
    ]
    ex = _collect_executables(checks)
    tools = [e["tool"] for e in ex]
    self.assertIn("panda_status", tools)
    self.assertIn("secoc_extract_key", tools)
    # dedup
    self.assertEqual(tools.count("panda_status"), 1)
    # confirm on fail
    panda = next(e for e in ex if e["tool"] == "panda_status")
    self.assertTrue(panda["confirm"])

  def test_ok_checks_produce_no_actions(self):
    from ai.tools.domains.platform.health_check_tools import _collect_executables
    ex = _collect_executables([_check("engage", "ok"), _check("alerts", "ok")])
    self.assertEqual(ex, [])

  def test_unknown_action_maps_to_nothing(self):
    from ai.tools.domains.platform.health_check_tools import _collect_executables
    ex = _collect_executables([_check("custom", "warn", "some custom action")])
    self.assertEqual(ex, [])


if __name__ == "__main__":
  unittest.main()