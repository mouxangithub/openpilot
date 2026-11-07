"""Tests for G12 startup diagnostics."""
from __future__ import annotations
import unittest

from ai.core import diagnostics
from ai.core.errors import ERR_STARTUP_DIAG


class DiagnosticsTest(unittest.TestCase):
  def test_run_never_raises(self) -> None:
    result = diagnostics.run_startup_diagnostics()
    self.assertIsInstance(result.checks, list)
    self.assertTrue(len(result.checks) > 0)

  def test_core_imports_pass(self) -> None:
    result = diagnostics.run_startup_diagnostics()
    for check in result.checks:
      if check["name"].startswith("import:ai.core") and check["severity"] == "fatal":
        self.assertTrue(check["ok"], msg=f"fatal core check failed: {check}")

  def test_error_code_present_on_failure(self) -> None:
    # Force a failing check by importing a bogus module via the private helper.
    check = diagnostics._check_import("ai.does_not_exist_module", fatal=True)
    self.assertFalse(check["ok"])
    self.assertEqual(check["error_code"], ERR_STARTUP_DIAG)


if __name__ == "__main__":
  unittest.main()