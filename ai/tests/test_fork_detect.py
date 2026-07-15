"""Tests for dynamic fork scan / detect."""

from __future__ import annotations

import unittest
from pathlib import Path

from ai.fork.detect_fork import detect_fork
from ai.fork.repo_scan import derive_fork_identity, scan_openpilot_repo
from ai.install.integrate_openpilot import collect_ai_params


class TestRepoScan(unittest.TestCase):
  def test_scan_openpilot_tree(self):
    root = Path(__file__).resolve().parents[2]
    scan = scan_openpilot_repo(root)
    self.assertTrue(scan.get("openpilot_root"))
    self.assertIsNotNone(scan.get("git_branch"))

  def test_derive_identity_not_fixed_enum(self):
    root = Path(__file__).resolve().parents[2]
    scan = scan_openpilot_repo(root)
    identity = derive_fork_identity(scan)
    self.assertTrue(identity.get("fork_id"))
    self.assertTrue(identity.get("fork_label"))
    self.assertIn(identity.get("confidence"), ("low", "medium", "high"))


class TestDetectFork(unittest.TestCase):
  def test_detect_returns_scan(self):
    root = Path(__file__).resolve().parents[2]
    out = detect_fork(root)
    self.assertTrue(out.get("ok"))
    self.assertIn("scan", out)
    self.assertIn(out.get("mode"), ("repository_scan", "ai_cached"))


class TestIntegrateParams(unittest.TestCase):
  def test_collect_ai_params(self):
    ai_dir = Path(__file__).resolve().parents[1]
    params = collect_ai_params(ai_dir)
    self.assertIn("ai_provider", params)
    self.assertIn("ai_first_run_done", params)


if __name__ == "__main__":
  unittest.main()
