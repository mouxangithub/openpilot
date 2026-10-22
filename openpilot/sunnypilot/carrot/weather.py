"""Live weather for the weather-conditioned driving offsets.

StarPilot asks Open-Meteo for the current conditions while driving and turns
the answer into the four offsets that lengthen the follow time, widen the
stopped gap and lower the accel / lateral ceilings. This fork had the offsets
and the classifier but no source for the state, so the feature could only be
driven by hand-written params - which in practice meant it never ran.

This module is the source. It is deliberately pure: no Params, no threads, no
clock of its own. `WeatherPoller.tick()` takes the time and the position and
returns the reading the caller should persist; the caller does the writing.
That keeps every decision replayable in a test and keeps the network out of
anything with a deadline.

Two rules shape the state machine, both from StarPilot:

  * a reading is reused for `interval_s`, because weather does not change
    between two green lights;
  * a reading is discarded early once the car has moved `max_cache_distance_km`,
    because a cached answer is about the place it was asked at.

A failed request is retried after `retry_interval_s` rather than after the
full interval: no signal in a tunnel should not cost a quarter of an hour of
stale weather in the rain.
"""
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass

from openpilot.selfdrive.controls.lib.weather_offsets import state_from_wmo_code

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_S = 10.0
DEFAULT_INTERVAL_S = 900.0      # 15 min, matching StarPilot's CHECK_INTERVAL
DEFAULT_RETRY_INTERVAL_S = 60.0
DEFAULT_MAX_CACHE_DISTANCE_KM = 25.0
USER_AGENT = "openpilot-carrot-weather/1.0"


def _finite(value) -> bool:
  return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class Reading:
  """One successful weather answer, with where and when it was asked."""

  state: str
  code: int
  latitude: float
  longitude: float
  at: float


def usable_position(latitude, longitude) -> tuple[float, float] | None:
  """(lat, lon) as floats, or None when there is nothing worth asking about.

  Rejects the same two things `gps_sources` rejects - non-finite coordinates
  and the null island - because either one produces a confident answer about
  the Gulf of Guinea.
  """
  if not (_finite(latitude) and _finite(longitude)):
    return None
  if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
    return None
  if latitude == 0.0 and longitude == 0.0:
    return None
  return float(latitude), float(longitude)


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
  """Great-circle distance in km. Absent from stdlib, so it lives here."""
  radius_km = 6371.0088
  phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
  d_phi = phi_b - phi_a
  d_lambda = math.radians(lon_b - lon_a)
  h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
  return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(h)))


def position_from_raw(raw) -> tuple[float, float] | None:
  """A `LastGPSPosition` value as (lat, lon), or None if it is not one.

  The param is written by mapd as a JSON string, but it is read here through a
  store that may hand back bytes (a value written by the C++ side) or an
  already-decoded dict (a JSON-typed param), so all three shapes are accepted.
  An empty or unparseable value means "no fix yet", not an error.
  """
  if isinstance(raw, (bytes, bytearray)):
    raw = raw.decode("utf-8", errors="replace")
  if isinstance(raw, str):
    if not raw.strip():
      return None
    try:
      raw = json.loads(raw)
    except ValueError:
      return None
  if not isinstance(raw, dict):
    return None
  return usable_position(raw.get("latitude"), raw.get("longitude"))


def build_url(latitude: float, longitude: float) -> str:
  """The request StarPilot makes, narrowed to the one field it needs.

  `current` alone is enough: the classifier reads a single WMO code, so the
  hourly and daily blocks StarPilot also asks for would be parsed and thrown
  away. Fewer fields is also a smaller answer to decode on a car computer.
  """
  query = urllib.parse.urlencode({
    "latitude": f"{latitude:.4f}",
    "longitude": f"{longitude:.4f}",
    "current": "weather_code",
    "timezone": "UTC",
  })
  return f"{OPEN_METEO_URL}?{query}"


def fetch_open_meteo(latitude: float, longitude: float, opener=None, timeout: float = REQUEST_TIMEOUT_S) -> dict | None:
  """Ask Open-Meteo, returning the decoded payload or None.

  Never raises: this runs in a background thread whose only job is to keep a
  parameter fresh, and a caller that has to guard a network call learns to
  ignore the answer. `opener` is injectable so the tests never touch a socket.
  """
  opener = opener if opener is not None else _default_open
  try:
    payload = opener(build_url(latitude, longitude), timeout)
  except Exception:
    return None
  return payload if isinstance(payload, dict) else None


def _default_open(url: str, timeout: float) -> dict:
  request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
  with urllib.request.urlopen(request, timeout=timeout) as response:
    return json.loads(response.read().decode("utf-8", errors="replace"))


def parse_reading(payload, latitude: float, longitude: float, at: float) -> Reading | None:
  """Turn an Open-Meteo payload into a Reading, or None if it is not one.

  A 200 with an error body is a real Open-Meteo answer, so the shape is checked
  rather than assumed.
  """
  current = payload.get("current") if isinstance(payload, dict) else None
  if not isinstance(current, dict):
    return None
  code = current.get("weather_code")
  if isinstance(code, bool) or not isinstance(code, int):
    return None
  return Reading(state_from_wmo_code(code), int(code), float(latitude), float(longitude), float(at))


class WeatherPoller:
  """Decides when to ask and what changed. Does neither of them itself.

  `tick()` is the whole API. It returns a Reading when the caller should
  persist a new state, and None when it should not - which covers "not due
  yet", "no position", "the request failed" and "the weather has not changed"
  with one answer, so the caller's loop stays one line long.
  """

  def __init__(self, fetch=None, interval_s: float = DEFAULT_INTERVAL_S,
               retry_interval_s: float = DEFAULT_RETRY_INTERVAL_S,
               max_cache_distance_km: float = DEFAULT_MAX_CACHE_DISTANCE_KM):
    self._fetch = fetch if fetch is not None else fetch_open_meteo
    self._interval_s = float(interval_s)
    self._retry_interval_s = float(retry_interval_s)
    self._max_cache_distance_km = float(max_cache_distance_km)
    self.reading: Reading | None = None
    self._next_attempt: float | None = None

  @property
  def state(self) -> str:
    """The state currently believed, or "clear" before the first answer."""
    return self.reading.state if self.reading is not None else "clear"

  def tick(self, now: float, latitude, longitude) -> Reading | None:
    """Ask if due, record the answer, and report whether it is news."""
    position = usable_position(latitude, longitude)
    if position is None or not self._due(now, position):
      return None

    payload = self._fetch(position[0], position[1])
    reading = parse_reading(payload, position[0], position[1], now) if payload is not None else None
    if reading is None:
      self._next_attempt = now + self._retry_interval_s
      return None

    self._next_attempt = now + self._interval_s
    previous = self.reading
    self.reading = reading
    if previous is not None and previous.state == reading.state:
      return None
    return reading

  def _due(self, now: float, position: tuple[float, float]) -> bool:
    if self._next_attempt is None:
      return True
    if now >= self._next_attempt:
      return True
    # Still inside the timer, so only a long drive invalidates what we hold.
    reading = self.reading
    if reading is None:
      return False
    moved_km = haversine_km(reading.latitude, reading.longitude, position[0], position[1])
    return moved_km > self._max_cache_distance_km
