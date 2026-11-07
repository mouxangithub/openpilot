"""Shared offroad checks for WebUI actions (driver view, etc.)."""

from __future__ import annotations

from typing import Any


def device_is_onroad() -> bool:
  try:
    import openpilot.cereal.messaging as messaging
    sm = messaging.SubMaster(["deviceState"], poll="deviceState")
    sm.update(500)
    if sm.valid.get("deviceState"):
      return bool(sm["deviceState"].started)
  except Exception:
    pass
  return False


def require_offroad() -> dict[str, Any] | None:
  if device_is_onroad():
    return {
      "ok": False,
      "error": "only_available_offroad",
      "message": "Only available while offroad",
    }
  return None
