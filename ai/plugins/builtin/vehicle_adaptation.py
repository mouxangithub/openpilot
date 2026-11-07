"""Vehicle adaptation plugin — metadata grouping."""

from __future__ import annotations

TOOL_META: dict[str, dict[str, Any]] = {
  "car_porting_auto_fingerprint": {"label": "自动指纹", "group": "read", "default_enabled": True, "driving": True, "plugin": "vehicle-adaptation"},
  "generate_adaptation_pr_draft": {"label": "适配 PR 草稿", "group": "read", "default_enabled": True, "driving": True, "plugin": "vehicle-adaptation"},
}

TOOL_SCHEMAS: list[dict] = []


def make_handlers(_ctx: dict) -> dict:
  return {}
