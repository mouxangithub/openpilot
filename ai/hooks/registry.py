"""Hook registry — before_tool_call, after_tool_call, before_chat_round, etc."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

HookFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None] | dict[str, Any] | None]

_registry: dict[str, list[tuple[int, HookFn]]] = defaultdict(list)


def register_hook(name: str, fn: HookFn, *, priority: int = 0) -> None:
  _registry[name].append((priority, fn))
  _registry[name].sort(key=lambda x: x[0], reverse=True)


def clear_hooks(name: str | None = None) -> None:
  if name is None:
    _registry.clear()
  else:
    _registry.pop(name, None)


async def run_hooks(name: str, ctx: dict[str, Any]) -> dict[str, Any]:
  """Run hooks in priority order; merge returned dicts into ctx."""
  out = dict(ctx)
  for _, fn in _registry.get(name, []):
    try:
      result = fn(out)
      if hasattr(result, "__await__"):
        result = await result
      if isinstance(result, dict):
        out.update(result)
        if out.get("block"):
          break
    except Exception as e:
      out.setdefault("hook_errors", []).append(f"{name}: {e}")
  return out
