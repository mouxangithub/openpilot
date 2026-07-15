"""Pending write confirmations for op助手 (preview before apply)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from openpilot.common.params import Params

from ai.tools.params_policy import validate_write_batch
from ai.system.admin import is_admin_mode

_PENDING_KEY = "ai_write_pending"
_TTL_SEC = 600


def _load_all(params: Params) -> dict[str, Any]:
  try:
    raw = params.get(_PENDING_KEY)
    if not raw:
      return {}
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def _save_all(params: Params, data: dict[str, Any]) -> None:
  params.put(_PENDING_KEY, json.dumps(data, ensure_ascii=False))


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
    from ai.tools.presets import get_preset
    preset = get_preset(str(payload.get("preset_id", "")))
    if not preset:
      return {"ok": False, "error": "Unknown preset_id"}
    ok, reason = validate_write_batch(preset["params"], admin=is_admin_mode(params))
  elif action == "select_driving_model":
    ok, reason = True, ""
  elif action == "save_adaptation_draft":
    files = payload.get("files") or {}
    ok, reason = (True, "") if isinstance(files, dict) and files else (False, "files required")
  elif action == "car_porting_fingerprint_to_draft":
    ok, reason = (True, "") if payload.get("project_id") and payload.get("route") else (False, "project_id and route required")
  elif action == "restore_tune_snapshot":
    ok, reason = True, ""
  else:
    return {"ok": False, "error": f"Unknown action {action}"}

  if not ok and action != "select_driving_model":
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
  return {
    "ok": True,
    "needs_confirmation": True,
    "pending_id": pid,
    "action": action,
    "preview": preview,
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
    from ai.tools.tune_write_pipeline import apply_param_writes
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
    from ai.tools.presets import get_preset
    from ai.tools.tune_write_pipeline import apply_param_writes
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

  if action == "select_driving_model":
    model = str(payload.get("model", ""))
    put_param(params, "dp_dev_model_selected", model)
    return {"ok": True, "model": model}

  if action == "save_adaptation_draft":
    from ai.tools.adaptation import save_adaptation_draft
    return save_adaptation_draft(
      project_id=str(payload.get("project_id", "")),
      fingerprint=str(payload.get("fingerprint", "")),
      files=payload.get("files") or {},
      notes=str(payload.get("notes", "")),
      metadata=payload.get("metadata"),
    )

  if action == "car_porting_fingerprint_to_draft":
    from ai.tools.car_porting_tools import car_porting_fingerprint_to_draft
    return car_porting_fingerprint_to_draft(
      project_id=str(payload.get("project_id", "")),
      route=str(payload.get("route", "")),
      platform=payload.get("platform") or None,
      notes=str(payload.get("notes", "")),
    )

  if action == "restore_tune_snapshot":
    from ai.tools.tune_snapshot_store import restore_tune_snapshot
    return restore_tune_snapshot(params, str(payload.get("snapshot_id", "")))

  return {"ok": False, "error": f"Unknown action {action}"}


def list_pending(params: Params) -> dict[str, Any]:
  store = _purge_expired(_load_all(params))
  _save_all(params, store)
  return {"ok": True, "pending": list(store.values())}
