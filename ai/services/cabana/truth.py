"""Physical truth series extraction from route logs (qlog/rlog).

Single streaming LogReader pass over the route logs collecting IMU / GPS
messages and deriving the anchor series used by the DBC reverse-engineering
pipeline:

- ``accel_long``  longitudinal acceleration (m/s^2), SensorVec.v[0]
- ``accel_vert``  vertical acceleration minus gravity (m/s^2), v[2] - 9.81
- ``yaw_rate``    yaw rate (rad/s), gyro SensorVec.v[2]
- ``gps_speed``   GPS speed (m/s), GpsLocationData.speed
- ``gps_accel``   smoothed longitudinal acceleration derived from gps_speed

All series timestamps are **absolute seconds** (``logMonoTime / 1e9``). The
CAN-side route-relative axis is produced downstream via the ``base`` returned
by ``handlers._filter_frames_rel``; never reuse the
``replay._encode_index_samples`` origin (different code base). Results are
cached on disk per route (mtime-invalidated) next to the CAN frame caches.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from ai.services.cabana.deps import LogReader, cloudlog
from ai.services.cabana.replay import (
  _cabana_cache_dir,
  _find_qlogs,
  _find_rlogs,
  _replay_log_paths,
  _route_dir,
  _route_path_digest,
)

TRUTH_CACHE_VERSION = 1
TRUTH_MAX_POINTS = 20000
_GRAVITY = 9.81

ACCEL_LONG = "accel_long"
ACCEL_VERT = "accel_vert"
YAW_RATE = "yaw_rate"
GPS_SPEED = "gps_speed"
GPS_ACCEL = "gps_accel"
# Shared series-name constants (referenced by anchor.py / profile.py / report).
TRUTH_SERIES = (ACCEL_LONG, ACCEL_VERT, YAW_RATE, GPS_SPEED, GPS_ACCEL)


def _empty_truth(note: str, *, scanned: bool = False) -> dict[str, Any]:
  return {
    "available": False,
    "scanned": scanned,
    "note": note,
    "series": {name: {"t": [], "v": []} for name in TRUTH_SERIES},
  }


def _sensor_v(event: Any) -> list[float] | None:
  """Extract SensorVec.v from a SensorEventData union (capnp-version safe).

  The union is read via ``which()`` whitelisting + ``getattr``; an inactive or
  empty union field yields None so the caller can skip the sample.
  """
  try:
    which = str(event.which())
  except Exception:
    return None
  if which not in ("acceleration", "gyro", "gravity", "linearAcceleration"):
    return None
  field = getattr(event, which, None)
  if field is None:
    return None
  v = getattr(field, "v", None)
  if v is None:
    return None
  try:
    values = [float(x) for x in v]
  except (TypeError, ValueError):
    return None
  if len(values) < 3:
    return None
  return values


def _consume_message(msg: Any, raw: dict[str, tuple[list[float], list[float]]]) -> None:
  """Accumulate raw sensor samples from one log message (never raises)."""
  try:
    mono = float(msg.logMonoTime) / 1e9
    which = str(msg.which())
  except Exception:
    return
  if which in ("accelerometer", "gyroscope"):
    event = getattr(msg, which, None)
    if event is None:
      return
    v = _sensor_v(event)
    if not v:
      return
    if which == "accelerometer":
      raw[ACCEL_LONG][0].append(mono)
      raw[ACCEL_LONG][1].append(v[0])
      raw[ACCEL_VERT][0].append(mono)
      raw[ACCEL_VERT][1].append(v[2] - _GRAVITY)
    else:
      raw[YAW_RATE][0].append(mono)
      raw[YAW_RATE][1].append(v[2])
    return
  if which in ("gpsLocationExternal", "gpsLocation"):
    loc = getattr(msg, which, None)
    speed = getattr(loc, "speed", None) if loc is not None else None
    if speed is None:
      return
    raw[GPS_SPEED][0].append(mono)
    raw[GPS_SPEED][1].append(float(speed))
    return
  if which == "sensorEventsDEPRECATED":
    events = getattr(msg, "sensorEventsDEPRECATED", None)
    for event in list(events or []):
      try:
        w = str(event.which())
      except Exception:
        continue
      if w not in ("acceleration", "gyro"):
        continue
      v = _sensor_v(event)
      if not v:
        continue
      if w == "acceleration":
        raw[ACCEL_LONG][0].append(mono)
        raw[ACCEL_LONG][1].append(v[0])
        raw[ACCEL_VERT][0].append(mono)
        raw[ACCEL_VERT][1].append(v[2] - _GRAVITY)
      else:
        raw[YAW_RATE][0].append(mono)
        raw[YAW_RATE][1].append(v[2])


def _decimate_series(ts: list[float], vs: list[float], max_points: int = TRUTH_MAX_POINTS) -> tuple[list[float], list[float]]:
  """Uniform stride decimation down to ``max_points`` (keeps endpoints)."""
  n = len(ts)
  if n <= max_points or n < 2:
    return ts, vs
  stride = max(1, -(-n // max_points))  # ceil division
  return ts[::stride], vs[::stride]


def _derive_gps_accel(gps: dict[str, list[float]], smooth_window: int = 5) -> dict[str, list[float]]:
  """Smoothed derivative of GPS speed (m/s^2) on the same timestamps."""
  ts, vs = gps.get("t", []), gps.get("v", [])
  if len(ts) < 3:
    return {"t": [], "v": []}
  half = max(1, smooth_window // 2)
  smoothed: list[float] = []
  for i in range(len(vs)):
    lo = max(0, i - half)
    hi = min(len(vs), i + half + 1)
    smoothed.append(sum(vs[lo:hi]) / (hi - lo))
  out_t: list[float] = []
  out_v: list[float] = []
  for i in range(1, len(ts) - 1):
    dt = ts[i + 1] - ts[i - 1]
    if dt <= 1e-6:
      continue
    out_t.append(ts[i])
    out_v.append((smoothed[i + 1] - smoothed[i - 1]) / dt)
  return {"t": out_t, "v": out_v}


def _extract_truth_series(route: str) -> dict[str, Any]:
  """Stream the route logs once and derive all truth series (absolute seconds)."""
  route_path = _route_dir(route)
  if route_path is None:
    return _empty_truth("route not found")
  if LogReader is None:
    return _empty_truth("LogReader not available")
  qlogs = _find_qlogs(route_path)
  rlogs = _find_rlogs(route_path)
  paths, _source = _replay_log_paths(qlogs, rlogs, full=True)
  if not paths:
    return _empty_truth("no qlog/rlog found in route")
  # name -> (times, values); raw samples in message order, sorted per series later.
  raw: dict[str, tuple[list[float], list[float]]] = {
    ACCEL_LONG: ([], []),
    ACCEL_VERT: ([], []),
    YAW_RATE: ([], []),
    GPS_SPEED: ([], []),
  }
  for log_path in paths:
    try:
      lr = LogReader(str(log_path))
    except Exception as e:
      cloudlog.warning(f"cabana: truth LogReader failed for {log_path.name}: {e}")
      continue
    try:
      for msg in lr:
        _consume_message(msg, raw)
    except Exception as e:
      cloudlog.warning(f"cabana: truth scan aborted for {log_path.name}: {e}")
  series: dict[str, dict[str, list[float]]] = {}
  for name in (ACCEL_LONG, ACCEL_VERT, YAW_RATE, GPS_SPEED):
    ts, vs = raw[name]
    if ts:
      pairs = sorted(zip(ts, vs, strict=True))
      ts_sorted = [p[0] for p in pairs]
      vs_sorted = [p[1] for p in pairs]
      ts_sorted, vs_sorted = _decimate_series(ts_sorted, vs_sorted)
      series[name] = {"t": ts_sorted, "v": vs_sorted}
    else:
      series[name] = {"t": [], "v": []}
  series[GPS_ACCEL] = _derive_gps_accel(series[GPS_SPEED])
  available = any(series[name]["t"] for name in (ACCEL_LONG, GPS_SPEED, YAW_RATE))
  note = "" if available else "no accelerometer/gyroscope/GPS messages found in this route"
  return {"available": available, "scanned": True, "note": note, "series": series}


def _truth_cache_file(route_path: Path) -> Path:
  """Cache path keyed by resolved route path + mtime + format version."""
  try:
    mtime = int(route_path.stat().st_mtime)
  except OSError:
    mtime = 0
  digest = _route_path_digest(route_path)
  return _cabana_cache_dir() / f"{digest}_{mtime}_truth_v{TRUTH_CACHE_VERSION}.json.gz"


def _load_truth_cache_file(cache_path: Path, route_path: Path) -> dict[str, Any] | None:
  if not cache_path.is_file():
    return None
  try:
    data = json.loads(gzip.decompress(cache_path.read_bytes()).decode("utf-8"))
  except Exception:
    return None
  if not isinstance(data, dict) or data.get("version") != TRUTH_CACHE_VERSION:
    return None
  if data.get("route") != route_path.name or data.get("route_key") != _route_path_digest(route_path):
    return None
  truth = data.get("truth")
  if not isinstance(truth, dict) or not isinstance(truth.get("series"), dict):
    return None
  return truth


def _save_truth_cache(cache_path: Path, route_path: Path, truth: dict[str, Any]) -> None:
  try:
    payload = json.dumps({
      "version": TRUTH_CACHE_VERSION,
      "route": route_path.name,
      "route_key": _route_path_digest(route_path),
      "truth": {k: truth.get(k) for k in ("available", "note", "series")},
    }, separators=(",", ":")).encode("utf-8")
    cache_path.write_bytes(gzip.compress(payload, compresslevel=3))
  except Exception as e:
    cloudlog.warning(f"cabana: truth cache write failed: {e}")


def _load_truth_cached(route: str) -> dict[str, Any] | None:
  """Truth series for a route with disk cache (zero log IO on cache hit)."""
  route_path = _route_dir(route)
  if route_path is None:
    return None
  cache_path = _truth_cache_file(route_path)
  cached = _load_truth_cache_file(cache_path, route_path)
  if cached is not None:
    return cached
  truth = _extract_truth_series(route)
  if truth.get("scanned"):
    _save_truth_cache(cache_path, route_path, truth)
  return truth
