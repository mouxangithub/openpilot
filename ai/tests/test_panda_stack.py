"""Tests for fork-aware panda stack detection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class PandaStackTests(unittest.TestCase):
  def test_unified_stack_on_sp_repo(self):
    from ai.system import panda_stack as ps

    with mock.patch.object(ps, "openpilot_root", return_value=ROOT):
      with mock.patch.object(ps, "has_panda_tici_tree", return_value=False):
        with mock.patch.object(ps, "has_pandad_tici_tree", return_value=False):
          with mock.patch.object(ps, "has_pandad_tree", return_value=True):
            with mock.patch.object(ps, "has_panda_tree", return_value=True):
              self.assertEqual(ps.stack_kind(), "unified")
              self.assertEqual(ps.resolve_pandad_module(), "selfdrive.pandad.pandad")
              self.assertFalse(ps.use_tici_panda_stack())

  def test_dp_style_split_stack(self):
    from ai.system import panda_stack as ps

    with mock.patch.object(ps, "has_panda_tici_tree", return_value=True):
      with mock.patch.object(ps, "has_pandad_tici_tree", return_value=True):
        with mock.patch.object(ps, "has_pandad_tree", return_value=False):
          with mock.patch.object(ps, "has_panda_tree", return_value=True):
            self.assertEqual(ps.stack_kind(), "panda_tici_pandad_tici")
            self.assertTrue(ps.use_tici_panda_stack())
            self.assertEqual(ps.resolve_pandad_module(), "selfdrive.pandad_tici.pandad")
            self.assertEqual(ps.resolve_panda_backend(for_h7=True), "panda_tici")

  def test_panda_tici_without_pandad_tici(self):
    from ai.system import panda_stack as ps

    with mock.patch.object(ps, "has_panda_tici_tree", return_value=True):
      with mock.patch.object(ps, "has_pandad_tici_tree", return_value=False):
        with mock.patch.object(ps, "has_pandad_tree", return_value=True):
          self.assertEqual(ps.stack_kind(), "panda_tici_pandad")
          self.assertEqual(ps.resolve_pandad_module(), "selfdrive.pandad.pandad")


if __name__ == "__main__":
  unittest.main()
