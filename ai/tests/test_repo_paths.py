"""Tests for openpilot repo layout path resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class RepoPathTests(unittest.TestCase):
  def test_detect_nested_layout(self):
    from ai.system.paths import openpilot_root, openpilot_source_root, repo_layout, source_path

    root = openpilot_root()
    self.assertEqual(root, ROOT)
    layout = repo_layout()
    if (ROOT / "openpilot" / "selfdrive").is_dir():
      self.assertEqual(layout, "nested")
      self.assertEqual(openpilot_source_root(), ROOT / "openpilot")
      self.assertTrue(source_path("selfdrive").is_dir())
    elif (ROOT / "selfdrive").is_dir():
      self.assertEqual(layout, "flat")
      self.assertEqual(openpilot_source_root(), ROOT)

  def test_tools_path_plotjuggler(self):
    from ai.system.paths import tools_path

    pj = tools_path("plotjuggler", "juggle.py")
    self.assertTrue(pj.is_file(), f"plotjuggler not found at {pj}")

  def test_tools_path_car_porting(self):
    from ai.system.paths import tools_path

    script = tools_path("car_porting", "test_car_model.py")
    self.assertTrue(script.is_file(), f"car_porting script not found at {script}")

  def test_find_params_keys(self):
    from ai.system.paths import find_repo_file

    path = find_repo_file("openpilot/common/params_keys.h", "common/params_keys.h")
    self.assertIsNotNone(path)
    assert path is not None
    self.assertTrue(path.is_file())

  def test_path_summary_includes_layout(self):
    from ai.system.paths import path_summary

    summary = path_summary()
    self.assertIn("repo_layout", summary)
    self.assertIn("openpilot_source_root", summary)
    self.assertIn(summary["repo_layout"], ("nested", "flat", "unknown"))


if __name__ == "__main__":
  unittest.main()
