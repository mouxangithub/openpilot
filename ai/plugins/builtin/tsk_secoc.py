"""TSK SecOC diagnostics plugin."""

from __future__ import annotations

from typing import Any, Callable


TOOL_META: dict[str, dict[str, Any]] = {
  "tsk_diagnose_failure": {"label": "TSK 结构化诊断", "group": "read", "default_enabled": True, "driving": True},
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "tsk_diagnose_failure", "description": "Structured TSK/SecOC pipeline status, issues, and next_steps for matcher/CAN/DF failures.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def make_handlers(ctx: dict) -> dict[str, Callable[..., Any]]:
  p = ctx.get("params")

  def h_diag(_a):
    from ai.tools.tsk_diagnose_tools import tsk_diagnose_failure
    return tsk_diagnose_failure(p)

  return {"tsk_diagnose_failure": h_diag}
