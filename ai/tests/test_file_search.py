"""Tests for file search indexing and scoring."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class TestFileSearch(unittest.TestCase):
  def test_score_prefers_openpilot_priority(self):
    from ai.tools.domains.platform import file_search as fs

    op_entry = {"name": "car_helpers.py", "rel": "opendbc/car/car_helpers.py", "root": "openpilot", "priority": 100}
    data_entry = {"name": "car_helpers.py", "rel": "data/tmp/car_helpers.py", "root": "data", "priority": 70}
    op_score = fs._score("car_helpers", op_entry)
    data_score = fs._score("car_helpers", data_entry)
    self.assertGreater(op_score, data_score)

  def test_build_index_from_temp_repo(self):
    from ai.tools.domains.platform import file_search as fs

    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "selfdrive").mkdir()
      (root / "selfdrive" / "controls.py").write_text("x = 1\n", encoding="utf-8")
      fs.invalidate_file_index()
      with patch.object(fs, "openpilot_root", return_value=root), patch.object(fs, "is_comma_device", return_value=False):
        fs.invalidate_file_index()
        result = fs.search_repo_files("controls", limit=10)
      self.assertTrue(result["ok"])
      self.assertGreaterEqual(len(result["files"]), 1)
      self.assertEqual(result["files"][0]["root"], "openpilot")

  def test_search_includes_directories(self):
    from ai.tools.domains.platform import file_search as fs

    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "opendbc_repo").mkdir()
      (root / "opendbc_repo" / "README.md").write_text("hi\n", encoding="utf-8")
      fs.invalidate_file_index()
      with patch.object(fs, "openpilot_root", return_value=root), patch.object(fs, "is_comma_device", return_value=False):
        fs.invalidate_file_index()
        result = fs.search_repo_files("opendbc", limit=10)
      self.assertTrue(result["ok"])
      kinds = {item.get("kind") for item in result["files"]}
      self.assertIn("dir", kinds)
      self.assertEqual(result["files"][0]["kind"], "dir")
      self.assertEqual(result["files"][0]["name"], "opendbc_repo")


if __name__ == "__main__":
  unittest.main()
