"""Tests for G3 event-projection compaction service."""
from __future__ import annotations
import unittest
from ai.core.session.compaction import CompactionConfig, CompactionService
from ai.core.session.log import EventType, SessionLog, SurfaceOp


class CompactionServiceTest(unittest.TestCase):
  def _seed(self, n_tool_results: int = 3) -> SessionLog:
    log = SessionLog("s1")
    log.append(EventType.USER_MESSAGE, {"role": "user", "content": "hi"}, surface_op=SurfaceOp.APPEND)
    for i in range(n_tool_results):
      log.append(EventType.ASSISTANT_MESSAGE, {"role": "assistant", "content": "tool call"}, surface_op=SurfaceOp.APPEND)
      log.append(EventType.TOOL_RESULT, {"tool_call_id": f"tc{i}", "content": "x" * 20000}, surface_op=SurfaceOp.APPEND)
    return log

  def test_compaction_prunes_without_llm(self) -> None:
    log = self._seed()
    svc = CompactionService(log, llm_stream=None)
    import asyncio
    result = asyncio.run(svc.compact_now(None))
    self.assertTrue(result)
    self.assertTrue(result.shadowed_seqs)
    # REPLACE collapsed shadowed tool results.
    types = [e.type for e in log.events]
    self.assertIn(EventType.LIFECYCLE, types)

  def test_compaction_with_llm_replaces_surface(self) -> None:
    log = self._seed(2)
    async def fake_llm(_msgs): return "SUMMARY TEXT"
    svc = CompactionService(log, llm_stream=fake_llm)
    import asyncio
    result = asyncio.run(svc.compact_now(None))
    self.assertIsNotNone(result.replacement_seq)
    self.assertEqual(result.summary, "SUMMARY TEXT")
    # Surface should now contain a user summary node replacing tool results.
    types = [n.event_type for n in log.surface]
    self.assertIn(EventType.USER_MESSAGE, types)

  def test_locked_prevents_second_run(self) -> None:
    log = self._seed(1)
    svc = CompactionService(log)
    import asyncio
    svc._locked = True
    result = asyncio.run(svc.compact_now(None))
    self.assertIsNone(result)


if __name__ == "__main__":
  unittest.main()
