"""Local dev cache inventory and age-based cleanup (routes, TSK extract, etc.)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from ai.tsk.lib.env import CACHE_DIR, CAN_MESSAGES_DIR, CAN_ORACLE_PATH, DATAFLASH_DIR


def _cabana_cache_dirs() -> list[Path]:
  try:
    from ai.services.cabana.app import _cabana_cache_dir

    return [_cabana_cache_dir()]
  except Exception:
    return []


def _cache_group_defs() -> list[dict[str, Any]]:
  return [
    {
      "id": "tsk_extract",
      "label": "TSK 提取（CAN / DataFlash）",
      "paths": [Path(CAN_ORACLE_PATH), Path(CAN_MESSAGES_DIR), Path(DATAFLASH_DIR)],
    },
    {
      "id": "cabana_routes",
      "label": "Cabana 路线回放缓存",
      "paths": _cabana_cache_dirs(),
    },
    {
      "id": "ai_cache",
      "label": "助手本地缓存目录",
      "paths": [Path(CACHE_DIR) / "ai"],
    },
  ]


def _iter_files(paths: list[Path]) -> list[Path]:
  out: list[Path] = []
  for p in paths:
    if p.is_file():
      out.append(p)
    elif p.is_dir():
      for root, _dirs, files in os.walk(p):
        for name in files:
          out.append(Path(root) / name)
  return out


def _file_age_seconds(path: Path) -> float | None:
  try:
    return max(0.0, time.time() - path.stat().st_mtime)
  except OSError:
    return None


def _matches_window(age_seconds: float, *, days: int, mode: str) -> bool:
  if mode == "all":
    return True
  cutoff = max(0, int(days)) * 86400
  if mode == "within":
    return age_seconds <= cutoff
  if mode == "older":
    return age_seconds > cutoff
  return False


def get_cache_status(*, days: int | None = None, mode: str | None = None) -> dict[str, Any]:
  filter_enabled = days is not None and mode is not None
  mode = mode if mode in ("within", "older", "all") else "within"
  days = max(0, int(days if days is not None else 3))
  groups_out: list[dict[str, Any]] = []
  total_bytes = 0
  total_files = 0
  for g in _cache_group_defs():
    files = _iter_files(g["paths"])
    nbytes = 0
    matched = 0
    for f in files:
      if filter_enabled and mode != "all":
        age = _file_age_seconds(f)
        if age is None or not _matches_window(age, days=days, mode=mode):
          continue
      try:
        nbytes += f.stat().st_size
      except OSError:
        pass
      matched += 1
    total_bytes += nbytes
    total_files += matched
    groups_out.append({
      "id": g["id"],
      "label": g["label"],
      "files": matched,
      "bytes": nbytes,
    })
  out: dict[str, Any] = {
    "ok": True,
    "groups": groups_out,
    "total_files": total_files,
    "total_bytes": total_bytes,
    "default_days": 3,
    "default_mode": "within",
  }
  if filter_enabled:
    out["filter"] = {"days": days, "mode": mode}
  return out


def clear_dev_cache(
  *,
  days: int = 3,
  mode: str = "within",
  groups: list[str] | None = None,
) -> dict[str, Any]:
  mode = mode if mode in ("within", "older", "all") else "within"
  days = max(0, int(days))
  selected = set(groups) if groups else None
  wants_tsk = not selected or "tsk_extract" in selected

  if wants_tsk and mode == "all":
    try:
      from ai.tsk import service as tsk_service

      result = tsk_service.run_clear_cache()
      if not result.get("ok"):
        return {
          "ok": False,
          "error": result.get("message") or "TSK 缓存清理被占用任务阻止",
          "status": result.get("status"),
        }
    except Exception as e:
      return {"ok": False, "error": str(e)}

  deleted_files = 0
  freed_bytes = 0
  errors: list[str] = []
  details: list[dict[str, Any]] = []
  touched_tsk = False

  for g in _cache_group_defs():
    if selected and g["id"] not in selected:
      continue
    if g["id"] == "tsk_extract":
      touched_tsk = True

    group_deleted = 0
    group_freed = 0
    for f in _iter_files(g["paths"]):
      age = _file_age_seconds(f)
      if age is None:
        continue
      if not _matches_window(age, days=days, mode=mode):
        continue
      try:
        sz = f.stat().st_size
        f.unlink()
        group_deleted += 1
        group_freed += sz
      except OSError as e:
        errors.append(f"{f}: {e}")
    deleted_files += group_deleted
    freed_bytes += group_freed
    details.append({"id": g["id"], "deleted": group_deleted, "freed_bytes": group_freed})

  if touched_tsk:
    try:
      from ai.tsk import service as tsk_service

      tsk_service.rehydrate_can_state()
      tsk_service.rehydrate_dataflash_state()
    except Exception:
      pass

  try:
    from ai.skills.loader import clear_cache as clear_skills_cache
    from ai.tools.domains.platform.catalog_builder import clear_catalog_cache

    clear_skills_cache()
    clear_catalog_cache()
  except Exception:
    pass

  return {
    "ok": True,
    "deleted_files": deleted_files,
    "freed_bytes": freed_bytes,
    "mode": mode,
    "days": days,
    "details": details,
    "errors": errors[:20],
  }
