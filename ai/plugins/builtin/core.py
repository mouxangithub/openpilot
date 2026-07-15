"""Built-in plugin — registers extension tool metadata (handlers live in agent_tools)."""

from __future__ import annotations

# Metadata-only plugin; execution handlers are wired in ai.tools.extensions.

TOOL_META: dict[str, dict] = {}

TOOL_SCHEMAS: list[dict] = []


def make_handlers(_ctx: dict) -> dict:
  return {}
