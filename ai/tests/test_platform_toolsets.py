"""Tests for platform toolsets (skip without openpilot runtime)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))
OP_ROOT = ROOT / "openpilot"
if OP_ROOT.is_dir() and str(OP_ROOT) not in sys.path:
  sys.path.insert(0, str(OP_ROOT))


def _require_openpilot():
  try:
    from openpilot.common.params import Params  # noqa: F401
  except ModuleNotFoundError as e:
    raise unittest.SkipTest(f"openpilot runtime not available: {e}") from e


class ToolsetTests(unittest.TestCase):
  def test_resolve_toolset_driving(self):
    _require_openpilot()
    from ai.tools.toolsets import resolve_toolset

    self.assertEqual(resolve_toolset(True), "driving_readonly")
    self.assertEqual(resolve_toolset(False, agent_id="secoc"), "secoc_pipeline")

  def test_driving_readonly_excludes_writes(self):
    _require_openpilot()
    from ai.tools.toolsets import tool_allowed_in_set

    self.assertFalse(tool_allowed_in_set("write_params", "driving_readonly"))
    self.assertTrue(tool_allowed_in_set("get_vehicle_state", "driving_readonly"))
    self.assertTrue(tool_allowed_in_set("sessions_list", "driving_readonly"))

  def test_platform_tools_in_schemas(self):
    _require_openpilot()
    from ai.tools.agent_tools import build_tool_schemas

    names = {s["function"]["name"] for s in build_tool_schemas()}
    self.assertIn("sessions_list", names)
    self.assertIn("call_mcp_tool", names)


if __name__ == "__main__":
  unittest.main()
