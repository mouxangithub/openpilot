"""sunnylink panel status + backup progress."""

from __future__ import annotations

import os
from typing import Any


def _consent_version() -> str:
  try:
    from openpilot.common.version import sunnylink_consent_version
    return sunnylink_consent_version
  except Exception:
    return "1.0"


def _consent_declined() -> str:
  try:
    from openpilot.common.version import sunnylink_consent_declined
    return sunnylink_consent_declined
  except Exception:
    return "-1"


def _status_name(val: Any) -> str:
  if val is None:
    return "idle"
  if hasattr(val, "name"):
    return str(val.name)
  text = str(val)
  return text.split(".")[-1] if "." in text else text


def _backup_snapshot(bm: Any) -> dict[str, Any]:
  """Mirror sunnylink.py handle_backup_restore_progress fields."""
  backup_status = _status_name(getattr(bm, "backupStatus", None))
  restore_status = _status_name(getattr(bm, "restoreStatus", None))
  backup_progress = float(getattr(bm, "backupProgress", 0) or 0)
  restore_progress = float(getattr(bm, "restoreProgress", 0) or 0)
  last_error = str(getattr(bm, "lastError", "") or "")

  phase = "idle"
  progress = 0.0
  if restore_status == "inProgress":
    phase = "restoring"
    progress = restore_progress
  elif backup_status == "inProgress":
    phase = "backing_up"
    progress = backup_progress
  elif restore_status == "failed":
    phase = "restore_failed"
  elif backup_status == "failed":
    phase = "backup_failed"
  elif restore_status == "completed" or (restore_status == "idle" and restore_progress >= 100.0):
    phase = "restore_done"
    progress = restore_progress
  elif backup_status == "completed" or (backup_status == "idle" and backup_progress >= 100.0):
    phase = "backup_done"
    progress = backup_progress

  return {
    "backup_status": backup_status,
    "restore_status": restore_status,
    "backup_progress": backup_progress,
    "restore_progress": restore_progress,
    "last_error": last_error,
    "phase": phase,
    "progress": progress,
    # Legacy keys used by older panel code.
    "status": phase,
  }


def sunnylink_status() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {
      "ok": True,
      "enabled": True,
      "dongle_id": "sl-dev-preview",
      "paired": True,
      "is_sponsor": True,
      "tier": "gold",
      "tier_color": "#FFD500",
      "description": "sunnylink connected — uploads enabled",
      "backup": _backup_snapshot(type("BM", (), {
        "backupStatus": "idle",
        "restoreStatus": "idle",
        "backupProgress": 0,
        "restoreProgress": 0,
        "lastError": "",
      })()),
      "dev_pc": True,
      "required_consent_version": "1.0",
      "consent_declined_value": "-1",
    }
  try:
    import openpilot.cereal.messaging as messaging
    from openpilot.common.params import Params
    from webui.server.bridge.webui_bg_services import sunnylink_tier_from_params

    p = Params()
    backup = _backup_snapshot(type("BM", (), {
      "backupStatus": "idle",
      "restoreStatus": "idle",
      "backupProgress": 0,
      "restoreProgress": 0,
      "lastError": "",
    })())
    sm = messaging.SubMaster(["backupManagerSP"], poll="backupManagerSP")
    sm.update(80)
    if sm.valid.get("backupManagerSP"):
      backup = _backup_snapshot(sm["backupManagerSP"])

    sl_info = sunnylink_tier_from_params()
    dongle_id = p.get("SunnylinkDongleId") or ""

    return {
      "ok": True,
      "enabled": p.get_bool("SunnylinkEnabled"),
      "dongle_id": dongle_id,
      "paired": sl_info["is_paired"] or bool(dongle_id),
      "is_sponsor": sl_info["is_sponsor"],
      "is_paired": sl_info["is_paired"],
      "tier": sl_info["tier"],
      "tier_color": sl_info["tier_color"],
      "description": sl_info["description"],
      "backup": backup,
      "consent_version": p.get("CompletedSunnylinkConsentVersion") or "",
      "required_consent_version": _consent_version(),
      "consent_declined_value": _consent_declined(),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


from webui.server.bridge.qr_data_url import qr_data_url as _qr_data_url


def sunnylink_pair_url(mode: str = "pair") -> dict[str, Any]:
  sponsor = mode == "sponsor"
  try:
    if sponsor:
      url = "https://github.com/sponsors/sunnyhaibin"
      return {"ok": True, "mode": "sponsor", "url": url, "qr_data_url": _qr_data_url(url)}

    import base64
    from openpilot.common.params import Params
    from openpilot.sunnypilot.sunnylink.api import SunnylinkApi, UNREGISTERED_SUNNYLINK_DONGLE_ID, API_HOST

    sl_dongle = Params().get("SunnylinkDongleId") or UNREGISTERED_SUNNYLINK_DONGLE_ID
    if sl_dongle == UNREGISTERED_SUNNYLINK_DONGLE_ID:
      return {"ok": False, "error": "sunnylink dongle id not registered"}
    token = SunnylinkApi(sl_dongle).get_token()
    payload = base64.b64encode(f"1|{sl_dongle}|{token}".encode()).decode()
    url = f"{API_HOST}/sso?state={payload}"
    return {"ok": True, "mode": "pair", "url": url, "qr_data_url": _qr_data_url(url)}
  except Exception as exc:
    if os.environ.get("WEBUI_DEV_PC") == "1":
      url = "https://github.com/sponsors/sunnyhaibin" if sponsor else "https://connect.sunnypilot.ai/?dongle=sl-dev-preview"
      return {
        "ok": True,
        "mode": "sponsor" if sponsor else "pair",
        "url": url,
        "qr_data_url": _qr_data_url(url),
        "dev_pc": True,
      }
    return {"ok": False, "error": str(exc)}
