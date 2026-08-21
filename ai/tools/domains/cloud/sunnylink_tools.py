"""Sunnylink cloud backup / restore triggers (when enabled on this install)."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params

try:
  from openpilot.sunnypilot.sunnylink.api import UNREGISTERED_SUNNYLINK_DONGLE_ID
except Exception:
  UNREGISTERED_SUNNYLINK_DONGLE_ID = "unregistered"


def get_sunnylink_status(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  sl_id = params.get("SunnylinkDongleId")
  if isinstance(sl_id, bytes):
    sl_id = sl_id.decode(errors="replace")
  sl_id = str(sl_id or UNREGISTERED_SUNNYLINK_DONGLE_ID)
  registered = sl_id not in (UNREGISTERED_SUNNYLINK_DONGLE_ID, "", "None")
  return {
    "ok": True,
    "SunnylinkEnabled": params.get_bool("SunnylinkEnabled") if params.get("SunnylinkEnabled") is not None else None,
    "EnableSunnylinkUploader": params.get_bool("EnableSunnylinkUploader") if params.get("EnableSunnylinkUploader") is not None else None,
    "SunnylinkDongleId": sl_id,
    "registered": registered,
    "SunnylinkTempFault": params.get_bool("SunnylinkTempFault") if params.get("SunnylinkTempFault") is not None else False,
    "CompletedSunnylinkConsentVersion": params.get("CompletedSunnylinkConsentVersion"),
    "backup_pending": bool(params.get_bool("BackupManager_CreateBackup")),
    "restore_version": params.get("BackupManager_RestoreVersion"),
    "hint": "Pair in UI Settings → Sunnylink; backup/restore via trigger_sunnylink_backup/restore (offroad).",
  }


def trigger_sunnylink_backup(params: Params) -> dict[str, Any]:
  if not params.get_bool("SunnylinkEnabled"):
    return {"ok": False, "error": "SunnylinkEnabled is off"}
  params.put_bool("BackupManager_CreateBackup", True)
  return {"ok": True, "hint": "Backup runs via backupManagerSP; poll cereal backupManagerSP or retry get_sunnylink_status."}


def trigger_sunnylink_restore(params: Params, version: str = "latest") -> dict[str, Any]:
  if not params.get_bool("SunnylinkEnabled"):
    return {"ok": False, "error": "SunnylinkEnabled is off"}
  params.put("BackupManager_RestoreVersion", version or "latest")
  return {"ok": True, "version": version or "latest", "hint": "Restore may restart UI when complete."}


def list_sunnylink_backups(params: Params | None = None) -> dict[str, Any]:
  """List cloud backups for this device from sunnylink API."""
  params = params or Params()
  if not params.get_bool("SunnylinkEnabled"):
    return {"ok": False, "error": "SunnylinkEnabled is off"}

  sl_id = params.get("SunnylinkDongleId")
  if isinstance(sl_id, bytes):
    sl_id = sl_id.decode(errors="replace")
  device_id = str(sl_id or "")
  if device_id in (UNREGISTERED_SUNNYLINK_DONGLE_ID, "", "None"):
    return {"ok": False, "error": "Sunnylink device not registered"}

  try:
    from openpilot.sunnypilot.sunnylink.api import SunnylinkApi

    api = SunnylinkApi(params.get("DongleId"))
    endpoint = f"backup/{device_id}?api-version=1"
    resp = api.api_get(endpoint, access_token=api.get_token())
    if resp is None:
      return {"ok": False, "error": "Sunnylink API unavailable (disabled or no network)"}
    if resp.status_code == 404:
      return {"ok": True, "backups": [], "count": 0}
    resp.raise_for_status()
    data = resp.json()
    backups: list[dict[str, Any]] = []
    if isinstance(data, list):
      raw_items = data
    elif isinstance(data, dict):
      raw_items = data.get("backups") or data.get("items") or ([data] if data.get("config") or data.get("created_at") else [])
    else:
      raw_items = []

    for item in raw_items:
      if not isinstance(item, dict):
        continue
      backups.append({
        "version": item.get("version") or item.get("id"),
        "created_at": item.get("created_at") or item.get("createdAt"),
        "updated_at": item.get("updated_at") or item.get("updatedAt"),
        "sunnypilot_version": item.get("sunnypilot_version") or item.get("sunnypilotVersion"),
        "is_encrypted": item.get("is_encrypted", item.get("isEncrypted")),
      })

    return {
      "ok": True,
      "device_id": device_id,
      "count": len(backups),
      "backups": backups,
      "hint": "Restore with trigger_sunnylink_restore(version=<id> or 'latest').",
    }
  except Exception as e:
    return {"ok": False, "error": str(e)}


def get_backup_manager_status(get_state_reader=None) -> dict[str, Any]:
  """Read backupManagerSP cereal + pending param flags."""
  out: dict[str, Any] = {"ok": True}
  params = Params()
  out["backup_pending"] = bool(params.get_bool("BackupManager_CreateBackup"))
  out["restore_version"] = params.get("BackupManager_RestoreVersion")

  if get_state_reader is None:
    out["hint"] = "No live cereal reader; only param flags available."
    return out

  try:
    reader = get_state_reader()
    reader.update(timeout=0)
    full = reader.latest()
    bm = None
    if isinstance(full, dict):
      bm = full.get("backupManagerSP")
    if bm is None:
      return out
    out["backup_status"] = getattr(bm, "backupStatus", None) or (bm.get("backupStatus") if isinstance(bm, dict) else None)
    out["restore_status"] = getattr(bm, "restoreStatus", None) or (bm.get("restoreStatus") if isinstance(bm, dict) else None)
    out["backup_progress"] = getattr(bm, "backupProgress", None) or (bm.get("backupProgress") if isinstance(bm, dict) else None)
    out["restore_progress"] = getattr(bm, "restoreProgress", None) or (bm.get("restoreProgress") if isinstance(bm, dict) else None)
    out["last_error"] = getattr(bm, "lastError", None) or (bm.get("lastError") if isinstance(bm, dict) else None)
  except Exception as e:
    out["cereal_error"] = str(e)
  return out


def sunnylink_backup_watch(params: Params | None = None) -> dict[str, Any]:
  """Structured backup/restore progress with retry hints."""
  params = params or Params()
  sl = get_sunnylink_status(params)
  bm = get_backup_manager_status()
  issues: list[str] = []
  if not sl.get("registered"):
    issues.append("not_registered")
  if sl.get("SunnylinkTempFault"):
    issues.append("temp_fault")
  if bm.get("last_error"):
    issues.append("backup_manager_error")
  if sl.get("backup_pending") and not bm.get("backup_progress"):
    issues.append("backup_stalled")

  next_steps = ["get_sunnylink_status", "get_backup_manager_status"]
  if "not_registered" in issues:
    next_steps.append("Settings → Sunnylink 配对")
  if sl.get("backup_pending"):
    next_steps.append("等待 backupManagerSP 或 trigger_sunnylink_backup(confirm=true)")
  if bm.get("last_error"):
    next_steps.append("检查网络后重试 trigger_sunnylink_backup")

  return {
    "ok": True,
    "sunnylink": sl,
    "backup_manager": bm,
    "issues": issues,
    "healthy": not issues,
    "next_steps": next_steps,
    "skill": "sunnylink-backup",
  }
