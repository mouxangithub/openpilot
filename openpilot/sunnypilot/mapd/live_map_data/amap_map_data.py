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


# Amap Web Service API.
#
# Endpoint versions, checked against the live docs:
#
#   * Geocoding is v3-only, and `/v3/geocode/geo` and `/v3/geocode/regeo` are NOT
#     two versions of one thing - they are two different functions:
#       - `/v3/geocode/geo`   地址 -> 坐标, REQUIRES an `address` string.
#       - `/v3/geocode/regeo` 坐标 -> 地址, REQUIRES `location`.
#     We hold vehicle coordinates, never a street address, so `geo` is unusable
#     here and `regeo` is the only correct choice. Amap has never shipped a v5
#     geocoding endpoint - the v5 namespace covers 路径规划2.0 and AOI only, so a
#     `/v5/geocode/...` URL returns SERVICE_NOT_AVAILABLE. Do not "upgrade" it.
#     (Third-party posts claiming `/v5/geocode/geo` exists are wrong.)
#
#     Note: endpoint existence cannot be probed without a key. The auth gate runs
#     BEFORE routing, so `/v3/geocode/<anything>` - real or not - answers
#     INVALID_USER_KEY; only a wrong *major version* (`/v9/...`) answers
#     SERVICE_NOT_AVAILABLE. Verify against the docs, not with a live probe.
#
#   * driving is on 路径规划2.0 `/v5/direction/driving`. v3's
#     `extensions=base|all` was replaced by `show_fields` (legal values for
#     driving: cost, navi, cities, polyline, tmcs), and v5 returns
#     `step_distance`/`road_name` instead of `distance`/`road`.
#
# One consequence has to be stated plainly: **neither version's documentation lists
# a roadmap speed field.** The speed-limit path reads `steps[].speed` (kph) from v3,
# a field that is not in the current v3 response table; Amap's road speed is only
# documented on the Android navigation SDK (`AMapNaviTrafficFacilityInfo.limitSpeed`),
# not on any Web Service endpoint. So the driving call is made against v5 - the
# current, actively documented version - with `show_fields` requesting everything
# that could plausibly carry a limit. The parser then reads both generations' names
# and treats a missing speed as "no limit known" rather than guessing, which is
# exactly how the code behaved before, just on a retired endpoint.
#
# Yes, there is a trade-off: if the undocumented v3 `speed` field did work, moving to
# v5 loses it. That is why `limits_ever_seen` exists in the diagnostics - it makes it
# immediately observable whether the speed path produces anything at all, instead of
# silently reporting 0 forever.
#
# Everything is wrapped defensively: a malformed or partial response must never take
# down mapd, it must simply leave the previous values in place.
AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/regeo"
AMAP_DIRECTION_URL = "https://restapi.amap.com/v5/direction/driving"

# Driving strategy for v5. 32 = 高德推荐, the documented default and the value the
# Amap app itself uses. (v3 used a different numbering entirely, where 0 was the
# default and 10-20 were recommended.)
AMAP_DRIVING_STRATEGY = "32"

# All optional v5 result groups. Requesting them all is deliberate: one of them may
# carry a speed field that the documentation does not enumerate, and the cost of
# asking is a slightly larger response.
AMAP_DRIVING_SHOW_FIELDS = "cost,navi,cities,polyline,tmcs"


# Amap reports failures as HTTP 200 with {"status":"0","infocode":"...","info":"..."}.
# Grouping them by cause lets us stop hammering a key that cannot recover, which the
# previous "status != 1 -> return" silently did at the full refresh rate forever.
AMAP_INFO_OK = "10000"

# Permanent for this session: retrying cannot help, so back off hard and say why.
AMAP_FATAL_INFOCODES: frozenset[str] = frozenset({
  "10001",  # INVALID_USER_KEY          - key wrong or expired
  "10002",  # SERVICE_NOT_AVAILABLE     - no permission for this service
  "10012",  # INSUFFICIENT_PRIVILEGES   - service refused
  "10013",  # USER_KEY_RECYCLED         - key deleted
  "10026",  # INVALID_REQUEST           - account banned
  "10041",  # NO_EFFECTIVE_INTERFACE    - interface permission expired
  "40000",  # QUOTA_PLAN_RUN_OUT        - balance exhausted
  "40002",  # SERVICE_EXPIRED           - purchased service expired
  "40003",  # ABROAD_QUOTA_PLAN_RUN_OUT - overseas balance exhausted
  "10009",  # USERKEY_PLAT_NOMATCH      - key is for a different platform
  "10005",  # INVALID_USER_IP           - source IP not whitelisted
  "10006",  # INVALID_USER_DOMAIN       - bound domain invalid
})

# Transient: rate limiting. Short backoff so we resume once the window rolls over.
AMAP_THROTTLE_INFOCODES: frozenset[str] = frozenset({
  "10003",  # DAILY_QUERY_OVER_LIMIT      - daily quota (reseeds at 00:00)
  "10004",  # ACCESS_TOO_FREQUENT         - per-minute quota
  "10010",  # IP_QUERY_OVER_LIMIT
  "10014",  # QPS_HAS_EXCEEDED_THE_LIMIT
  "10015",  # GATEWAY_TIMEOUT
  "10016",  # SERVER_IS_BUSY
  "10019",  # CQPS_HAS_EXCEEDED_THE_LIMIT
  "10020",  # CKQPS_HAS_EXCEEDED_THE_LIMIT
  "10021",  # CUQPS_HAS_EXCEEDED_THE_LIMIT
  "10029",  # ABROAD_DAILY_QUERY_OVER_LIMIT
  "10044",  # USER_DAILY_QUERY_OVER_LIMIT
  "10045",  # USER_ABROAD_DAILY_QUERY_OVER_LIMIT
})

# Not a fault: the request was fine, there is simply no data for this position.
# Logging these at warning level every refresh would be noise.
AMAP_DATA_INFOCODES: frozenset[str] = frozenset({
  "20011",  # INSUFFICIENT_ABROAD_PRIVILEGES - outside China without overseas rights
  "20800",  # OUT_OF_SERVICE                 - planning point outside mainland China
  "20801",  # NO_ROADS_NEARBY                - no road near the planning point
  "20802",  # ROUTE_FAIL                     - road connectivity failure
  "20803",  # OVER_DIRECTION_RANGE           - origin/destination too far apart
})

AMAP_FATAL_BACKOFF_SEC = 600.0    # 10 min: long enough to stop the churn, short
                                  # enough to pick up a fixed key without a restart
AMAP_THROTTLE_BACKOFF_SEC = 60.0

# The error strings a user would act on, surfaced through AmapLastError.
AMAP_INFO_HINTS = {
  "10001": "Amap API key invalid or expired",
  "10002": "Amap key has no permission for this service (needs a Web Service key)",
  "10003": "Amap daily quota exceeded",
  "10004": "Amap rate limit hit (too many requests per minute)",
  "10005": "Amap source IP not in the key's whitelist",
  "10006": "Amap bound domain invalid",
  "10009": "Amap key is bound to a different platform (needs a Web Service key)",
  "10012": "Amap key lacks privileges for this service",
  "10013": "Amap key was deleted",
  "10026": "Amap account is banned",
  "10041": "Amap interface permission expired",
  "40000": "Amap quota balance exhausted",
  "40002": "Amap purchased service expired",
}

# Amap Web API uses GCJ-02 coordinates; openpilot GPS is WGS-84.
WGS84_A = 6378137.0
WGS84_EE = 0.00669342162296594323

# Curve-speed derivation from the driving polyline.
#
# Amap's polyline arrives as "lng,lat;lng,lat;..." in GCJ-02. Only the *shape* is
# used, and a GCJ-02 offset is a smooth local translation, so it cancels out of a
# second derivative - no inverse transform is needed to measure curvature. (The
# repo has no gcj02->wgs84 routine; adding one just for this would be needless.)
CURVE_LOOKAHEAD_M = 500.0        # only look this far ahead
CURVE_MIN_SEGMENT_M = 3.0        # ignore polyline vertices closer than this
CURVE_LAT_ACCEL_MAX = 1.8        # m/s^2 comfortable lateral acceleration
CURVE_MIN_SPEED_KPH = 20.0       # never plan below this; keeps the result sane
CURVE_MAX_SPEED_KPH = 130.0      # effectively "no curve constraint"
CURVE_MIN_VERTICES = 3           # need at least this many usable points
CURVE_POLYLINE_MAX_POINTS = 2000  # guard against a pathological response


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


def _as_float(value, default: float = 0.0) -> float:
  """Coerce an Amap value (string or number) to float.

  Amap returns numbers as strings, and uses an empty array ``[]`` for "absent"
  rather than null, so a bare ``float()`` is not safe on any of these fields.
  """
  if isinstance(value, bool) or value is None:
    return default
  if isinstance(value, (int, float)):
    return float(value)
  try:
    return float(str(value).strip())
  except (ValueError, TypeError):
    return default


def _as_int(value, default: int = 0) -> int:
  return int(_as_float(value, float(default)))


def _as_text(value, default: str = "") -> str:
  """Amap returns ``[]`` (an empty list) wherever a string field is absent."""
  if value is None:
    return default
  if isinstance(value, str):
    return value
  if isinstance(value, (list, tuple)):
    # A populated list is Amap's "multiple values" form; join them.
    return ";".join(str(v) for v in value if isinstance(v, (str, int, float)))
  return str(value)


# ---- response shape helpers ---------------------------------------------- #
#
# v3 and v5 name the same ideas differently (v3: distance/road/extensions,
# v5: step_distance/road_name/show_fields), and the nesting differs too - v5 nests
# `route.paths` one level deeper than v3. These helpers accept either generation so
# the parser does not care which one answered.

def _extract_steps(path: dict) -> list[dict]:
  """Return the step list of a path, tolerating both nesting styles."""
  steps = path.get("steps")
  if isinstance(steps, list):
    return [s for s in steps if isinstance(s, dict)]
  if isinstance(steps, dict):
    # A single step delivered as an object rather than a list of one.
    return [steps]
  return []


def _step_speed_kph(step: dict) -> float:
  """Road speed limit of a step, in kph, or 0.0 when absent.

  Amap documents no road-speed field on either the v3 or the v5 driving response, so
  several plausible names are tried rather than assuming one. `speed` is what the
  original code read; `limit_speed`/`speed_limit` match the spelling Amap uses for the
  same concept on its navigation SDK.
  """
  for key in ("speed", "limit_speed", "speed_limit", "limitSpeed"):
    value = _as_float(step.get(key), 0.0)
    if value > 0:
      return value
  return 0.0


def _step_distance_m(step: dict) -> float:
  """Length of a step in metres. v5 names it `step_distance`, v3 `distance`."""
  for key in ("step_distance", "distance"):
    value = _as_float(step.get(key), 0.0)
    if value > 0:
      return value
  return 0.0


def _http_get_json(url: str, timeout: float = 5.0) -> dict | None:
  try:
    with urllib.request.urlopen(url, timeout=timeout) as response:
      data = response.read().decode("utf-8")
      parsed = json.loads(data)
      return parsed if isinstance(parsed, dict) else None
  except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
    cloudlog.warning(f"amap_map_data: HTTP request failed: {e}")
    return None


class AmapMapData(BaseMapData):
  """Live map data provider backed by the Amap (Gaode) Web API.

  Requires the ``AmapApiKey`` param to be set. The provider is selected by
  ``mapd_manager`` when ``AmapMapDataEnabled`` is true and a key is present.

  Notes:
    - GPS position from ``liveLocationKalman`` is WGS-84; Amap expects
      GCJ-02, so we convert before every request.
    - Road speed limits returned by Amap are in kph and converted to m/s.
    - Requests are cached for a few seconds to stay within the free-tier
      quota and to avoid blocking the 1 Hz ``mapd_manager`` tick.
    - Two optional features are gated by their own params and default off:
      ``AmapCurveSpeedEnabled`` (curve speed from the route polyline) and
      ``AmapTrafficLightHintEnabled`` (traffic-light count on the route).
      Both are display/advisory data; neither is a second speed-limit source.
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
    self._curve_speed_limit: float = 0.0        # m/s, 0 = no constraint
    self._traffic_light_count: int = -1         # -1 = unknown

    self._last_update_mono: float = 0.0
    self._last_refresh_position: tuple[float, float] | None = None
    self._cache_ttl: float = 2.0  # seconds
    self._min_movement_m: float = 20.0  # meters

    # Error handling. ``_backoff_until`` stops the retry loop when a call fails in
    # a way retrying cannot fix; ``_last_error`` is published so the user can see
    # why the provider went quiet instead of silently falling back to OSM.
    self._backoff_until: float = 0.0
    self._last_error: str = ""
    self._last_info_code: str = ""
    self._consecutive_failures: int = 0
    # Number of responses that actually contained a road speed. Amap documents no
    # such field on either driving version, so this is the one number that answers
    # "does the speed-limit source produce anything at all?" without guesswork.
    self._limits_ever_seen: int = 0

    # Feature switches, refreshed with the key.
    self._curve_speed_enabled = False
    self._traffic_light_hint_enabled = False

  # ---- configuration ----------------------------------------------------- #

  def _refresh_api_key(self) -> str | None:
    now = time.monotonic()
    if self._api_key is None or now - self._last_key_read_mono > 30.0:
      self._api_key = self.params.get("AmapApiKey")
      self._last_key_read_mono = now
      self._curve_speed_enabled = bool(self.params.get_bool("AmapCurveSpeedEnabled"))
      self._traffic_light_hint_enabled = bool(self.params.get_bool("AmapTrafficLightHintEnabled"))
    return self._api_key

  def _note_failure(self, what: str, infocode: str, info: str) -> None:
    """Record an Amap failure and decide whether retrying is worth anything."""
    self._last_info_code = infocode
    self._consecutive_failures += 1
    detail = AMAP_INFO_HINTS.get(infocode, info or "no info")
    self._last_error = f"{what}: {detail}" + (f" (infocode {infocode})" if infocode else "")

    if infocode in AMAP_FATAL_INFOCODES:
      # Retrying cannot help - back off hard so we are not sending a doomed
      # request every couple of seconds for the whole drive.
      self._backoff_until = time.monotonic() + AMAP_FATAL_BACKOFF_SEC
      cloudlog.error(f"amap_map_data: {self._last_error}; backing off "
                     f"{AMAP_FATAL_BACKOFF_SEC:.0f}s")
    elif infocode in AMAP_THROTTLE_INFOCODES:
      self._backoff_until = time.monotonic() + AMAP_THROTTLE_BACKOFF_SEC
      cloudlog.warning(f"amap_map_data: {self._last_error}; backing off "
                       f"{AMAP_THROTTLE_BACKOFF_SEC:.0f}s")
    elif infocode in AMAP_DATA_INFOCODES:
      # Legitimate "no data here" answer, not a fault.
      pass
    else:
      cloudlog.warning(f"amap_map_data: {self._last_error}")

  def _note_success(self) -> None:
    if self._consecutive_failures or self._last_error:
      cloudlog.info("amap_map_data: request succeeded again; clearing the error state")
    self._consecutive_failures = 0
    self._last_error = ""
    self._last_info_code = AMAP_INFO_OK

  def _check_response(self, result: dict | None, what: str) -> bool:
    """True when ``result`` is a usable Amap response; otherwise records why not."""
    if result is None:
      self._note_failure(what, "", "no response")
      return False
    if str(result.get("status", "")) == "1":
      return True
    self._note_failure(what, str(result.get("infocode", "")), str(result.get("info", "")))
    return False

  def get_diagnostics(self) -> dict[str, object]:
    """Provider state for the UI: why it stopped working and what it last used."""
    return {
      "error": self._last_error,
      "infocode": self._last_info_code,
      "failures": self._consecutive_failures,
      "backoff_s": max(0.0, self._backoff_until - time.monotonic()),
      "traffic_light_count": self._traffic_light_count,
      "curve_speed_ms": self._curve_speed_limit,
      "limits_ever_seen": self._limits_ever_seen,
    }

  # ---- location / scheduling --------------------------------------------- #

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
    if now < self._backoff_until:
      return False

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

    # Only advance the refresh bookkeeping when something actually came back. The
    # old code wrote these unconditionally, so a permanently failing request was
    # re-issued at the full rate forever.
    if self._consecutive_failures == 0:
      self._last_update_mono = time.monotonic()
      self._last_refresh_position = self._last_position

  # ---- regeo ------------------------------------------------------------- #

  def _update_road_name(self, api_key: str, location_str: str) -> None:
    params = {
      "key": api_key,
      "location": location_str,
      "extensions": "all",
      # Documented range is 0-3000 m with a 1000 m default. The old value of 100
      # was inside the range but below the documented default, which made the
      # nearby-road lookup needlessly narrow.
      "radius": "1000",
    }
    url = f"{AMAP_GEOCODE_URL}?{urllib.parse.urlencode(params)}"
    result = _http_get_json(url)
    if not self._check_response(result, "regeo"):
      return

    try:
      regeocode = result.get("regeocode")
      if not isinstance(regeocode, dict):
        return
      address = regeocode.get("addressComponent")
      if not isinstance(address, dict):
        return

      # The documented shape of the current road is
      # addressComponent.streetNumber.street. Older/alternative payloads have also
      # carried addressComponent.street as an object with a name. Check both, then
      # fall back to progressively coarser names so a road name is shown when one
      # of the finer ones is absent.
      road = ""
      street_number = address.get("streetNumber")
      if isinstance(street_number, dict):
        road = _as_text(street_number.get("street"))
      if not road:
        street = address.get("street")
        if isinstance(street, dict):
          road = _as_text(street.get("name"))
        else:
          road = _as_text(street)
      if not road:
        road = _as_text(address.get("township"))
      if not road:
        road = _as_text(address.get("district"))

      if road:
        self._road_name = road
        self._note_success()
    except Exception as e:
      cloudlog.warning(f"amap_map_data: failed to parse road name: {e}")

  # ---- direction --------------------------------------------------------- #

  def _update_speed_limits(self, api_key: str, location_str: str) -> None:
    paths = self._request_route(api_key, location_str)
    if not paths:
      return

    try:
      first_path = paths[0]
      if not isinstance(first_path, dict):
        return
      steps = _extract_steps(first_path)
      if not steps:
        return

      # Current road speed limit from the first step that carries one.
      # `_step_speed_kph` covers both the v3 name (`speed`) and the plausible v5
      # spellings, because Amap documents neither.
      current_speed_kph = 0.0
      for step in steps:
        current_speed_kph = _step_speed_kph(step)
        if current_speed_kph > 0:
          break
      self._speed_limit = _kph_to_ms(current_speed_kph) if current_speed_kph > 0 else 0.0
      if current_speed_kph > 0:
        self._limits_ever_seen += 1

      # Look for the next step with a lower speed limit.
      #
      # `accumulated` deliberately starts at zero and skips steps[0], i.e. the
      # reported distance begins at the end of the current step rather than at the
      # vehicle. That is the pre-existing contract and it is the conservative
      # direction (an under-reported distance makes the resolver brake earlier), so
      # it is kept as-is: this change is an API migration, not a redefinition of the
      # distance. Worth revisiting separately - since `origin` is the vehicle
      # position, step[0] has not yet been driven, so the physically accurate figure
      # is one step longer than what is reported here.
      self._next_speed_limit = 0.0
      self._next_speed_limit_distance = 0.0
      if current_speed_kph > 0:
        accumulated = 0.0
        for step in steps[1:]:
          step_speed = _step_speed_kph(step)
          accumulated += _step_distance_m(step)
          if 0 < step_speed < current_speed_kph:
            self._next_speed_limit = _kph_to_ms(step_speed)
            self._next_speed_limit_distance = accumulated
            break

      # Traffic-light count for the whole scheme (path level, not per step).
      if self._traffic_light_hint_enabled:
        count = first_path.get("traffic_lights")
        self._traffic_light_count = _as_int(count, -1) if count not in (None, "") else -1
      else:
        self._traffic_light_count = -1

      # Curve speed from the route polyline.
      #
      # `_curve_limit_from_path` works in kph, because that is the unit the rest of
      # that geometry chain and its tests use. `_curve_speed_limit` is stored in m/s
      # to match `_speed_limit` and the caller that consumes it, so convert here.
      # This assignment previously stored kph into the m/s field, which would have
      # made the value 3.6x too high the moment anything read it.
      if self._curve_speed_enabled:
        self._curve_speed_limit = _kph_to_ms(self._curve_limit_from_path(first_path))
      else:
        self._curve_speed_limit = 0.0

      # `_curve_limit_from_path` returns CURVE_MAX_SPEED_KPH for "effectively straight",
      # which is an absence of a constraint rather than a 130 kph limit. Normalise it
      # to 0 so consumers cannot mistake it for a real cap; the flag is what tells them
      # whether a curve constraint exists at all.
      if self._curve_speed_limit >= _kph_to_ms(CURVE_MAX_SPEED_KPH) - 1e-6:
        self._curve_speed_limit = 0.0

      self._note_success()
    except Exception as e:
      cloudlog.warning(f"amap_map_data: failed to parse speed limits: {e}")

  def _request_route(self, api_key: str, location_str: str) -> list:
    """Fetch a short ahead-route and return its ``paths`` list (possibly empty)."""
    # Destination is a small offset along current bearing so Amap returns a
    # route starting at the vehicle location. Without a bearing we go north.
    bearing = self._last_bearing or 0.0
    dst_lat, dst_lng = self._offset_position(self._last_position[0], self._last_position[1], 500.0, bearing)
    dst_gcj_lat, dst_gcj_lng = wgs84_to_gcj02(dst_lat, dst_lng)
    destination_str = f"{dst_gcj_lng:.6f},{dst_gcj_lat:.6f}"

    params = {
      "key": api_key,
      "origin": location_str,
      "destination": destination_str,
      # 路径规划2.0: `show_fields` replaces v3's `extensions`. Asking for every group
      # maximises the chance of receiving a speed field if one exists.
      "show_fields": AMAP_DRIVING_SHOW_FIELDS,
      "strategy": AMAP_DRIVING_STRATEGY,
    }
    url = f"{AMAP_DIRECTION_URL}?{urllib.parse.urlencode(params)}"
    result = _http_get_json(url)
    if not self._check_response(result, "direction"):
      return []

    try:
      route = result.get("route")
      if not isinstance(route, dict):
        return []
      paths = route.get("paths")
      if isinstance(paths, list):
        return paths
      # v3 nested paths under `route.paths[0]` as well, but some payloads deliver
      # `route.paths` as a single object; tolerate that too.
      return [paths] if isinstance(paths, dict) else []
    except Exception as e:
      cloudlog.warning(f"amap_map_data: failed to read route paths: {e}")
      return []

  # ---- curve speed ------------------------------------------------------- #

  def _curve_limit_from_path(self, path: dict) -> float:
    """Lowest safe curve speed (m/s) along the path polyline, 0 when unconstrained.

    The polyline is a "lng,lat;lng,lat;..." string per step. Steps are walked in
    order until the lookahead distance is covered, each polyline is resampled into
    local metres, and every triple of consecutive points is fitted to a circle.
    The minimum speed over the window wins.
    """
    try:
      steps = _extract_steps(path)
      if not steps:
        return 0.0

      points: list[tuple[float, float]] = []
      consumed = 0.0
      for step in steps:
        if not isinstance(step, dict):
          continue
        polyline = _as_text(step.get("polyline"))
        if polyline:
          points.extend(_parse_polyline(polyline))
        consumed += _step_distance_m(step)
        if points and consumed >= CURVE_LOOKAHEAD_M:
          break

      if len(points) < CURVE_MIN_VERTICES:
        return 0.0

      return _min_curve_speed_kph(points, CURVE_LOOKAHEAD_M)
    except Exception as e:
      cloudlog.warning(f"amap_map_data: failed to derive curve speed: {e}")
      return 0.0

  # ---- geometry ---------------------------------------------------------- #

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
    return _as_float(value, 0.0)

  # ---- getters ----------------------------------------------------------- #

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

  # ---- optional outputs (not part of the speed-limit contract) ----------- #

  def get_curve_speed_and_distance(self) -> tuple[float, float]:
    """``(curve_speed_ms, distance_m)``; ``(0.0, 0.0)`` when there is none.

    ``0.0`` means "no curve constraint", not "stop": the geometry chain returns
    ``CURVE_MAX_SPEED_KPH`` for a straight road and that is normalised to 0 in
    ``_update_speed_limits``. The pair is the contract - a bare speed cannot
    distinguish "straight road" from "provider without route geometry".

    The distance is fixed at ``CURVE_LOOKAHEAD_M`` rather than a per-curve figure:
    the geometry chain reports the lowest safe speed anywhere inside that window,
    not where along the polyline it occurs. Publishing a window length is honest
    about that, whereas inventing a point distance would not be. Consumers must
    treat it as "this cap applies within the next N metres".
    """
    if self._should_refresh():
      self._update_from_api()
    if not self._curve_speed_enabled or self._curve_speed_limit <= 0.0:
      return 0.0, 0.0
    return self._curve_speed_limit, CURVE_LOOKAHEAD_M

  def get_traffic_light_count(self) -> int:
    """Traffic lights on the route ahead, or -1 when unknown / the feature is off."""
    if self._should_refresh():
      self._update_from_api()
    return self._traffic_light_count if self._traffic_light_hint_enabled else -1


def _parse_polyline(polyline: str) -> list[tuple[float, float]]:
  """Parse Amap's "lng,lat;lng,lat;..." string into (lat, lng) tuples."""
  out: list[tuple[float, float]] = []
  if not polyline:
    return out
  for chunk in polyline.split(";"):
    if not chunk:
      continue
    parts = chunk.split(",")
    if len(parts) < 2:
      continue
    lng = _as_float(parts[0], float("nan"))
    lat = _as_float(parts[1], float("nan"))
    if math.isnan(lng) or math.isnan(lat):
      continue
    out.append((lat, lng))
    if len(out) >= CURVE_POLYLINE_MAX_POINTS:
      break
  return out


def _to_local_xy(points: list[tuple[float, float]],
                 ref_lat: float, ref_lng: float) -> list[tuple[float, float]]:
  """Project (lat, lng) to metres east/north of a reference point.

  A local tangent-plane approximation is plenty for a few hundred metres, and it
  keeps the polyline in GCJ-02, where the offset is a smooth translation and so
  drops out of the curvature.
  """
  m_per_deg_lat = 111132.92
  m_per_deg_lng = 111319.49 * math.cos(math.radians(ref_lat))
  return [((lng - ref_lng) * m_per_deg_lng, (lat - ref_lat) * m_per_deg_lat) for lat, lng in points]


def _min_curve_speed_kph(points: list[tuple[float, float]], lookahead_m: float) -> float:
  """Lowest safe speed (kph) over the first ``lookahead_m`` of the polyline.

  Returns CURVE_MAX_SPEED_KPH when the road is effectively straight.
  """
  if len(points) < CURVE_MIN_VERTICES:
    return CURVE_MAX_SPEED_KPH

  xy = _to_local_xy(points, points[0][0], points[0][1])

  # Drop near-duplicate vertices; they make the circumcircle degenerate.
  cleaned: list[tuple[float, float]] = [xy[0]]
  for x, y in xy[1:]:
    px, py = cleaned[-1]
    if math.hypot(x - px, y - py) >= CURVE_MIN_SEGMENT_M:
      cleaned.append((x, y))
  if len(cleaned) < CURVE_MIN_VERTICES:
    return CURVE_MAX_SPEED_KPH

  best_kph = CURVE_MAX_SPEED_KPH
  travelled = 0.0
  for i in range(len(cleaned) - 2):
    ax, ay = cleaned[i]
    bx, by = cleaned[i + 1]
    cx, cy = cleaned[i + 2]
    travelled += math.hypot(bx - ax, by - ay)
    if travelled > lookahead_m:
      break

    # Circumradius of the triangle; a straight stretch gives a huge radius.
    a = math.hypot(cx - bx, cy - by)
    b = math.hypot(cx - ax, cy - ay)
    c = math.hypot(bx - ax, by - ay)
    if a <= 0.0 or b <= 0.0 or c <= 0.0:
      continue
    area2 = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
    if area2 <= 1e-9:
      continue  # collinear: no curvature to speak of
    radius = (a * b * c) / (2.0 * area2)
    if radius <= 1.0:
      continue

    # v = sqrt(a_lat * R), clamped into a sane band.
    kph = math.sqrt(CURVE_LAT_ACCEL_MAX * radius) * 3.6
    kph = max(CURVE_MIN_SPEED_KPH, min(CURVE_MAX_SPEED_KPH, kph))
    best_kph = min(best_kph, kph)

  return best_kph
