"""Run ai unit tests on PC with openpilot mocks installed."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import ai.tests.bootstrap_pc  # noqa: F401 — side effect: mocks

if __name__ == "__main__":
  loader = unittest.TestLoader()
  suite = loader.discover("ai/tests", pattern="test_*.py")
  runner = unittest.TextTestRunner(verbosity=2)
  raise SystemExit(not runner.run(suite).wasSuccessful())
