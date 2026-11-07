"""Tests for WorkflowError fatal semantics (D-P0.1)."""
from __future__ import annotations

import unittest

import ai.tests.bootstrap_pc  # noqa: F401


class TestWorkflowErrorFatal(unittest.TestCase):
  def test_default_fatal_true(self):
    from ai.core.workflow.errors import WorkflowError, WorkflowErrorCode
    err = WorkflowError("boom", WorkflowErrorCode.TOOL_FAILED)
    self.assertTrue(err.fatal)
    self.assertTrue(err.to_dict()["fatal"])

  def test_non_fatal(self):
    from ai.core.workflow.errors import WorkflowError, WorkflowErrorCode
    err = WorkflowError("inner", WorkflowErrorCode.TOOL_FAILED, fatal=False)
    self.assertFalse(err.fatal)
    self.assertFalse(err.to_dict()["fatal"])

  def test_to_dict_shape(self):
    from ai.core.workflow.errors import WorkflowError, WorkflowErrorCode
    err = WorkflowError("x", WorkflowErrorCode.TOOL_NOT_FOUND, details={"tool": "t"})
    d = err.to_dict()
    self.assertFalse(d["ok"])
    self.assertEqual(d["code"], "WF_TOOL_NOT_FOUND")
    self.assertEqual(d["details"]["tool"], "t")


if __name__ == "__main__":
  unittest.main()