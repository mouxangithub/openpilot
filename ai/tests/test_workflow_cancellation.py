"""Tests for WorkflowEngine cooperative cancellation (T-P1.6)."""
from __future__ import annotations

import asyncio
import unittest

import ai.tests.bootstrap_pc  # noqa: F401


class TestWorkflowCancellation(unittest.TestCase):
  def test_adapter_races_tool_against_cancel_event(self):
    from ai.core.workflow.tool_adapter import WorkflowToolAdapter
    from ai.core.workflow.errors import WorkflowErrorCode

    async def slow_tool(_args):
      await asyncio.sleep(10)
      return {"ok": True}

    cancel_event = asyncio.Event()
    adapter = WorkflowToolAdapter({"slow": slow_tool}, cancel_event=cancel_event)

    async def _run():
      task = asyncio.create_task(adapter.run("slow", {}))
      await asyncio.sleep(0.05)
      cancel_event.set()
      return await task

    result = asyncio.run(_run())
    self.assertFalse(result["ok"])
    self.assertEqual(result["code"], WorkflowErrorCode.CANCELLED.value)

  def test_engine_cancel_aborts_run(self):
    from ai.core.workflow import WorkflowEngine
    from ai.core.workflow.definition import WorkflowDefinition, Step, StepKind
    from ai.core.workflow.errors import WorkflowErrorCode

    async def slow_tool(_args):
      await asyncio.sleep(10)
      return {"ok": True}

    from ai.core.workflow.tool_adapter import WorkflowToolAdapter

    cancel_event = asyncio.Event()
    engine = WorkflowEngine()
    adapter = WorkflowToolAdapter({"slow": slow_tool}, cancel_event=cancel_event)
    engine.set_tool_runner(adapter.run)

    defn = WorkflowDefinition(
      id="cancel-test",
      name="cancel-test",
      version="1",
      inputs_schema={},
      steps=[
        Step(id="s1", kind=StepKind.TOOL, inputs={"tool": "slow"}),
      ],
      outputs={},
    )

    async def _run():
      task = asyncio.create_task(engine.run(defn, {}, cancel_event=cancel_event))
      await asyncio.sleep(0.05)
      cancel_event.set()
      return await task

    result = asyncio.run(_run())
    self.assertFalse(result.ok)
    self.assertEqual(result.error, WorkflowErrorCode.CANCELLED)


if __name__ == "__main__":
  unittest.main()
