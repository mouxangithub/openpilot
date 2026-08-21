"""Sunnylink cloud backup plugin."""

from __future__ import annotations

from typing import Any, Callable


TOOL_META: dict[str, dict[str, Any]] = {
  "sunnylink_backup_watch": {"label": "Sunnylink 备份进度", "group": "read", "default_enabled": True, "driving": True},
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "sunnylink_backup_watch", "description": "Poll Sunnylink backup/restore manager state and suggest retry steps.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def make_handlers(ctx: dict) -> dict[str, Callable[..., Any]]:
  p = ctx.get("params")

  def h_watch(_a):
    from ai.tools.sunnylink_tools import sunnylink_backup_watch
    return sunnylink_backup_watch(p)

  return {"sunnylink_backup_watch": h_watch}
