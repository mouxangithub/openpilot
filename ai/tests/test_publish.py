"""Tests for publish units, forge helpers, and publish target resolution."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai.tools.forge import infer_forge_from_url, parse_repo_url, repo_slug


class TestForge(unittest.TestCase):
  def test_infer_github(self):
    self.assertEqual(infer_forge_from_url("https://github.com/foo/bar"), "github")

  def test_infer_gitee(self):
    self.assertEqual(infer_forge_from_url("https://gitee.com/foo/bar"), "gitee")

  def test_parse_github(self):
    forge, owner, repo = parse_repo_url("https://github.com/mouxangithub/ai")
    self.assertEqual(forge, "github")
    self.assertEqual(repo_slug(owner, repo), "mouxangithub/ai")

  def test_parse_gitee(self):
    forge, owner, repo = parse_repo_url("https://gitee.com/user/openpilot.git")
    self.assertEqual(forge, "gitee")
    self.assertEqual(repo_slug(owner, repo), "user/openpilot")


class TestPublishTarget(unittest.TestCase):
  def test_assistant_upstream(self):
    from ai.tools.publish_tools import resolve_publish_target

    unit = {"id": "assistant", "kind": "assistant", "branch": "main"}
    out = resolve_publish_target(unit, target_mode="")
    self.assertTrue(out.get("ok"))
    self.assertEqual(out.get("target_mode"), "assistant_upstream")
    self.assertIn("mouxangithub", out.get("repo_url", ""))

  def test_project_current_remote(self):
    from ai.tools.publish_tools import resolve_publish_target

    unit = {
      "id": "openpilot",
      "kind": "project",
      "branch": "master-c3",
      "origin_url": "https://gitee.com/myuser/openpilot",
      "forge": "gitee",
    }
    with patch("ai.tools.publish_tools.project_default_mode", return_value="current_remote"):
      out = resolve_publish_target(unit, target_mode="")
    self.assertTrue(out.get("ok"))
    self.assertEqual(out.get("target_mode"), "current_remote")
    self.assertIn("gitee.com", out.get("repo_url", ""))

  def test_project_user_fork_missing(self):
    from ai.tools.publish_tools import resolve_publish_target

    unit = {"id": "openpilot", "kind": "project", "origin_url": "https://gitee.com/a/b"}
    with patch("ai.tools.publish_tools.project_fork_config", return_value=None):
      out = resolve_publish_target(unit, target_mode="user_fork")
    self.assertFalse(out.get("ok"))


class TestPublishConfig(unittest.TestCase):
  def test_defaults(self):
    from ai.common.publish_config import get_publish_settings

    data = get_publish_settings()
    self.assertTrue(data.get("ok"))
    settings = data["settings"]
    self.assertTrue(settings["assistant_publish"]["fixed_upstream"])
    self.assertEqual(settings["project_publish"]["default_mode"], "current_remote")


if __name__ == "__main__":
  unittest.main()
