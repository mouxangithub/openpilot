"""Tests for error-code taxonomy (T-P2.5, T-P2.6)."""
from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401


class TestErrorCodes(unittest.TestCase):
  def test_new_codes_exist(self):
    from ai.core.errors import ERR_DEPENDENCY_UNAVAILABLE, ERR_STATIONARY_REQUIRED
    self.assertTrue(ERR_STATIONARY_REQUIRED)
    self.assertTrue(ERR_DEPENDENCY_UNAVAILABLE)

  def test_stationary_check_returns_code(self):
    from ai.core.errors import ERR_STATIONARY_REQUIRED, tool_error
    from ai.system.safety import is_action_allowed

    err = tool_error("must be stationary", code=ERR_STATIONARY_REQUIRED)
    self.assertFalse(err["ok"])
    self.assertEqual(err["error_code"], ERR_STATIONARY_REQUIRED)
    # Verify the permission service blocks write_param while driving for non-admin.
    class _State:
      is_driving = True
      v_ego = 5.0
      enabled = True
      started = True
      ignition = True
      reader_unavailable = False
    allowed, reason = is_action_allowed("write_param", _State(), admin=False)
    self.assertFalse(allowed)
    self.assertTrue(reason)


if __name__ == "__main__":
  unittest.main()
