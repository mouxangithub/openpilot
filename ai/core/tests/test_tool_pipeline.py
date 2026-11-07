"""Tests for ai.core.tools.pipeline."""

import asyncio
import json
import unittest
from unittest.mock import patch

from ai.core.tools.pipeline import (
  ToolDefinition,
  ToolPipeline,
  ToolResult,
  build_tool_result,
  classify_result_kind,
  truncate_content_head_tail,
)


class ToolPipelineTestCase(unittest.TestCase):
  def test_unknown_tool(self):
    pipeline = ToolPipeline()
    result = asyncio.run(pipeline.execute("id", "missing", "{}"))
    self.assertFalse(result["ok"])
    self.assertIn("not implemented", result["error"])

  def test_sync_tool(self):
    pipeline = ToolPipeline()
    pipeline.register(ToolDefinition(
      name="echo",
      description="echo",
      parameters={"type": "object", "properties": {}},
      handler=lambda args: {"ok": True, "echo": args.get("x")},
    ))
    result = asyncio.run(pipeline.execute("id", "echo", '{"x": 1}'))
    self.assertTrue(result["ok"])
    self.assertEqual(result["echo"], 1)

  def test_structured_result_and_utf8_retention(self):
    self.assertEqual(classify_result_kind({"ok": True, "content": "文本"}), "content")
    self.assertEqual(build_tool_result(3).value, 3)
    retained = truncate_content_head_tail("头" * 50 + "尾" * 50, 32)
    self.assertLessEqual(len(retained.encode("utf-8")), 32)
    self.assertIn("truncated", retained)

  def test_post_waterfall_runs_inner_to_outer(self):
    pipeline = ToolPipeline({"echo": lambda args: {"ok": True, "value": "x"}})
    calls = []

    async def outer(ctx, result, next_stage):
      calls.append("outer-before")
      result = await next_stage()
      calls.append("outer-after")
      result.value["outer"] = True
      return result

    async def inner(ctx, result, next_stage):
      calls.append("inner-before")
      result = await next_stage()
      calls.append("inner-after")
      result.value["inner"] = True
      return result

    pipeline.add_post_waterfall(outer)
    pipeline.add_post_waterfall(inner)
    result = asyncio.run(pipeline.execute("id", "echo", "{}"))
    self.assertTrue(result["outer"])
    self.assertTrue(result["inner"])
    self.assertEqual(calls, ["outer-before", "inner-before", "inner-after", "outer-after"])

  def test_guard_blocks(self):
    pipeline = ToolPipeline()

    def guard(args):
      if args.get("x") == 1:
        return "blocked"
      return None

    pipeline.register(ToolDefinition(
      name="gated",
      description="gated",
      parameters={"type": "object", "properties": {}},
      handler=lambda args: {"ok": True},
      guard=guard,
    ))
    result = asyncio.run(pipeline.execute("id", "gated", '{"x": 1}'))
    self.assertFalse(result["ok"])
    self.assertEqual(result["error"], "blocked")

  def test_spill_post_waterfall_externalizes_large_text(self):
    """Verify the dsh spill post-waterfall converts oversized text to a toolresult:// pointer."""
    from ai.tools.result_externalize import spill_text_if_needed

    def fake_workspace_path(*parts, mkdir=False):
      from pathlib import Path
      base = Path(__file__).parent / "_spill_test_ws"
      if mkdir:
        base.mkdir(parents=True, exist_ok=True)
      path = base.joinpath(*parts)
      if mkdir and parts:
        path.mkdir(parents=True, exist_ok=True)
      return path

    with patch("ai.tools.result_externalize.workspace_path", fake_workspace_path):
      pipeline = ToolPipeline()
      pipeline.register(ToolDefinition(
        name="big_echo",
        description="returns a large string",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: {"ok": True, "content": "x" * 20_000},
      ))

      async def spill_hook(exec_ctx, result: ToolResult, next_stage):
        name = getattr(exec_ctx, "name", "")
        downstream = await next_stage()
        if not downstream.ok:
          return downstream
        if exec_ctx.extra.get("parent") is not None:
          return downstream
        from ai.tools.result_externalize import spill_text_if_needed
        text = downstream.content
        if text is None:
          return downstream
        replaced, ref = spill_text_if_needed(
          text,
          session_id="spill-test",
          tool_name=name,
          call_id=exec_ctx.call_id,
          params={"ai_externalize_results": True, "ai_externalize_threshold": 1024},
        )
        if replaced is None:
          return downstream
        pointer = {
          "ok": True,
          "externalized": True,
          "ref": ref["ref"],
          "path": ref["path"],
          "tool": name,
          "size_bytes": ref["size_bytes"],
          "preview": replaced,
          "hint": ref["hint"],
        }
        return ToolResult(ok=True, value=pointer, content=replaced, block=pointer)

      pipeline.add_post_waterfall(spill_hook)
      result = asyncio.run(pipeline.execute("cid-1", "big_echo", "{}"))

    self.assertTrue(result.get("ok"))
    self.assertTrue(result.get("externalized"))
    self.assertIn("toolresult://", result.get("ref", ""))
    # size_bytes records the original spilled payload, not the preview.
    self.assertEqual(result.get("size_bytes"), 20_000)
    self.assertLess(len(result.get("preview", "").encode("utf-8")), 20_000)

    # Verify the spilled artifact file exists and contains the full text.
    from pathlib import Path
    self.assertTrue(Path(result["path"]).exists())
    self.assertEqual(Path(result["path"]).read_text(encoding="utf-8"), "x" * 20_000)


if __name__ == "__main__":
  unittest.main()
