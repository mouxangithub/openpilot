"""OSM region tree + map status for settings panel."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent / "data"
_CACHE_DIR = _DATA_DIR / "cache"
_SIZE_CACHE: dict[str, Any] = {"ts": 0.0, "size_mb": 0.0, "computing": False}
_SIZE_TTL = 20.0
_REGIONS_CACHE: dict[str, dict[str, Any]] = {}


def _bundled_regions(region_type: str) -> dict[str, Any] | None:
  key = region_type or "Country"
  fname = "osm_countries.json" if key == "Country" else "osm_us_states.json"
  path = _DATA_DIR / fname
  if not path.is_file():
    return None
  try:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if key == "Country":
      countries = sorted(
        [{"name": k, "title": v.get("full_name", k)} for k, v in raw.items()],
        key=lambda c: c["title"],
      )
      return {"ok": True, "region_type": "Country", "countries": countries, "bundled": True, "full": len(countries) >= 150}
    states = sorted(
      [{"name": k, "title": v.get("full_name", k)} for k, v in raw.items() if k != "All"],
      key=lambda s: s["title"],
    )
    states.insert(0, {"name": "All", "title": raw.get("All", {}).get("full_name", "All states (~6.0 GB)")})
    return {"ok": True, "region_type": "State", "states": states, "bundled": True, "full": len(states) >= 50}
  except Exception:
    return None


def _disk_cache_path(region_type: str) -> Path:
  key = (region_type or "Country").lower()
  return _CACHE_DIR / f"osm_{key}_regions.json"


def _load_disk_cache(region_type: str) -> dict[str, Any] | None:
  path = _disk_cache_path(region_type)
  if not path.is_file():
    return None
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("ok"):
      data["cached"] = True
      return data
  except Exception:
    pass
  return None


def _save_disk_cache(region_type: str, data: dict[str, Any]) -> None:
  try:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in data.items() if k not in ("bundled", "cached", "full")}
    _disk_cache_path(region_type).write_text(json.dumps(payload), encoding="utf-8")
  except Exception:
    pass


def _shm_params():
  from openpilot.common.params import Params
  if os.name != "posix" or not Path("/dev/shm/params").exists():
    return Params()
  return Params("/dev/shm/params")


def _mock_regions(region_type: str = "Country") -> dict[str, Any]:
  if region_type == "State":
    return {
      "ok": True,
      "region_type": "State",
      "states": [
        {"name": "All", "title": "All states (~6.0 GB)"},
        {"name": "CA", "title": "California"},
        {"name": "TX", "title": "Texas"},
      ],
      "dev_pc": True,
    }
  return {
    "ok": True,
    "region_type": "Country",
    "countries": [
      {"name": "US", "title": "United States"},
      {"name": "CA", "title": "Canada"},
      {"name": "DE", "title": "Germany"},
    ],
    "dev_pc": True,
  }


def _calculate_map_size_bytes() -> int:
  try:
    from openpilot.common.hardware.hw import Paths
    root = Path(Paths.mapd_root()) / "offline"
    if not root.exists():
      return 0
    total = 0
    stack = [root]
    while stack:
      path = stack.pop()
      try:
        with os.scandir(path) as it:
          for entry in it:
            try:
              if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
              elif entry.is_dir(follow_symlinks=False):
                stack.append(entry.path)
            except OSError:
              continue
      except OSError:
        continue
    return total
  except Exception:
    return 0


def _refresh_size_cache_async() -> None:
  if _SIZE_CACHE.get("computing"):
    return
  _SIZE_CACHE["computing"] = True

  def run() -> None:
    try:
      total = _calculate_map_size_bytes()
      _SIZE_CACHE["size_mb"] = round(total / (1024 ** 2), 2)
      _SIZE_CACHE["ts"] = time.monotonic()
    finally:
      _SIZE_CACHE["computing"] = False

  threading.Thread(target=run, daemon=True).start()


def osm_regions() -> dict[str, Any]:
  """Lightweight placeholder — real regions load on demand."""
  return {"ok": True, "lazy": True}


def osm_fetch_regions(region_type: str = "Country") -> dict[str, Any]:
  key = region_type or "Country"
  if key in _REGIONS_CACHE:
    return _REGIONS_CACHE[key]
  if os.environ.get("WEBUI_DEV_PC") == "1":
    data = _mock_regions(key)
    _REGIONS_CACHE[key] = data
    return data
  try:
    import requests
    base_url = "https://raw.githubusercontent.com/pfeiferj/openpilot-mapd/main/"
    file_name = "nation_bounding_boxes.json" if key == "Country" else "us_states_bounding_boxes.json"
    raw = requests.get(base_url + file_name, timeout=10).json()
    if key == "Country":
      countries = sorted(
        [{"name": k, "title": v.get("full_name", k)} for k, v in raw.items()],
        key=lambda c: c["title"],
      )
      data = {"ok": True, "region_type": "Country", "countries": countries}
    else:
      states = sorted(
        [{"name": k, "title": v.get("full_name", k)} for k, v in raw.items()],
        key=lambda s: s["title"],
      )
      states.insert(0, {"name": "All", "title": "All states (~6.0 GB)"})
      data = {"ok": True, "region_type": "State", "states": states}
    _REGIONS_CACHE[key] = data
    _save_disk_cache(key, data)
    return data
  except Exception as exc:
    if key in _REGIONS_CACHE:
      return _REGIONS_CACHE[key]
    cached = _load_disk_cache(key)
    if cached:
      _REGIONS_CACHE[key] = cached
      return cached
    bundled = _bundled_regions(key)
    if bundled:
      _REGIONS_CACHE[key] = bundled
      return bundled
    if os.environ.get("WEBUI_DEV_PC") == "1":
      data = _mock_regions(key)
      _REGIONS_CACHE[key] = data
      return data
    return {"ok": False, "error": str(exc)}


def osm_select_region(country: str, country_title: str, state: str = "", state_title: str = "") -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    if country:
      p.put("OsmLocationName", country, block=True)
      p.put("OsmLocationTitle", country_title, block=True)
      p.put_bool("OsmLocal", True, block=True)
    if state:
      p.put("OsmStateName", state, block=True)
      p.put("OsmStateTitle", state_title, block=True)
    else:
      p.remove("OsmStateName")
      p.remove("OsmStateTitle")
    return {"ok": True, "values": _osm_param_values(p)}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _osm_param_values(p) -> dict[str, str]:
  keys = (
    "MapdVersion",
    "OsmLocationName",
    "OsmLocationTitle",
    "OsmStateName",
    "OsmStateTitle",
    "OsmDownloadedDate",
  )
  out: dict[str, str] = {}
  for key in keys:
    try:
      raw = p.get(key)
      out[key] = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
    except Exception:
      out[key] = ""
  return out


def osm_clear_incomplete_us() -> dict[str, Any]:
  """Rollback country when US state picker is cancelled without a selection."""
  try:
    from openpilot.common.params import Params
    p = Params()
    if p.get("OsmLocationName") != "US" or p.get("OsmStateName"):
      return {"ok": True, "skipped": True, "values": _osm_param_values(p)}
    for key in ("OsmDownloadedDate", "OsmLocal", "OsmLocationName", "OsmLocationTitle", "OsmStateName", "OsmStateTitle"):
      try:
        p.remove(key)
      except Exception:
        pass
    return {"ok": True, "values": _osm_param_values(p)}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def osm_download_progress() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {"ok": True, "progress": 0, "active": False, "downloading": False, "done": 0, "total": 0, "dev_pc": True}
  try:
    p = _shm_params()
    downloading = bool(p.get("OSMDownloadLocations"))
    pending = bool(p.get_bool("OsmDbUpdatesCheck"))
    progress_raw = p.get("OSMDownloadProgress")
    total = done = 0
    if progress_raw:
      try:
        obj = json.loads(progress_raw) if isinstance(progress_raw, str) else progress_raw
        if isinstance(obj, dict):
          total = int(obj.get("total_files") or 0)
          done = int(obj.get("downloaded_files") or 0)
      except Exception:
        pass
    pct = max(0.0, min(100.0, (done / total) * 100.0)) if total > 0 else 0.0
    active = downloading or pending
    return {
      "ok": True,
      "progress": pct,
      "active": active,
      "downloading": downloading,
      "done": done,
      "total": total,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def osm_map_size_mb(*, refresh: bool = False) -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {"ok": True, "size_mb": 128.5, "pending": False, "dev_pc": True}
  now = time.monotonic()
  age = now - float(_SIZE_CACHE.get("ts") or 0)
  if refresh or age > _SIZE_TTL:
    _refresh_size_cache_async()
  pending = bool(_SIZE_CACHE.get("computing")) or age > _SIZE_TTL
  return {"ok": True, "size_mb": float(_SIZE_CACHE.get("size_mb") or 0), "pending": pending}


def osm_panel_custom() -> dict[str, Any]:
  prog = osm_download_progress()
  size = osm_map_size_mb(refresh=bool(prog.get("downloading")))
  try:
    from openpilot.common.params import Params
    values = _osm_param_values(Params())
  except Exception:
    values = {}
  return {"ok": True, "size": size, "progress": prog, "values": values}


def osm_delete_maps() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return {"ok": True, "dev_pc": True}
  try:
    from openpilot.common.params import Params
    Params().put_bool("OsmDbDelete", True, block=True)
    _SIZE_CACHE["ts"] = 0.0
    _refresh_size_cache_async()
    return {"ok": True}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
