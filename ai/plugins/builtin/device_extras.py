"""Device health plugin — registers device_health / panda_status metadata."""

from __future__ import annotations

from typing import Any, Callable

TOOL_META: dict[str, dict[str, Any]] = {
  "device_health": {"label": "设备健康", "group": "read", "default_enabled": True, "driving": True},
  "panda_status": {"label": "Panda 状态", "group": "read", "default_enabled": True, "driving": True},
}

TOOL_SCHEMAS: list[dict] = []


def make_handlers(ctx: dict) -> dict[str, Callable[..., Any]]:
  get_state_reader = ctx.get("get_state_reader")

  def h_device_health(_a):
    from ai.tools.device_health_tools import device_health
    return device_health()

  def h_panda_status(_a):
    from ai.tools.device_health_tools import panda_status
    return panda_status(get_state_reader=get_state_reader)

  return {
    "device_health": h_device_health,
    "panda_status": h_panda_status,
  }
