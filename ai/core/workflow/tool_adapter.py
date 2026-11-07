"""Stable WorkflowEngine tool bridge (T-P0.5, T-P1.7).

The naive bridge rebuilt ``make_handlers()`` on every TOOL step, which is
expensive and drops caller state (params / reader / audit). This adapter
caches a single handler map for the life of a run, wraps sync/async handlers
uniformly, honors cooperative cancellation through ``RunContext.cancel_event``
and normalizes failures into the ``{ok, error, code}`` contract used by
``WorkflowErrorCode``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from ai.core.workflow.context import RunContext
from ai.core.workflow.errors import WorkflowErrorCode


class WorkflowToolAdapter:
  """Adapt the full tool-handler map into a ``ToolRunner``.

  Construct once per workflow run (or once globally and reuse), then pass
  ``adapter.run`` as ``engine.set_tool_runner``.
  """

  def __init__(
    self,
    handlers: dict[str, Callable[..., Any]],
    *,
    ctx: RunContext | None = None,
    cancel_event: asyncio.Event | None = None,
  ) -> None:
    self._handlers = handlers
    self._ctx = ctx
    self._cancel_event = cancel_event

  @classmethod
  def from_factory(
    cls,
    handlers_factory: Callable[[], dict[str, Callable[..., Any]]],
    *,
    ctx: RunContext | None = None,
    cancel_event: asyncio.Event | None = None,
  ) -> "WorkflowToolAdapter":
    """Build an adapter whose handler map is created lazily and then cached."""
    return cls(handlers_factory(), ctx=ctx, cancel_event=cancel_event)

  def _active_cancel_event(self) -> asyncio.Event | None:
    if self._cancel_event is not None:
      return self._cancel_event
    if self._ctx is not None:
      return self._ctx.cancel_event
    return None

  def _is_cancelled(self) -> bool:
    """True if the run was cancelled via the flag or the shared cancel event.

    ``RunContext`` exposes both ``cancelled`` (a boolean set by dispose) and
    ``cancel_event``; ``RunContext.check_cancelled`` treats them identically, so
    the adapter must too.
    """
    if self._ctx is not None and getattr(self._ctx, "cancelled", False):
      return True
    event = self._active_cancel_event()
    return event is not None and event.is_set()

  def tool_names(self) -> list[str]:
    return sorted(self._handlers.keys())

  def has_tool(self, name: str) -> bool:
    return name in self._handlers

  async def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Invoke ``name`` with ``args``, normalizing sync/async + errors."""
    handler = self._handlers.get(name)
    if handler is None:
      return {
        "ok": False,
        "error": f"tool '{name}' not found",
        "code": WorkflowErrorCode.TOOL_NOT_FOUND.value,
      }

    cancel_event = self._active_cancel_event()
    if self._is_cancelled():
      return {
        "ok": False,
        "error": "cancelled before invocation",
        "code": WorkflowErrorCode.CANCELLED.value,
      }

    try:
      if asyncio.iscoroutinefunction(handler):
        coro = handler(args)
        if cancel_event is not None:
          coro_task = asyncio.ensure_future(coro)
          wait_tasks = {coro_task}
          # Race the tool against cancellation; if the workflow is cancelled
          # first, abort the tool without waiting for it to finish.
          event_task = asyncio.create_task(cancel_event.wait())
          wait_tasks.add(event_task)
          done, pending = await asyncio.wait(
            wait_tasks,
            return_when=asyncio.FIRST_COMPLETED,
          )
          for p in pending:
            p.cancel()
          if event_task in done:
            return {
              "ok": False,
              "error": "cancelled before completion",
              "code": WorkflowErrorCode.CANCELLED.value,
            }
          result = coro_task.result()
        else:
          result = await coro
      else:
        result = handler(args)
        if self._is_cancelled():
          return {
            "ok": False,
            "error": "cancelled before completion",
            "code": WorkflowErrorCode.CANCELLED.value,
          }
    except asyncio.CancelledError:
      return {
        "ok": False,
        "error": "cancelled",
        "code": WorkflowErrorCode.CANCELLED.value,
      }
    except Exception as exc:
      return {
        "ok": False,
        "error": str(exc),
        "code": WorkflowErrorCode.TOOL_FAILED.value,
      }

    if isinstance(result, dict) and "ok" not in result:
      # Coerce to the standard contract without dropping original fields.
      return {"ok": True, **result}
    return result


__all__ = ["WorkflowToolAdapter"]