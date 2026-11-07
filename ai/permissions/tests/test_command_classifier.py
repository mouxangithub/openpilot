"""Tests for CommandSafetyClassifier."""

from __future__ import annotations

import unittest

from ai.permissions.command_classifier import CommandSafetyClassifier, SafetyTier


class TestCommandSafetyClassifier(unittest.TestCase):
  def test_blocked(self) -> None:
    svc = CommandSafetyClassifier()
    result = svc.check("rm -rf /")
    self.assertFalse(result["allowed"])
    self.assertEqual(result["tier"], SafetyTier.BLOCKED.value)

  def test_safe(self) -> None:
    svc = CommandSafetyClassifier()
    result = svc.check("ls -la")
    self.assertTrue(result["allowed"])
    self.assertEqual(result["tier"], SafetyTier.SAFE.value)

  def test_readonly_blocks_destructive(self) -> None:
    svc = CommandSafetyClassifier()
    result = svc.check("rm -rf build/", policy_mode="read-only")
    self.assertFalse(result["allowed"])


if __name__ == "__main__":
  unittest.main()
