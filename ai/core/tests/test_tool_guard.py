"""Tests for hook-registry guard bridge on ToolPipeline."""

import asyncio
import unittest

from ai.core.tools.guard import GuardContext, install_hook_guards
from ai.core.tools.pipeline import ToolDefinition, ToolPipeline


class ToolGuardTestCase(unittest.TestCase):
  def tearDown(self):
    try:
      from ai.hooks.registry import clear_hooks
      clear_hooks()
    except Exception:
      pass

  def test_guard_blocks_via_before_hook(self):
    from ai.hooks.registry import register_hook

    async def _block(ctx):
      if ctx.get("name") == "danger":
        return {"block": True, "reason": "nope"}
      return None

    register_hook("before_tool_call", _block)

    pipeline = ToolPipeline()
    pipeline.register(ToolDefinition(
      name="danger",
      description="danger",
      parameters={"type": "object", "properties": {}},
      handler=lambda args: {"ok": True},
    ))
    install_hook_guards(
      pipeline,
      agent_id="a1",
      session_id="s1",
      params={},
      body={},
      get_state_reader=lambda: None,
    )

    result = asyncio.run(pipeline.execute("id", "danger", "{}"))
    self.assertFalse(result["ok"])
    self.assertIn("nope", result["error"])

  def test_guard_modifies_result_via_after_hook(self):
    from ai.hooks.registry import register_hook

    async def _rewrite(ctx):
      result = ctx.get("result")
      if isinstance(result, dict):
        result["rewritten"] = True
        return {"result": result}
      return None

    register_hook("after_tool_call", _rewrite)

    pipeline = ToolPipeline()
    pipeline.register(ToolDefinition(
      name="echo",
      description="echo",
      parameters={"type": "object", "properties": {}},
      handler=lambda args: {"ok": True, "value": 1},
    ))
    install_hook_guards(
      pipeline,
      agent_id="a1",
      session_id="s1",
      params={},
      body={},
      get_state_reader=lambda: None,
    )

    result = asyncio.run(pipeline.execute("id", "echo", "{}"))
    self.assertTrue(result["ok"])
    self.assertTrue(result.get("rewritten"))

  def test_guard_context_extra(self):
    pipeline = ToolPipeline()
    ctx = GuardContext("a1", "s1", {}, {}, lambda: None)
    from ai.core.tools.guard import attach_guard_context
    attach_guard_context(pipeline, ctx)
    self.assertIs(pipeline._guard_context, ctx)


if __name__ == "__main__":
  unittest.main()
