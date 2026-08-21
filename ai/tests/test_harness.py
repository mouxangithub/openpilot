"""Tests for WorkBuddy-style harness improvements."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import ai.tests.bootstrap_pc  # noqa: F401 — mocks openpilot on PC


class DeferredLoadingTests(unittest.TestCase):
  @patch("ai.tools.deferred_loading.deferred_loading_enabled", return_value=True)
  def test_search_and_load_tools(self, _enabled):
    from ai.tools.deferred_loading import (
      apply_deferred_filter,
      handle_load_tool,
      handle_search_tools,
      reset_session,
      session_key,
    )

    catalog = [
      {"type": "function", "function": {"name": "get_vehicle_state", "description": "vehicle"}},
      {"type": "function", "function": {"name": "git_commit", "description": "commit git changes"}},
      {"type": "function", "function": {"name": "write_params", "description": "write parameters"}},
    ]
    key = session_key("sess1", "")
    reset_session(key)
    filtered = apply_deferred_filter(catalog, key)
    names = {t["function"]["name"] for t in (filtered or [])}
    self.assertIn("search_tools", names)
    self.assertIn("load_tool", names)
    self.assertIn("get_vehicle_state", names)
    self.assertNotIn("git_commit", names)

    search = handle_search_tools({"query": "git commit"}, session_id="sess1")
    self.assertTrue(search.get("ok"))
    self.assertTrue(any(h["name"] == "git_commit" for h in search.get("tools", [])))

    loaded = handle_load_tool({"tools": ["git_commit"]}, session_id="sess1")
    self.assertTrue(loaded.get("ok"))
    self.assertIn("git_commit", loaded.get("loaded", []))

    filtered2 = apply_deferred_filter(catalog, key)
    names2 = {t["function"]["name"] for t in (filtered2 or [])}
    self.assertIn("git_commit", names2)


class ResultExternalizeTests(unittest.TestCase):
  @patch("ai.tools.result_externalize.externalize_enabled", return_value=True)
  def test_externalize_large_result(self, _enabled):
    from ai.tools import result_externalize as ext

    with tempfile.TemporaryDirectory() as td:
      def _fake_workspace(*parts, mkdir=False):
        p = Path(td).joinpath(*parts)
        if mkdir:
          p.mkdir(parents=True, exist_ok=True)
        return p

      with patch.object(ext, "workspace_path", _fake_workspace):
        big = {"ok": True, "data": "x" * 20000}
        compact, artifact = ext.externalize_if_needed(big, session_id="s1", tool_name="grep_log")
        self.assertTrue(compact.get("externalized"))
        self.assertIsNotNone(artifact)
        self.assertIn("preview", compact)

  def test_small_result_not_externalized(self):
    from ai.tools import result_externalize as ext

    small = {"ok": True, "value": 1}
    compact, artifact = ext.externalize_if_needed(small, session_id="s1", tool_name="test")
    self.assertIs(compact, small)
    self.assertIsNone(artifact)


class PromptBudgetTests(unittest.TestCase):
  def test_assemble_trims_long_blocks(self):
    from ai.common.prompt_budget import PromptBudget

    budget = PromptBudget(total_window=128_000, system_max=50)
    parts = [("base", "word " * 500, 50, 100)]
    texts, report = budget.assemble_system_parts(parts)
    self.assertEqual(len(texts), 1)
    self.assertIn("truncated", texts[0])
    self.assertGreater(report["system_tokens"], 0)


class AuditChainTests(unittest.TestCase):
  def test_hash_chain_roundtrip(self):
    import ai.tools.domains.platform.audit_store as audit

    with tempfile.TemporaryDirectory() as td:
      audit._AUDIT_PATH = Path(td) / "audit.jsonl"
      audit._CHAIN_STATE_PATH = Path(td) / "chain.state"
      audit._prev_hash = ""
      audit.record_audit(action="test1", tool="a", detail={"n": 1})
      audit.record_audit(action="test2", tool="b", detail={"n": 2})
      verify = audit.verify_audit_chain()
      self.assertTrue(verify.get("ok"))
      self.assertFalse(verify.get("broken"))
      self.assertGreaterEqual(verify.get("verified", 0), 2)

      trail = audit.list_audit_trail(limit=5)
      self.assertTrue(trail.get("chain_ok"))


class PermissionHookTests(unittest.TestCase):
  def test_blocks_high_risk_while_driving(self):
    import asyncio
    from ai.hooks.permissions import evaluate_tool_permission

    class _State:
      is_driving = True

    class _Reader:
      def update(self, timeout=0):
        return _State()

    ctx = {
      "name": "reboot_device",
      "body": {"_get_state_reader": _Reader, "_params": None},
    }

    async def _run():
      import ai.system.admin as admin_mod
      with patch.object(admin_mod, "is_admin_mode", return_value=False):
        with patch("openpilot.common.params.Params", return_value=object()):
          return await evaluate_tool_permission(ctx)

    result = asyncio.run(_run())
    self.assertTrue(result.get("block"))


class TranscriptStoreTests(unittest.TestCase):
  def test_append_and_recover(self):
    from ai.tools.domains.platform import transcript_store as ts

    with tempfile.TemporaryDirectory() as td:
      def _dir(*parts, mkdir=False):
        p = Path(td).joinpath(*parts)
        if mkdir:
          p.mkdir(parents=True, exist_ok=True)
        return p

      with patch.object(ts, "transcript_dir", lambda: _dir(mkdir=True)):
        with patch.object(ts, "transcript_path", lambda sid: _dir(f"{sid}.jsonl")):
          ts.append_event("sess-x", {"type": "content", "delta": "hello "})
          ts.append_event("sess-x", {"type": "content", "delta": "world"})
          ts.append_event("sess-x", {"type": "tool_call", "id": "t1", "name": "read_file"})
          rec = ts.recover_partial("sess-x")
          self.assertTrue(rec.get("recoverable"))
          self.assertEqual(rec.get("content"), "hello world")
          self.assertEqual(len(rec.get("toolCalls") or []), 0)


class ModelTierTests(unittest.TestCase):
  def test_reorder_lite_prefers_flash(self):
    from ai.common.model_tier import reorder_chain_for_tier

    class _Cfg:
      def __init__(self, model):
        self.model = model

    chain = [_Cfg("gpt-4"), _Cfg("deepseek-flash")]
    ordered = reorder_chain_for_tier(chain, "lite")
    self.assertEqual(ordered[0].model, "deepseek-flash")


class HarnessDbTests(unittest.TestCase):
  def test_usage_and_audit_sqlite(self):
    from ai.tools.domains.platform import harness_db as db

    with tempfile.TemporaryDirectory() as td:
      db.HARNESS_DB = Path(td) / "harness.db"
      db._DB = None
      db.record_audit_event(action="test", tool="read_file", ok=True, session_id="s1")
      db.record_usage_event(provider="p", model="m", usage={"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5})
      audit = db.query_audit(limit=5)
      self.assertTrue(audit.get("ok"))
      self.assertGreaterEqual(audit.get("count", 0), 1)
      usage = db.query_usage_summary()
      self.assertTrue(usage.get("ok"))
      db.close_db()


class ProfileSyncTests(unittest.TestCase):
  def test_manifest_merge(self):
    from ai.tools.domains.platform.profile_sync import build_manifest, merge_remote_manifest

    with patch("openpilot.common.params.Params", return_value=object()):
      m = build_manifest(None)
      self.assertIn("sections", m)
      self.assertIn("harness", m["sections"])


class WorkflowCustomTests(unittest.TestCase):
  def test_save_and_load_custom(self):
    from ai.tools.domains.platform import workflow_custom as wc

    with tempfile.TemporaryDirectory() as td:
      wc._CUSTOM_PATH = Path(td) / "custom.json"
      result = wc.save_custom({"my_flow": {"name": "Test", "steps": ["a"], "prompt": "p"}})
      self.assertTrue(result.get("ok"))
      loaded = wc.load_custom()
      self.assertIn("my_flow", loaded)
      prompt = wc.merged_system_prompt("my_flow")
      self.assertIn("Test", prompt)


if __name__ == "__main__":
  unittest.main()
