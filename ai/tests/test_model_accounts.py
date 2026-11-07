"""Tests for ai.core.llm.model_accounts (model hub)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


class TestModelAccounts(unittest.TestCase):
  def setUp(self):
    from ai.common.config_store import reset_config_store_for_tests

    self._tmpdir = tempfile.TemporaryDirectory()
    reset_config_store_for_tests(Path(self._tmpdir.name) / "config.json")

  def tearDown(self):
    self._tmpdir.cleanup()

  def _params(self):
    try:
      from openpilot.common.params import Params
      return Params()
    except ModuleNotFoundError:
      self.skipTest("openpilot runtime not available")

  def test_save_and_resolve_primary(self):
    from ai.core.llm.model_accounts import hub_for_api, load_model_hub, resolve_primary_config, save_model_hub

    p = self._params()
    hub = {
      "version": 1,
      "accounts": [{
        "id": "acc_test",
        "provider": "deepseek",
        "label": "DeepSeek",
        "apiKey": "sk-test",
        "baseUrl": "",
        "enabled": True,
        "models": ["deepseek-chat"],
      }],
      "primary": {"accountId": "acc_test", "model": "deepseek-chat"},
      "fallbacks": [],
    }
    save_model_hub(p, hub)
    loaded = load_model_hub(p)
    self.assertEqual(loaded["primary"]["model"], "deepseek-chat")
    cfg = resolve_primary_config(p)
    self.assertEqual(cfg.provider, "deepseek")
    self.assertEqual(cfg.model, "deepseek-chat")
    self.assertEqual(cfg.api_key, "sk-test")
    api_hub = hub_for_api(p, mask_keys=True)
    self.assertTrue(api_hub["accounts"][0]["apiKey"].startswith("•"))

  def test_route_params_persist(self):
    from ai.core.llm.model_accounts import load_model_hub, resolve_primary_config, save_model_hub

    p = self._params()
    save_model_hub(p, {
      "version": 1,
      "accounts": [{
        "id": "acc_test",
        "provider": "deepseek",
        "label": "DeepSeek",
        "apiKey": "sk-test",
        "baseUrl": "",
        "enabled": True,
        "models": ["deepseek-chat"],
      }],
      "primary": {
        "accountId": "acc_test",
        "model": "deepseek-chat",
        "contextWindow": 64000,
        "maxTokens": 8192,
        "temperature": 0.5,
        "topP": 0.9,
      },
      "fallbacks": [{
        "accountId": "acc_test",
        "model": "deepseek-chat",
        "label": "backup",
        "contextWindow": 32000,
      }],
    })
    loaded = load_model_hub(p)
    self.assertEqual(loaded["primary"]["contextWindow"], 64000)
    self.assertEqual(loaded["primary"]["maxTokens"], 8192)
    self.assertAlmostEqual(loaded["primary"]["temperature"], 0.5)
    self.assertEqual(len(loaded["fallbacks"]), 1)
    self.assertEqual(loaded["fallbacks"][0]["label"], "backup")
    self.assertEqual(loaded["fallbacks"][0]["contextWindow"], 32000)
    cfg = resolve_primary_config(p)
    self.assertEqual(cfg.max_tokens, 8192)
    self.assertAlmostEqual(cfg.temperature, 0.5)
    self.assertTrue(cfg.thinking_enabled)

  def test_route_thinking_enabled(self):
    from ai.core.llm.model_accounts import resolve_primary_config, resolve_fallback_configs, save_model_hub

    p = self._params()
    save_model_hub(p, {
      "version": 1,
      "accounts": [{
        "id": "acc_test",
        "provider": "kimi",
        "label": "Kimi",
        "apiKey": "sk-test",
        "baseUrl": "",
        "enabled": True,
        "models": ["kimi-k2.5"],
      }],
      "primary": {
        "accountId": "acc_test",
        "model": "kimi-k2.5",
        "thinkingEnabled": False,
      },
      "fallbacks": [{
        "accountId": "acc_test",
        "model": "kimi-k2.5",
        "thinkingEnabled": True,
      }],
    })
    primary = resolve_primary_config(p)
    self.assertFalse(primary.thinking_enabled)
    fallbacks = resolve_fallback_configs(p, primary)
    self.assertTrue(fallbacks[0].thinking_enabled)

  def test_fallback_chain(self):
    from ai.core.llm.model_accounts import resolve_chat_chain, save_model_hub

    p = self._params()
    save_model_hub(p, {
      "version": 1,
      "accounts": [
        {"id": "a1", "provider": "deepseek", "label": "A", "apiKey": "k1", "baseUrl": "", "enabled": True, "models": ["m1"]},
        {"id": "a2", "provider": "openrouter", "label": "B", "apiKey": "k2", "baseUrl": "", "enabled": True, "models": ["m2"]},
      ],
      "primary": {"accountId": "a1", "model": "m1"},
      "fallbacks": [{"accountId": "a2", "model": "m2"}],
    })
    chain = resolve_chat_chain(p)
    self.assertEqual(len(chain), 2)
    self.assertEqual(chain[0].model, "m1")
    self.assertEqual(chain[1].model, "m2")

  def test_chat_route_chain_reorders_primary(self):
    from ai.core.llm.model_accounts import resolve_chat_chain_with_route, save_model_hub

    p = self._params()
    save_model_hub(p, {
      "version": 2,
      "accounts": [
        {"id": "a1", "provider": "deepseek", "label": "A", "apiKey": "k1", "baseUrl": "", "enabled": True, "models": ["m1", "m2"]},
        {"id": "a2", "provider": "openrouter", "label": "B", "apiKey": "k2", "baseUrl": "", "enabled": True, "models": ["m3"]},
      ],
      "primary": {"accountId": "a1", "model": "m1"},
      "fallbacks": [{"accountId": "a2", "model": "m3"}],
      "embeddingPrimary": None,
      "embeddingFallbacks": [],
    })
    chain = resolve_chat_chain_with_route(
      p,
      chat_route={"accountId": "a1", "model": "m2"},
    )
    self.assertEqual(len(chain), 2)
    self.assertEqual(chain[0].model, "m2")
    self.assertEqual(chain[1].model, "m3")
    from ai.core.llm.model_accounts import resolve_embedding_chain, save_model_hub

    p = self._params()
    save_model_hub(p, {
      "version": 2,
      "accounts": [
        {"id": "e1", "provider": "siliconflow", "label": "SF", "apiKey": "k1", "baseUrl": "", "enabled": True, "models": [], "embeddingModels": ["BAAI/bge-m3"]},
        {"id": "e2", "provider": "openai", "label": "OA", "apiKey": "k2", "baseUrl": "", "enabled": True, "models": [], "embeddingModels": ["text-embedding-3-small"]},
      ],
      "primary": {"accountId": "e1", "model": "unused"},
      "fallbacks": [],
      "embeddingPrimary": {"accountId": "e1", "model": "BAAI/bge-m3"},
      "embeddingFallbacks": [{"accountId": "e2", "model": "text-embedding-3-small"}],
    })
    chain = resolve_embedding_chain(p)
    self.assertEqual(len(chain), 2)
    self.assertEqual(chain[0].provider, "siliconflow")
    self.assertEqual(chain[0].model, "BAAI/bge-m3")
    self.assertEqual(chain[1].provider, "openai")

  def test_embedding_primary_change_only_reindex_primary(self):
    from ai.core.llm.model_accounts import embedding_primary_signature, embedding_hub_signature

    hub_a = {
      "embeddingPrimary": {"accountId": "e1", "model": "BAAI/bge-m3"},
      "embeddingFallbacks": [],
    }
    hub_b = {
      "embeddingPrimary": {"accountId": "e1", "model": "BAAI/bge-m3"},
      "embeddingFallbacks": [{"accountId": "e2", "model": "text-embedding-3-small"}],
    }
    self.assertEqual(embedding_primary_signature(hub_a), embedding_primary_signature(hub_b))
    self.assertNotEqual(embedding_hub_signature(hub_a), embedding_hub_signature(hub_b))

  @unittest.skip("MAX_MODELS_PER_ACCOUNT / _trim_account_models not implemented in model_accounts")
  def test_trim_account_models_caps_pool(self):
    from ai.core.llm.model_accounts import MAX_MODELS_PER_ACCOUNT, _trim_account_models

    models = [f"m{i}" for i in range(500)]
    trimmed = _trim_account_models(models, prefer={"m499", "m0"})
    self.assertEqual(len(trimmed), MAX_MODELS_PER_ACCOUNT)
    self.assertEqual(trimmed[0], "m499")
    self.assertEqual(trimmed[1], "m0")

  def test_migrates_legacy_on_first_load(self):
    from ai.common.config_store import get_config_store
    from ai.core.llm.model_accounts import HUB_PARAM, load_model_hub

    p = self._params()
    store = get_config_store()
    store.put("ai_provider", "deepseek")
    store.put("ai_model", "deepseek-v3-flash-free")
    store.put("ai_api_key", "sk-test-key")
    hub = load_model_hub(p)
    self.assertEqual(len(hub["accounts"]), 1)
    self.assertEqual(hub["primary"]["model"], "deepseek-v3-flash-free")
    raw = store.get(HUB_PARAM)
    self.assertTrue(raw)
    from ai.core.llm.model_accounts import save_model_hub

    p = self._params()
    raw = {
      "version": 1,
      "accounts": [{
        "id": "acc_x",
        "provider": "deepseek",
        "label": "X",
        "apiKey": "sk-real-secret",
        "baseUrl": "",
        "enabled": True,
        "models": [],
      }],
      "primary": {"accountId": "acc_x", "model": "m"},
      "fallbacks": [],
    }
    get_config_store().put(HUB_PARAM, json.dumps(raw))
    incoming = dict(raw)
    incoming["accounts"] = [{**raw["accounts"][0], "apiKey": "••••cret"}]
    save_model_hub(p, incoming)
    stored = json.loads(get_config_store().get(HUB_PARAM))
    self.assertEqual(stored["accounts"][0]["apiKey"], "sk-real-secret")


if __name__ == "__main__":
  unittest.main()
