"""Semver boundary tests for ai.skill.semver."""

from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401

from ai.skill.semver import Semver


class SemverTests(unittest.TestCase):
  def test_parse_standard(self):
    v = Semver.parse("1.2.3")
    self.assertEqual(v.major, 1)
    self.assertEqual(v.minor, 2)
    self.assertEqual(v.patch, 3)

  def test_parse_prerelease_and_build(self):
    v = Semver.parse("1.2.3-alpha.1+build.2")
    self.assertEqual(v.prerelease, "alpha.1")
    self.assertEqual(v.build, "build.2")

  def test_numeric_comparison(self):
    self.assertLess(Semver.parse("1.2.0"), Semver.parse("1.10.0"))
    self.assertLess(Semver.parse("1.10.0"), Semver.parse("2.0.0"))

  def test_prerelease_precedence(self):
    self.assertLess(Semver.parse("2.0.0-alpha"), Semver.parse("2.0.0"))
    self.assertLess(Semver.parse("2.0.0-alpha"), Semver.parse("2.0.0-alpha.1"))
    self.assertLess(Semver.parse("2.0.0-alpha.1"), Semver.parse("2.0.0-beta"))

  def test_exact_constraint(self):
    self.assertTrue(Semver.parse("1.2.3").satisfies("=1.2.3"))
    self.assertFalse(Semver.parse("1.2.3").satisfies("=1.2.4"))

  def test_gte_constraint(self):
    self.assertTrue(Semver.parse("1.2.3").satisfies(">=1.2.0"))
    self.assertTrue(Semver.parse("1.2.3").satisfies(">=1.2.3"))
    self.assertFalse(Semver.parse("1.2.3").satisfies(">=1.3.0"))

  def test_lt_constraint(self):
    self.assertTrue(Semver.parse("1.2.3").satisfies("<2.0.0"))
    self.assertFalse(Semver.parse("1.2.3").satisfies("<1.2.3"))

  def test_caret_constraint(self):
    self.assertTrue(Semver.parse("1.2.3").satisfies("^1.0.0"))
    self.assertTrue(Semver.parse("1.9.9").satisfies("^1.2.3"))
    self.assertFalse(Semver.parse("2.0.0").satisfies("^1.2.3"))
    self.assertFalse(Semver.parse("1.2.2").satisfies("^1.2.3"))

  def test_tilde_constraint(self):
    self.assertTrue(Semver.parse("1.2.5").satisfies("~1.2.3"))
    self.assertFalse(Semver.parse("1.3.0").satisfies("~1.2.3"))
    self.assertFalse(Semver.parse("1.2.2").satisfies("~1.2.3"))

  def test_from_string_invalid_returns_zero(self):
    v = Semver.from_string("not-a-version")
    self.assertEqual(v.major, 0)
    self.assertEqual(v.minor, 0)
    self.assertEqual(v.patch, 0)

  def test_equality_with_string(self):
    self.assertEqual(Semver.parse("1.2.3"), "1.2.3")
    self.assertNotEqual(Semver.parse("1.2.3"), "1.2.4")


if __name__ == "__main__":
  unittest.main()
