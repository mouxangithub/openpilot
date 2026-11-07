"""Phase-2 extras: shell safety, workspace, sidecar."""

from __future__ import annotations

import unittest


class TestShellSafety(unittest.TestCase):
  def test_blocks_steering_command(self):
    from ai.system.shell import assert_shell_safe

    err = assert_shell_safe("python -c 'car.send([0x123])'")
    self.assertIsNotNone(err)
    self.assertIn("forbidden", err.lower())

  def test_allows_uptime(self):
    from ai.system.shell import assert_shell_safe

    self.assertIsNone(assert_shell_safe("uptime"))


class TestWorkspace(unittest.TestCase):
  def test_default_files_and_prompt(self):
    from ai.core.wspace.store import ensure_default_workspace_files, workspace_prompt_blocks

    ensure_default_workspace_files()
    blocks = workspace_prompt_blocks()
    self.assertTrue(any("SOUL" in b or "助手" in b for b in blocks))


class TestSidecarHub(unittest.TestCase):
  def test_recent_events_ring(self):
    from ai.core.runtime.sidecar_hub import _recent, recent_events

    _recent.clear()
    for i in range(5):
      _recent.append({"type": "tool_start", "name": f"t{i}"})
    ev = recent_events(3)
    self.assertEqual(len(ev), 3)
    self.assertEqual(ev[-1]["name"], "t4")


if __name__ == "__main__":
  unittest.main()
