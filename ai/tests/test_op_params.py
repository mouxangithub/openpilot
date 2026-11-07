"""Tests for openpilot Params native lib compatibility helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.common.op_params import (
  detect_params_native_kind,
  find_params_native_so,
  scons_native_targets,
)


class OpParamsCompatTest(unittest.TestCase):
  def test_find_prefers_libparams_c_when_both_exist(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "common").mkdir()
      (root / "common" / "params_pyx.so").write_bytes(b"legacy")
      (root / "common" / "libparams_c.so").write_bytes(b"new")
      so = find_params_native_so(root)
      self.assertEqual(so, root / "common" / "libparams_c.so")

  def test_find_legacy_params_pyx_only(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "openpilot" / "common").mkdir(parents=True)
      (root / "openpilot" / "common" / "params_pyx.so").write_bytes(b"legacy")
      self.assertEqual(find_params_native_so(root), root / "openpilot" / "common" / "params_pyx.so")

  def test_detect_from_params_py_libparams_c(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "openpilot" / "common").mkdir(parents=True)
      (root / "openpilot" / "common" / "params.py").write_text(
        'lib = ctypes.CDLL("libparams_c.so")\n',
        encoding="utf-8",
      )
      self.assertEqual(detect_params_native_kind(root), "libparams_c")

  def test_detect_from_params_py_params_pyx(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "common").mkdir()
      (root / "common" / "params.py").write_text(
        "from openpilot.common import params_pyx\n",
        encoding="utf-8",
      )
      self.assertEqual(detect_params_native_kind(root), "params_pyx")

  def test_scons_targets_legacy_first(self):
    self.assertEqual(
      scons_native_targets("params_pyx"),
      ["openpilot/common/params_pyx.so", "common/params_pyx.so"],
    )


if __name__ == "__main__":
  unittest.main()
