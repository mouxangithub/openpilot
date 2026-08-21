"""Tool execution with audit logging."""

from __future__ import annotations

import asyncio
import json
from typing import Any


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
    try:
      from ai.tools.audit_store import record_audit
      ok = True
      if isinstance(result, dict) and result.get("ok") is False:
        ok = False
      record_audit(action="tool_call", tool=name, detail={"args": args, "ok": ok}, ok=ok)
    except Exception:
      pass
    return result
  except Exception as e:
    return {"ok": False, "error": f"Tool execution failed: {e}"}


async def execute_tool_async(handlers: dict[str, Any], name: str, arguments: str) -> Any:
  handler = handlers.get(name)
  if handler is None:
    return {"ok": False, "error": f"Tool '{name}' not implemented"}
  try:
    args = json.loads(arguments) if arguments else {}
  except json.JSONDecodeError:
    return {"ok": False, "error": "Invalid tool arguments JSON"}
  try:
    result = handler(args)
    if asyncio.iscoroutine(result):
      result = await result
    try:
      from ai.tools.audit_store import record_audit
      ok = True
      if isinstance(result, dict) and result.get("ok") is False:
        ok = False
      record_audit(action="tool_call", tool=name, detail={"args": args, "ok": ok}, ok=ok)
    except Exception:
      pass
    return result
  except Exception as e:
    return {"ok": False, "error": f"Tool execution failed: {e}"}
