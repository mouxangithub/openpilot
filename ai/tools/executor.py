"""Tool execution with audit logging.

Backward-compatible helpers that can delegate to ai.core.tools.pipeline.ToolPipeline
so older callers get the same guard/hook semantics as the Agent facade.
"""

from __future__ import annotations

import asyncio
import functools
import json
from typing import Any, Callable


def _record_tool_audit(name: str, args: dict[str, Any], result: Any) -> None:
  try:
    from ai.tools.audit_store import record_audit
    ok = True
    if isinstance(result, dict) and result.get("ok") is False:
      ok = False
    record_audit(action="tool_call", tool=name, detail={"args": args, "ok": ok}, ok=ok)
  except Exception:
    pass


def execute_tool(handlers: dict[str, Any], name: str, arguments: str) -> Any:
  handler = handlers.get(name)
  if handler is None:
    return {"ok": False, "error": f"Tool '{name}' not implemented"}
  try:
    args = json.loads(arguments) if arguments else {}
  except json.JSONDecodeError:
    return {"ok": False, "error": "Invalid tool arguments JSON"}
  try:
    result = handler(args)
    _record_tool_audit(name, args, result)
    return result
  except Exception as e:
    return {"ok": False, "error": f"Tool execution failed: {e}"}


async def execute_tool_async(
  handlers: dict[str, Any],
  name: str,
  arguments: str,
  *,
  timeout: float | None = None,
  is_cancelled: Callable[[], bool] | None = None,
  pipeline: Any | None = None,
) -> Any:
  """Execute a tool handler without blocking the event loop.

  If ``pipeline`` is provided it takes precedence over ``handlers`` and runs
  through the ToolPipeline guard/hook stages.

  Synchronous handlers run in the default thread pool. ``timeout`` applies to
  the overall handler invocation. ``is_cancelled`` is polled before execution
  and, for coroutine handlers, between await points where the handler itself
  yields control. Synchronous handlers cannot be interrupted mid-flight, but
  their result is discarded if cancellation is requested before they return.
  """
  if pipeline is not None:
    return await execute_tool_async_with_pipeline(
      pipeline, name, arguments, timeout=timeout, is_cancelled=is_cancelled
    )

  handler = handlers.get(name)
  if handler is None:
    return {"ok": False, "error": f"Tool '{name}' not implemented"}
  try:
    args = json.loads(arguments) if arguments else {}
  except json.JSONDecodeError:
    return {"ok": False, "error": "Invalid tool arguments JSON"}

  if is_cancelled and is_cancelled():
    return {"ok": False, "error": "Tool call was cancelled before execution"}

  async def _invoke() -> Any:
    if asyncio.iscoroutinefunction(handler):
      # Async handlers get cancellation propagated naturally. We shield only
      # the outer wait_for timeout so a job-level cancel reaches the coroutine.
      return await handler(args)
    loop = asyncio.get_running_loop()
    # run_in_executor keeps sync handlers off the event loop. They cannot be
    # force-killed, but they will not stall other async work.
    return await loop.run_in_executor(None, functools.partial(handler, args))

  try:
    if timeout is not None and timeout > 0:
      # Shield the inner coroutine from timeout cancellation so that a
      # deliberate job cancel can still propagate to async handlers.
      result = await asyncio.wait_for(_invoke(), timeout=timeout)
    else:
      result = await _invoke()
  except asyncio.TimeoutError:
    return {"ok": False, "error": f"Tool '{name}' timed out after {timeout}s"}
  except asyncio.CancelledError:
    # Re-raise so the caller's cancellation semantics work (e.g. ChatCancelled).
    raise
  except Exception as e:
    return {"ok": False, "error": f"Tool execution failed: {e}"}

  # For sync handlers that were already running when cancellation was requested,
  # discard the result and report cancellation instead of leaking it onward.
  if is_cancelled and is_cancelled():
    return {"ok": False, "error": "Tool call was cancelled during execution"}

  _record_tool_audit(name, args, result)
  return result


def execute_tool_with_pipeline(
  pipeline: Any,
  name: str,
  arguments: str,
  *,
  call_id: str = "",
  timeout: float | None = None,
) -> Any:
  """Execute via a ToolPipeline (synchronous wrapper for compatibility)."""
  try:
    return asyncio.run(pipeline.execute(
      call_id=call_id or name,
      name=name,
      raw_arguments=arguments,
      timeout_seconds=timeout,
    ))
  except Exception as e:
    return {"ok": False, "error": f"Tool execution failed: {e}"}


async def execute_tool_async_with_pipeline(
  pipeline: Any,
  name: str,
  arguments: str,
  *,
  call_id: str = "",
  timeout: float | None = None,
  is_cancelled: Callable[[], bool] | None = None,
) -> Any:
  """Execute via a ToolPipeline with cancellation and timeout support."""
  return await pipeline.execute(
    call_id=call_id or name,
    name=name,
    raw_arguments=arguments,
    timeout_seconds=timeout,
    is_cancelled=is_cancelled,
  )
