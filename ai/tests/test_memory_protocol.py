"""Memory protocol + daily journal tests (no network)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from ai.tools.daily_memory import (
  append_daily_memory,
  build_daily_memory_prompt_block,
  read_daily_index,
  read_daily_memory,
  read_recent_daily_memories,
  refresh_daily_index,
)
from ai.tools.memory_protocol import (
  apply_memory_payload,
  conversation_tail,
  should_skip_auto_extract,
)


class TestDailyMemory(unittest.TestCase):
  def test_append_and_read(self):
    with tempfile.TemporaryDirectory() as tmp:
      with mock.patch("ai.tools.daily_memory.workspace_dir", return_value=Path(tmp)):
        r = append_daily_memory(bullets=["调了跟车距离 2→3"], session_id="sess123", title="调参")
        self.assertTrue(r.get("ok"))
        text = read_daily_memory()
        self.assertIn("跟车距离", text)
        self.assertIn("sess123"[:8], text)

  def test_prompt_block(self):
    with tempfile.TemporaryDirectory() as tmp:
      with mock.patch("ai.tools.daily_memory.workspace_dir", return_value=Path(tmp)):
        append_daily_memory(bullets=["line one"])
        block = build_daily_memory_prompt_block(days=3, max_chars=2000)
        self.assertIn("Daily memory", block)
        self.assertIn("line one", block)
        self.assertIn("Daily Memory Index", read_daily_index())

  def test_recent_memories(self):
    with tempfile.TemporaryDirectory() as tmp:
      with mock.patch("ai.tools.daily_memory.workspace_dir", return_value=Path(tmp)):
        append_daily_memory(bullets=["test entry"])
        block = read_recent_daily_memories(days=1)
        self.assertIn("test entry", block)


class TestMemoryProtocol(unittest.TestCase):
  def test_conversation_tail(self):
    msgs = [
      {"role": "system", "content": "x"},
      {"role": "user", "content": "hello"},
      {"role": "assistant", "content": "hi"},
    ]
    tail = conversation_tail(msgs)
    self.assertEqual(len(tail), 2)

  def test_skip_trivial(self):
    reason = should_skip_auto_extract([
      {"role": "user", "content": "谢谢"},
      {"role": "assistant", "content": "不客气"},
    ])
    self.assertEqual(reason, "trivial")

  def test_apply_payload(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      with mock.patch("ai.tools.daily_memory.workspace_dir", return_value=root):
        with mock.patch("ai.core.wspace.store.workspace_dir", return_value=root):
          out = apply_memory_payload(None, {
            "skip": False,
            "daily_bullets": ["用户偏好跟车远"],
          })
          self.assertFalse(out.get("skipped"))
          self.assertTrue(out.get("applied", {}).get("daily"))
          self.assertTrue((root / "memory").exists())


if __name__ == "__main__":
  unittest.main()
