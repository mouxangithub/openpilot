"""Spill waterfall semantics tests (dsh spill-policy port, G1/U3)."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

import ai.tests.bootstrap_pc  # noqa: F401

from ai.core.tools.pipeline import ToolPipeline, ToolResult
from ai.tools import result_externalize
from ai.tools.result_externalize import spill_text_if_needed


class SpillTextIfNeededTests(unittest.TestCase):
  """Direct unit tests of the spill decision/replacement core."""

  def setUp(self) -> None:
    self.session_id = "spilltest_session"

  def test_small_text_not_spilled(self) -> None:
    replaced, ref = spill_text_if_needed(
      "small", session_id=self.session_id, tool_name="echo", max_bytes=8192,
    )
    self.assertIsNone(replaced)
    self.assertIsNone(ref)

  def test_large_text_spilled_with_bounded_replacement(self) -> None:
    text = "x" * 20_000
    replaced, ref = spill_text_if_needed(
      text, session_id=self.session_id, tool_name="echo", max_bytes=8192,
    )
    self.assertIsNotNone(ref)
    assert ref is not None
    self.assertTrue(ref["ref"].startswith("toolresult://"))
    self.assertLessEqual(len(replaced.encode("utf-8")), 8192)
    self.assertIn("Full formatted result stored at:", replaced)

  def test_notice_reserved_inside_cap(self) -> None:
    # Tiny cap: notice alone is near the cap; replacement must still fit.
    text = "z" * 5000
    replaced, ref = spill_text_if_needed(
      text, session_id=self.session_id, tool_name="echo", max_bytes=400,
    )
    self.assertIsNotNone(ref)
    assert replaced is not None
    self.assertLessEqual(len(replaced.encode("utf-8")), 400)

  def test_notice_over_cap_keeps_original(self) -> None:
    # Path is long so the notice exceeds an extremely small cap: keep original.
    text = "q" * 5000
    replaced, ref = spill_text_if_needed(
      text, session_id=self.session_id, tool_name="tool_with_a_very_long_name",
      max_bytes=80,
    )
    # Either no spill (None) or a within-cap replacement; never an oversized one.
    if replaced is not None:
      self.assertLessEqual(len(replaced.encode("utf-8")), 80)

  def test_no_session_keeps_original(self) -> None:
    replaced, ref = spill_text_if_needed(
      "x" * 20_000, session_id="", tool_name="echo", max_bytes=8192,
    )
    self.assertIsNone(replaced)
    self.assertIsNone(ref)

  def test_utf8_multibyte_head_tail_retention(self) -> None:
    text = "你好" * 6000  # 3 bytes per char -> 36_000 bytes
    replaced, ref = spill_text_if_needed(
      text, session_id=self.session_id, tool_name="echo", max_bytes=4096,
    )
    self.assertIsNotNone(replaced)
    assert replaced is not None
    self.assertLessEqual(len(replaced.encode("utf-8")), 4096)
    # Head and tail Chinese text should survive (valid UTF-8).
    self.assertIn("你好", replaced)

  def test_saved_file_contains_full_text(self) -> None:
    text = "FULL-" + "y" * 30_000
    replaced, ref = spill_text_if_needed(
      text, session_id=self.session_id, tool_name="echo", max_bytes=4096,
    )
    self.assertIsNotNone(ref)
    assert ref is not None
    from pathlib import Path
    saved = Path(ref["path"]).read_text(encoding="utf-8")
    self.assertEqual(saved, text)


class SpillWaterfallPipelineTests(unittest.TestCase):
  """End-to-end: waterfall ordering + tool results through ToolPipeline."""

  def _spill_hook(self, agent):
    # Re-create the hook logic from agent.py in isolation.
    from ai.core.tools.pipeline import ToolResult

    async def _spill(exec_ctx, result: ToolResult, next_stage) -> ToolResult:
      name = getattr(exec_ctx, "name", "")
      downstream = await next_stage()
      if name in ("read", "read_file", "read_file_text") or "grep" in name:
        return downstream
      if not downstream.ok:
        return downstream
      if exec_ctx.extra.get("parent") is not None:
        return downstream
      from ai.tools.result_externalize import spill_text_if_needed
      text = downstream.content
      if text is None:
        return downstream
      replaced, ref = spill_text_if_needed(
        text, session_id=agent["session"], tool_name=name,
        call_id=exec_ctx.call_id, max_bytes=agent["cap"],
      )
      if replaced is None:
        return downstream
      pointer = {
        "ok": True, "externalized": True, "ref": ref["ref"],
        "path": ref["path"], "tool": name, "size_bytes": ref["size_bytes"],
        "preview": replaced, "hint": ref["hint"],
      }
      return ToolResult(ok=True, value=pointer, content=replaced,
                        block={"type": "text", "text": replaced}, meta=downstream.meta)

    return _spill

  def setUp(self) -> None:
    self.agent = {"session": "spilltest_session", "cap": 2048}

  async def _run(self, name: str, args: dict[str, Any], parent: bool = False) -> dict[str, Any]:
    pipeline = ToolPipeline()
    pipeline.add_post_waterfall(self._spill_hook(self.agent))

    async def handler(_: dict[str, Any]) -> Any:
      return {"ok": True, "content": args["_text"]}

    pipeline.register_primitive(name, handler)
    extra = {"parent": {"id": "p1"}} if parent else {}
    return await pipeline.execute(
      call_id=f"{name}:1", name=name, raw_arguments="{}", extra=extra,
    )

  def test_large_plain_text_result_is_spilled(self) -> None:
    result = asyncio.run(self._run("bash", {"_text": "z" * 10_000}))
    self.assertTrue(result.get("ok"))
    self.assertTrue(result.get("externalized"))
    self.assertEqual(result.get("tool"), "bash")
    self.assertLessEqual(len(result.get("preview", "").encode("utf-8")), 2048)

  def test_read_tool_is_not_spilled(self) -> None:
    result = asyncio.run(self._run("read_file", {"_text": "z" * 10_000}))
    self.assertTrue(result.get("ok"))
    self.assertNotIn("externalized", result)
    # Original dict passes through untouched.
    self.assertEqual(result.get("content"), "z" * 10_000)

  def test_failed_result_is_not_spilled(self) -> None:
    pipeline = ToolPipeline()
    pipeline.add_post_waterfall(self._spill_hook(self.agent))

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
      return {"ok": False, "error": "boom"}

    pipeline.register_primitive("fail", handler)
    result = asyncio.run(pipeline.execute("f:1", "fail", "{}"))
    self.assertFalse(result.get("ok"))
    self.assertNotIn("externalized", result)

  def test_parent_call_skips_model_facing_spill(self) -> None:
    result = asyncio.run(self._run("run_code", {"_text": "z" * 10_000}, parent=True))
    self.assertTrue(result.get("ok"))
    # parent calls keep the full content inline (dispatch-log arm is separate).
    self.assertEqual(result.get("content"), "z" * 10_000)

  def test_waterfall_ordering_next_runs_first(self) -> None:
    order: list[str] = []
    pipeline = ToolPipeline()

    async def outer(exec_ctx, result, next_stage) -> ToolResult:
      order.append("outer:before-next")
      downstream = await next_stage()
      order.append("outer:after-next")
      return downstream

    async def inner(exec_ctx, result, next_stage) -> ToolResult:
      order.append("inner")
      return result

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
      order.append("handler")
      return {"ok": True, "content": "small"}

    pipeline.add_post_waterfall(outer)
    pipeline.add_post_waterfall(inner)
    pipeline.register_primitive("t", handler)
    asyncio.run(pipeline.execute("t:1", "t", "{}"))
    # Tool execution precedes post stages; then outer awaits next() and
    # receives the inner stage result before returning to the caller.
    self.assertEqual(order[0], "handler")
    self.assertLess(order.index("outer:before-next"), order.index("inner"))
    self.assertLess(order.index("inner"), order.index("outer:after-next"))

  def test_value_replacement_passes_through_unchanged(self) -> None:
    # A hook that replaces value (not content) must not be spilled.
    pipeline = ToolPipeline()

    async def replace_value(exec_ctx, result, next_stage) -> ToolResult:
      downstream = await next_stage()
      return ToolResult(ok=True, value={"ok": True, "replaced": 1}, content=None)

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
      return {"ok": True, "content": "z" * 10_000}

    pipeline.add_post_waterfall(replace_value)
    pipeline.add_post_waterfall(self._spill_hook(self.agent))
    pipeline.register_primitive("t", handler)
    result = asyncio.run(pipeline.execute("t:1", "t", "{}"))
    self.assertEqual(result, {"ok": True, "replaced": 1})


if __name__ == "__main__":
  unittest.main()
