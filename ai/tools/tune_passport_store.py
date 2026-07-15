"""Tune passport journal + param watchlist for op助手."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path

_WATCHLIST_KEY = "ai_param_watchlist"
_MAX_PASSPORT = 500


def _passport_path() -> Path:
  return workspace_path("ai_tune_passport.jsonl")


def record_tune_passport(
  *,
  action: str,
  params_changed: dict[str, Any] | None = None,
  route_name: str = "",
  snapshot_id: str = "",
  score_before: float | None = None,
  score_after: float | None = None,
  note: str = "",
) -> dict[str, Any]:
  entry = {
    "id": f"tp_{uuid.uuid4().hex[:10]}",
    "at": int(time.time()),
    "action": action,
    "params_changed": params_changed or {},
    "route_name": route_name,
    "snapshot_id": snapshot_id,
    "score_before": score_before,
    "score_after": score_after,
    "note": (note or "")[:500],
  }
  path = _passport_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
  return {"ok": True, "entry": entry}


def list_tune_passport(*, limit: int = 30) -> dict[str, Any]:
  path = _passport_path()
  if not path.is_file():
    return {"ok": True, "entries": [], "count": 0, "path": str(path)}
  lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
  entries: list[dict[str, Any]] = []
  for line in reversed(lines[-_MAX_PASSPORT:]):
    line = line.strip()
    if not line:
      continue
    try:
      entries.append(json.loads(line))
    except json.JSONDecodeError:
      continue
    if len(entries) >= max(1, min(limit, 100)):
      break
  return {"ok": True, "entries": entries, "count": len(entries), "path": str(path)}


def get_param_watchlist(params=None) -> list[str]:
  from openpilot.common.params import Params
  params = params or Params()
  try:
    raw = params.get(_WATCHLIST_KEY)
    if not raw:
      return []
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    return [str(x) for x in data if x][:30]
  except Exception:
    return []


def manage_param_watchlist(
  params,
  *,
  add: list[str] | None = None,
  remove: list[str] | None = None,
  replace: list[str] | None = None,
) -> dict[str, Any]:
  current = get_param_watchlist(params)
  if replace is not None:
    current = [str(x).strip() for x in replace if str(x).strip()][:30]
  else:
    for key in add or []:
      k = str(key).strip()
      if k and k not in current:
        current.append(k)
    for key in remove or []:
      k = str(key).strip()
      if k in current:
        current.remove(k)
    current = current[:30]
  params.put(_WATCHLIST_KEY, json.dumps(current, ensure_ascii=False))
  return {"ok": True, "watchlist": current}


def check_param_watchlist(params, *, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
  """Compare watchlist params to baseline (or store baseline on first run)."""
  keys = get_param_watchlist(params)
  if not keys:
    return {"ok": True, "watchlist": [], "hint": "Use manage_param_watchlist to add keys."}

  state_key = "ai_param_watchlist_baseline"
  if baseline is None:
    try:
      raw = params.get(state_key)
      if raw:
        if isinstance(raw, bytes):
          raw = raw.decode("utf-8", errors="replace")
        baseline = json.loads(raw)
      else:
        baseline = {}
        for k in keys:
          try:
            v = params.get(k)
            baseline[k] = v.decode(errors="replace") if isinstance(v, bytes) else v
          except Exception:
            baseline[k] = None
        params.put(state_key, json.dumps(baseline, ensure_ascii=False))
    except Exception:
      baseline = {}

  changes: dict[str, Any] = {}
  for k in keys:
    try:
      cur = params.get(k)
      cur_s = cur.decode(errors="replace") if isinstance(cur, bytes) else cur
    except Exception:
      cur_s = None
    base_s = baseline.get(k)
    if str(cur_s) != str(base_s):
      changes[k] = {"before": base_s, "after": cur_s}

  return {
    "ok": True,
    "watchlist": keys,
    "changes": changes,
    "change_count": len(changes),
    "drifted": len(changes) > 0,
  }
