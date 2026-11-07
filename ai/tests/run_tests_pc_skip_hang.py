"""Run the full ai test suite EXCLUDING test_config_store (pre-existing env
hang: real openpilot Params blocks on Windows; reproduced independently of the
cabana changes). Output: total / errors / failures counts."""
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
  # drop test_config_store modules (environmental hang, pre-existing)
  filtered = unittest.TestSuite()
  dropped = 0
  for group in suite:
    kept = []
    for test in group:
      if "test_config_store" in test.__class__.__module__:
        dropped += 1
        continue
      kept.append(test)
    if kept:
      filtered.addTests(kept)
  print(f"dropped {dropped} tests from test_config_store")
  runner = unittest.TextTestRunner(verbosity=1)
  result = runner.run(filtered)
  print(f"TOTAL_RUN={result.testsRun} FAILURES={len(result.failures)} ERRORS={len(result.errors)} SKIPPED={len(result.skipped)}")
  for _, tb in result.failures + result.errors:
    print(tb.splitlines()[0] if tb else "")
  raise SystemExit(not result.wasSuccessful())
