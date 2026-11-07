"""Unified skill catalog tests."""

from __future__ import annotations

import unittest
from unittest import mock


class UnifiedSkillCatalogTest(unittest.TestCase):
  def test_dynamic_priority_over_file(self) -> None:
    from ai.skills.unified import unified_skill_catalog
    legacy = [{"id": "dup-skill", "name": "file version"}]
    dynamic = [{"id": "dup-skill", "name": "dynamic version"}]
    with mock.patch("ai.skills.unified._legacy_entries", return_value=legacy), \
         mock.patch("ai.skills.unified._dynamic_entries", return_value=dynamic):
      cat = unified_skill_catalog()
      self.assertIn("dup-skill", cat)
      self.assertEqual(cat["dup-skill"]["name"], "dynamic version")
      self.assertEqual(cat["dup-skill"]["source"], "dynamic")

  def test_no_dynamic_keeps_file_source(self) -> None:
    from ai.skills.unified import unified_skill_catalog
    legacy = [{"id": "file-only", "name": "f"}]
    with mock.patch("ai.skills.unified._legacy_entries", return_value=legacy), \
         mock.patch("ai.skills.unified._dynamic_entries", return_value=[]):
      cat = unified_skill_catalog()
      self.assertEqual(cat["file-only"]["source"], "file")

  def test_import_errors_are_contained(self) -> None:
    from ai.skills.unified import unified_skill_catalog
    with mock.patch("ai.skills.unified._legacy_entries", side_effect=Exception("boom")), \
         mock.patch("ai.skills.unified._dynamic_entries", return_value=[]):
      self.assertEqual(unified_skill_catalog(), {})


if __name__ == "__main__":
  unittest.main()