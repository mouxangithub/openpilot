"""Bridge between hook-registry policies and ToolPipeline guards.

This lets the existing before_tool_call / after_tool_call hook registry
(e.g. driving safety, audit, canvas, externalize) run as ToolPipeline
pre/post hooks, so any code path that uses ToolPipeline gets the same guard
semantics as the chat runner.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ai.core.tools.pipeline import PostToolDecision, PreToolDecision, ToolExecution, ToolPipeline


class GuardContext:
  """Context forwarded to hook-based guards through ToolExecution.extra."""

  def __init__(
    self,
    agent_id: str,
    session_id: str,
    params: Any,
    body: dict[str, Any],
    get_state_reader: Callable[[], Any],
  ) -> None:
    self.agent_id = agent_id
    self.session_id = session_id
    self.params = params
    self.body = body
    self.get_state_reader = get_state_reader

  def to_hook_body(self) -> dict[str, Any]:
    return {
      **self.body,
      "_get_state_reader": self.get_state_reader,
      "_params": self.params,
    }


def _arguments_json(arguments: dict[str, Any]) -> str:
  try:
    return json.dumps(arguments, ensure_ascii=False)
  except Exception:
    return ""


async def _hook_pre_guard(exec_ctx: ToolExecution) -> PreToolDecision:
  extra = exec_ctx.extra or {}
  guard_ctx = extra.get("_guard_ctx")
  if guard_ctx is None:
    return PreToolDecision("allow")

  from ai.hooks.registry import run_hooks
  ctx = await run_hooks("before_tool_call", {
    "name": exec_ctx.name,
    "arguments": _arguments_json(exec_ctx.arguments),
    "agent_id": guard_ctx.agent_id,
    "session_id": guard_ctx.session_id,
    "body": guard_ctx.to_hook_body(),
  })
  if ctx.get("block"):
    return PreToolDecision("deny", ctx.get("reason") or "Tool blocked by hook")
  return PreToolDecision("allow")


async def _hook_post_guard(exec_ctx: ToolExecution, result: dict[str, Any]) -> PostToolDecision:
  extra = exec_ctx.extra or {}
  guard_ctx = extra.get("_guard_ctx")
  if guard_ctx is None:
    return PostToolDecision("accept")

  from ai.hooks.registry import run_hooks
  ctx = await run_hooks("after_tool_call", {
    "name": exec_ctx.name,
    "arguments": _arguments_json(exec_ctx.arguments),
    "agent_id": guard_ctx.agent_id,
    "session_id": guard_ctx.session_id,
    "body": {**guard_ctx.body, "_params": guard_ctx.params},
    "result": result,
  })
  if ctx.get("block"):
    return PostToolDecision("block", feedback=ctx.get("reason") or "Tool result blocked by hook")
  if "result" in ctx:
    return PostToolDecision("accept", result=ctx["result"])
  return PostToolDecision("accept")


def install_hook_guards(
  pipeline: ToolPipeline,
  *,
  agent_id: str,
  session_id: str,
  params: Any,
  body: dict[str, Any],
  get_state_reader: Callable[[], Any],
) -> None:
  """Register registry-based before/after hooks as pipeline guards."""
  guard_ctx = GuardContext(agent_id, session_id, params, body, get_state_reader)
  # Store context on the pipeline so execute() can attach it to each ToolExecution.
  pipeline._guard_context = guard_ctx  # type: ignore[attr-defined]
  pipeline.add_pre_hook(_hook_pre_guard)
  pipeline.add_post_hook(_hook_post_guard)


def attach_guard_context(pipeline: ToolPipeline, guard_ctx: GuardContext) -> None:
  """Attach a guard context to a pipeline for one-shot use."""
  pipeline._guard_context = guard_ctx  # type: ignore[attr-defined]
