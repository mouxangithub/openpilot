"""Persist tune snapshots for rollback (file-backed)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openpilot.common.params import Params

from ai.tools.diagnostics_tools import snapshot_tune_state
from ai.tools.param_write import put_param
from ai.system.paths import tune_snapshots_dir

_MAX_SNAPSHOTS = 8


def _dir() -> Path:
  p = tune_snapshots_dir()
  p.mkdir(parents=True, exist_ok=True)
  return p


def save_tune_snapshot(params: Params, *, label: str = "manual", brand: str = "") -> dict[str, Any]:
  snap = snapshot_tune_state(params, brand=brand)
  payload = snap.get("params") or {}
  if not payload:
    return {"ok": False, "error": "No tunable params to snapshot"}

  entry = {
    "id": f"snap_{int(time.time())}",
    "label": label[:64],
    "brand": brand,
    "at": int(time.time()),
    "params": payload,
  }
  path = _dir() / f"{entry['id']}.json"
  path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

  all_snaps = sorted(_dir().glob("snap_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
  for old in all_snaps[_MAX_SNAPSHOTS:]:
    try:
      old.unlink()
    except OSError:
      pass

  return {"ok": True, "snapshot": {"id": entry["id"], "label": label, "param_count": len(payload)}}


def list_tune_snapshots() -> dict[str, Any]:
  snaps = []
  for p in sorted(_dir().glob("snap_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
    try:
      data = json.loads(p.read_text(encoding="utf-8"))
      snaps.append({
        "id": data.get("id", p.stem),
        "label": data.get("label", ""),
        "at": data.get("at", 0),
        "param_count": len(data.get("params") or {}),
      })
    except Exception:
      continue
  return {"ok": True, "snapshots": snaps[:_MAX_SNAPSHOTS]}


def restore_tune_snapshot(params: Params, snapshot_id: str = "") -> dict[str, Any]:
  files = sorted(_dir().glob("snap_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
  if not files:
    return {"ok": False, "error": "No snapshots saved"}

  target = None
  if snapshot_id:
    for p in files:
      if p.stem == snapshot_id or p.name.startswith(snapshot_id):
        target = p
        break
    if target is None:
      return {"ok": False, "error": f"Snapshot '{snapshot_id}' not found"}
  else:
    target = files[0]

  try:
    data = json.loads(target.read_text(encoding="utf-8"))
  except Exception as e:
    return {"ok": False, "error": str(e)}

  writes = data.get("params") or {}
  from ai.tools.params_policy import validate_write_batch
  ok, reason = validate_write_batch(writes)
  if not ok:
    return {"ok": False, "error": reason}

  for key, value in writes.items():
    put_param(params, key, value)

  return {
    "ok": True,
    "restored_id": data.get("id", target.stem),
    "label": data.get("label", ""),
    "param_count": len(writes),
    "hint": "Re-engage or restart UI if settings do not apply immediately.",
  }
