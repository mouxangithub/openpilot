"""OSM offline maps (Settings → OSM / mapd)."""

from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

import requests

from openpilot.common.params import Params

_REGION_URLS = {
  "Country": "https://raw.githubusercontent.com/pfeiferj/openpilot-mapd/main/nation_bounding_boxes.json",
  "State": "https://raw.githubusercontent.com/pfeiferj/openpilot-mapd/main/us_states_bounding_boxes.json",
}


def _map_root() -> Path:
  try:
    from openpilot.common.hardware.hw import Paths

    return Path(Paths.mapd_root()) / "offline"
  except Exception:
    return Path("/data/media/0/osm/offline")


def _shm_params(params: Params) -> Params:
  if platform.system() != "Darwin":
    try:
      return Params("/dev/shm/params")
    except Exception:
      pass
  return params


def _map_size_mb() -> float:
  root = _map_root()
  if not root.exists():
    return 0.0
  total = 0
  for dirpath, _dirnames, filenames in os.walk(root):
    for name in filenames:
      try:
        total += os.path.getsize(os.path.join(dirpath, name))
      except OSError:
        pass
  return round(total / (1024 ** 2), 2)


def get_osm_status(params: Params | None = None) -> dict[str, Any]:
  """OSM map download state, region selection, mapd version."""
  params = params or Params()
  mem = _shm_params(params)
  downloading = bool(mem.get("OSMDownloadLocations"))
  progress = mem.get("OSMDownloadProgress")
  if isinstance(progress, bytes):
    try:
      progress = json.loads(progress.decode(errors="replace"))
    except Exception:
      progress = None

  return {
    "ok": True,
    "mapd_version": params.get("MapdVersion"),
    "country_code": params.get("OsmLocationName"),
    "country_title": params.get("OsmLocationTitle"),
    "state_code": params.get("OsmStateName"),
    "state_title": params.get("OsmStateTitle"),
    "osm_local": params.get_bool("OsmLocal") if params.get("OsmLocal") is not None else None,
    "downloaded_date": params.get("OsmDownloadedDate"),
    "db_update_pending": params.get_bool("OsmDbUpdatesCheck"),
    "downloading": downloading,
    "download_progress": progress,
    "maps_size_mb": _map_size_mb(),
    "map_path": str(_map_root()),
    "hint": "select_osm_region + trigger_osm_download while offroad with WiFi.",
  }


def list_osm_regions(region_type: str = "Country") -> dict[str, Any]:
  """List selectable OSM countries or US states (same source as on-device UI)."""
  region_type = region_type.strip().title()
  if region_type not in _REGION_URLS:
    return {"ok": False, "error": "region_type must be Country or State"}
  try:
    data = requests.get(_REGION_URLS[region_type], timeout=15).json()
    regions = sorted(
      [{"code": code, "title": info.get("full_name", code)} for code, info in data.items()],
      key=lambda x: x["title"],
    )
    if region_type == "State":
      regions.insert(0, {"code": "All", "title": "All states (~6.0 GB)"})
    return {"ok": True, "region_type": region_type, "regions": regions, "count": len(regions)}
  except Exception as e:
    return {"ok": False, "error": str(e)}


def select_osm_region(
  params: Params,
  *,
  country_code: str = "",
  country_title: str = "",
  state_code: str = "",
  state_title: str = "",
) -> dict[str, Any]:
  """Set OsmLocation* / OsmState* params (does not start download)."""
  country_code = str(country_code or "").strip()
  if not country_code:
    for key in (
      "OsmLocationName", "OsmLocationTitle", "OsmStateName", "OsmStateTitle",
      "OsmLocal", "OsmDownloadedDate",
    ):
      try:
        params.remove(key)
      except Exception:
        pass
    return {"ok": True, "cleared": True}

  if not country_title:
    listed = list_osm_regions("Country")
    if listed.get("ok"):
      country_title = next((r["title"] for r in listed["regions"] if r["code"] == country_code), country_code)

  params.put_bool("OsmLocal", True)
  params.put("OsmLocationName", country_code)
  params.put("OsmLocationTitle", country_title or country_code)

  if country_code == "US" and state_code:
    state_code = str(state_code).strip()
    if not state_title:
      listed = list_osm_regions("State")
      if listed.get("ok"):
        state_title = next((r["title"] for r in listed["regions"] if r["code"] == state_code), state_code)
    params.put("OsmStateName", state_code)
    params.put("OsmStateTitle", state_title or state_code)
  elif country_code != "US":
    for key in ("OsmStateName", "OsmStateTitle"):
      try:
        params.remove(key)
      except Exception:
        pass

  return {"ok": True, "status": get_osm_status(params)}


def trigger_osm_download(params: Params) -> dict[str, Any]:
  if not params.get("OsmLocationName"):
    return {"ok": False, "error": "Select a country first (select_osm_region)"}
  params.put_bool("OsmDbUpdatesCheck", True)
  return {"ok": True, "hint": "Download starts via mapd; poll get_osm_status.", "status": get_osm_status(params)}


def cancel_osm_download(params: Params) -> dict[str, Any]:
  """Best-effort cancel in-progress OSM download (clears shm queue + pending flag)."""
  mem = _shm_params(params)
  had = bool(mem.get("OSMDownloadLocations"))
  try:
    mem.remove("OSMDownloadLocations")
  except Exception:
    pass
  try:
    mem.remove("OSMDownloadProgress")
  except Exception:
    pass
  params.put_bool("OsmDbUpdatesCheck", False)
  return {"ok": True, "cancelled": had, "status": get_osm_status(params)}


def delete_osm_maps(params: Params) -> dict[str, Any]:
  root = _map_root()
  if root.exists():
    shutil.rmtree(root, ignore_errors=True)
  for key in ("OsmDownloadedDate", "OsmLocal", "OsmLocationName", "OsmLocationTitle", "OsmStateName", "OsmStateTitle"):
    try:
      params.remove(key)
    except Exception:
      pass
  return {"ok": True, "maps_size_mb": _map_size_mb()}
