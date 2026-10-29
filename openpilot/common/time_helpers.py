import datetime
import email.utils
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

MIN_DATE = datetime.datetime(year=2025, month=2, day=21)
MAX_DATE = datetime.datetime(year=2035, month=1, day=1)

# Endpoints used to bootstrap the clock when NTP is unreachable. These are
# domestic CDNs that answer even on a walled network, which is exactly the
# situation where the device has no GPS fix and NTP is blocked.
#
# Plain http, not https: the clock being bootstrapped is wrong, and a wrong
# clock fails TLS certificate validation ("certificate is not yet valid"),
# so https could not bootstrap the clock it depends on. A redirect to
# https is fine — the 301 response itself carries the endpoint's Date.
TIME_HTTP_ENDPOINTS = (
  "http://www.baidu.com",
  "http://www.aliyun.com",
  "http://www.qq.com",
)

TIME_HTTP_TIMEOUT_S = 10

# A clock that is merely slow is left to NTP; only a large backward drift
# breaks TLS against github, so that is what gets corrected here.
LARGE_DRIFT = datetime.timedelta(days=1)


def min_date():
  # on systemd systems, the default time is the systemd build time
  systemd_path = Path("/lib/systemd/systemd")
  if systemd_path.exists():
    d = datetime.datetime.fromtimestamp(systemd_path.stat().st_mtime)
    return max(MIN_DATE, d + datetime.timedelta(days=1))
  return MIN_DATE

def system_time_valid():
  return min_date() < datetime.datetime.now() < MAX_DATE


class _NoRedirect(urllib.request.HTTPRedirectHandler):
  """Stop at the 301: its Date header is all this needs, and following it
  would land on https, which a bogus clock cannot negotiate."""

  def redirect_request(self, req, fp, code, msg, headers, newurl):
    return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_time_candidates(endpoints: tuple[str, ...] = TIME_HTTP_ENDPOINTS,
                         timeout_s: int = TIME_HTTP_TIMEOUT_S) -> list[datetime.datetime]:
  """Wall times reported by each endpoint's HTTP Date header.

  Every endpoint is tried independently and failures are skipped: on the
  networks this exists for, some of them may be unreachable too.
  """
  times: list[datetime.datetime] = []
  for url in endpoints:
    try:
      req = urllib.request.Request(url, method="HEAD")
      try:
        with _OPENER.open(req, timeout=timeout_s) as resp:
          raw = resp.headers.get("Date")
      except urllib.error.HTTPError as e:
        # A redirect response is good enough; its headers are real.
        raw = e.headers.get("Date")
      if not raw:
        continue
      dt = email.utils.parsedate_to_datetime(raw)
      if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.UTC).replace(tzinfo=None)
      times.append(dt)
    except Exception:
      continue
  return times


def pick_http_time(now: datetime.datetime, candidates: list[datetime.datetime]) -> datetime.datetime | None:
  """The time to set, or None when the clock does not need correcting.

  The candidates are the endpoints' Date headers, which can disagree by a
  second or two and can be outright wrong on a captive network. The median
  of the plausible ones is used, so one bad endpoint cannot move the clock.

  Policy on direction:
  - an invalid clock (fresh boot, dead RTC) is corrected in either
    direction: nothing depends on a bogus time, and a clock in the far
    future fails the validity gate just like one in the past;
  - a valid clock is only moved forward, and only when it is behind by
    more than LARGE_DRIFT, because pulling time backwards can break
    running TLS sessions and log ordering.
  """
  plausible = [t for t in candidates if min_date() < t < MAX_DATE]
  if not plausible:
    return None

  plausible.sort()
  new_time = plausible[len(plausible) // 2]

  if not (MIN_DATE < now < MAX_DATE):
    # The clock is bogus; any plausible time is better than it.
    return new_time if abs(new_time - now) > datetime.timedelta(seconds=30) else None
  if new_time < now:
    return None
  return new_time if new_time - now > LARGE_DRIFT else None


def set_system_time(new_time: datetime.datetime) -> None:
  """Set the system clock. Needs root, so it is a no-op off the device."""
  if os.name != "posix":
    raise OSError("setting the system clock is only supported on posix")
  subprocess.run(
    ["date", "-s", new_time.strftime("%Y-%m-%d %H:%M:%S")],
    env={"TZ": "UTC", "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
    check=True,
  )


def sync_system_time_http(endpoints: tuple[str, ...] = TIME_HTTP_ENDPOINTS,
                          timeout_s: int = TIME_HTTP_TIMEOUT_S,
                          candidates: list[datetime.datetime] | None = None,
                          now: datetime.datetime | None = None) -> bool:
  """Bootstrap the clock from HTTP Date headers.

  Returns whether the clock is valid after the attempt. Used by the update
  daemon, which cannot run while the clock is bogus, and whose git fetches
  fail TLS when the clock is months behind.
  """
  if candidates is None:
    candidates = http_time_candidates(endpoints, timeout_s)
  if now is None:
    now = datetime.datetime.now()
  new_time = pick_http_time(now, candidates)
  if new_time is None:
    return system_time_valid()
  try:
    set_system_time(new_time)
  except Exception:
    # Without root there is nothing this can do; the caller falls back to
    # waiting for NTP the same way it did before this existed.
    pass
  return system_time_valid()
