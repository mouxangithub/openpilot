"""Route analytics plugin — metadata grouping for route scoring tools."""

from __future__ import annotations

TOOL_META: dict[str, dict[str, Any]] = {
  "batch_compare_routes_tune": {"label": "批量路线调参评分", "group": "read", "default_enabled": True, "driving": True, "plugin": "route-analytics"},
  "score_route_tune": {"label": "路线调参评分", "group": "read", "default_enabled": True, "driving": True, "plugin": "route-analytics"},
}

TOOL_SCHEMAS: list[dict] = []


def make_handlers(_ctx: dict) -> dict:
  return {}
