"""Unified param write pipeline: snapshot, passport, regression guard."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params

from ai.tools.param_write import put_param
from ai.tools.params_policy import validate_write_batch


def apply_param_writes(
  params: Params,
  writes: dict[str, Any],
  *,
  action: str,
  brand: str = "",
  route_before: str = "",
  route_after: str = "",
  skip_regression_check: bool = False,
  snapshot_label: str = "auto_before_write",
  preset_id: str | None = None,
  admin: bool = True,
) -> dict[str, Any]:
  """Validate, optional regression check, snapshot, apply, passport."""
  if not writes:
    return {"ok": False, "error": "No params to write"}

  ok, reason = validate_write_batch(writes, admin=admin)
  if not ok:
    return {"ok": False, "error": reason}

  reg: dict[str, Any] = {}
  rb = (route_before or "").strip()
  ra = (route_after or "").strip()
  if rb and ra and not skip_regression_check:
    from ai.tools.tune_regression import check_tune_regression
    reg = check_tune_regression(rb, ra, block_on_regression=True)
    if not reg.get("ok"):
      return reg

  from ai.tools.tune_snapshot_store import save_tune_snapshot
  from ai.tools.tune_passport_store import record_tune_passport

  snap = save_tune_snapshot(params, label=snapshot_label, brand=brand)
  applied: dict[str, Any] = {}
  for key, value in writes.items():
    put_param(params, key, value)
    applied[key] = value

  snap_obj = snap.get("snapshot") or {}
  record_tune_passport(
    action=action,
    params_changed=applied,
    route_name=ra or rb,
    snapshot_id=snap_obj.get("id", "") if isinstance(snap_obj, dict) else "",
    score_before=reg.get("score_before") if rb and ra else None,
    score_after=reg.get("score_after") if rb and ra else None,
    note=f"preset={preset_id}" if preset_id else "",
  )

  out: dict[str, Any] = {
    "ok": True,
    "applied": applied,
    "auto_snapshot": snap_obj,
  }
  if preset_id:
    out["preset"] = preset_id
  if rb and ra:
    out["regression_check"] = reg
  return out
