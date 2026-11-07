"""Offline tests for ai.spill.manager."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from ai.spill.manager import MemorySpillStore, SpillManager


def _stub_summarizer(messages, max_tokens=None):
  return asyncio.sleep(0, result="summary of " + str(len(messages)) + " messages")


class TestSpillManager(unittest.TestCase):
  def test_estimate_tokens_counts_content(self):
    manager = SpillManager()
    messages = [
      {"role": "system", "content": "x" * 35},
      {"role": "user", "content": "hello"},
    ]
    tokens = manager.estimate_tokens(messages)
    self.assertGreater(tokens, 8)

  def test_should_spill_by_turns(self):
    manager = SpillManager(max_turns_before_spill=3, keep_recent_turns=1)
    messages = [
      {"role": "user", "content": "a"},
      {"role": "assistant", "content": "b"},
      {"role": "user", "content": "c"},
      {"role": "assistant", "content": "d"},
      {"role": "user", "content": "e"},
    ]
    self.assertTrue(manager.should_spill(messages))

  def test_should_spill_by_tokens(self):
    manager = SpillManager(max_inline_tokens=100, reserve_tokens=0)
    messages = [{"role": "user", "content": "x" * 400}]
    self.assertTrue(manager.should_spill(messages))

  def test_should_not_spill_when_under_budget(self):
    manager = SpillManager(max_inline_tokens=10000)
    messages = [{"role": "user", "content": "hello"}]
    self.assertFalse(manager.should_spill(messages))

  def test_spill_replaces_old_messages(self):
    async def run():
      manager = SpillManager(
        max_turns_before_spill=3,
        keep_recent_turns=1,
        summarizer=_stub_summarizer,
      )
      messages = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old assistant"},
        {"role": "user", "content": "middle user"},
        {"role": "assistant", "content": "middle assistant"},
        {"role": "user", "content": "recent user"},
      ]
      compacted = await manager.spill(messages, session_id="sess-1")
      self.assertEqual(len(compacted), 2)
      self.assertEqual(compacted[0]["role"], "system")
      self.assertIn("summary of 4 messages", compacted[0]["content"])
      self.assertEqual(compacted[1]["content"], "recent user")

    asyncio.run(run())

  def test_spill_respects_force(self):
    async def run():
      manager = SpillManager(keep_recent_turns=1, summarizer=_stub_summarizer)
      messages = [
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
      ]
      compacted = await manager.spill(messages, force=True)
      self.assertEqual(compacted[0]["role"], "system")

    asyncio.run(run())

  def test_status(self):
    manager = SpillManager(max_inline_tokens=100, reserve_tokens=10)
    messages = [{"role": "user", "content": "x" * 400}]
    status = manager.status(messages)
    self.assertIn("estimatedTokens", status)
    self.assertEqual(status["maxInlineTokens"], 100)
    self.assertEqual(status["reserveTokens"], 10)
    self.assertTrue(status["needsSpill"])

  def test_recall_summary(self):
    async def run():
      store = MemorySpillStore()
      ref = await store.save_text({
        "owner": {"session_id": "s"},
        "content": "stored summary",
      })
      recalled = await store.get_text(ref.locator)
      self.assertEqual(recalled, "stored summary")

    asyncio.run(run())


if __name__ == "__main__":
  unittest.main()
