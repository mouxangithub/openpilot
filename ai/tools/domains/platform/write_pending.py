"""Pending write confirmations for op助手 (preview before apply)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from openpilot.common.params import Params

from ai.common.storage import read_param, write_param

from ai.tools.domains.platform.params_policy import validate_write_batch
from ai.system.admin import is_admin_mode

_PENDING_KEY = "ai_write_pending"
_TTL_SEC = 600


def _load_all(params: Params) -> dict[str, Any]:
  try:
    raw = read_param(params, _PENDING_KEY)
    if not raw:
      return {}
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def _save_all(params: Params, data: dict[str, Any]) -> None:
  write_param(params, _PENDING_KEY, json.dumps(data, ensure_ascii=False))


def _purge_expired(store: dict[str, Any]) -> dict[str, Any]:
  now = int(time.time())
  return {k: v for k, v in store.items() if now - int(v.get("created_at", 0)) < _TTL_SEC}


def create_pending(
  params: Params,
  *,
  action: str,
  payload: dict[str, Any],
  preview: dict[str, Any],
) -> dict[str, Any]:
  if action == "write_params":
    writes = payload.get("params") or {}
    ok, reason = validate_write_batch(writes, admin=is_admin_mode(params))
  elif action == "apply_tune_preset":
    from ai.tools.domains.tune.presets import get_preset
    preset = get_preset(str(payload.get("preset_id", "")))
    if not preset:
      return {"ok": False, "error": "Unknown preset_id"}
    ok, reason = validate_write_batch(preset["params"], admin=is_admin_mode(params))
  elif action == "apply_sp_tune_preset":
    from ai.tools.domains.tune.sp_presets import get_sp_preset
    preset = get_sp_preset(str(payload.get("preset_id", "")))
    if not preset:
      return {"ok": False, "error": "Unknown sp preset_id"}
    ok, reason = validate_write_batch(preset["params"], admin=is_admin_mode(params))
  elif action in ("select_driving_model", "select_car_platform", "select_model_bundle"):
    ok, reason = True, ""
  elif action == "set_mads_settings":
    writes = payload.get("params") or {}
    ok, reason = validate_write_batch(writes, admin=is_admin_mode(params))
  elif action in (
    "set_torque_settings", "set_lane_change_settings", "set_speed_limit_settings", "set_visuals_settings",
    "set_model_tune_settings", "set_display_settings", "set_device_settings",
  ):
    ok, reason = True, ""
  elif action in (
    "clear_model_cache", "cancel_osm_download", "manage_model_favorites",
    "trigger_sunnylink_backup", "trigger_sunnylink_restore", "set_sp_dev_beep",
    "install_github_runner",
  ):
    ok, reason = True, ""
    if action == "install_github_runner" and not str(payload.get("token", "") or "").strip():
      ok, reason = False, "registration token required"
  elif action == "save_adaptation_draft":
    files = payload.get("files") or {}
    ok, reason = (True, "") if isinstance(files, dict) and files else (False, "files required")
  elif action == "car_porting_fingerprint_to_draft":
    ok, reason = (True, "") if payload.get("project_id") and payload.get("route") else (False, "project_id and route required")
  elif action == "restore_tune_snapshot":
    ok, reason = True, ""
  else:
    return {"ok": False, "error": f"Unknown action {action}"}

  if not ok and action not in ("select_driving_model", "select_car_platform", "select_model_bundle"):
    return {"ok": False, "error": reason}

  pid = f"w_{uuid.uuid4().hex[:12]}"
  store = _purge_expired(_load_all(params))
  store[pid] = {
    "id": pid,
    "action": action,
    "payload": payload,
    "preview": preview,
    "created_at": int(time.time()),
  }
  _save_all(params, store)
  consumer_preview = None
  try:
    from ai.tools.domains.platform.consumer_tools import enrich_write_preview
    enriched = enrich_write_preview(preview)
    consumer_preview = enriched.get("consumer")
  except Exception:
    pass
  return {
    "ok": True,
    "needs_confirmation": True,
    "pending_id": pid,
    "action": action,
    "preview": preview,
    "consumer_preview": consumer_preview,
    "message": "User must confirm in Web UI or set confirm=true after explicit approval.",
  }


def confirm_pending(params: Params, pending_id: str) -> dict[str, Any]:
  store = _purge_expired(_load_all(params))
  entry = store.pop(pending_id, None)
  if not entry:
    return {"ok": False, "error": "Pending write expired or not found."}
  _save_all(params, store)

  action = entry.get("action")
  payload = entry.get("payload") or {}

  if action == "write_params":
    writes = payload.get("params") or {}
    from ai.tools.domains.tune.tune_write_pipeline import apply_param_writes
    brand = str(payload.get("brand", "") or "")
    return apply_param_writes(
      params,
      writes,
      action="write_params",
      brand=brand,
      route_before=str(payload.get("route_before", "") or ""),
      route_after=str(payload.get("route_after", "") or ""),
      skip_regression_check=bool(payload.get("skip_regression_check")),
      snapshot_label="auto_before_write",
      admin=is_admin_mode(params),
    )

  if action == "apply_tune_preset":
    from ai.tools.domains.tune.presets import get_preset
    from ai.tools.domains.tune.tune_write_pipeline import apply_param_writes
    preset_id = str(payload.get("preset_id", ""))
    preset = get_preset(preset_id)
    if not preset:
      return {"ok": False, "error": "Unknown preset_id"}
    return apply_param_writes(
      params,
      preset["params"],
      action="apply_tune_preset",
      brand=str(payload.get("brand", "") or ""),
      route_before=str(payload.get("route_before", "") or ""),
      route_after=str(payload.get("route_after", "") or ""),
      skip_regression_check=bool(payload.get("skip_regression_check")),
      snapshot_label=f"auto_before_{preset_id}",
      preset_id=preset_id,
      admin=is_admin_mode(params),
    )

  if action == "apply_sp_tune_preset":
    from ai.tools.domains.tune.sp_presets import get_sp_preset
    from ai.tools.domains.tune.tune_write_pipeline import apply_param_writes
    preset_id = str(payload.get("preset_id", ""))
    preset = get_sp_preset(preset_id)
    if not preset:
      return {"ok": False, "error": "Unknown sp preset_id"}
    return apply_param_writes(
      params,
      preset["params"],
      action="apply_sp_tune_preset",
      brand=str(payload.get("brand", "") or ""),
      route_before=str(payload.get("route_before", "") or ""),
      route_after=str(payload.get("route_after", "") or ""),
      skip_regression_check=bool(payload.get("skip_regression_check")),
      snapshot_label=f"auto_before_{preset_id}",
      preset_id=preset_id,
      admin=is_admin_mode(params),
    )

  if action in ("select_driving_model", "select_car_platform"):
    from ai.tools.domains.vehicle.vehicle_platform import put_car_platform_bundle
    model = str(payload.get("model", ""))
    return put_car_platform_bundle(params, model)

  if action == "select_model_bundle":
    from ai.tools.domains.platform.model_manager_tools import select_model_bundle
    return select_model_bundle(params, str(payload.get("ref", "")))

  if action == "set_mads_settings":
    from ai.tools.domains.vehicle.mads_tools import apply_mads_writes
    return apply_mads_writes(params, payload.get("params") or {})

  if action == "set_torque_settings":
    from ai.tools.domains.tune.sp_tune_groups import apply_torque_writes
    return apply_torque_writes(params, payload.get("params") or {})

  if action == "set_lane_change_settings":
    from ai.tools.domains.tune.sp_tune_groups import apply_lane_change_writes
    return apply_lane_change_writes(params, payload.get("params") or {})

  if action == "set_speed_limit_settings":
    from ai.tools.domains.tune.sp_tune_groups import apply_speed_limit_writes
    return apply_speed_limit_writes(params, payload.get("params") or {})

  if action == "set_visuals_settings":
    from ai.tools.domains.tune.sp_tune_groups import apply_visuals_writes
    return apply_visuals_writes(params, payload.get("params") or {})

  if action == "set_model_tune_settings":
    from ai.tools.domains.tune.model_tune_tools import apply_model_tune_writes
    return apply_model_tune_writes(params, payload.get("params") or {})

  if action == "set_display_settings":
    from ai.tools.domains.platform.display_device_tools import apply_display_writes
    return apply_display_writes(params, payload.get("params") or {})

  if action == "set_device_settings":
    from ai.tools.domains.platform.display_device_tools import apply_device_writes
    return apply_device_writes(params, payload.get("params") or {})

  if action == "clear_model_cache":
    from ai.tools.domains.platform.model_manager_tools import clear_model_cache
    return clear_model_cache(params)

  if action == "cancel_osm_download":
    from ai.tools.domains.platform.osm_tools import cancel_osm_download
    return cancel_osm_download(params)

  if action == "manage_model_favorites":
    from ai.tools.domains.platform.model_manager_tools import manage_model_favorites
    return manage_model_favorites(
      params,
      add=payload.get("add"),
      remove=payload.get("remove"),
      replace=payload.get("replace"),
    )

  if action == "trigger_sunnylink_backup":
    from ai.tools.domains.cloud.sunnylink_tools import trigger_sunnylink_backup
    return trigger_sunnylink_backup(params)

  if action == "trigger_sunnylink_restore":
    from ai.tools.domains.cloud.sunnylink_tools import trigger_sunnylink_restore
    return trigger_sunnylink_restore(params, str(payload.get("version", "latest") or "latest"))

  if action == "set_sp_dev_beep":
    from ai.tools.domains.platform.device_hw_tools import set_sp_dev_beep
    return set_sp_dev_beep(params, bool(payload.get("enabled")))

  if action == "install_github_runner":
    from ai.tools.domains.devops.github_runner_tools import install_github_runner_preview
    return install_github_runner_preview(
      token=str(payload.get("token", "") or ""),
      repo_url=str(payload.get("repo_url", "") or ""),
      start_at_boot=bool(payload.get("start_at_boot")),
      restore=bool(payload.get("restore")),
      confirm=True,
      params=params,
    )

  if action == "save_adaptation_draft":
    from ai.tools.domains.vehicle.adaptation import save_adaptation_draft
    return save_adaptation_draft(
      project_id=str(payload.get("project_id", "")),
      fingerprint=str(payload.get("fingerprint", "")),
      files=payload.get("files") or {},
      notes=str(payload.get("notes", "")),
      metadata=payload.get("metadata"),
    )

  if action == "car_porting_fingerprint_to_draft":
    from ai.tools.domains.vehicle.car_porting_tools import car_porting_fingerprint_to_draft
    return car_porting_fingerprint_to_draft(
      project_id=str(payload.get("project_id", "")),
      route=str(payload.get("route", "")),
      platform=payload.get("platform") or None,
      notes=str(payload.get("notes", "")),
    )

  if action == "restore_tune_snapshot":
    from ai.tools.domains.tune.tune_snapshot_store import restore_tune_snapshot
    return restore_tune_snapshot(params, str(payload.get("snapshot_id", "")))

  return {"ok": False, "error": f"Unknown action {action}"}


def list_pending(params: Params) -> dict[str, Any]:
  store = _purge_expired(_load_all(params))
  _save_all(params, store)
  return {"ok": True, "pending": list(store.values())}
