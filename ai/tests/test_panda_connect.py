"""Tests for comma device panda / pandad (unified stack)."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_panda_connect():
  path = Path(__file__).resolve().parents[1] / "tsk" / "lib" / "panda_connect.py"
  spec = importlib.util.spec_from_file_location("panda_connect_under_test", path)
  mod = importlib.util.module_from_spec(spec)
  assert spec.loader is not None
  spec.loader.exec_module(mod)
  return mod


pc = _load_panda_connect()


class TestPandaConnect(unittest.TestCase):
  def setUp(self):
    self._patcher = mock.patch.object(pc, "_query_panda_mcu_type", return_value=None)
    self._patcher.start()

  def tearDown(self):
    self._patcher.stop()

  def test_dos_from_env(self):
    with mock.patch.dict(os.environ, {"TICI_DOS": "1"}, clear=False):
      self.assertTrue(pc.is_tici_dos())
      self.assertEqual(pc.panda_backend(), "panda")
      self.assertEqual(pc.pandad_process_name(), "pandad")

  def test_tres_from_env(self):
    with mock.patch.dict(os.environ, {"TICI_TRES": "1"}, clear=False):
      self.assertFalse(pc.is_tici_dos())
      self.assertEqual(pc.panda_backend(), "panda")
      self.assertEqual(pc.pandad_process_name(), "pandad")

  def test_c3_tici_device_type_is_dos(self):
    env = {k: v for k, v in os.environ.items() if k not in ("TICI_DOS", "TICI_TRES")}
    with mock.patch.dict(os.environ, env, clear=True):
      with mock.patch.object(pc, "get_device_type", return_value="tici"):
        self.assertTrue(pc.is_tici_dos())
        self.assertEqual(pc.panda_backend(), "panda")

  def test_pandad_module_matches_stack(self):
    self.assertIn("pandad", pc.pandad_module())
    self.assertIn(pc.pandad_process_name(), ("pandad", "pandad_tici"))

  def test_has_panda_tici_reflects_tree(self):
    from ai.system import panda_stack as ps
    with mock.patch.object(ps, "has_panda_tici_tree", return_value=True):
      self.assertTrue(pc.has_panda_tici())
    with mock.patch.object(ps, "has_panda_tici_tree", return_value=False):
      self.assertFalse(pc.has_panda_tici())

  def test_probe_pc_panda_f4(self):
    class FakePanda:
      def __init__(self, cli=False):
        pass

      def get_mcu_type(self):
        return "STM32F4"

      def close(self):
        pass

    fake_mod = types.ModuleType("panda")
    fake_mod.Panda = FakePanda
    with mock.patch.dict(sys.modules, {"panda": fake_mod}):
      probe = pc.probe_pc_panda()
    self.assertTrue(probe["connected"])
    self.assertEqual(probe["panda_mcu"], "F4")
    self.assertEqual(probe["panda_backend"], "panda")

  def test_stop_pandad_uses_module_pattern(self):
    with mock.patch.object(pc, "pandad_module", return_value="selfdrive.pandad.pandad"):
      with mock.patch.object(pc.subprocess, "run") as run:
        pc.stop_pandad()
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["pkill", "-9", "-f", "selfdrive.pandad.pandad"])


if __name__ == "__main__":
  unittest.main()
