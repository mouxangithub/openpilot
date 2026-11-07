"""G7 — Subagent capability matrix + parent-child lineage events.

Proves behavior, not existence:
- a request needing a capability the provider lacks is refused with a
  structured error (SUBAGENT_CAPABILITY_MISSING), provider never invoked;
- the delegation depth ceiling applies even when an injected runner bypasses
  the provider registry (SUBAGENT_DEPTH_EXCEEDED);
- run_subagent pairs a subagent/start with a subagent/end event on the parent
  SessionLog (runId/provider/depth vocabulary, dsh SubagentRunInfo);
- the pool threads session_log through submit -> run_subagent.
"""

from __future__ import annotations

import asyncio
import unittest

from ai.core.session.log import EventType, SessionLog
from ai.subagent.capabilities import SubagentCapabilities
from ai.subagent.models import SubagentResult, SubagentTask
from ai.subagent.pool import SubagentPool
from ai.subagent.providers import register_provider
from ai.subagent.runner import SubagentRunner, run_subagent


def _task(**kw) -> SubagentTask:
  defaults = dict(id="t1", agent_id="agent-x", prompt="do things")
  defaults.update(kw)
  return SubagentTask(**defaults)


def _fake_provider(calls: list):
  async def provider(task, **kw):
    calls.append(task)
    return SubagentResult(task_id=task.id, ok=True, output="done", stop_reason="completed")
  return provider


def _fake_chat(calls: list):
  """Injected-runner fake: returns the dict shape SubagentRunner expects."""
  async def chat(*args, **kw):
    calls.append(1)
    return {"ok": True, "events": [{"type": "content", "delta": "hello"}]}
  return chat


class CapabilityMatrixTests(unittest.TestCase):
  def test_missing_capability_refused_loud(self) -> None:
    calls: list = []
    register_provider("caps-no-schema", _fake_provider(calls), SubagentCapabilities(output_schema=False))
    task = _task(id="t-caps", provider="caps-no-schema", output_schema={"type": "object"})
    result = asyncio.run(run_subagent(task, params=None))
    self.assertFalse(result.ok)
    self.assertEqual(result.stop_reason, "refusal")
    self.assertEqual(result.error_code, "SUBAGENT_CAPABILITY_MISSING")
    self.assertEqual(calls, [], "provider must not be invoked on refusal")

  def test_depth_ceiling_applies_with_injected_runner(self) -> None:
    called: list = []

    async def fake_chat(*args, **kw):
      called.append(1)
      return {"ok": True, "events": [], "output": "ok"}

    runner = SubagentRunner(run_chat=fake_chat)
    result = asyncio.run(runner.run(_task(id="t-deep", depth=3, max_depth=3), params=None))
    self.assertFalse(result.ok)
    self.assertEqual(result.error_code, "SUBAGENT_DEPTH_EXCEEDED")
    self.assertEqual(called, [], "injected runner must not run past depth ceiling")

  def test_within_depth_runs_normally(self) -> None:
    runner = SubagentRunner(run_chat=_fake_chat([]))
    result = asyncio.run(runner.run(_task(id="t-ok"), params=None))
    self.assertTrue(result.ok)
    self.assertEqual(result.stop_reason, "completed")

  def test_capabilities_to_dict(self) -> None:
    caps = SubagentCapabilities(output_schema=True, tool_filter=True).to_dict()
    self.assertEqual(caps["outputSchema"], True)
    self.assertEqual(caps["depthLimit"], False)


class LineageEventTests(unittest.TestCase):
  def test_start_end_pair_on_parent_log(self) -> None:
    calls: list = []
    register_provider("lineage-stub", _fake_provider(calls), SubagentCapabilities())

    async def scenario():
      log = SessionLog("lineage-test")
      result = await run_subagent(_task(id="t-line", provider="lineage-stub"), params=None, session_log=log)
      return result, log

    result, log = asyncio.run(scenario())
    self.assertTrue(result.ok)
    kinds = [e.type for e in log.events]
    self.assertIn(EventType.SUBAGENT_START, kinds)
    self.assertIn(EventType.SUBAGENT_END, kinds)
    start = next(e for e in log.events if e.type == EventType.SUBAGENT_START)
    end = next(e for e in log.events if e.type == EventType.SUBAGENT_END)
    self.assertEqual(start.data["runId"], end.data["runId"])
    self.assertEqual(start.data["provider"], "lineage-stub")
    self.assertEqual(start.data["taskId"], "t-line")
    self.assertEqual(start.data["delegationDepth"], 0)
    self.assertEqual(end.data["stopReason"], "completed")
    self.assertTrue(end.data["ok"])

  def test_pool_threads_session_log(self) -> None:
    async def scenario() -> tuple:
      log = SessionLog("pool-lineage-test")
      calls: list = []
      runner = SubagentRunner(run_chat=_fake_chat(calls))
      pool = SubagentPool(max_concurrency=2, runner=runner)
      result = await pool.run(_task(id="t-pool"), params=None, session_log=log)
      return result, log, calls

    result, log, calls = asyncio.run(scenario())
    self.assertTrue(result.ok)
    self.assertEqual(len(calls), 1)
    kinds = [e.type for e in log.events]
    self.assertIn(EventType.SUBAGENT_START, kinds)
    self.assertIn(EventType.SUBAGENT_END, kinds)

  def test_refusal_still_emits_end_event(self) -> None:
    async def scenario() -> SessionLog:
      log = SessionLog("lineage-refusal-test")
      await run_subagent(_task(id="t-ref", depth=9, max_depth=3), params=None, session_log=log)
      return log

    log = asyncio.run(scenario())
    end = next(e for e in log.events if e.type == EventType.SUBAGENT_END)
    self.assertEqual(end.data["stopReason"], "refusal")
    self.assertFalse(end.data["ok"])


if __name__ == "__main__":
  unittest.main()
