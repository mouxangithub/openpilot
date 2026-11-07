"""Tests for runtime tool metadata registry (T-P2.2)."""
from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401


class TestRuntimeMeta(unittest.TestCase):
  def test_register_and_lookup(self):
    from ai.tools.runtime_meta import clear_tool_meta, get_tool_meta, register_tool_meta

    clear_tool_meta()
    register_tool_meta("mcp__test__echo", label="Echo", description="echo tool", group="mcp")
    meta = get_tool_meta("mcp__test__echo")
    self.assertIsNotNone(meta)
    self.assertEqual(meta["label"], "Echo")
    self.assertEqual(meta["group"], "mcp")

  def test_enrich_falls_back_to_runtime(self):
    from ai.tools.domains.platform.tool_ui_meta import enrich_tool_meta_for_ui
    from ai.tools.runtime_meta import clear_tool_meta, register_tool_meta

    clear_tool_meta()
    register_tool_meta("dynamic_tool", label="Dynamic", description="runtime desc")
    out = enrich_tool_meta_for_ui({"dynamic_tool": {"group": "read"}})
    self.assertEqual(out["dynamic_tool"]["label"], "Dynamic")
    self.assertEqual(out["dynamic_tool"]["description"], "runtime desc")


if __name__ == "__main__":
  unittest.main()
