"""Tests for @-mention context resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class TestContextResolve(unittest.TestCase):
  def test_normalize_url_adds_scheme(self):
    from ai.tools.domains.platform import context_resolve as cr

    self.assertEqual(cr._normalize_url("example.com/docs"), "https://example.com/docs")
    self.assertIsNone(cr._normalize_url("not a url"))

  def test_fetch_url_rejects_invalid(self):
    from ai.tools.domains.platform import context_resolve as cr

    result = cr.fetch_url_context("ftp://bad.example")
    self.assertFalse(result["ok"])

  def test_text_extractor_strips_html(self):
    from ai.tools.domains.platform.context_resolve import _TextExtractor

    parser = _TextExtractor()
    parser.feed("<html><head><title>T</title><style>.x{}</style></head><body><p>Hello</p></body></html>")
    self.assertIn("Hello", parser.text())
    self.assertNotIn("style", parser.text())

  def test_fetch_branch_context(self):
    from ai.tools.domains.platform import context_resolve as cr

    with patch("ai.tools.domains.devops.git_tools.git_status", return_value={"ok": True, "branch": "dev", "head": "abc", "dirty_count": 0}), \
         patch("ai.tools.domains.devops.git_tools._git", return_value={"ok": False}), \
         patch("ai.tools.domains.devops.git_tools.git_diff", return_value={"ok": True, "stdout": "diff line"}):
      result = cr.fetch_branch_context()
    self.assertTrue(result["ok"])
    self.assertIn("dev", result["content"])


if __name__ == "__main__":
  unittest.main()
