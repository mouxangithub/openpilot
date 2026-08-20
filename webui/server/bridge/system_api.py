"""System actions: reboot, updater, sunnylink, calibration."""

from __future__ import annotations

import subprocess
import os
from typing import Any


def _params():
  from openpilot.common.params import Params
  return Params()


def run_action(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
  payload = payload or {}
  try:
    p = _params()

    if action == "reboot":
      p.put_bool("DoReboot", True, block=True)
      return {"ok": True, "action": action}

    if action == "shutdown":
      p.put_bool("DoShutdown", True, block=True)
      return {"ok": True, "action": action}

    if action == "uninstall":
      p.put_bool("DoUninstall", True, block=True)
      return {"ok": True, "action": action}

    if action == "reset_calibration":
      for key in ("CalibrationParams", "LiveTorqueParameters", "LiveParametersV2", "LiveDelay"):
        try:
          p.remove(key)
        except Exception:
          pass
      p.put_bool("OnroadCycleRequested", True, block=True)
      return {"ok": True, "action": action}

    if action == "reset_all_params":
      try:
        from openpilot.common.hardware import HARDWARE
        p.clear_all()
        HARDWARE.reboot()
      except Exception:
        p.clear_all()
      return {"ok": True, "action": action}

    if action == "pair_device":
      from webui.server.bridge.device_api import device_pair_url
      return device_pair_url()

    if action == "updater_check":
      subprocess.run("pkill -SIGUSR1 -f openpilot.system.updated.updated", shell=True, check=False)
      return {"ok": True, "action": action}

    if action == "updater_download":
      subprocess.run("pkill -SIGHUP -f openpilot.system.updated.updated", shell=True, check=False)
      return {"ok": True, "action": action}

    if action == "updater_install":
      p.put_bool("DoReboot", True, block=True)
      return {"ok": True, "action": action}

    if action == "agnos_install":
      from webui.server.bridge.agnos_api import start_agnos_install
      return start_agnos_install()

    if action == "agnos_reboot":
      from webui.server.bridge.agnos_api import agnos_reboot
      return agnos_reboot()

    if action == "sunnylink_backup":
      p.put_bool("BackupManager_CreateBackup", True, block=True)
      return {"ok": True, "action": action}

    if action == "sunnylink_restore":
      p.put("BackupManager_RestoreVersion", "latest", block=True)
      return {"ok": True, "action": action}

    if action == "models_sync":
      p.put("ModelManager_LastSyncTime", 0, block=True)
      return {"ok": True, "action": action}

    if action == "models_clear_cache":
      p.put_bool("ModelManager_ClearCache", True, block=True)
      return {"ok": True, "action": action}

    if action == "osm_check_updates":
      p.put_bool("OsmDbUpdatesCheck", True, block=True)
      return {"ok": True, "action": action}

    if action == "osm_delete_maps":
      p.put_bool("OsmDbDelete", True, block=True)
      return {"ok": True, "action": action}

    if action == "network_set_apn":
      apn = str(payload.get("apn", "")).strip()
      if apn:
        p.put("GsmApn", apn, block=True)
      else:
        p.remove("GsmApn")
      return {"ok": True, "action": action, "apn": apn}

    if action == "models_cancel_download":
      p.remove("ModelManager_DownloadIndex")
      return {"ok": True, "action": action}

    if action == "developer_delete_error_log":
      from webui.server.bridge.developer_api import developer_delete_error_log
      return developer_delete_error_log()

    if action == "webrtc_enable":
      p.put_bool("IsLiveStreaming", True, block=True)
      return {"ok": True, "action": action}

    if action == "webrtc_disable":
      p.put_bool("IsLiveStreaming", False, block=True)
      return {"ok": True, "action": action}

    if action in ("driver_view_enable", "driver_view_disable"):
      from webui.server.bridge.offroad_guard import require_offroad
      blocked = require_offroad()
      if blocked:
        return blocked
      p.put_bool("IsDriverViewEnabled", action == "driver_view_enable", block=True)
      return {"ok": True, "action": action}

    if action == "bookmark":
      try:
        import openpilot.cereal.messaging as messaging
        pm = messaging.PubMaster(["bookmarkButton"])
        msg = messaging.new_message("bookmarkButton")
        msg.valid = True
        pm.send("bookmarkButton", msg)
        return {"ok": True, "action": action}
      except Exception as exc:
        if os.environ.get("WEBUI_DEV_PC") == "1":
          return {"ok": True, "action": action, "dev_pc": True}
        return {"ok": False, "error": str(exc)}

    if action == "dismiss_offroad_alert":
      key = str(payload.get("key", "")).strip()
      if not key:
        return {"ok": False, "error": "key required"}
      try:
        p.remove(key)
      except Exception:
        pass
      return {"ok": True, "action": action, "key": key}

    if action == "set_branch":
      branch = str(payload.get("branch", "")).strip()
      if not branch:
        return {"ok": False, "error": "branch required"}
      p.put("UpdaterTargetBranch", branch, block=True)
      subprocess.run("pkill -SIGUSR1 -f openpilot.system.updated.updated", shell=True, check=False)
      return {"ok": True, "action": action, "branch": branch}

    return {"ok": False, "error": f"unknown action: {action}"}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _sort_branches(branches: list[str], git_branch: str) -> list[str]:
  """Match openpilot selfdrive/ui/layouts/settings/software.py branch picker order."""
  ordered = list(branches)
  for b in [git_branch, "devel-staging", "devel", "nightly", "nightly-dev", "master"]:
    if b in ordered:
      ordered.remove(b)
      ordered.insert(0, b)
  return ordered


def software_status(*, started: bool | None = None) -> dict[str, Any]:
  try:
    p = _params()

    def _text(key: str) -> str:
      raw = p.get(key)
      if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
      return raw or ""

    is_onroad = False
    is_offroad = True
    if started is None:
      try:
        from webui.server.bridge.state_hub import get_started
        hub_started = get_started()
        if hub_started is not None:
          started = hub_started
      except Exception:
        pass
    if started is not None:
      is_onroad = bool(started)
      is_offroad = not is_onroad
    else:
      try:
        import openpilot.cereal.messaging as messaging
        sm = messaging.SubMaster(["deviceState"], poll="deviceState")
        sm.update(300)
        if sm.valid.get("deviceState"):
          is_onroad = bool(sm["deviceState"].started)
          is_offroad = not is_onroad
      except Exception:
        pass

    updater_state = p.get("UpdaterState") or "idle"
    fetch_available = p.get_bool("UpdaterFetchAvailable")
    update_available = p.get_bool("UpdateAvailable")
    failed_count = int(p.get("UpdateFailedCount") or 0)

    download_label = "CHECK"
    download_value = ""
    download_enabled = is_offroad and updater_state == "idle"

    state_labels = {
      "checking...": "checking...",
      "downloading...": "downloading...",
      "finalizing update...": "finalizing update...",
    }
    if updater_state != "idle":
      download_value = state_labels.get(updater_state, updater_state)
      download_enabled = False
    elif failed_count > 0:
      download_value = "failed to check for update"
      download_label = "CHECK"
    elif fetch_available:
      download_value = "update available"
      download_label = "DOWNLOAD"
    else:
      last_update = p.get("LastUpdateTime")
      last_update_epoch = None
      if last_update is not None:
        try:
          if hasattr(last_update, "timestamp"):
            last_update_epoch = int(last_update.timestamp())
          elif hasattr(last_update, "isoformat"):
            import datetime
            dt = last_update
            if dt.tzinfo is None:
              dt = dt.replace(tzinfo=datetime.timezone.utc)
            last_update_epoch = int(dt.timestamp())
        except Exception:
          last_update_epoch = None
      if not last_update:
        download_value = "up to date, last checked never"
      elif last_update_epoch:
        download_value = "up to date, last checked {}"  # formatted client-side
      else:
        download_value = f"up to date, last checked {last_update}"
      download_label = "CHECK"

    last_update_raw = p.get("LastUpdateTime")
    last_update_epoch_out = None
    if last_update_raw is not None:
      try:
        if hasattr(last_update_raw, "timestamp"):
          last_update_epoch_out = int(last_update_raw.timestamp())
        elif hasattr(last_update_raw, "isoformat"):
          import datetime
          dt = last_update_raw
          if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
          last_update_epoch_out = int(dt.timestamp())
      except Exception:
        last_update_epoch_out = None
    if last_update_raw is not None and hasattr(last_update_raw, "isoformat"):
      last_update_raw = last_update_raw.isoformat()
    if updater_state == "idle" and failed_count == 0 and not fetch_available and last_update_epoch_out:
      download_value = "up to date, last checked {}"

    download_status = "idle"
    if updater_state != "idle":
      download_status = "busy"
    elif failed_count > 0:
      download_status = "failed"
    elif fetch_available:
      download_status = "fetch_available"
    elif last_update_raw:
      download_status = "up_to_date"

    return {
      "ok": True,
      "current": p.get("UpdaterCurrentDescription") or "",
      "current_release_notes": _text("UpdaterCurrentReleaseNotes"),
      "updater_state": updater_state,
      "fetch_available": fetch_available,
      "update_available": update_available,
      "new_description": p.get("UpdaterNewDescription") or "",
      "new_release_notes": _text("UpdaterNewReleaseNotes"),
      "target_branch": p.get("UpdaterTargetBranch") or "",
      "git_branch": p.get("GitBranch") or "",
      "branches": _sort_branches(
        [b for b in (p.get("UpdaterAvailableBranches") or "").split(",") if b],
        p.get("GitBranch") or "",
      ),
      "failed_count": failed_count,
      "last_update_time": last_update_raw or "",
      "last_update_epoch": last_update_epoch_out,
      "download_status": download_status,
      "download_state": updater_state if updater_state != "idle" else "",
      "disable_updates": p.get_bool("DisableUpdates"),
      "is_onroad": is_onroad,
      "is_offroad": is_offroad,
      "download_label": download_label,
      "download_value": download_value,
      "download_enabled": download_enabled,
      "install_visible": is_offroad and update_available,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def manager_last_error() -> dict[str, Any]:
  path = "/tmp/manager_last_error.txt"
  try:
    if os.path.isfile(path):
      with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read(12000)
      return {"ok": True, "text": text, "has_error": bool(text.strip())}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
  return {"ok": True, "text": "", "has_error": False}
