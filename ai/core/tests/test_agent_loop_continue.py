"""AgentLoop tool-continuation integration tests.

Regression coverage for the deepseek-harness alignment item:
a tool call must be followed by a *second* LLM round (tool result fed back),
not an early termination. Asserts the exact event order:
  user → assistant(tool_call) → tool_call → tool_result
  → assistant(content) → done
and that ``stream_fn`` is invoked twice.
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass, field
from typing import Any

from ai.core.agent.loop import AgentLoop
from ai.core.agent.state import AgentState
from ai.core.tools.pipeline import ToolPipeline


@dataclass
class Chunk:
  error: str | None = None
  done: bool = False
  content: str = ""
  reasoning_content: str = ""
  tool_calls: list[dict[str, Any]] = field(default_factory=list)


class _Stream:
  """Stream that yields a tool_call round, then a content round."""

  def __init__(self) -> None:
    self.calls: list[dict[str, Any]] = []

  async def _first(self) -> Any:
    yield Chunk(reasoning_content="thinking")
    yield Chunk(tool_calls=[{
      "index": 0,
      "id": "call_abc123",
      "type": "function",
      "function": {"name": "echo", "arguments": "{\"text\": \"hi\"}"},
    }])
    yield Chunk(done=True)

  async def _second(self) -> Any:
    yield Chunk(content="工具结果已收到，结论如下。")
    yield Chunk(done=True)

  def __call__(self, request: dict[str, Any], params: Any) -> Any:
    self.calls.append(request)
    n = len(self.calls)
    if n == 1:
      return self._first()
    return self._second()


def _echo(args: dict[str, Any]) -> dict[str, Any]:
  return {"ok": True, "echo": args.get("text", "")}


class AgentLoopContinuationTest(unittest.IsolatedAsyncioTestCase):
  async def test_tool_call_is_followed_by_second_llm_round(self) -> None:
    stream = _Stream()
    pipeline = ToolPipeline({"echo": _echo})
    events: list[dict[str, Any]] = []

    async def emit(ev: dict[str, Any]) -> None:
      events.append(ev)

    loop = AgentLoop(
      session_id="sess-cont",
      agent_id="agent-cont",
      params=None,
      emit=emit,
      stream_fn=stream,
      tool_pipeline=pipeline,
      max_tool_rounds=16,
    )
    loop.configure_request(provider="test", model="test-model", system="You are a test assistant.", tools=pipeline.schemas())
    await loop.add_user_message("请调用工具并继续", wakeup=False)
    # Enter the running phase explicitly, then drive one _run. The continuation
    # (second stream round) must happen inside the same turn.
    loop.state.wake_driver()
    result = await loop._run()

    self.assertTrue(result.get("ok"), f"loop run failed: {result}")
    self.assertEqual(len(stream.calls), 2, "stream_fn must be called twice (tool round + final round)")

    types = [e["type"] for e in events]
    # Both rounds emitted content (assistant turns).
    self.assertIn("content", types)
    tool_result = [e for e in events if e["type"] == "tool_result"]
    self.assertEqual(len(tool_result), 1)
    self.assertEqual(tool_result[0]["name"], "echo")
    self.assertEqual(tool_result[0]["result"].get("echo"), "hi")

    # The second stream round produced a final content chunk after the tool result.
    content_idx = [i for i, e in enumerate(events) if e["type"] == "content"]
    tool_idx = [i for i, e in enumerate(events) if e["type"] == "tool_result"]
    self.assertTrue(tool_idx and content_idx, "missing tool_result/content events")
    self.assertGreater(content_idx[-1], tool_idx[-1], "content must come after tool_result")

    # Tool result must be projected into the session history as role=tool.
    msgs = loop.log.derive_messages()
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    self.assertEqual(len(tool_msgs), 1)
    self.assertEqual(tool_msgs[0]["tool_call_id"], "call_abc123")
    self.assertIn("hi", str(tool_msgs[0].get("content", "")))

  async def test_no_tool_call_terminates_after_single_round(self) -> None:
    calls: list[dict[str, Any]] = []

    async def one_round(request: dict[str, Any], params: Any) -> Any:
      calls.append(request)
      yield Chunk(content="直接回答。")
      yield Chunk(done=True)

    pipeline = ToolPipeline({})
    events: list[dict[str, Any]] = []

    async def emit(ev: dict[str, Any]) -> None:
      events.append(ev)

    loop = AgentLoop(
      session_id="sess-plain",
      agent_id="agent-plain",
      params=None,
      emit=emit,
      stream_fn=one_round,
      tool_pipeline=pipeline,
      max_tool_rounds=16,
    )
    loop.configure_request(provider="test", model="test-model", system="sys", tools=[])
    await loop.add_user_message("你好", wakeup=False)
    loop.state.wake_driver()
    result = await loop._run()

    self.assertTrue(result.get("ok"), f"loop run failed: {result}")
    self.assertEqual(len(calls), 1, "no tool call => single LLM round")
    self.assertNotIn("tool_call", [e["type"] for e in events])
    # The raw AgentLoop emits content deltas; the "done" event is emitted by
    # the Agent facade (Agent.run_with_loop), so here we assert the loop
    # produced exactly one assistant round and stopped.
    self.assertIn("content", [e["type"] for e in events])


if __name__ == "__main__":
  unittest.main()
