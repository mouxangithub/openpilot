"""Standalone runner to capture P1/P2 regression results to JSON."""
from __future__ import annotations

import json
import sys
import time
import traceback
import unittest
from pathlib import Path

import ai.tests.bootstrap_pc  # noqa: F401


def run_tests():
  loader = unittest.TestLoader()
  module = __import__("ai.tests.test_p1p2_regression", fromlist=["test_p1p2_regression"])
  suite = loader.loadTestsFromModule(module)

  class JSONTestResult(unittest.TestResult):
    def __init__(self):
      super().__init__()
      self.records: list[dict] = []

    def addSuccess(self, test):
      super().addSuccess(test)
      self.records.append({"test": str(test), "status": "passed"})

    def addError(self, test, err):
      super().addError(test, err)
      self.records.append({"test": str(test), "status": "error", "trace": self._fmt(err)})

    def addFailure(self, test, err):
      super().addFailure(test, err)
      self.records.append({"test": str(test), "status": "failed", "trace": self._fmt(err)})

    def _fmt(self, err):
      return "".join(traceback.format_exception(*err))

  result = JSONTestResult()
  start = time.time()
  suite.run(result)
  elapsed = time.time() - start

  passed = sum(1 for r in result.records if r["status"] == "passed")
  failed = sum(1 for r in result.records if r["status"] == "failed")
  errors = sum(1 for r in result.records if r["status"] == "error")

  return {
    "total": len(result.records),
    "passed": passed,
    "failed": failed,
    "errors": errors,
    "elapsed_seconds": elapsed,
    "records": result.records,
  }


if __name__ == "__main__":
  report = run_tests()
  out_path = Path(__file__).with_suffix(".report.json")
  out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
  print(f"REPORT_WRITTEN={out_path}")
  sys.exit(0 if report["failed"] == 0 and report["errors"] == 0 else 1)
