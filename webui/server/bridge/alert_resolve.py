"""Onroad alert resolution — mirrors openpilot/selfdrive/ui/onroad/alert_renderer.py get_alert()."""

from __future__ import annotations

import time
from typing import Any

SELFDRIVE_STATE_TIMEOUT = 5
SELFDRIVE_UNRESPONSIVE_TIMEOUT = 10


def _size_name(ss) -> str:
  if not hasattr(ss, "alertSize") or ss.alertSize is None:
    return "none"
  raw = ss.alertSize.raw if hasattr(ss.alertSize, "raw") else int(ss.alertSize)
  mapping = {0: "none", 1: "small", 2: "mid", 3: "full"}
  if raw in mapping:
    return mapping[raw]
  name = str(ss.alertSize).split(".")[-1].lower()
  return name if name in mapping.values() else "none"


def _status_name(ss) -> str:
  if not hasattr(ss, "alertStatus") or ss.alertStatus is None:
    return "normal"
  name = str(ss.alertStatus).split(".")[-1].lower()
  return name if name else "normal"


def resolve_onroad_alert(sm: Any, ss: Any, started: bool) -> dict[str, str] | None:
  """
  Return alert dict {text1, text2, size, status, synthetic} or None when no alert.
  Matches native AlertRenderer.get_alert() precedence.
  """
  if not started:
    return None

  try:
    from webui.server.bridge.car_context import get_car_context
    from openpilot.common.hardware import TICI

    car_ctx = get_car_context()
    started_frame = int(car_ctx.started_frame or 0)
    started_time = float(car_ctx.started_time or 0.0)
  except Exception:
    started_frame = 0
    started_time = 0.0
    TICI = False

  updated = True
  try:
    updated = bool(sm.updated["selfdriveState"])
  except Exception:
    pass

  recv_frame = int(sm.recv_frame.get("selfdriveState", 0) if hasattr(sm, "recv_frame") else 0)

  if not updated and started_time > 0:
    time_since_onroad = time.monotonic() - started_time if started_time > 0 else 0.0
    waiting_for_startup = recv_frame < started_frame
    if waiting_for_startup and time_since_onroad > 5:
      return {
        "text1": "sunnypilot Unavailable",
        "text2": "Waiting to start",
        "size": "mid",
        "status": "normal",
        "synthetic": True,
      }
    if TICI and not waiting_for_startup:
      try:
        ss_missing = time.monotonic() - sm.recv_time["selfdriveState"]
      except Exception:
        ss_missing = 0.0
      if ss_missing > SELFDRIVE_STATE_TIMEOUT:
        enabled = bool(getattr(ss, "enabled", False))
        if enabled and (ss_missing - SELFDRIVE_STATE_TIMEOUT) < SELFDRIVE_UNRESPONSIVE_TIMEOUT:
          return {
            "text1": "TAKE CONTROL IMMEDIATELY",
            "text2": "System Unresponsive",
            "size": "full",
            "status": "critical",
            "synthetic": True,
          }
        return {
          "text1": "System Unresponsive",
          "text2": "Reboot Device",
          "size": "mid",
          "status": "normal",
          "synthetic": True,
        }

  size = _size_name(ss)
  if size in ("none", ""):
    return None
  if recv_frame < started_frame and started_frame > 0:
    return None

  return {
    "text1": ss.alertText1 or "",
    "text2": ss.alertText2 or "",
    "size": size,
    "status": _status_name(ss),
    "synthetic": False,
  }
