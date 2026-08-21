"""Tests for ai config store (no openpilot compile required)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class TestAiConfigStore(unittest.TestCase):
  def test_roundtrip_and_defaults(self):
    from ai.common.config_store import reset_config_store_for_tests

    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / "config.json"
      store = reset_config_store_for_tests(path)
      self.assertEqual(store.get("ai_provider"), "opencode-zen")
      store.put("ai_api_key", "secret")
      self.assertEqual(store.get("ai_api_key"), "secret")
      store.put_bool("ai_admin_mode", False)
      self.assertFalse(store.get_bool("ai_admin_mode"))
      reloaded = json.loads(path.read_text(encoding="utf-8"))
      self.assertEqual(reloaded["ai_api_key"], "secret")

  def test_put_param_routes_ai_keys(self):
    from ai.common.config_store import reset_config_store_for_tests
    from ai.tools.param_write import put_param

    with tempfile.TemporaryDirectory() as tmp:
      reset_config_store_for_tests(Path(tmp) / "config.json")
      try:
        from openpilot.common.params import Params
      except ModuleNotFoundError:
        self.skipTest("openpilot runtime not available")
      p = Params()
      put_param(p, "ai_model", "test-model")
      from ai.common.config_store import get_config_store
      self.assertEqual(get_config_store().get("ai_model"), "test-model")


if __name__ == "__main__":
  unittest.main()
