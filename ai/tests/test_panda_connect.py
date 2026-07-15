"""Tests for comma device panda / pandad variant selection."""

from __future__ import annotations

import os
import sys
import types
from unittest import mock

import pytest

from ai.tsk.lib import panda_connect as pc


@pytest.fixture(autouse=True)
def _reset_panda_connect_state():
  with mock.patch.object(pc, "_query_panda_mcu_type", return_value=None):
    with mock.patch.object(pc, "has_panda_tici", return_value=True):
      with mock.patch.object(pc, "has_pandad_tici", return_value=True):
        yield


def test_dos_from_env():
  with mock.patch.dict(os.environ, {"TICI_DOS": "1"}, clear=False):
    assert pc.is_tici_dos() is True
    assert pc.panda_backend() == "panda_tici"
    assert pc.pandad_process_name() == "pandad_tici"


def test_tres_from_env():
  with mock.patch.dict(os.environ, {"TICI_TRES": "1"}, clear=False):
    assert pc.is_tici_dos() is False
    assert pc.panda_backend() == "panda"
    assert pc.pandad_process_name() == "pandad"


def test_c3_tici_device_type_is_dos():
  env = {k: v for k, v in os.environ.items() if k not in ("TICI_DOS", "TICI_TRES")}
  with mock.patch.dict(os.environ, env, clear=True):
    with mock.patch.object(pc, "get_device_type", return_value="tici"):
      assert pc.is_tici_dos() is True
      assert pc.panda_backend() == "panda_tici"


def test_c3x_tizi_device_type_is_tres():
  env = {k: v for k, v in os.environ.items() if k not in ("TICI_DOS", "TICI_TRES")}
  with mock.patch.dict(os.environ, env, clear=True):
    with mock.patch.object(pc, "get_device_type", return_value="tizi"):
      assert pc.is_tici_dos() is False
      assert pc.panda_backend() == "panda"


def test_c4_mici_device_type_is_tres():
  env = {k: v for k, v in os.environ.items() if k not in ("TICI_DOS", "TICI_TRES")}
  with mock.patch.dict(os.environ, env, clear=True):
    with mock.patch.object(pc, "get_device_type", return_value="mici"):
      assert pc.is_tici_dos() is False
      assert pc.panda_backend() == "panda"


def test_dos_from_mcu_cache():
  env = {k: v for k, v in os.environ.items() if k not in ("TICI_DOS", "TICI_TRES")}
  with mock.patch.dict(os.environ, env, clear=True):
    with mock.patch.object(pc, "get_device_type", return_value=None):
      with mock.patch.object(pc, "is_comma_hw", return_value=True):
        with mock.patch.object(pc, "_read_mcu_cache", return_value="F4"):
          assert pc.is_tici_dos() is True


def test_pc_dev_defaults_to_panda():
  env = {k: v for k, v in os.environ.items() if k not in ("TICI_DOS", "TICI_TRES", "TICI_HW")}
  with mock.patch.dict(os.environ, env, clear=True):
    with mock.patch.object(pc, "get_device_type", return_value=None):
      with mock.patch.object(pc, "is_comma_hw", return_value=False):
        assert pc.is_tici_dos() is False
        assert pc.panda_backend() == "panda"


def test_tici_info_includes_device_type():
  with mock.patch.object(pc, "get_device_type", return_value="tizi"):
    with mock.patch.object(pc, "is_tici_dos", return_value=False):
      info = pc.tici_info()
      assert info["device_type"] == "tizi"
      assert info["product_label"] == "C3X"
      assert info["product_name"] == "comma threeX"
      assert info["panda_backend"] == "panda"


def test_dos_falls_back_without_tici_packages():
  with mock.patch.dict(os.environ, {"TICI_DOS": "1"}, clear=False):
    with mock.patch.object(pc, "has_panda_tici", return_value=False):
      with mock.patch.object(pc, "has_pandad_tici", return_value=False):
        assert pc.use_tici_panda_stack() is False
        assert pc.panda_backend() == "panda"
        assert pc.pandad_process_name() == "pandad"
        assert pc.pandad_module() == pc.PANDAD_MODULE


def test_dos_requires_both_tici_packages():
  with mock.patch.dict(os.environ, {"TICI_DOS": "1"}, clear=False):
    with mock.patch.object(pc, "has_panda_tici", return_value=True):
      with mock.patch.object(pc, "has_pandad_tici", return_value=False):
        assert pc.use_tici_panda_stack() is False
        assert pc.panda_backend() == "panda"


def test_probe_pc_panda_f4_fallback_without_pandad_tici():
  class FakePanda:
    def __init__(self, cli=False):
      pass

    def get_mcu_type(self):
      return "STM32F4"

    def close(self):
      pass

  fake_mod = types.ModuleType("panda_tici")
  fake_mod.Panda = FakePanda
  with mock.patch.object(pc, "has_panda_tici", return_value=True):
    with mock.patch.object(pc, "has_pandad_tici", return_value=False):
      with mock.patch.dict(sys.modules, {"panda_tici": fake_mod}):
        probe = pc.probe_pc_panda()
  assert probe["panda_mcu"] == "F4"
  assert probe["panda_backend"] == "panda"
  assert probe["pandad_process"] == "pandad"


def test_stop_pandad_uses_module_pattern():
  with mock.patch.object(pc, "pandad_module", return_value="selfdrive.pandad_tici.pandad"):
    with mock.patch("ai.tsk.lib.panda_connect.subprocess.run") as run:
      pc.stop_pandad()
      run.assert_called_once()
      assert run.call_args.args[0] == ["pkill", "-9", "-f", "selfdrive.pandad_tici.pandad"]


def test_probe_pc_panda_f4():
  class FakePanda:
    def __init__(self, cli=False):
      pass

    def get_mcu_type(self):
      return "STM32F4"

    def close(self):
      pass

  fake_mod = types.ModuleType("panda_tici")
  fake_mod.Panda = FakePanda
  with mock.patch.dict(sys.modules, {"panda_tici": fake_mod}):
    probe = pc.probe_pc_panda()
  assert probe["connected"] is True
  assert probe["panda_mcu"] == "F4"
  assert probe["panda_backend"] == "panda_tici"
  assert probe["inferred_class"] == "C3"


def test_probe_pc_panda_h7():
  class FakePanda:
    def __init__(self, cli=False):
      pass

    def get_mcu_type(self):
      return "STM32H7"

    def close(self):
      pass

  fake_mod = types.ModuleType("panda_tici")
  fake_mod.Panda = FakePanda
  with mock.patch.dict(sys.modules, {"panda_tici": fake_mod}):
    probe = pc.probe_pc_panda()
  assert probe["panda_mcu"] == "H7"
  assert probe["panda_backend"] == "panda"
  assert probe["inferred_class"] == "C3X/C4"


def test_host_hardware_profile_on_pc():
  with mock.patch.object(pc, "is_comma_hw", return_value=False):
    with mock.patch.object(pc, "is_manager_running", return_value=False):
      with mock.patch.object(pc, "is_pandad_running", return_value=False):
        with mock.patch.object(pc, "probe_pc_panda", return_value={"connected": False, "probe": "panda_tici", "error": "no device"}):
          profile = pc.host_hardware_profile()
  assert profile["host_kind_label"] == "PC"
  assert profile["panda_connected"] is False
