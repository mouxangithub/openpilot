"""Engaged / ui_status derivation matching native sunnypilot UI.

Deliberately does NOT import openpilot.selfdrive.ui.sunnypilot.ui_state:
that module pulls in the whole raylib stack (system.ui.lib.application
instantiates GuiApplication at import time), which is wrong for a headless
server process and silently degraded to a fallback without lat_only /
long_only — the reason the border never turned blue (MADS-only) in webui.
The state machine below replicates UIStateSP.update_status with plain
cereal enum comparisons.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("webui.ui_status")


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


def _status_native_machine(sm: Any, ss: Any, ss_sp: Any) -> str:
  """Mirror of openpilot/selfdrive/ui/sunnypilot/ui_state.py UIStateSP.update_status."""
  from openpilot.cereal import custom
  from openpilot.cereal import log as capnp_log

  OpenpilotState = capnp_log.SelfdriveState.OpenpilotState
  MADSState = custom.ModularAssistiveDrivingSystem.ModularAssistiveDrivingSystemState

  state = ss.state
  mads = ss_sp.mads
  mads_state = mads.state

  if state == OpenpilotState.preEnabled:
    return "override"

  if state == OpenpilotState.overriding:
    if not mads.available:
      return "override"
    if sm.valid.get("onroadEvents"):
      try:
        if any(e.overrideLongitudinal for e in sm["onroadEvents"]):
          return "override"
      except TypeError:
        pass

  if mads_state in (MADSState.paused, MADSState.overriding):
    return "override"

  # MADS specific statuses
  if not mads.available:
    return "engaged" if ss.enabled else "disengaged"

  if not mads.enabled and not ss.enabled:
    return "disengaged"

  if mads.enabled and ss.enabled:
    return "engaged"

  if mads.enabled:
    return "lat_only"

  if ss.enabled:
    return "long_only"

  return "disengaged"


def _status_fallback(ss: Any) -> str:
  """Last resort when selfdriveStateSP is unavailable."""
  if getattr(ss, "active", False):
    return "engaged"
  state_name = str(getattr(ss, "state", "")).lower()
  if "override" in state_name:
    return "override"
  return "disengaged"


def derive_ui_status(sm: Any) -> str:
  ss = sm["selfdriveState"]
  ss_sp = None
  if sm.valid.get("selfdriveStateSP"):
    try:
      ss_sp = sm["selfdriveStateSP"]
    except Exception:
      ss_sp = None
  if ss_sp is None:
    return _status_fallback(ss)
  try:
    return _status_native_machine(sm, ss, ss_sp)
  except Exception as exc:
    # degraded but observable — never crash the state poller
    log.warning("ui_status native machine failed, falling back: %s", exc)
    return _status_fallback(ss)
