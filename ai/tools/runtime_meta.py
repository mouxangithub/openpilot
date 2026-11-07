"""Runtime tool metadata registry.

Allows dynamically discovered tools (MCP, learned skills, workflow-generated)
to publish stable UI labels and descriptions without modifying static
``TOOL_META`` constants.
"""

from __future__ import annotations

from typing import Any

_runtime_meta: dict[str, dict[str, Any]] = {}


def register_tool_meta(
  name: str,
  *,
  label: str = "",
  description: str = "",
  group: str = "read",
  default_enabled: bool = True,
  driving: bool = True,
  **extra: Any,
) -> None:
  """Register or update metadata for a runtime-discovered tool."""
  _runtime_meta[name] = {
    "label": label or name,
    "description": description,
    "group": group,
    "default_enabled": default_enabled,
    "driving": driving,
    **extra,
  }


def get_tool_meta(name: str) -> dict[str, Any] | None:
  """Return metadata for ``name`` if it has been registered at runtime."""
  return dict(_runtime_meta.get(name, {})) if name in _runtime_meta else None


def list_tool_meta() -> dict[str, dict[str, Any]]:
  """Return a copy of all runtime-registered tool metadata."""
  return {k: dict(v) for k, v in _runtime_meta.items()}


def clear_tool_meta(name: str = "") -> None:
  """Clear metadata for a single tool, or all runtime metadata if empty."""
  if name:
    _runtime_meta.pop(name, None)
  else:
    _runtime_meta.clear()


__all__ = ["register_tool_meta", "get_tool_meta", "list_tool_meta", "clear_tool_meta"]
