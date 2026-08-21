"""Mirror hardwared startup/onroad gating for WebUI (headless troubleshooting)."""

from __future__ import annotations

import threading
from typing import Any

# User-facing messages (i18n keys on the client).
BLOCKER_MESSAGES: dict[str, str] = {
  "ignition": "Connect vehicle ignition to start driving",
  "not_onroad_cycle": "Wait a moment after toggling offroad mode",
  "device_temp_good": "Device temperature too high — wait for cooldown",
  "not_always_offroad": "Disable Always Offroad mode in Device settings",
  "accepted_terms": "Accept the Terms of Service (complete onboarding or Device settings)",
  "accepted_terms_sp": "Accept the sunnypilot Terms of Service",
  "completed_training": "Complete the training guide (Device → Training Guide)",
  "not_driver_view": "Disable driver camera preview before driving",
  "device_temp_engageable": "Device too hot to start — wait for cooldown",
  "device_booted": "Device is still booting — wait a moment",
  "free_space": "Free up storage (less than 2% space remaining)",
  "up_to_date": "Connect to the internet to finish software update checks",
  "no_excessive_actuation": "Acknowledge excessive actuation alert on the home screen",
  "not_uninstalling": "Uninstall in progress",
}


def _terms_versions() -> tuple[str, str, str]:
  try:
    from openpilot.common.version import terms_version, terms_version_sp, training_version
    return terms_version, terms_version_sp, training_version
  except Exception:
    return "2", "1.0", "0.2.0"


def _ignition_from_sm(sm: Any) -> bool:
  if sm is None or not sm.valid.get("pandaStates") or not sm["pandaStates"]:
    return False
  try:
    from openpilot.cereal import log
    return any(
      ps.ignitionLine or ps.ignitionCan
      for ps in sm["pandaStates"]
      if ps.pandaType != log.PandaState.PandaType.unknown
    )
  except Exception:
    return False


def _thermal_engageable(ds: Any) -> bool:
  if ds is None:
    return True
  try:
    from openpilot.cereal import log
    ts = ds.thermalStatus
    if hasattr(ts, "raw"):
      return int(ts) < int(log.DeviceState.ThermalStatus.overheated)
    name = str(ts).split(".")[-1].lower()
    return name not in ("overheated", "danger")
  except Exception:
    return True


def _thermal_onroad_ok(ds: Any) -> bool:
  if ds is None:
    return True
  try:
    from openpilot.cereal import log
    ts = ds.thermalStatus
    if hasattr(ts, "raw"):
      return int(ts) < int(log.DeviceState.ThermalStatus.critical)
    name = str(ts).split(".")[-1].lower()
    return name != "danger"
  except Exception:
    return True


def evaluate_startup_gates(p: Any, ds: Any | None = None) -> dict[str, bool]:
  """Return hardwared-like condition map (True = satisfied)."""
  terms_version, terms_version_sp, training_version = _terms_versions()
  offroad_mode = p.get_bool("OffroadMode")

  startup = {
    "up_to_date": (
      p.get("Offroad_ConnectivityNeeded") is None
      or p.get_bool("DisableUpdates")
      or p.get_bool("SnoozeUpdate")
    ),
    "no_excessive_actuation": p.get("Offroad_ExcessiveActuation") is None,
    "not_uninstalling": not p.get_bool("DoUninstall"),
    "accepted_terms": p.get("HasAcceptedTerms") == terms_version,
    "accepted_terms_sp": p.get("HasAcceptedTermsSP") == terms_version_sp,
    "free_space": True if ds is None else int(getattr(ds, "freeSpacePercent", 100) or 100) > 2,
    "completed_training": p.get("CompletedTrainingVersion") == training_version,
    "not_driver_view": not p.get_bool("IsDriverViewEnabled"),
    "device_temp_engageable": _thermal_engageable(ds),
    "device_booted": True,
    "not_always_offroad": not offroad_mode,
  }
  try:
    from openpilot.common.hardware import HARDWARE
    startup["device_booted"] = HARDWARE.booted()
  except Exception:
    pass

  onroad = {
    "ignition": False,
    "not_onroad_cycle": True,
    "device_temp_good": _thermal_onroad_ok(ds),
    "not_always_offroad": not offroad_mode,
  }
  return {"startup": startup, "onroad": onroad}


def startup_blockers_from_sm(sm: Any) -> dict[str, Any]:
  """Build blocker list for UI from cereal SubMaster."""
  try:
    from openpilot.common.params import Params
    p = Params()
  except Exception:
    return {"ok": False, "blockers": [], "ignition": False, "can_start": False}

  ds = sm["deviceState"] if sm.valid.get("deviceState") else None
  started = bool(ds and ds.started)
  gates = evaluate_startup_gates(p, ds)
  onroad = gates["onroad"]
  startup = gates["startup"]

  onroad["ignition"] = _ignition_from_sm(sm)

  can_start = all(onroad.values()) and all(startup.values())
  if started:
    return {
      "ok": True,
      "started": True,
      "ignition": onroad["ignition"],
      "can_start": True,
      "blockers": [],
    }

  failed: list[dict[str, str]] = []
  ignition = onroad["ignition"]

  always_show = {"not_driver_view", "accepted_terms", "accepted_terms_sp", "completed_training", "not_always_offroad"}
  for key, ok in startup.items():
    if ok:
      continue
    if ignition or key in always_show:
      failed.append({"id": key, "message": BLOCKER_MESSAGES.get(key, key)})

  if ignition:
    for key, ok in onroad.items():
      if ok:
        continue
      failed.append({"id": key, "message": BLOCKER_MESSAGES.get(key, key)})

  return {
    "ok": True,
    "started": False,
    "ignition": ignition,
    "can_start": can_start,
    "blockers": failed,
  }


_gate_cache: dict[str, Any] | None = None
_gate_lock = threading.Lock()


def set_startup_gate_cache(gate: dict[str, Any]) -> None:
  global _gate_cache
  with _gate_lock:
    _gate_cache = gate


def get_startup_gate() -> dict[str, Any]:
  with _gate_lock:
    if _gate_cache is not None:
      return dict(_gate_cache)
  return startup_blockers_snapshot()


def startup_blockers_snapshot() -> dict[str, Any]:
  """Snapshot from shared SubMaster when available, else cold poll."""
  try:
    from webui.server.bridge.state_hub import get_shared_sm
    sm = get_shared_sm()
    if sm is not None:
      return startup_blockers_from_sm(sm)
  except Exception:
    pass
  try:
    import openpilot.cereal.messaging as messaging
    sm = messaging.SubMaster(["deviceState", "pandaStates"], poll="deviceState")
    sm.update(400)
    return startup_blockers_from_sm(sm)
  except Exception as exc:
    return {"ok": False, "error": str(exc), "blockers": [], "ignition": False, "can_start": False}
