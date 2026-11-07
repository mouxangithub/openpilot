"""Tool execution pipeline with pre/guard/around/post/result stages.

A minimal Python port of dsh-tools: registered tools pass through
pre-execute policy, guards, execution, post-execute policy, and result
materialization. The pipeline is intentionally synchronous-friendly while
still supporting async tool bodies.
"""

from __future__ import annotations

import asyncio
import functools
import json
import time
from contextvars import ContextVar, Token, copy_context

session_ctx: ContextVar[Any] = ContextVar("session_ctx", default=None)
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
  """Structured tool result separating value, textual content, and block."""

  ok: bool
  value: Any
  content: str | None = None
  block: dict[str, Any] | None = None
  meta: dict[str, Any] = field(default_factory=dict)


def build_tool_result(result: Any) -> ToolResult:
  """Classify a legacy result without changing its wire representation."""
  if isinstance(result, dict):
    content = None
    for key in ("content", "text", "stdout", "preview"):
      if isinstance(result.get(key), str):
        content = result[key]
        break
    return ToolResult(
      ok=result.get("ok") is not False,
      value=result,
      content=content,
      block=result,
    )
  if isinstance(result, str):
    return ToolResult(ok=True, value=result, content=result)
  return ToolResult(ok=True, value=result)


def classify_result_kind(result: Any) -> str:
  """Return the dsh-style result arm: value, content, or block."""
  structured = build_tool_result(result)
  if structured.content is not None:
    return "content"
  if structured.block is not None:
    return "block"
  return "value"


def truncate_content_head_tail(content: str, max_bytes: int, *, notice: str = "\\n... (truncated) ...\\n") -> str:
  """UTF-8-safe head/tail retention with the notice reserved in the cap."""
  raw = str(content).encode("utf-8")
  if max_bytes <= 0 or len(raw) <= max_bytes:
    return str(content)
  notice_bytes = notice.encode("utf-8")
  if len(notice_bytes) >= max_bytes:
    return notice_bytes[:max_bytes].decode("utf-8", errors="ignore")
  budget = max_bytes - len(notice_bytes)
  head_budget = budget // 2
  tail_budget = budget - head_budget
  head = raw[:head_budget].decode("utf-8", errors="ignore")
  tail = raw[-tail_budget:].decode("utf-8", errors="ignore") if tail_budget else ""
  return head + notice + tail


class ToolError(Exception):
  def __init__(self, message: str, code: str = "TOOL_ERROR") -> None:
    super().__init__(message)
    self.code = code


class ToolNotFoundError(ToolError):
  def __init__(self, name: str) -> None:
    super().__init__(f"Tool '{name}' not implemented", "UNKNOWN_TOOL")
    self.name = name


@dataclass
class ToolDefinition:
  name: str
  description: str
  parameters: dict[str, Any]
  handler: Callable[[dict[str, Any]], Any]
  guard: Callable[[dict[str, Any]], str | None] | None = None
  timeout_ms: int | None = None
  is_async: bool = False

  def schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": self.parameters,
      },
    }


PreDecisionKind = str
PostDecisionKind = str


@dataclass
class PreToolDecision:
  kind: PreDecisionKind  # allow | deny | ask
  reason: str = ""


@dataclass
class PostToolDecision:
  kind: PostDecisionKind  # accept | block
  result: dict[str, Any] | None = None
  feedback: str = ""


@dataclass
class ToolExecution:
  call_id: str
  name: str
  arguments: dict[str, Any]
  cancelled: bool = False
  extra: dict[str, Any] = field(default_factory=dict)


PreExecuteHook = Callable[[ToolExecution], PreToolDecision | Coroutine[Any, Any, PreToolDecision]]
PostExecuteHook = Callable[[ToolExecution, dict[str, Any]], PostToolDecision | Coroutine[Any, Any, PostToolDecision]]
WaterfallNext = Callable[[], Coroutine[Any, Any, ToolResult]]
WaterfallHook = Callable[[ToolExecution, ToolResult, WaterfallNext], ToolResult | None | Coroutine[Any, Any, ToolResult | None]]


class ToolPipeline:
  """Runs tools through policy + guard + body + post-policy."""

  def __init__(self, handlers: dict[str, Any] | None = None) -> None:
    self._tools: dict[str, ToolDefinition] = {}
    self._pre_hooks: list[PreExecuteHook] = []
    self._post_hooks: list[PostExecuteHook] = []
    self._post_waterfall: list[WaterfallHook] = []
    if handlers:
      for name, handler in handlers.items():
        self.register_primitive(name, handler)

  def register(self, tool: ToolDefinition) -> None:
    self._tools[tool.name] = tool

  def register_primitive(self, name: str, handler: Callable[[dict[str, Any]], Any]) -> None:
    self._tools[name] = ToolDefinition(
      name=name,
      description="",
      parameters={"type": "object", "properties": {}},
      handler=handler,
    )

  def add_pre_hook(self, hook: PreExecuteHook) -> Callable[[], None]:
    self._pre_hooks.append(hook)

    def remove() -> None:
      try:
        self._pre_hooks.remove(hook)
      except ValueError:
        pass
    return remove

  def add_post_hook(self, hook: PostExecuteHook) -> Callable[[], None]:
    self._post_hooks.append(hook)

    def remove() -> None:
      try:
        self._post_hooks.remove(hook)
      except ValueError:
        pass
    return remove

  def add_post_waterfall(self, hook: WaterfallHook) -> Callable[[], None]:
    """Add a post-result waterfall stage; ``next`` continues the chain."""
    self._post_waterfall.append(hook)

    def remove() -> None:
      try:
        self._post_waterfall.remove(hook)
      except ValueError:
        pass
    return remove

  def schemas(self) -> list[dict[str, Any]]:
    return [t.schema() for t in self._tools.values()]

  def get(self, name: str) -> ToolDefinition | None:
    return self._tools.get(name)

  async def execute(
    self,
    call_id: str,
    name: str,
    raw_arguments: str,
    *,
    is_cancelled: Callable[[], bool] | None = None,
    timeout_seconds: float | None = None,
    extra: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    tool = self._tools.get(name)
    if tool is None:
      return {"ok": False, "error": f"Tool '{name}' not implemented", "error_code": "UNKNOWN_TOOL"}

    try:
      args = json.loads(raw_arguments) if raw_arguments else {}
      if not isinstance(args, dict):
        args = {"value": args}
    except json.JSONDecodeError as e:
      return {"ok": False, "error": f"Invalid tool arguments JSON: {e}", "error_code": "INVALID_INPUT"}

    exec_ctx = ToolExecution(call_id=call_id, name=name, arguments=args, extra=extra or {})
    guard_ctx = getattr(self, "_guard_context", None)
    if guard_ctx is not None:
      exec_ctx.extra["_guard_ctx"] = guard_ctx

    # Pre-execute hooks
    for hook in self._pre_hooks:
      decision = hook(exec_ctx)
      if asyncio.iscoroutine(decision):
        decision = await decision
      if decision.kind != "allow":
        return {"ok": False, "error": decision.reason or f"Tool '{name}' blocked by pre-execute policy", "error_code": "BLOCKED"}

    # Guard
    if tool.guard is not None:
      reason = tool.guard(args)
      if reason:
        return {"ok": False, "error": reason, "error_code": "BLOCKED"}

    if is_cancelled and is_cancelled():
      exec_ctx.cancelled = True
      return {"ok": False, "error": "Tool call was cancelled before execution", "error_code": "CANCELLED"}

    # Execute
    context_token: Token[Any] | None = None
    if extra and extra.get("session_ctx") is not None:
      context_token = session_ctx.set(extra["session_ctx"])
    try:
      effective_timeout = timeout_seconds
      if effective_timeout is None and tool.timeout_ms:
        effective_timeout = tool.timeout_ms / 1000.0

      body_invoked = True
      try:
        if asyncio.iscoroutinefunction(tool.handler) or getattr(tool, "is_async", False):
          if effective_timeout is not None and effective_timeout > 0:
            result = await asyncio.wait_for(tool.handler(args), timeout=effective_timeout)
          else:
            result = await tool.handler(args)
        else:
          # ContextVar does NOT propagate into executor threads automatically;
          # run the handler inside a copy of the current context so session
          # handlers can read `session_ctx` (domain event sink binding).
          loop = asyncio.get_running_loop()
          run_ctx = copy_context()
          if effective_timeout is not None and effective_timeout > 0:
            result = await asyncio.wait_for(
              loop.run_in_executor(None, functools.partial(run_ctx.run, tool.handler, args)),
              timeout=effective_timeout,
            )
          else:
            result = await loop.run_in_executor(None, functools.partial(run_ctx.run, tool.handler, args))
      except TimeoutError:
        body_invoked = False
        result = {"ok": False, "error": f"Tool '{name}' timed out after {effective_timeout}s", "error_code": "TOOL_TIMEOUT", "retryable": True}
      except asyncio.CancelledError:
        raise
      except Exception as e:
        result = {"ok": False, "error": f"Tool execution failed: {e}", "error_code": "TOOL_ERROR"}

      if is_cancelled and is_cancelled():
        if body_invoked:
          return {"ok": False, "error": "Tool call was cancelled during execution", "error_code": "CANCELLED"}
        return {"ok": False, "error": "Tool call was cancelled before execution", "error_code": "CANCELLED"}

      if not isinstance(result, dict):
        result = {"ok": True, "value": result}

      # Post-execute hooks
      for hook in self._post_hooks:
        decision = hook(exec_ctx, result)
        if asyncio.iscoroutine(decision):
          decision = await decision
        if decision.kind == "block":
          return {"ok": False, "error": decision.feedback or "Tool result blocked by post-execute policy", "error_code": "BLOCKED"}
        if decision.kind == "accept" and decision.result is not None:
          result = decision.result

      if self._post_waterfall:
        async def run_stage(index: int, current: ToolResult) -> ToolResult:
          if index >= len(self._post_waterfall):
            return current
          stage = self._post_waterfall[index]

          async def next_stage() -> ToolResult:
            return await run_stage(index + 1, current)

          updated = stage(exec_ctx, current, next_stage)
          if asyncio.iscoroutine(updated):
            updated = await updated
          return updated if isinstance(updated, ToolResult) else current

        structured = await run_stage(0, build_tool_result(result))
        result = structured.value

      return result
    finally:
      if context_token is not None:
        session_ctx.reset(context_token)

  def wrap_executor(self) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Return a callable matching the old execute_tool_async signature."""
    async def _run(
      handlers: dict[str, Any],
      name: str,
      arguments: str,
      *,
      timeout_seconds: float | None = None,
      is_cancelled: Callable[[], bool] | None = None,
    ) -> Any:
      # Rebuild pipeline from handlers for compatibility.
      pipeline = ToolPipeline(handlers)
      return await pipeline.execute(
        call_id=f"{name}:{int(time.monotonic() * 1000)}",
        name=name,
        raw_arguments=arguments,
        is_cancelled=is_cancelled,
        timeout_seconds=timeout_seconds,
      )
    return _run
