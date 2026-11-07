"""Web UI headless mode preference (auto / on / off)."""

from __future__ import annotations

from typing import Any

from webui.server.bridge.headless_util import (
  get_headless_mode_pref,
  has_builtin_display_hardware,
  is_headless_mode,
  set_headless_mode_pref,
)


def snapshot_headless_mode() -> dict[str, Any]:
  has_display = has_builtin_display_hardware()
  return {
    "ok": True,
    "mode": get_headless_mode_pref(),
    "effective_headless": is_headless_mode(),
    "has_builtin_display": has_display,
    "can_turn_off": has_display,
  }


def apply_headless_mode(mode: str) -> dict[str, Any]:
  result = set_headless_mode_pref(mode)
  if not result.get("ok"):
    return result
  return snapshot_headless_mode()
