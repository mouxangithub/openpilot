"""Derive browser-playable alert sound id from cereal selfdriveState (mirrors soundd)."""

from __future__ import annotations

import time
from typing import Any

SELFDRIVE_STATE_TIMEOUT = 5
SELFDRIVE_UNRESPONSIVE_TIMEOUT = 10


def _enum_name(val: Any) -> str:
  if val is None:
    return "none"
  name = str(val).split(".")[-1].strip()
  return name if name else "none"


def derive_alert_sound(sm: Any, ss: Any, started: bool) -> str:
  if not started:
    return "none"
  try:
    ss_missing = time.monotonic() - sm.recv_time["selfdriveState"]
    enabled = bool(getattr(ss, "enabled", False))
    if ss_missing > SELFDRIVE_STATE_TIMEOUT:
      if enabled and (ss_missing - SELFDRIVE_STATE_TIMEOUT) < SELFDRIVE_UNRESPONSIVE_TIMEOUT:
        return "warningImmediate"
  except Exception:
    pass
  try:
    if hasattr(ss, "alertSound"):
      return _enum_name(ss.alertSound)
  except Exception:
    pass
  return "none"


def quiet_mode_enabled() -> bool:
  try:
    from openpilot.common.params import Params
    return Params().get_bool("QuietMode")
  except Exception:
    return False
