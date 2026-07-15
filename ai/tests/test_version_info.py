"""Tests for ai package version / update helpers."""

from __future__ import annotations

import unittest
from unittest import mock

from ai import version_info as vi


class TestVersionInfo(unittest.TestCase):
  def test_read_version(self):
    v = vi.read_version()
    self.assertRegex(v, r"^\d+\.\d+\.\d+")

  def test_version_lt(self):
    self.assertTrue(vi.version_lt("0.1.0", "0.2.0"))
    self.assertFalse(vi.version_lt("0.2.0", "0.1.0"))

  def test_check_update_newer_remote(self):
    with mock.patch.object(vi, "package_info", return_value={"ok": True, "version": "0.1.0", "is_git_install": False}):
      with mock.patch.object(vi, "_fetch_remote_version_git", return_value={"remote_version": None, "remote_commit": None}):
        with mock.patch.object(vi, "_fetch_remote_version_http", return_value="0.2.0"):
          out = vi.check_update(fetch_remote=True)
    self.assertTrue(out["update_available"])
    self.assertEqual(out["remote_version"], "0.2.0")


if __name__ == "__main__":
  unittest.main()
