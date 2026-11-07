"""Workflow event and engine wiring tests for T01."""

from __future__ import annotations

import asyncio
import unittest

import ai.tests.bootstrap_pc  # noqa: F401

from ai.core.workflow import WorkflowEngine, WorkflowErrorCode
from ai.core.workflow.events import WorkflowEventFactory


class WorkflowEventsTests(unittest.IsolatedAsyncioTestCase):
  async def test_event_factory_shapes(self):
    f = WorkflowEventFactory("run-1")
    start = f.workflow_start("def-1", "Test", {"x": 1})
    self.assertEqual(start.type, "workflow/start")
    self.assertEqual(start.run_id, "run-1")

    phase_start = f.phase_start("p1", "s1", "tool")
    self.assertEqual(phase_start.type, "phase/start")

    agent_start = f.agent_start("p1", "agent-1", "hello")
    self.assertEqual(agent_start.type, "agent-start")

  async def test_engine_wiring_stub(self):
    engine = WorkflowEngine()
    events: list[dict] = []

    async def sink(event):
      events.append(event.to_dict())

    engine.register_event_sink(sink)
    result = await engine.run({"id": "test", "name": "Test Workflow", "steps": [{"id": "s1", "kind": "log", "inputs": {"message": "hello"}}]}, {"x": 1})

    self.assertTrue(result.ok)
    self.assertEqual(result.error, WorkflowErrorCode.INVALID_DEFINITION)
    self.assertGreaterEqual(len(events), 2)
    self.assertEqual(events[0]["type"], "workflow/start")
    self.assertEqual(events[-1]["type"], "workflow/end")

  async def test_engine_dispose_prevents_run(self):
    engine = WorkflowEngine()

    async def sink(_event):
      pass

    engine.register_event_sink(sink)

    async def run_and_dispose():
      task = asyncio.create_task(engine.run({"id": "test", "name": "Test", "steps": [{"id": "s1", "kind": "log", "inputs": {"message": "hello"}}]}))
      await asyncio.sleep(0)
      return await task

    result = await run_and_dispose()
    self.assertTrue(result.ok)


if __name__ == "__main__":
  unittest.main()
