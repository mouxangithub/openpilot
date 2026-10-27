"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Mapbox Driving-Match speed limit filler, ported from StarPilot
(``starpilot/controls/lib/mapbox_speed_limit.py``).

Fills the gap left by the offline map, carrot and the vision pipeline: when
none of them has a limit for the road ahead, a Mapbox Driving-Match lookup
around the current GPS fix supplies one. All requests run on a single-worker
``ThreadPoolExecutor`` so ``plannerd``'s 10 Hz loop is never blocked; a
discarded future may still finish, but only ``update()`` publishes its result.

The two StarPilot utilities this module depended on
(``calculate_bearing_offset``, ``is_url_pingable``) have no equivalent in the
sunnypilot tree, so they are inlined here verbatim rather than adding a new
cross-fork dependency.

Params (registered in ``common/params_keys.h``):
  * ``MapboxSecretKey``  - PERSISTENT STRING, the Mapbox access token.
  * ``MapBoxRequests``   - PERSISTENT JSON ``{total_requests, max_requests, month}``.
    Monthly quota bookkeeping; the writer passes a dict and lets ``Params``
    JSON-cast it.
"""
import calendar
import json
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog

EARTH_RADIUS = 6378137  # Radius of the Earth in meters
FREE_MAPBOX_REQUESTS = 100_000
STEERING_MATCH_MAX_DEG = 45.  # |steeringAngleDeg - angleOffsetDeg| above this means the GPS bearing is not the road bearing


def _calculate_bearing_offset(latitude: float, longitude: float, current_bearing: float, distance: float) -> tuple[float, float]:
  """Great-circle forward point: ``distance`` meters from (lat, lon) along ``bearing``.

  Pure geometry, inlined from StarPilot's ``calculate_bearing_offset``. Used
  to project a point ahead of the car so the Driving-Match request covers the
  road being driven, not the road at the fix.
  """
  bearing = math.radians(current_bearing)
  lat_rad = math.radians(latitude)
  lon_rad = math.radians(longitude)

  delta = distance / EARTH_RADIUS

  new_lat = math.asin(math.sin(lat_rad) * math.cos(delta) + math.cos(lat_rad) * math.sin(delta) * math.cos(bearing))
  new_lon = lon_rad + math.atan2(math.sin(bearing) * math.sin(delta) * math.cos(lat_rad),
                                 math.cos(delta) - math.sin(lat_rad) * math.sin(new_lat))
  return math.degrees(new_lat), math.degrees(new_lon)


def _is_url_pingable(url: str) -> bool:
  """True when the host answers a HEAD (or, on 405/501, a GET) request.

  Inlined from StarPilot's ``is_url_pingable``. Runs on the worker thread
  only; a failed ping just costs the request attempt.
  """
  if not url:
    return False

  if not hasattr(_is_url_pingable, "session"):
    _is_url_pingable.session = requests.Session()  # type: ignore[attr-defined]
    _is_url_pingable.session.headers.update({"User-Agent": "sunnypilot-ping-test/1.0"})  # type: ignore[attr-defined]

  try:
    response = _is_url_pingable.session.head(url, timeout=10, allow_redirects=True)  # type: ignore[attr-defined]
    if response.status_code in (405, 501):
      response = _is_url_pingable.session.get(url, timeout=10, allow_redirects=True, stream=True)  # type: ignore[attr-defined]

    is_accessible = response.ok
    response.close()
    return is_accessible
  except (requests.exceptions.ConnectionError, requests.exceptions.SSLError):
    return False
  except requests.exceptions.RequestException as error:
    cloudlog.warning(f"mapbox_speed_limit: {error.__class__.__name__} while pinging {url}: {error}")
    return False
  except Exception as exception:
    cloudlog.warning(f"mapbox_speed_limit: unexpected error while pinging {url}: {exception}")
    return False


class MapboxSpeedLimit:
  """Async Mapbox Driving-Match speed limit provider.

  ``update()`` is called every resolver tick. It never blocks: requests are
  submitted to a single-worker executor and the finished future's result is
  collected on a later tick. While ``segment_distance > 0`` the last retrieved
  limit is reused (decaying by ``v_ego * DT_MDL`` per tick) without issuing a
  new request.
  """

  def __init__(self, params: Any):
    self.params = params
    # MapBoxRequests is a JSON param: get() already returns a dict, put() expects one.
    try:
      stored = self.params.get("MapBoxRequests")
      self.requests: dict = dict(stored) if isinstance(stored, dict) else {}
    except Exception:
      self.requests = {}
    self.requests.setdefault("total_requests", 0)
    self.requests.setdefault("max_requests", FREE_MAPBOX_REQUESTS - 28 * 100)

    self.host = "https://api.mapbox.com"
    try:
      token = self.params.get("MapboxSecretKey")
    except Exception:
      token = None
    self.token = token if token else None
    self.limit = 0.0
    self.segment_distance = 0.0
    self.future = None
    self._error_warned = False  # one-shot: avoid a log flood every frame
    self.executor = ThreadPoolExecutor(max_workers=1)
    self.session = requests.Session()
    self.session.headers.update({"Accept-Language": "en"})
    self.session.headers.update({"User-Agent": "sunnypilot-mapbox-speed-limit-retriever/1.0"})

  def reset(self) -> None:
    """Drop the in-flight request (it may still finish, but update() won't publish it) and any cached limit."""
    if self.future is not None:
      self.future.cancel()
      self.future = None
    self.limit = 0.0
    self.segment_distance = 0.0

  def shutdown(self) -> None:
    self.reset()
    self.executor.shutdown(wait=False, cancel_futures=True)
    self.session.close()

  def _request(self, position: dict, v_ego: float) -> tuple[float, float]:
    """The blocking request, run on the worker thread. Returns (limit m/s, segment distance m)."""
    if not _is_url_pingable(self.host):
      return 0.0, v_ego

    self.requests["total_requests"] += 1
    self.params.put_nonblocking("MapBoxRequests", self.requests)

    bearing = position.get("bearing")
    latitude = position.get("latitude")
    longitude = position.get("longitude")
    future_latitude, future_longitude = _calculate_bearing_offset(latitude, longitude, bearing, v_ego)
    url = f"{self.host}/matching/v5/mapbox/driving/{longitude},{latitude};{future_longitude},{future_latitude}.json"
    params = {
      "access_token": self.token,
      "annotations": "maxspeed,distance",
      "geometries": "polyline6",
      "overview": "full",
      "steps": "false",
      "radiuses": "10;10",
      "tidy": "true",
    }
    response = self.session.get(url, params=params, timeout=10)
    response.raise_for_status()
    matchings = response.json().get("matchings") or []
    if not matchings:
      return 0.0, v_ego
    legs = (matchings[0] or {}).get("legs") or []
    if not legs:
      return 0.0, v_ego

    annotation = legs[0].get("annotation") or {}
    distances = annotation.get("distance") or [v_ego]
    speeds = annotation.get("maxspeed") or []
    if not speeds:
      return 0.0, v_ego
    first = speeds[0]
    try:
      speed = float(first.get("speed")) if first.get("speed") != "none" else 0.0
    except (TypeError, ValueError):
      speed = 0.0
    if speed <= 0:
      return 0.0, v_ego
    conversion = CV.MPH_TO_MS if first.get("unit", "km/h") == "mph" else CV.KPH_TO_MS
    return speed * conversion, distances[0]

  def update(self, now, time_validated: bool, v_ego: float, gps_valid: bool, position: dict,
             steering_angle: float, angle_offset: float) -> None:
    """Advance the filler one tick. Never blocks; see class docstring."""
    if not gps_valid or not self.token or abs(steering_angle - angle_offset) >= STEERING_MATCH_MAX_DEG:
      self.reset()
      return

    # Monthly quota bookkeeping: 100k free requests minus 100 per day of the month.
    if time_validated and now.month != self.requests.get("month"):
      self.requests.update({
        "month": now.month,
        "total_requests": 0,
        "max_requests": FREE_MAPBOX_REQUESTS - calendar.monthrange(now.year, now.month)[1] * 100,
      })
    if self.requests["total_requests"] >= self.requests["max_requests"]:
      self.reset()
      return

    if self.future is not None:
      if not self.future.done():
        return  # request still in flight; do not block the caller
      future = self.future
      self.future = None
      try:
        self.limit, self.segment_distance = future.result()
      except Exception as exception:
        if not self._error_warned:
          self._error_warned = True
          cloudlog.warning(f"mapbox_speed_limit: request failed: {type(exception).__name__}: {exception}")
        self.limit, self.segment_distance = 0.0, v_ego
      return

    # No new requests below walking pace or at standstill; an already-cached
    # limit keeps being reused without decaying.
    if v_ego < 1:
      return
    if self.segment_distance > 0:
      self.segment_distance -= v_ego * DT_MDL
      return

    try:
      self.future = self.executor.submit(self._request, dict(position), v_ego)
    except RuntimeError:
      self.segment_distance = v_ego
      return
