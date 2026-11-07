"""Tests for issue templates and issue target resolution."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai.tools.issue_template_lib import (
  _parse_github_issue_yaml,
  get_builtin_template,
  list_builtin_templates,
  render_issue_body,
)


class TestIssueTemplates(unittest.TestCase):
  def test_builtin_templates(self):
    tpls = list_builtin_templates()
    self.assertGreaterEqual(len(tpls), 4)
    bug = get_builtin_template("bug")
    self.assertIsNotNone(bug)
    self.assertIn("bug", bug.get("labels", []))

  def test_render_body(self):
    tpl = get_builtin_template("bug")
    body = render_issue_body(tpl, {"description": "Something broke", "repro": "1. click"})
    self.assertIn("Something broke", body)
    self.assertIn("Steps to reproduce", body)

  def test_shim_exports_private_parser(self):
    parsed = _parse_github_issue_yaml("name: Test\n", "bug.yml")
    self.assertIsNotNone(parsed)
    self.assertEqual(parsed.get("name"), "Test")


class TestIssueTarget(unittest.TestCase):
  def test_assistant_upstream(self):
    from ai.tools.issue_tools import resolve_issue_target

    with patch("ai.tools.issue_tools.get_unit") as mock_unit:
      mock_unit.return_value = {
        "id": "assistant",
        "kind": "assistant",
        "branch": "main",
        "git_root": "/tmp/ai",
      }
      out = resolve_issue_target("assistant")
    self.assertTrue(out.get("ok"))
    self.assertIn("mouxangithub", out.get("repo_url", ""))


class TestPublishIssueConfig(unittest.TestCase):
  def test_issue_defaults(self):
    from ai.common.publish_config import get_publish_settings

    settings = get_publish_settings()["settings"]
    self.assertIn("issue_publish", settings)
    self.assertEqual(settings["issue_publish"]["default_template"], "bug")


if __name__ == "__main__":
  unittest.main()
