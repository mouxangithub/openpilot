"""Engaged / ui_status derivation matching native sunnypilot UI."""

from __future__ import annotations

from typing import Any


def derive_engaged(sm: Any, started: bool) -> bool:
  if not started:
    return False
  ss = sm["selfdriveState"]
  enabled = bool(getattr(ss, "enabled", False))
  if sm.valid.get("selfdriveStateSP"):
    try:
      return enabled or bool(sm["selfdriveStateSP"].mads.enabled)
    except Exception:
      pass
  return enabled


def derive_ui_status(sm: Any) -> str:
  ss = sm["selfdriveState"]
  try:
    from openpilot.selfdrive.ui.sunnypilot.ui_state import UIStateSP

    ss_sp = sm["selfdriveStateSP"] if sm.valid.get("selfdriveStateSP") else None
    if ss_sp is not None:
      onroad_evt = []
      if sm.valid.get("onroadEvents"):
        try:
          onroad_evt = list(sm["onroadEvents"])
        except TypeError:
          onroad_evt = []
      return UIStateSP.update_status(ss, ss_sp, onroad_evt)
  except Exception:
    pass

  if getattr(ss, "active", False):
    return "engaged"
  state_name = str(getattr(ss, "state", "")).lower()
  if "override" in state_name:
    return "override"
  return "disengaged"
