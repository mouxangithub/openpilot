"""On-device storage breakdown and cleanup for WebUI storage panel."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_CACHE_TTL = 60.0

SAFE_STAGING_ROOT = "/data/safe_staging"
SCONS_CACHE_ROOT = "/data/scons_cache"

_CATEGORY_PATHS: dict[str, list[str]] = {}

_CATEGORY_ORDER = (
  "routes",
  "models",
  "maps",
  "software",
  "logs",
  "ota_staging",
  "scons_cache",
  "other",
)


def _init_paths() -> None:
  if _CATEGORY_PATHS:
    return
  try:
    from openpilot.common.hardware.hw import Paths

    routes = [Paths.log_root().rstrip("/")]
    ext = Paths.log_root_external().rstrip("/")
    if ext and ext != routes[0]:
      routes.append(ext)
    _CATEGORY_PATHS.update({
      "routes": routes,
      "models": [Paths.model_root().rstrip("/")],
      "maps": [Paths.mapd_root().rstrip("/")],
      "software": ["/data/openpilot"],
      "logs": [
        Paths.swaglog_root().rstrip("/"),
        Paths.stats_root().rstrip("/"),
        Paths.stats_sp_root().rstrip("/"),
        Paths.crash_log_root().rstrip("/"),
      ],
      "download_cache": [Paths.download_cache_root().rstrip("/")],
    })
  except Exception:
    home = os.path.join(os.path.expanduser("~"), ".comma")
    _CATEGORY_PATHS.update({
      "routes": [os.path.join(home, "media", "0", "realdata")],
      "models": [os.path.join(home, "media", "0", "models")],
      "maps": [os.path.join(home, "media", "0", "osm")],
      "software": [home],
      "logs": [os.path.join(home, "log")],
      "download_cache": ["/tmp/comma_download_cache"],
    })


def _data_mount() -> str:
  _init_paths()
  if os.path.isdir("/data"):
    return "/data"
  try:
    from openpilot.common.hardware.hw import Paths
    return str(Path(Paths.comma_home()).parent)
  except Exception:
    return os.path.expanduser("~")


def _safe_staging_bytes() -> int:
  """Disk used by OTA staging (exclude merged overlay to avoid double-counting /data/openpilot)."""
  root = SAFE_STAGING_ROOT
  if not os.path.isdir(root):
    return 0
  total = 0
  for name in ("finalized", "upper", "metadata"):
    total += _dir_bytes(os.path.join(root, name))
  return total


def _dir_bytes(path: str) -> int:
  if not path or not os.path.isdir(path):
    return 0
  try:
    import subprocess
    proc = subprocess.run(
      ["du", "-sb", path],
      capture_output=True,
      text=True,
      timeout=90,
      check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
      return int(proc.stdout.split()[0])
  except Exception:
    pass
  total = 0
  try:
    for root, _dirs, files in os.walk(path):
      for name in files:
        fp = os.path.join(root, name)
        try:
          total += os.path.getsize(fp)
        except OSError:
          pass
  except OSError:
    return 0
  return total


def _disk_totals(mount: str) -> tuple[int, int, int]:
  try:
    st = os.statvfs(mount)
    total = int(st.f_blocks * st.f_frsize)
    free = int(st.f_bavail * st.f_frsize)
    used = max(0, total - free)
    return total, used, free
  except OSError:
    return 0, 0, 0


def _is_offroad() -> bool:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return True
  try:
    from openpilot.common.params import Params
    p = Params()
    if p.get_bool("IsOnroad"):
      return False
    if p.get_bool("IsOffroad"):
      return True
  except Exception:
    pass
  try:
    from webui.server.bridge.state_hub import get_state
    st = get_state()
    return bool(st.get("is_offroad", True))
  except Exception:
    return True


def _external_root() -> str:
  try:
    from openpilot.common.hardware.hw import Paths
    return Paths.log_root_external().rstrip("/")
  except Exception:
    return "/mnt/external_realdata"


def _internal_routes_root() -> str:
  try:
    from openpilot.common.hardware.hw import Paths
    return Paths.log_root().rstrip("/")
  except Exception:
    home = os.path.join(os.path.expanduser("~"), ".comma")
    return os.path.join(home, "media", "0", "realdata")


def _is_mounted(path: str) -> bool:
  if not path or not os.path.isdir(path):
    return False
  try:
    return Path(path).is_mount()
  except Exception:
    return os.path.ismount(path)


def _volume_payload(
  *,
  volume_id: str,
  label: str,
  mount: str,
  categories: list[dict[str, Any]],
  total: int,
  used: int,
  free: int,
) -> dict[str, Any]:
  return {
    "id": volume_id,
    "label": label,
    "mount": mount,
    "total_bytes": total,
    "used_bytes": used,
    "free_bytes": free,
    "free_percent": round(100.0 * free / total, 1) if total else 0,
    "low_space": (free / total < 0.10) if total else False,
    "critical_space": (free / total < 0.02) if total else False,
    "categories": categories,
  }


def _segment_route_id(name: str) -> str | None:
  if "--" not in name:
    return None
  route_id, _, seg = name.rpartition("--")
  try:
    int(seg)
  except ValueError:
    return None
  return route_id or None


def _has_preserve_xattr(path: str) -> bool:
  try:
    from openpilot.system.loggerd.deleter import PRESERVE_ATTR_NAME, PRESERVE_ATTR_VALUE
    from openpilot.system.loggerd.xattr_cache import getxattr
    return getxattr(path, PRESERVE_ATTR_NAME) == PRESERVE_ATTR_VALUE
  except OSError:
    return False


def _route_roots() -> list[tuple[str, str]]:
  roots: list[tuple[str, str]] = [("internal", _internal_routes_root())]
  ext = _external_root()
  if _is_mounted(ext):
    roots.append(("external", ext))
  return roots


def _starred_route_ids(root: str) -> set[str]:
  starred: set[str] = set()
  if not os.path.isdir(root):
    return starred
  try:
    for name in os.listdir(root):
      path = os.path.join(root, name)
      if not os.path.isdir(path):
        continue
      route_id = _segment_route_id(name)
      if route_id and _has_preserve_xattr(path):
        starred.add(route_id)
  except OSError:
    pass
  return starred


def _scan_starred_routes() -> dict[str, Any]:
  items: list[dict[str, Any]] = []
  for volume_id, root in _route_roots():
    if not os.path.isdir(root):
      continue
    starred_ids = _starred_route_ids(root)
    if not starred_ids:
      continue
    segments_by_route: dict[str, list[str]] = {rid: [] for rid in starred_ids}
    try:
      for name in os.listdir(root):
        route_id = _segment_route_id(name)
        if route_id and route_id in starred_ids:
          segments_by_route.setdefault(route_id, []).append(name)
    except OSError:
      continue
    for route_id in sorted(starred_ids):
      seg_names = segments_by_route.get(route_id, [])
      bytes_total = 0
      for seg in seg_names:
        bytes_total += _dir_bytes(os.path.join(root, seg))
      items.append({
        "id": route_id,
        "volume": volume_id,
        "segments": len(seg_names),
        "bytes": bytes_total,
      })
  items.sort(key=lambda it: (it["volume"], it["id"]))
  total_bytes = sum(int(it["bytes"]) for it in items)
  return {"count": len(items), "bytes": total_bytes, "items": items}


def _estimate_routes_clearable_bytes(*, starred_only: bool) -> int:
  from openpilot.system.loggerd.deleter import DELETE_LAST, get_preserved_segments
  from openpilot.system.loggerd.uploader import listdir_by_creation

  total = 0
  for _volume_id, root in _route_roots():
    if not os.path.isdir(root):
      continue
    starred_ids = _starred_route_ids(root)
    dirs = listdir_by_creation(root)
    preserved = get_preserved_segments(dirs)
    for name in dirs:
      if name in DELETE_LAST:
        continue
      path = os.path.join(root, name)
      if not os.path.isdir(path):
        continue
      route_id = _segment_route_id(name)
      is_starred_route = bool(route_id and route_id in starred_ids)
      if starred_only:
        if not is_starred_route:
          continue
      elif is_starred_route or name in preserved:
        continue
      try:
        if any(f.endswith(".lock") for f in os.listdir(path)):
          continue
      except OSError:
        continue
      total += _dir_bytes(path)
  return total


def _mock_snapshot() -> dict[str, Any]:
  total = 128 * 1024 ** 3
  routes_int = int(40 * 1024 ** 3)
  routes_starred = int(8 * 1024 ** 3)
  routes_clearable = int(44 * 1024 ** 3)
  cats = {
    "routes": routes_int,
    "models": int(9 * 1024 ** 3),
    "maps": int(4 * 1024 ** 3),
    "software": int(18 * 1024 ** 3),
    "logs": int(2 * 1024 ** 3),
    "ota_staging": int(9 * 1024 ** 3),
    "scons_cache": int(900 * 1024 ** 2),
    "other": int(100 * 1024 ** 2),
  }
  used = sum(cats.values())
  free = max(0, total - used)
  ext_total = 512 * 1024 ** 3
  routes_ext = int(120 * 1024 ** 3)
  ext_free = ext_total - routes_ext
  internal_cats = [
    {"id": k, "bytes": cats[k], "percent": round(100.0 * cats[k] / total, 1) if total else 0}
    for k in _CATEGORY_ORDER
  ]
  return {
    "ok": True,
    "dev_pc": True,
    "scanning": False,
    "last_scan_ts": int(time.time()),
    "offroad": True,
    "total_bytes": total,
    "used_bytes": used,
    "free_bytes": free,
    "free_percent": round(100.0 * free / total, 1) if total else 0,
    "low_space": free / total < 0.10 if total else False,
    "critical_space": free / total < 0.02 if total else False,
    "categories": internal_cats,
    "internal": _volume_payload(
      volume_id="internal",
      label="Internal storage",
      mount="/data",
      categories=internal_cats,
      total=total,
      used=used,
      free=free,
    ),
    "external": {
      "mounted": True,
      "label": "External SSD",
      "mount": "/mnt/external_realdata",
      "total_bytes": ext_total,
      "used_bytes": routes_ext,
      "free_bytes": ext_free,
      "free_percent": round(100.0 * ext_free / ext_total, 1),
      "low_space": ext_free / ext_total < 0.10,
      "critical_space": ext_free / ext_total < 0.02,
      "routes_bytes": routes_ext,
      "categories": [
        {"id": "routes", "bytes": routes_ext, "percent": round(100.0 * routes_ext / ext_total, 1)},
      ],
    },
    "routes_internal_bytes": routes_int,
    "routes_external_bytes": routes_ext,
    "starred_routes": {
      "count": 3,
      "bytes": routes_starred,
      "items": [
        {"id": "2024-03-15", "volume": "internal", "segments": 12, "bytes": int(3 * 1024 ** 3)},
        {"id": "2024-02-28", "volume": "internal", "segments": 8, "bytes": int(2.5 * 1024 ** 3)},
        {"id": "2024-01-10", "volume": "external", "segments": 15, "bytes": int(2.5 * 1024 ** 3)},
      ],
    },
    "clearable": {
      "routes": routes_clearable,
      "routes_starred": routes_starred,
      "maps": cats["maps"],
      "models_cache": int(3 * 1024 ** 3),
      "logs": cats["logs"],
      "scons_cache": cats["scons_cache"],
      "download_cache": int(512 * 1024 ** 2),
    },
  }


def snapshot_storage(*, force: bool = False) -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return _mock_snapshot()

  now = time.time()
  if not force and _CACHE.get("data") and now - float(_CACHE.get("ts", 0)) < _CACHE_TTL:
    return _CACHE["data"]

  _init_paths()
  mount = _data_mount()
  total, used_disk, free = _disk_totals(mount)

  routes_internal = _dir_bytes(_internal_routes_root())
  routes_external = 0
  external_root = _external_root()
  external_mounted = _is_mounted(external_root)
  if external_mounted:
    routes_external = _dir_bytes(external_root)

  cat_bytes: dict[str, int] = {"routes": routes_internal}
  for cat_id, paths in _CATEGORY_PATHS.items():
    if cat_id in ("download_cache", "routes"):
      continue
    size = 0
    for p in paths:
      size += _dir_bytes(p)
    cat_bytes[cat_id] = size

  cat_bytes["ota_staging"] = _safe_staging_bytes()
  cat_bytes["scons_cache"] = _dir_bytes(SCONS_CACHE_ROOT)

  download_cache = sum(_dir_bytes(p) for p in _CATEGORY_PATHS.get("download_cache", []))
  known = sum(cat_bytes.values()) + download_cache
  other = max(0, used_disk - known)
  cat_bytes["other"] = other

  categories = []
  for cat_id in _CATEGORY_ORDER:
    b = int(cat_bytes.get(cat_id, 0))
    categories.append({
      "id": cat_id,
      "bytes": b,
      "percent": round(100.0 * b / total, 1) if total else 0,
    })

  internal = _volume_payload(
    volume_id="internal",
    label="Internal storage",
    mount=mount,
    categories=categories,
    total=total,
    used=used_disk,
    free=free,
  )

  external: dict[str, Any] | None = None
  if external_mounted:
    ext_total, ext_used, ext_free = _disk_totals(external_root)
    if ext_total <= 0:
      ext_total = max(routes_external, ext_used)
      ext_free = max(0, ext_total - routes_external)
      ext_used = routes_external
    ext_cats = [{
      "id": "routes",
      "bytes": routes_external,
      "percent": round(100.0 * routes_external / ext_total, 1) if ext_total else 0,
    }]
    external = {
      "mounted": True,
      "label": "External SSD",
      "mount": external_root,
      "total_bytes": ext_total,
      "used_bytes": ext_used,
      "free_bytes": ext_free,
      "free_percent": round(100.0 * ext_free / ext_total, 1) if ext_total else 0,
      "low_space": (ext_free / ext_total < 0.10) if ext_total else False,
      "critical_space": (ext_free / ext_total < 0.02) if ext_total else False,
      "routes_bytes": routes_external,
      "categories": ext_cats,
    }

  starred = _scan_starred_routes()
  routes_clearable = _estimate_routes_clearable_bytes(starred_only=False)
  routes_starred_clearable = _estimate_routes_clearable_bytes(starred_only=True)

  clearable = {
    "routes": int(routes_clearable),
    "routes_starred": int(routes_starred_clearable),
    "maps": int(cat_bytes.get("maps", 0)),
    "models_cache": None,
    "logs": int(cat_bytes.get("logs", 0)),
    "scons_cache": int(cat_bytes.get("scons_cache", 0)),
    "download_cache": int(download_cache),
  }

  try:
    from openpilot.common.params import Params
    p = Params()
    active = (p.get("ActiveModel") or "").strip()
    model_root = (_CATEGORY_PATHS.get("models") or [""])[0]
    if active and model_root and os.path.isdir(model_root):
      active_path = os.path.join(model_root, active)
      total_models = cat_bytes.get("models", 0)
      active_size = _dir_bytes(active_path) if os.path.isdir(active_path) else 0
      clearable["models_cache"] = max(0, total_models - active_size)
    else:
      clearable["models_cache"] = int(cat_bytes.get("models", 0))
  except Exception:
    clearable["models_cache"] = int(cat_bytes.get("models", 0))

  out = {
    "ok": True,
    "scanning": False,
    "last_scan_ts": int(now),
    "offroad": _is_offroad(),
    "total_bytes": total,
    "used_bytes": used_disk,
    "free_bytes": free,
    "free_percent": round(100.0 * free / total, 1) if total else 0,
    "low_space": (free / total < 0.10) if total else False,
    "critical_space": (free / total < 0.02) if total else False,
    "categories": categories,
    "internal": internal,
    "external": external,
    "routes_internal_bytes": routes_internal,
    "routes_external_bytes": routes_external,
    "starred_routes": starred,
    "clearable": clearable,
  }
  _CACHE["ts"] = now
  _CACHE["data"] = out
  return out


def _invalidate_cache() -> None:
  _CACHE["ts"] = 0.0
  _CACHE["data"] = None


def _clear_dir_contents(path: str) -> int:
  if not os.path.isdir(path):
    return 0
  freed = _dir_bytes(path)
  for entry in os.listdir(path):
    fp = os.path.join(path, entry)
    try:
      if os.path.isdir(fp):
        shutil.rmtree(fp)
      else:
        os.remove(fp)
    except OSError:
      pass
  return freed


def clear_storage(category: str) -> dict[str, Any]:
  if not _is_offroad():
    return {"ok": False, "error": "Only available while offroad"}

  _init_paths()
  freed = 0

  try:
    if category == "routes":
      from openpilot.system.loggerd.deleter import DELETE_LAST, get_preserved_segments
      from openpilot.system.loggerd.uploader import listdir_by_creation

      route_roots = [_internal_routes_root()]
      if _is_mounted(_external_root()):
        route_roots.append(_external_root())
      for root in route_roots:
        if not os.path.isdir(root):
          continue
        dirs = listdir_by_creation(root)
        preserved = get_preserved_segments(dirs)
        for name in sorted(dirs, key=lambda d: (d in DELETE_LAST, d in preserved)):
          if name in preserved or name in DELETE_LAST:
            continue
          path = os.path.join(root, name)
          if not os.path.isdir(path):
            continue
          try:
            if any(f.endswith(".lock") for f in os.listdir(path)):
              continue
          except OSError:
            continue
          size = _dir_bytes(path)
          shutil.rmtree(path, ignore_errors=True)
          freed += size

    elif category == "routes_starred":
      from openpilot.system.loggerd.deleter import DELETE_LAST
      from openpilot.system.loggerd.uploader import listdir_by_creation

      for root in [r for _vol, r in _route_roots()]:
        if not os.path.isdir(root):
          continue
        starred_ids = _starred_route_ids(root)
        if not starred_ids:
          continue
        for name in listdir_by_creation(root):
          if name in DELETE_LAST:
            continue
          route_id = _segment_route_id(name)
          if not route_id or route_id not in starred_ids:
            continue
          path = os.path.join(root, name)
          if not os.path.isdir(path):
            continue
          try:
            if any(f.endswith(".lock") for f in os.listdir(path)):
              continue
          except OSError:
            continue
          size = _dir_bytes(path)
          shutil.rmtree(path, ignore_errors=True)
          freed += size

    elif category == "maps":
      from openpilot.common.params import Params
      p = Params()
      p.put_bool("OsmDbDelete", True, block=True)
      for path in _CATEGORY_PATHS.get("maps", []):
        freed += _clear_dir_contents(path)

    elif category == "models_cache":
      from openpilot.common.params import Params
      p = Params()
      p.put_bool("ModelManager_ClearCache", True, block=True)
      model_root = (_CATEGORY_PATHS.get("models") or [""])[0]
      active = (p.get("ActiveModel") or "").strip()
      if model_root and os.path.isdir(model_root):
        for name in os.listdir(model_root):
          if active and name == active:
            continue
          fp = os.path.join(model_root, name)
          if os.path.isdir(fp):
            freed += _dir_bytes(fp)
            shutil.rmtree(fp, ignore_errors=True)

    elif category == "logs":
      for path in _CATEGORY_PATHS.get("logs", []):
        freed += _clear_dir_contents(path)

    elif category == "download_cache":
      for path in _CATEGORY_PATHS.get("download_cache", []):
        freed += _clear_dir_contents(path)

    elif category == "scons_cache":
      if os.path.isdir(SCONS_CACHE_ROOT):
        freed += _dir_bytes(SCONS_CACHE_ROOT)
        shutil.rmtree(SCONS_CACHE_ROOT, ignore_errors=True)

    else:
      return {"ok": False, "error": f"unknown category: {category}"}

    _invalidate_cache()
    return {"ok": True, "category": category, "freed_bytes": freed}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
