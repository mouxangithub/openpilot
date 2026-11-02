"""
Local timezone (for on-screen display) resolution and persistent storage helper.

GPS only provides UTC (absolute time), so showing "local time in that country"
on screen requires a timezone (IANA name). The timezone is resolved by priority:

  1) app   - timezone sent by the carrot app (carrot_serv) -- most trusted
  2) wifi  - timezone received via internet (IP-based geolocation)
  3) gps   - approximate from GPS longitude (offline last resort, no DST)

The resolved timezone is applied as a /data/etc/localtime (system-read path)
symlink, and the name/source are recorded in Params. Once recorded it survives
offline reboots. A lower-priority source (gps) never overwrites a value set by
a higher-priority source (app/wifi).
"""
import json
import os
import subprocess
import urllib.request

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

LOCALTIME_PATH = "/data/etc/localtime"
ZONEINFO_DIR = "/usr/share/zoneinfo"

# Higher number = more trusted. ""(unset) is 0.
SOURCE_PRIORITY = {"": 0, "gps": 1, "wifi": 2, "app": 3}


def _valid_zone(tz: str) -> bool:
  return bool(tz) and os.path.isfile(os.path.join(ZONEINFO_DIR, tz))


def current_source(params: Params | None = None) -> str:
  params = params or Params()
  return params.get("TimezoneSource") or ""


def apply_timezone(tz: str, source: str, params: Params | None = None) -> bool:
  """Apply tz (IANA name). Ignored when the source priority is lower than the
  current one (downgrade prevention)."""
  params = params or Params()
  if not _valid_zone(tz):
    cloudlog.error(f"timezone: invalid zone '{tz}' (source={source})")
    return False

  cur = current_source(params)
  if SOURCE_PRIORITY.get(source, 0) < SOURCE_PRIORITY.get(cur, 0):
    return False  # a more trusted source already set it -> keep

  # Same timezone already? Skip rewriting the symlink (only refresh the source)
  target = os.path.join(ZONEINFO_DIR, tz)
  already = os.path.islink(LOCALTIME_PATH) and os.path.realpath(LOCALTIME_PATH) == os.path.realpath(target)
  if not already:
    try:
      os.makedirs(os.path.dirname(LOCALTIME_PATH), exist_ok=True)
      subprocess.run(["sudo", "rm", "-f", LOCALTIME_PATH], check=True)
      subprocess.run(["sudo", "ln", "-s", target, LOCALTIME_PATH], check=True)
    except subprocess.CalledProcessError:
      cloudlog.exception("timezone: failed to set /data/etc/localtime")
      return False

  params.put("TimezoneName", tz)
  params.put("TimezoneSource", source)
  cloudlog.info(f"timezone: set to {tz} (source={source})")
  return True


def timezone_from_internet(timeout: float = 5.0) -> str | None:
  """[2nd priority] When on WiFi/internet, get the IANA timezone via IP-based
  geolocation. Keyless free endpoint (ip-api.com). None on failure."""
  try:
    req = urllib.request.Request(
      "http://ip-api.com/json/?fields=status,timezone",
      headers={"User-Agent": "openpilot-timed"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
      data = json.loads(resp.read().decode())
    if data.get("status") == "success":
      tz = data.get("timezone")
      return tz if _valid_zone(tz) else None
  except Exception:
    return None
  return None


def timezone_from_gps(longitude: float) -> str:
  """[3rd priority / last resort] Approximate timezone from GPS longitude
  (Etc/GMT fixed offset, no DST). POSIX Etc/GMT sign is inverted:
  Etc/GMT-9 == UTC+9."""
  offset = int(round(longitude / 15.0))
  offset = max(-12, min(14, offset))  # Etc/GMT+12 .. Etc/GMT-14 range
  if offset == 0:
    return "Etc/GMT"
  return f"Etc/GMT{'-' if offset > 0 else '+'}{abs(offset)}"
