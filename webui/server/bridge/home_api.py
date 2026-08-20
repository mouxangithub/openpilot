"""Offroad home screen data (Prime, Setup, header)."""

from __future__ import annotations

import os
import threading
from typing import Any

_slow_lock = threading.Lock()
_slow_cache_ready = False
_slow_cache: dict[str, Any] = {
  "offroad_alerts": [],
  "new_description": "",
  "new_release_notes": "",
  "manager_error": None,
}


def _format_offroad_alerts() -> list[dict[str, Any]]:
  try:
    from openpilot.common.params import Params
    from openpilot.selfdrive.selfdrived.alertmanager import OFFROAD_ALERTS
    from openpilot.selfdrive.ui.widgets.offroad_alerts import _format_offroad_alert

    p = Params()
    alerts: list[dict[str, Any]] = []
    for key, config in sorted(OFFROAD_ALERTS.items(), key=lambda x: x[1].get("severity", 0), reverse=True):
      alert_json = p.get(key)
      if not alert_json:
        continue
      text = _format_offroad_alert(key, alert_json)
      if not text:
        continue
      alerts.append({
        "key": key,
        "text": text,
        "severity": int(config.get("severity", 0)),
      })
    return alerts
  except Exception:
    return []


def refresh_home_slow_cache(*, headless: bool = False) -> dict[str, Any]:
  """Expensive home fields — offroad alerts, release notes, manager error."""
  from webui.server.bridge.system_api import manager_last_error, software_status

  extras: dict[str, Any] = {
    "offroad_alerts": _format_offroad_alerts(),
    "new_description": "",
    "new_release_notes": "",
    "manager_error": None,
  }
  try:
    from webui.server.bridge.state_hub import get_started
    started = get_started()
  except Exception:
    started = None
  sw = software_status(started=started)
  if sw.get("ok"):
    extras["new_description"] = sw.get("new_description") or ""
    extras["new_release_notes"] = sw.get("new_release_notes") or ""
  if headless:
    mgr = manager_last_error()
    if mgr.get("ok") and mgr.get("has_error"):
      extras["manager_error"] = mgr.get("text") or ""
  global _slow_cache_ready
  with _slow_lock:
    _slow_cache.clear()
    _slow_cache.update(extras)
    _slow_cache_ready = True
  return dict(extras)


def get_home_slow_cache() -> dict[str, Any]:
  with _slow_lock:
    return dict(_slow_cache)


def ensure_home_slow_cache(*, headless: bool = False) -> dict[str, Any]:
  """Populate slow home fields once if startup refresh has not completed yet."""
  global _slow_cache_ready
  with _slow_lock:
    if _slow_cache_ready:
      return dict(_slow_cache)
  return refresh_home_slow_cache(headless=headless)


def snapshot_home_core(*, started: bool | None = None) -> dict[str, Any]:
  """Fast home snapshot — Params + cached gate only."""
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return _mock_home()

  try:
    from openpilot.common.params import Params
    from webui.server.bridge.webui_bg_services import prime_status_from_cache
    from webui.server.bridge.startup_blockers import get_startup_gate
    from webui.server.bridge.headless_util import is_headless_mode

    p = Params()
    dongle = p.get("DongleId") or ""
    version = p.get("UpdaterCurrentDescription") or p.get("GitBranch") or ""
    update_available = p.get_bool("UpdateAvailable")
    fetch_available = p.get_bool("UpdaterFetchAvailable")
    experimental = p.get_bool("ExperimentalMode")

    prime_info = prime_status_from_cache()
    gate = get_startup_gate()
    headless = is_headless_mode()
    slow = ensure_home_slow_cache(headless=headless)

    from webui.server.bridge.agnos_api import agnos_home_fields

    return {
      "ok": True,
      "paired": prime_info["paired"],
      "prime": prime_info["prime"],
      "experimental_mode": experimental,
      "version_text": version,
      "update_available": update_available,
      "fetch_available": fetch_available,
      "update_visible": bool(update_available or fetch_available),
      "new_description": slow.get("new_description") or "",
      "new_release_notes": slow.get("new_release_notes") or "",
      "alert_count": len(slow.get("offroad_alerts") or []),
      "offroad_alerts": slow.get("offroad_alerts") or [],
      "dongle_id": dongle,
      "headless": headless,
      "startup_blockers": gate.get("blockers") or [],
      "ignition": bool(gate.get("ignition")),
      "can_start": bool(gate.get("can_start", True)),
      "manager_error": slow.get("manager_error") if headless else None,
      **agnos_home_fields(),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def snapshot_home() -> dict[str, Any]:
  """Full home snapshot (refreshes slow cache). Used for cold HTTP / first boot."""
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return _mock_home()
  try:
    from webui.server.bridge.headless_util import is_headless_mode
    refresh_home_slow_cache(headless=is_headless_mode())
  except Exception:
    pass
  return snapshot_home_core()


def _mock_home() -> dict[str, Any]:
  from webui.dev.mock_runtime import SIM
  from webui.server.bridge.agnos_api import agnos_home_fields

  paired = bool(SIM.get("paired", False))
  alerts = SIM.get("offroad_alerts") or []
  return {
    "ok": True,
    "dev_pc": True,
    "paired": paired,
    "prime": paired,
    "experimental_mode": True,
    "version_text": "sunnypilot dev-preview / master-c3",
    "update_available": bool(SIM.get("update_available", False)),
    "fetch_available": bool(SIM.get("fetch_available", False)),
    "update_visible": bool(SIM.get("update_available") or SIM.get("fetch_available")),
    "new_description": SIM.get("new_description", "sunnypilot dev-preview build"),
    "new_release_notes": SIM.get("new_release_notes", "<p>Dev preview release notes.</p>"),
    "alert_count": len(alerts),
    "offroad_alerts": alerts,
    "dongle_id": "dev-preview-0000",
    "headless": bool(SIM.get("headless")),
    "startup_blockers": _mock_startup_blockers(SIM),
    **agnos_home_fields(),
  }


def _mock_startup_blockers(sim: dict[str, Any]) -> list[dict[str, str]]:
  if not sim.get("headless") or sim.get("started"):
    return []
  return [
    {
      "id": "completed_training",
      "message": "Complete the training guide (Device → Training Guide)",
    },
  ]
