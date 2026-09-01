#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import math
import platform
import os
import glob
import shutil
from datetime import datetime

from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.selfdrived.alertmanager import set_offroad_alert
from openpilot.sunnypilot.mapd.live_map_data.osm_map_data import OsmMapData
from openpilot.common.hardware.hw import Paths
from openpilot.sunnypilot.mapd import MAPD_PATH
from openpilot.sunnypilot.mapd.mapd_installer import VERSION, update_installed_version
from openpilot.sunnypilot.mapd.china_provinces import CHINA_NATION_REF, get_province_bbox

# PFEIFER - MAPD {{
params = Params()
mem_params = Params("/dev/shm/params") if platform.system() != "Darwin" else params
# }} PFEIFER - MAPD


def get_files_for_cleanup() -> list[str]:
  paths = [
    f"{Paths.mapd_root()}/db",
    f"{Paths.mapd_root()}/v*"
  ]
  files_to_remove = []
  for path in paths:
    if os.path.exists(path):
      files = glob.glob(path + '/**', recursive=True)
      files_to_remove.extend(files)
  # check for version and mapd files
  if not os.path.isfile(MAPD_PATH):
    files_to_remove.append(MAPD_PATH)
  return files_to_remove


def cleanup_old_osm_data(files_to_remove: list[str]) -> None:
  for file in files_to_remove:
    # Remove trailing slash if path is file
    if file.endswith('/') and os.path.isfile(file[:-1]):
      file = file[:-1]
    # Try to remove as file or symbolic link first
    if os.path.islink(file) or os.path.isfile(file):
      os.remove(file)
    elif os.path.isdir(file):  # If it's a directory
      shutil.rmtree(file, ignore_errors=False)


def clear_downloaded_maps() -> None:
  """Deletes downloaded OSM map data and resets params."""
  path = f"{Paths.mapd_root()}/offline"
  if os.path.exists(path):
    shutil.rmtree(path, ignore_errors=True)

  for param in ("OsmDownloadedDate", "OsmLocal", "OsmLocationName", "OsmLocationTitle",
                "OsmStateName", "OsmStateTitle"):
    params.remove(param)

  cloudlog.info("mapd: downloaded maps cleared")


def request_refresh_osm_location_data(nations: list[str], states: list[str] | None = None) -> None:
  params.put("OsmDownloadedDate", str(datetime.now().timestamp()), block=True)
  params.put_bool("OsmDbUpdatesCheck", False, block=True)

  osm_download_locations = {
    "nations": nations,
    "states": states or []
  }

  print(f"Downloading maps for {json.dumps(osm_download_locations)}")
  mem_params.put("OSMDownloadLocations", osm_download_locations, block=True)


def filter_nations_and_states(nations: list[str], states: list[str] | None = None) -> tuple[list[str], list[str]]:
  """Filters and prepares nation and state data for OSM map download.

  If the nation is 'US' and a specific state is provided, the nation 'US' is removed from the list.
  If the nation is 'US' and the state is 'All', the 'All' is removed from the list.
  The idea behind these filters is that if a specific state in the US is provided,
  there's no need to download map data for the entire US. Conversely,
  if the state is unspecified (i.e., 'All'), we intend to download map data for the whole US,
  and 'All' isn't a valid state name, so it's removed.

  Parameters:
  nations (list): A list of nations for which the map data is to be downloaded.
  states (list, optional): A list of states for which the map data is to be downloaded. Defaults to None.

  Returns:
  tuple: Two lists. The first list is filtered nations and the second list is filtered states.
  """

  if "US" in nations and states and not any(x.lower() == "all" for x in states):
    # If a specific state in the US is provided, remove 'US' from nations
    nations.remove("US")
  elif "US" in nations and states and any(x.lower() == "all" for x in states):
    # If 'All' is provided as a state (case invariant), remove those instances from states
    states = [x for x in states if x.lower() != "all"]
  elif "US" not in nations and states and any(x.lower() == "all" for x in states):
    states.remove("All")
  return nations, states or []


# mapd v1.12.0 quantises bboxes to 2 degree tiles. When downloading a CUSTOM
# bbox (Chinese provinces) it writes per-location totals but leaves the top-level
# progress.TotalFiles at 0 because CUSTOM is not in STATE_BOXES. Replicate the
# tile count here so UI progress bars have a meaningful denominator.
GROUP_AREA_BOX_DEGREES = 2


def _count_mapd_tiles(bounds: dict[str, float]) -> int:
  """Replicate mapd v1.12.0 countFilesForBounds()."""
  min_lat = int(math.floor(bounds["min_lat"] / GROUP_AREA_BOX_DEGREES)) * GROUP_AREA_BOX_DEGREES
  min_lon = int(math.floor(bounds["min_lon"] / GROUP_AREA_BOX_DEGREES)) * GROUP_AREA_BOX_DEGREES
  max_lat = int(math.floor(bounds["max_lat"] / GROUP_AREA_BOX_DEGREES)) * GROUP_AREA_BOX_DEGREES
  max_lon = int(math.floor(bounds["max_lon"] / GROUP_AREA_BOX_DEGREES)) * GROUP_AREA_BOX_DEGREES

  if bounds["max_lat"] > max_lat:
    max_lat += GROUP_AREA_BOX_DEGREES
  if bounds["max_lon"] > max_lon:
    max_lon += GROUP_AREA_BOX_DEGREES

  lat_tiles = (max_lat - min_lat) // GROUP_AREA_BOX_DEGREES
  lon_tiles = (max_lon - min_lon) // GROUP_AREA_BOX_DEGREES
  return max(0, int(lat_tiles * lon_tiles))


def _fix_custom_download_progress() -> None:
  """Backfill total_files for CUSTOM bbox downloads where mapd leaves it at 0."""
  total_tiles = 0
  bounds_json = mem_params.get("OSMDownloadBounds")
  if bounds_json:
    try:
      bounds = json.loads(bounds_json)
      total_tiles = _count_mapd_tiles(bounds)
    except Exception:
      pass

  progress = params.get("OSMDownloadProgress")
  if not isinstance(progress, dict):
    return

  if total_tiles <= 0:
    custom_details = progress.get("location_details", {}).get("CUSTOM", {})
    total_tiles = custom_details.get("location_total_files", 0)

  if total_tiles <= 0:
    return

  if progress.get("total_files"):
    return

  progress["total_files"] = total_tiles
  location_details = progress.setdefault("location_details", {})
  custom_details = location_details.setdefault("CUSTOM", {})
  custom_details["location_total_files"] = total_tiles
  params.put("OSMDownloadProgress", progress, block=True)


def update_osm_db() -> None:
  if params.get_bool("OsmDbUpdatesCheck"):
    cleanup_old_osm_data(get_files_for_cleanup())
    country = params.get("OsmLocationName", return_default=True)
    state = params.get("OsmStateName", return_default=True)
    cn_bbox = get_province_bbox(state) if country == CHINA_NATION_REF else None
    if cn_bbox is not None:
      # Chinese provinces are not in mapd v1.12.0's built-in STATE_BOXES, so route the
      # selection through OSMDownloadBounds (the bbox-based escape hatch in mapd's
      # download.go). mapd downloads exactly this bbox and labels the job 'CUSTOM'.
      #
      # mapd v1.12.0 has a quirk: DownloadIfTriggered() initialises
      # progress.LocationDetails as an empty map, and DownloadBounds(_, "CUSTOM")
      # then dereferences progress.LocationDetails["CUSTOM"].TotalFiles unguarded.
      # If we set OSMDownloadBounds without also seeding a "CUSTOM" entry through
      # the locations branch, mapd nil-pointer-panics. Seed it via OSMDownloadLocations:
      # an unknown state code logs a harmless warning, but AddLocationDetailsToProgress
      # creates the LocationDetails entry the bounds branch needs.
      params.put("OsmDownloadedDate", str(datetime.now().timestamp()), block=True)
      params.put_bool("OsmDbUpdatesCheck", False, block=True)
      mem_params.put("OSMDownloadLocations", {"nations": [], "states": ["CUSTOM"]}, block=True)
      mem_params.put("OSMDownloadBounds", json.dumps(cn_bbox), block=True)

      # mapd writes OSMDownloadProgress to persistent params but leaves total_files at 0.
      # Seed the totals now so the UI progress bar works during and after the download.
      total_tiles = _count_mapd_tiles(cn_bbox)
      progress = params.get("OSMDownloadProgress") or {}
      if not isinstance(progress, dict):
        progress = {}
      progress["total_files"] = total_tiles
      progress["downloaded_files"] = progress.get("downloaded_files", 0)
      progress["locations_to_download"] = ["CUSTOM"]
      location_details = progress.setdefault("location_details", {})
      custom_details = location_details.setdefault("CUSTOM", {})
      custom_details["location_total_files"] = total_tiles
      custom_details["location_downloaded_files"] = custom_details.get("location_downloaded_files", 0)
      params.put("OSMDownloadProgress", progress, block=True)

      print(f"Downloading map for CN.{state}: {json.dumps(cn_bbox)}")
    else:
      filtered_nations, filtered_states = filter_nations_and_states([country], [state])
      request_refresh_osm_location_data(filtered_nations, filtered_states)

  if not mem_params.get("OSMDownloadBounds"):
    mem_params.put("OSMDownloadBounds", "", block=True)

  if not mem_params.get("LastGPSPosition"):
    mem_params.put("LastGPSPosition", "{}", block=True)


def main_thread():
  update_installed_version(VERSION, params)
  config_realtime_process([0, 1, 2, 3], 5)

  rk = Ratekeeper(1, print_delay_threshold=None)
  live_map_sp = OsmMapData()

  # Create folder needed for OSM
  try:
    os.mkdir(Paths.mapd_root())
  except FileExistsError:
    pass
  except PermissionError:
    cloudlog.exception(f"mapd: failed to make {Paths.mapd_root()}")

  while True:
    show_alert = bool(get_files_for_cleanup() and params.get_bool("OsmLocal"))
    set_offroad_alert("Offroad_OSMUpdateRequired", show_alert, "This alert will be cleared when new maps are downloaded.")

    if params.get("Mapd_ClearCache"):
      clear_downloaded_maps()
      params.remove("Mapd_ClearCache")

    update_osm_db()
    _fix_custom_download_progress()
    live_map_sp.tick()
    rk.keep_time()


def main():
  main_thread()


if __name__ == "__main__":
  main()
