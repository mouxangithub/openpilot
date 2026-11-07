import math
import time


def latest_gps_source(sm) -> str | None:
  """The service with the freshest usable GPS fix, or None."""
  now = time.monotonic()
  sources = [s for s in ('gpsLocation', 'gpsLocationExternal')
             if sm.valid[s] and sm[s].hasFix and 0 <= now - sm.recv_time[s] < 2]
  return max(sources, key=lambda s: sm.logMonoTime[s]) if sources else None


MAX_LATITUDE = 85.05112878  # web-mercator limit; anything beyond is corrupt


def parse_destination_coordinate(destination) -> tuple[float, float] | None:
  """Validate a NavDestination dict, returning (longitude, latitude) or None.

  A corrupted params write (missing keys, non-numeric or out-of-range values)
  used to raise inside the routing loop every cycle; treat it as no
  destination instead (cp navd coordinate_from_param parity).
  """
  if not isinstance(destination, dict):
    return None
  try:
    lon = float(destination['longitude'])
    lat = float(destination['latitude'])
  except (KeyError, TypeError, ValueError):
    return None
  if not (math.isfinite(lat) and math.isfinite(lon) and
          abs(lat) <= MAX_LATITUDE and abs(lon) <= 180):
    return None
  return lon, lat
