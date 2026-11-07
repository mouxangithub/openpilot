"""Audit coverage wrapper for platform tool handlers (T-P1.4).

Automatically records tool invocations that mutate state or access sensitive
capabilities. Read-only queries (sessions_list, read_daily_memory, etc.) are
not wrapped to keep the audit trail focused.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any, Callable

from ai.tools.domains.platform.audit_store import record_audit


_AUDITED_TOOLS: frozenset[str] = frozenset({
  "sessions_send",
  "approve_learned_skill",
  "update_user_profile",
  "update_workspace_file",
  "bootstrap_workspace",
  "restore_platform_backup",
  "run_workflow",
  "run_evolution_pipeline",
  "run_gepa_evolution",
  "schedule_task",
  "cancel_scheduled_task",
  "append_unified_memory",
  "manage_mcp_server",
  "call_mcp_tool",
  "read_mcp_resource",
  "get_mcp_prompt",
  "export_platform_backup",
})

_SENSITIVE_KEYS: frozenset[str] = frozenset({
  "bundle", "content", "arguments", "args", "command", "env", "token", "api_key",
  "secret", "password", "private_key", "confirm",
})


def _scrub_args(args: dict[str, Any]) -> dict[str, Any]:
  """Return a shallow copy with sensitive / large values redacted."""
  out = copy.copy(args)
  for key in list(out.keys()):
    low = key.lower()
    if low in _SENSITIVE_KEYS:
      val = out[key]
      if isinstance(val, (dict, list)):
        out[key] = f"<{type(val).__name__}:{len(val)}>"
      else:
        out[key] = "<redacted>"
    elif low == "definition" and isinstance(out[key], dict):
      # workflow definitions can be large; keep id/name only
      definition = out[key]
      out[key] = {"id": definition.get("id"), "name": definition.get("name")}
  return out


def _session_id_from_args(args: dict[str, Any]) -> str:
  for key in ("session_id", "sessionId"):
    if args.get(key):
      return str(args[key])
  return ""


def wrap_with_audit(
  handlers: dict[str, Callable[..., Any]],
  *,
  session_id_supplier: Callable[[], str] | None = None,
) -> dict[str, Callable[..., Any]]:
  """Wrap selected handlers so every call writes an audit entry."""
  wrapped: dict[str, Callable[..., Any]] = {}

  def _audit(name: str, args: dict[str, Any], result: Any) -> None:
    ok = bool(result.get("ok")) if isinstance(result, dict) else True
    session_id = session_id_supplier() if session_id_supplier else _session_id_from_args(args)
    record_audit(
      action="tool_invoke",
      tool=name,
      detail={
        "args": _scrub_args(args),
        "result_ok": ok,
        "error": result.get("error") if isinstance(result, dict) else "",
      },
      ok=ok,
      session_id=session_id,
    )

  for name, handler in handlers.items():
    if name not in _AUDITED_TOOLS:
      wrapped[name] = handler
      continue

    if asyncio.iscoroutinefunction(handler):
      async def _async_wrapper(args: dict[str, Any], _name: str = name, _fn: Callable[..., Any] = handler) -> Any:
        try:
          result = await _fn(args)
        except Exception as exc:
          _audit(_name, args, {"ok": False, "error": str(exc)})
          raise
        _audit(_name, args, result)
        return result
      wrapped[name] = _async_wrapper
    else:
      def _sync_wrapper(args: dict[str, Any], _name: str = name, _fn: Callable[..., Any] = handler) -> Any:
        try:
          result = _fn(args)
        except Exception as exc:
          _audit(_name, args, {"ok": False, "error": str(exc)})
          raise
        if asyncio.iscoroutine(result):
          # If a sync-looking handler returns a coroutine, wrap it.
          async def _await_and_audit(coro: Any, _n: str = _name, _a: dict[str, Any] = args) -> Any:
            try:
              res = await coro
            except Exception as exc:
              _audit(_n, _a, {"ok": False, "error": str(exc)})
              raise
            _audit(_n, _a, res)
            return res
          return _await_and_audit(result)
        _audit(_name, args, result)
        return result
      wrapped[name] = _sync_wrapper

  return wrapped
