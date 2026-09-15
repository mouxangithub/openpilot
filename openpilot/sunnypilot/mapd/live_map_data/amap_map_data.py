#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

from openpilot.cereal import log
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.mapd.live_map_data.base_map_data import BaseMapData


AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/regeo"
AMAP_DIRECTION_URL = "https://restapi.amap.com/v3/direction/driving"

# Amap Web API uses GCJ-02 coordinates; openpilot GPS is WGS-84.
WGS84_A = 6378137.0
WGS84_EE = 0.00669342162296594323


def wgs84_to_gcj02(lat: float, lng: float) -> tuple[float, float]:
  """Convert WGS-84 latitude/longitude to GCJ-02 (Mars coordinates)."""
  if _out_of_china(lat, lng):
    return lat, lng

  dlat = _transform_lat(lng - 105.0, lat - 35.0)
  dlng = _transform_lng(lng - 105.0, lat - 35.0)
  radlat = lat / 180.0 * math.pi
  magic = math.sin(radlat)
  magic = 1 - WGS84_EE * magic * magic
  sqrtmagic = math.sqrt(magic)
  dlat = (dlat * 180.0) / ((WGS84_A * (1 - WGS84_EE)) / (magic * sqrtmagic) * math.pi)
  dlng = (dlng * 180.0) / (WGS84_A / sqrtmagic * math.cos(radlat) * math.pi)
  return lat + dlat, lng + dlng


def _transform_lat(lng: float, lat: float) -> float:
  ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
  ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
  ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
  ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
  return ret


def _transform_lng(lng: float, lat: float) -> float:
  ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
  ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
  ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
  ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
  return ret


def _out_of_china(lat: float, lng: float) -> bool:
  return lng < 72.004 or lng > 137.8347 or lat < 0.8293 or lat > 55.8271


def _kph_to_ms(kph: float) -> float:
  return kph / 3.6


def _http_get_json(url: str, timeout: float = 5.0) -> dict | None:
  try:
    with urllib.request.urlopen(url, timeout=timeout) as response:
      data = response.read().decode("utf-8")
      return json.loads(data)
  except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
    cloudlog.warning(f"amap_map_data: HTTP request failed: {e}")
    return None


class AmapMapData(BaseMapData):
  """Live map data provider backed by the Amap (Gaode) Web API.

  Requires the ``AmapApiKey`` param to be set.  The provider is selected by
  ``mapd_manager`` when ``AmapEnabled`` is true and a key is present.

  Notes:
    - GPS position from ``liveLocationKalman`` is WGS-84; Amap expects
      GCJ-02, so we convert before every request.
    - Road speed limits returned by Amap are in kph and converted to m/s.
    - Requests are cached for a few seconds to stay within the free-tier
      quota and to avoid blocking the 1 Hz ``mapd_manager`` tick.
  """

  def __init__(self):
    super().__init__()
    self.params = Params()

    self._api_key: str | None = None
    self._last_key_read_mono = 0.0

    self._last_position: tuple[float, float] | None = None
    self._last_bearing: float | None = None

    self._road_name: str = ""
    self._speed_limit: float = 0.0
    self._next_speed_limit: float = 0.0
    self._next_speed_limit_distance: float = 0.0

    self._last_update_mono: float = 0.0
    self._last_refresh_position: tuple[float, float] | None = None
    self._cache_ttl: float = 2.0  # seconds
    self._min_movement_m: float = 20.0  # meters

  def _refresh_api_key(self) -> str | None:
    now = time.monotonic()
    if self._api_key is None or now - self._last_key_read_mono > 30.0:
      self._api_key = self.params.get("AmapApiKey")
      self._last_key_read_mono = now
    return self._api_key

  def update_location(self) -> None:
    location = self.sm['liveLocationKalman']
    self.localizer_valid = (location.status == log.LiveLocationKalman.Status.valid) and location.positionGeodetic.valid

    if self.localizer_valid:
      self._last_bearing = math.degrees(location.calibratedOrientationNED.value[2])
      self._last_position = (location.positionGeodetic.value[0], location.positionGeodetic.value[1])

  def _should_refresh(self) -> bool:
    if self._last_position is None:
      return False

    if not self._refresh_api_key():
      return False

    now = time.monotonic()
    if now - self._last_update_mono < self._cache_ttl:
      return False

    if self._last_refresh_position is not None and self._distance_moved() < self._min_movement_m:
      return False

    return True

  def _distance_moved(self) -> float:
    if self._last_position is None or self._last_refresh_position is None:
      return 0.0
    # Approximate degree-to-meter conversion; accurate enough for refresh heuristics.
    lat_diff = (self._last_position[0] - self._last_refresh_position[0]) * 111320.0
    lng_diff = (self._last_position[1] - self._last_refresh_position[1]) * 111320.0 * \
               math.cos(math.radians(self._last_position[0]))
    return math.hypot(lat_diff, lng_diff)

  def _update_from_api(self) -> None:
    api_key = self._refresh_api_key()
    if not api_key:
      return

    lat, lng = self._last_position
    gcj_lat, gcj_lng = wgs84_to_gcj02(lat, lng)
    location_str = f"{gcj_lng:.6f},{gcj_lat:.6f}"

    self._update_road_name(api_key, location_str)
    self._update_speed_limits(api_key, location_str)

    self._last_update_mono = time.monotonic()
    self._last_refresh_position = self._last_position

  def _update_road_name(self, api_key: str, location_str: str) -> None:
    params = {
      "key": api_key,
      "location": location_str,
      "extensions": "all",
      "radius": "100",
    }
    url = f"{AMAP_GEOCODE_URL}?{urllib.parse.urlencode(params)}"
    result = _http_get_json(url)
    if result is None or result.get("status") != "1":
      return

    try:
      regeocode = result.get("regeocode", {})
      address = regeocode.get("addressComponent", {})
      road = address.get("street", {}).get("name", "")
      if not road:
        road = address.get("township", "")
      if not road:
        road = address.get("district", "")
      self._road_name = road
    except Exception as e:
      cloudlog.warning(f"amap_map_data: failed to parse road name: {e}")

  def _update_speed_limits(self, api_key: str, location_str: str) -> None:
    # Destination is a small offset along current bearing so Amap returns a
    # route starting at the vehicle location.  Without a bearing we go north.
    bearing = self._last_bearing or 0.0
    dst_lat, dst_lng = self._offset_position(self._last_position[0], self._last_position[1], 500.0, bearing)
    dst_gcj_lat, dst_gcj_lng = wgs84_to_gcj02(dst_lat, dst_lng)
    destination_str = f"{dst_gcj_lng:.6f},{dst_gcj_lat:.6f}"

    params = {
      "key": api_key,
      "origin": location_str,
      "destination": destination_str,
      "extensions": "all",
      "strategy": "2",  # shortest path without traffic
    }
    url = f"{AMAP_DIRECTION_URL}?{urllib.parse.urlencode(params)}"
    result = _http_get_json(url)
    if result is None or result.get("status") != "1":
      return

    try:
      route = result.get("route", {})
      paths = route.get("paths", [])
      if not paths:
        return

      steps = paths[0].get("steps", [])
      if not steps:
        return

      # Current road speed limit from the first step.
      current_speed_kph = self._parse_speed(steps[0].get("speed", ""))
      self._speed_limit = _kph_to_ms(current_speed_kph) if current_speed_kph > 0 else 0.0

      # Look for the next step with a different (lower) speed limit.
      self._next_speed_limit = 0.0
      self._next_speed_limit_distance = 0.0
      accumulated = 0.0
      for step in steps[1:]:
        step_distance = float(step.get("distance", 0))
        step_speed = self._parse_speed(step.get("speed", ""))
        accumulated += step_distance
        if 0 < step_speed < current_speed_kph:
          self._next_speed_limit = _kph_to_ms(step_speed)
          self._next_speed_limit_distance = accumulated
          break
    except Exception as e:
      cloudlog.warning(f"amap_map_data: failed to parse speed limits: {e}")

  def _offset_position(self, lat: float, lng: float, distance_m: float, bearing_deg: float) -> tuple[float, float]:
    """Return a point ``distance_m`` away at ``bearing_deg`` (clockwise from north)."""
    R = 6371000.0  # Earth radius in meters
    lat_rad = math.radians(lat)
    lng_rad = math.radians(lng)
    bearing_rad = math.radians(bearing_deg)

    new_lat_rad = math.asin(
      math.sin(lat_rad) * math.cos(distance_m / R) +
      math.cos(lat_rad) * math.sin(distance_m / R) * math.cos(bearing_rad)
    )
    new_lng_rad = lng_rad + math.atan2(
      math.sin(bearing_rad) * math.sin(distance_m / R) * math.cos(lat_rad),
      math.cos(distance_m / R) - math.sin(lat_rad) * math.sin(new_lat_rad)
    )
    return math.degrees(new_lat_rad), math.degrees(new_lng_rad)

  @staticmethod
  def _parse_speed(value: str | int | float) -> float:
    if isinstance(value, (int, float)):
      return float(value)
    try:
      return float(value)
    except (ValueError, TypeError):
      return 0.0

  def get_current_speed_limit(self) -> float:
    if self._should_refresh():
      self._update_from_api()
    return self._speed_limit

  def get_current_road_name(self) -> str:
    if self._should_refresh():
      self._update_from_api()
    return self._road_name

  def get_next_speed_limit_and_distance(self) -> tuple[float, float]:
    if self._should_refresh():
      self._update_from_api()
    return self._next_speed_limit, self._next_speed_limit_distance
