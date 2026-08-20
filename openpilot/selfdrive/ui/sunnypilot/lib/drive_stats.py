"""
Local drive statistics from on-device route logs (no cloud API).
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta

from openpilot.common.hardware.hw import Paths
from openpilot.common.swaglog import cloudlog
from openpilot.tools.lib.logreader import LogReader

SEGMENT_DIR_RE = re.compile(
  r"^(?P<route>.+\|\d{4}-\d{2}-\d{2}--\d{2}-\d{2}-\d{2})--(?P<seg>\d+)$"
)
ROUTE_TIME_RE = re.compile(r"\|(\d{4}-\d{2}-\d{2}--\d{2}-\d{2}-\d{2})$")
METERS_PER_MILE = 1609.344


def _route_start(route_key: str) -> datetime | None:
  match = ROUTE_TIME_RE.search(route_key)
  if not match:
    return None
  try:
    return datetime.strptime(match.group(1), "%Y-%m-%d--%H-%M-%S")
  except ValueError:
    return None


def _qlog_path(log_root: str, segment_name: str) -> str | None:
  for name in ("qlog.zst", "qlog.bz2", "rlog.zst", "rlog.bz2"):
    path = os.path.join(log_root, segment_name, name)
    if os.path.isfile(path):
      return path
  return None


def _segment_stats(log_path: str) -> tuple[float, float]:
  """Return (distance_miles, duration_minutes) for one segment log."""
  distance_m = 0.0
  first_t = None
  last_t = None
  last_v = 0.0

  try:
    for msg in LogReader(log_path):
      if msg.which() != "carState":
        continue
      t = msg.logMonoTime * 1e-9
      v = float(msg.carState.vEgo)
      if last_t is not None and t > last_t:
        distance_m += (last_v + v) * 0.5 * (t - last_t)
      if first_t is None:
        first_t = t
      last_t = t
      last_v = v
  except Exception:
    cloudlog.exception(f"failed to read segment log: {log_path}")
    return 0.0, 1.0

  if first_t is None or last_t is None or last_t <= first_t:
    return 0.0, 1.0

  miles = distance_m / METERS_PER_MILE
  minutes = max((last_t - first_t) / 60.0, 1.0)
  return miles, minutes


def _empty_bucket() -> dict[str, float | int]:
  return {"routes": 0, "distance": 0.0, "minutes": 0.0}


def compute_local_drive_stats(log_root: str | None = None, cache: dict | None = None) -> dict:
  log_root = log_root or Paths.log_root()
  cache = dict(cache or {})
  segment_cache: dict[str, dict] = dict(cache.get("segments", {}))

  week_cutoff = datetime.now() - timedelta(days=7)
  buckets = {"all": _empty_bucket(), "week": _empty_bucket()}
  seen_routes: dict[str, set[str]] = {"all": set(), "week": set()}

  if not os.path.isdir(log_root):
    return {"all": buckets["all"], "week": buckets["week"], "segments": segment_cache, "updated_at": time.time()}

  route_segments: dict[str, list[str]] = {}
  active_segments: set[str] = set()
  for entry in os.listdir(log_root):
    match = SEGMENT_DIR_RE.match(entry)
    if not match:
      continue
    active_segments.add(entry)
    route_key = match.group("route")
    route_segments.setdefault(route_key, []).append(entry)

  for segment_name in list(segment_cache):
    if segment_name not in active_segments:
      del segment_cache[segment_name]

  for route_key, segment_names in sorted(route_segments.items()):
    route_miles = 0.0
    route_minutes = 0.0
    for segment_name in sorted(segment_names, key=lambda s: int(SEGMENT_DIR_RE.match(s).group("seg"))):
      cached = segment_cache.get(segment_name)
      if cached is None:
        log_path = _qlog_path(log_root, segment_name)
        if log_path is None:
          cached = {"distance": 0.0, "minutes": 1.0}
        else:
          miles, minutes = _segment_stats(log_path)
          cached = {"distance": miles, "minutes": minutes}
        segment_cache[segment_name] = cached
      route_miles += float(cached["distance"])
      route_minutes += float(cached["minutes"])

    seen_routes["all"].add(route_key)
    buckets["all"]["routes"] = len(seen_routes["all"])
    buckets["all"]["distance"] = float(buckets["all"]["distance"]) + route_miles
    buckets["all"]["minutes"] = float(buckets["all"]["minutes"]) + route_minutes

    route_start = _route_start(route_key)
    if route_start is not None and route_start >= week_cutoff:
      seen_routes["week"].add(route_key)
      buckets["week"]["routes"] = len(seen_routes["week"])
      buckets["week"]["distance"] = float(buckets["week"]["distance"]) + route_miles
      buckets["week"]["minutes"] = float(buckets["week"]["minutes"]) + route_minutes

  return {
    "all": buckets["all"],
    "week": buckets["week"],
    "segments": segment_cache,
    "updated_at": time.time(),
  }


def refresh_local_drive_stats(params, param_key: str = "LocalDriveStats") -> dict:
  cache = params.get(param_key) or {}
  stats = compute_local_drive_stats(cache=cache)
  params.put(param_key, stats)
  return stats
