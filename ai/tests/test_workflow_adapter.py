"""Tests for the stable workflow tool adapter (T-P0.5)."""
from __future__ import annotations

import asyncio
import unittest

import ai.tests.bootstrap_pc  # noqa: F401


def _sync_handler(args):
  return {"ok": True, "echo": args.get("v")}


async def _async_handler(args):
  await asyncio.sleep(0)
  return {"ok": True, "echo": args.get("v")}


class TestWorkflowToolAdapter(unittest.TestCase):
  def setUp(self):
    from ai.core.workflow.context import RunContext
    self.ctx = RunContext(run_id="r1", inputs={})

  def test_sync_handler(self):
    from ai.core.workflow.tool_adapter import WorkflowToolAdapter
    adapter = WorkflowToolAdapter({"echo": _sync_handler}, ctx=self.ctx)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      result = loop.run_until_complete(adapter.run("echo", {"v": 42}))
    finally:
      loop.close()
    self.assertTrue(result["ok"])
    self.assertEqual(result["echo"], 42)

  def test_async_handler(self):
    from ai.core.workflow.tool_adapter import WorkflowToolAdapter
    adapter = WorkflowToolAdapter({"hello": _async_handler}, ctx=self.ctx)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      result = loop.run_until_complete(adapter.run("hello", {"v": "x"}))
    finally:
      loop.close()
    self.assertTrue(result["ok"])

  def test_missing_tool(self):
    from ai.core.workflow.errors import WorkflowErrorCode
    from ai.core.workflow.tool_adapter import WorkflowToolAdapter
    adapter = WorkflowToolAdapter({"echo": _sync_handler}, ctx=self.ctx)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      result = loop.run_until_complete(adapter.run("nope", {}))
    finally:
      loop.close()
    self.assertFalse(result["ok"])
    self.assertEqual(result["code"], WorkflowErrorCode.TOOL_NOT_FOUND.value)

  def test_exception_normalized(self):
    from ai.core.workflow.errors import WorkflowErrorCode
    from ai.core.workflow.tool_adapter import WorkflowToolAdapter

    def _boom(args):
      raise RuntimeError("boom")
    adapter = WorkflowToolAdapter({"boom": _boom}, ctx=self.ctx)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      result = loop.run_until_complete(adapter.run("boom", {}))
    finally:
      loop.close()
    self.assertFalse(result["ok"])
    self.assertIn("boom", result["error"])
    self.assertEqual(result["code"], WorkflowErrorCode.TOOL_FAILED.value)

  def test_cancelled_returns_cancelled_code(self):
    from ai.core.workflow.context import RunContext
    from ai.core.workflow.errors import WorkflowErrorCode
    from ai.core.workflow.tool_adapter import WorkflowToolAdapter
    ctx = RunContext(run_id="r2", inputs={})
    ctx.cancelled = True

    adapter = WorkflowToolAdapter({"echo": _sync_handler}, ctx=ctx)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      result = loop.run_until_complete(adapter.run("echo", {}))
    finally:
      loop.close()
    self.assertFalse(result["ok"])
    self.assertEqual(result["code"], WorkflowErrorCode.CANCELLED.value)

  def test_from_factory_caches(self):
    from ai.core.workflow.tool_adapter import WorkflowToolAdapter
    calls = {"n": 0}

    def _factory():
      calls["n"] += 1
      return {"echo": _sync_handler}

    adapter = WorkflowToolAdapter.from_factory(_factory, ctx=self.ctx)
    self.assertEqual(adapter.tool_names(), ["echo"])
    # second access does not re-run the factory
    adapter.has_tool("echo")
    self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
  unittest.main()