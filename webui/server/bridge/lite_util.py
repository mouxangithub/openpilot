"""Lite hardware (C3 without I2C amplifier) helpers for WebUI."""

from __future__ import annotations

import os

LITE_UNAVAILABLE_PARAMS = frozenset({
  "RecordAudio",
})


def is_lite_hw() -> bool:
  return os.getenv("LITE") is not None


def should_hide_widget(widget: dict) -> bool:
  lite = is_lite_hw()
  if widget.get("lite_only") and not lite:
    return True
  param = widget.get("param")
  if lite and param in LITE_UNAVAILABLE_PARAMS:
    return True
  return False
