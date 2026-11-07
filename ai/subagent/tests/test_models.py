"""Tests for ai.subagent models, runner, and pool."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from ai.subagent.models import SubagentResult, SubagentTask
from ai.subagent.pool import SubagentPool
from ai.subagent.runner import SubagentRunner, run_subagent


class _FakeParams:
  pass


class TestSubagentModels(unittest.TestCase):
  def test_task_roundtrip(self) -> None:
    task = SubagentTask(
      id="sub-1",
      agent_id="devops",
      prompt="hello",
      workflow="health_check",
      output_schema={"type": "object"},
    )
    restored = SubagentTask.from_dict(task.to_dict())
    self.assertEqual(restored.id, task.id)
    self.assertEqual(restored.agent_id, task.agent_id)
    self.assertEqual(restored.prompt, task.prompt)
    self.assertEqual(restored.workflow, task.workflow)
    self.assertEqual(restored.output_schema, task.output_schema)

  def test_result_roundtrip(self) -> None:
    result = SubagentResult(
      task_id="sub-1",
      ok=True,
      output="done",
      stop_reason="completed",
      events=[{"type": "content", "delta": "done"}],
    )
    restored = SubagentResult.from_dict(result.to_dict())
    self.assertEqual(restored.task_id, result.task_id)
    self.assertTrue(restored.ok)
    self.assertEqual(restored.output, "done")


class TestSubagentRunner(unittest.IsolatedAsyncioTestCase):
  async def test_run_uses_provided_chat_fn(self) -> None:
    called: dict[str, Any] = {}

    async def fake_run_chat(body: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
      called["args"] = args
      called["kwargs"] = kwargs
      emit = kwargs.get("emit") or (args[1] if len(args) > 1 else None)
      if emit is not None:
        await emit({"type": "content", "delta": "hello"})
      return {"ok": True}

    runner = SubagentRunner(run_chat=fake_run_chat)
    task = SubagentTask(id="sub-1", agent_id="devops", prompt="say hi")
    result = await runner.run(task, params=_FakeParams())
    self.assertTrue(result.ok)
    self.assertEqual(result.output, "hello")
    self.assertEqual(called["kwargs"]["tools"], None)

  async def test_run_builds_body(self) -> None:
    captured_body: dict[str, Any] | None = None

    async def fake_run_chat(body: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
      nonlocal captured_body
      captured_body = body
      return {"ok": True}

    runner = SubagentRunner(run_chat=fake_run_chat)
    task = SubagentTask(
      id="sub-1",
      agent_id="devops",
      prompt="run health check",
      workflow="health_check",
      session_id="sess-1",
    )
    await runner.run(task, params=_FakeParams())
    self.assertIsNotNone(captured_body)
    self.assertEqual(captured_body.get("workflow"), "health_check")
    self.assertTrue(captured_body.get("_subagent"))

  async def test_run_subagent_helper(self) -> None:
    async def fake_run_chat(body: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
      emit = kwargs.get("emit") or (args[1] if len(args) > 1 else None)
      if emit is not None:
        await emit({"type": "content", "delta": "world"})
      return {"ok": True, "structured": {"a": 1}}

    result = await run_subagent(
      {"id": "sub-2", "agent_id": "devops", "prompt": "x"},
      params=_FakeParams(),
      runner=SubagentRunner(run_chat=fake_run_chat),
    )
    self.assertTrue(result.ok)
    self.assertEqual(result.output, "world")
    self.assertEqual(result.structured, {"a": 1})


class TestSubagentPool(unittest.IsolatedAsyncioTestCase):
  async def test_pool_limits_concurrency(self) -> None:
    running = 0
    max_running = 0
    lock = asyncio.Lock()

    async def fake_run_chat(body: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
      nonlocal running, max_running
      async with lock:
        running += 1
        max_running = max(max_running, running)
      await asyncio.sleep(0.05)
      async with lock:
        running -= 1
      return {"ok": True}

    pool = SubagentPool(
      max_concurrency=2,
      runner=SubagentRunner(run_chat=fake_run_chat),
      params=_FakeParams(),
    )
    tasks = [pool.create_task("devops", f"task {i}") for i in range(5)]
    results = await pool.run_many(tasks)
    self.assertEqual(len(results), 5)
    self.assertTrue(all(isinstance(r, SubagentResult) and r.ok for r in results))
    self.assertLessEqual(max_running, 2)

  async def test_pool_tracks_status(self) -> None:
    async def fake_run_chat(body: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
      await asyncio.sleep(0.01)
      return {"ok": True}

    pool = SubagentPool(
      runner=SubagentRunner(run_chat=fake_run_chat),
      params=_FakeParams(),
    )
    task = pool.create_task("devops", "prompt")
    self.assertEqual(task.status, "pending")
    result = await pool.run(task)
    self.assertTrue(result.ok)
    self.assertEqual(pool.get_task(task.id).status, "completed")

  async def test_pool_cancel(self) -> None:
    async def fake_run_chat(body: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
      await asyncio.sleep(0.5)
      return {"ok": True}

    pool = SubagentPool(
      runner=SubagentRunner(run_chat=fake_run_chat),
      params=_FakeParams(),
    )
    task = pool.create_task("devops", "prompt")
    t = await pool.submit(task)
    pool.cancel(task.id)
    result = await t
    self.assertIn(result.stop_reason, ("aborted", "error"))


if __name__ == "__main__":
  unittest.main()
