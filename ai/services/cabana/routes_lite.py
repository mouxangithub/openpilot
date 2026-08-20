"""Cabana route listing without openpilot Params (stdlib + paths only)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
  from zoneinfo import ZoneInfo

  try:
    _DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
  except Exception:
    _DEFAULT_TZ = timezone(timedelta(hours=8))
except ImportError:
  _DEFAULT_TZ = timezone(timedelta(hours=8))
_ROUTE_TZ_OFFSET_HOURS = 8

from ai.system.paths import routes_dir

_ROUTE_DATETIME_RE = re.compile(
  r"^(?P<date>\d{4}-\d{2}-\d{2})--(?P<time>\d{2}-\d{2}-\d{2})",
)


def _is_can_log_file(path: Path, prefix: str) -> bool:
  if not path.is_file():
    return False
  name = path.name
  if name.endswith(".lock"):
    return False
  if not name.startswith(prefix):
    return False
  try:
    if path.stat().st_size == 0:
      return False
  except OSError:
    return False
  return True


def _find_logs(route_dir: Path, prefix: str) -> list[Path]:
  found: set[Path] = set()
  for path in route_dir.rglob(f"{prefix}*"):
    if _is_can_log_file(path, prefix):
      found.add(path)
  return sorted(found)


def _route_datetime_from_name(name: str) -> datetime | None:
  m = _ROUTE_DATETIME_RE.match(name)
  if not m:
    return None
  try:
    dt = datetime.strptime(
      f"{m.group('date')} {m.group('time').replace('-', ':')}",
      "%Y-%m-%d %H:%M:%S",
    )
    if _ROUTE_TZ_OFFSET_HOURS:
      dt += timedelta(hours=_ROUTE_TZ_OFFSET_HOURS)
    return dt
  except ValueError:
    return None


def _route_sort_ts(path: Path) -> float:
  dt = _route_datetime_from_name(path.name)
  if dt is not None:
    return dt.timestamp()
  try:
    return path.stat().st_mtime
  except OSError:
    return 0.0


def _route_date_label(route_path: Path, *, display_tz=_DEFAULT_TZ) -> str:
  dt = _route_datetime_from_name(route_path.name)
  if dt is not None:
    return dt.strftime("%Y-%m-%d %H:%M")
  try:
    return datetime.fromtimestamp(route_path.stat().st_mtime, tz=display_tz).strftime("%Y-%m-%d %H:%M")
  except OSError:
    return ""


def list_routes_lite(*, routes_path: Path | None = None) -> tuple[list[dict[str, Any]], str | None]:
  """Return (routes, routes_dir_str) — same shape as cabana._list_routes entries."""
  rd = routes_path or Path(routes_dir())
  if not rd.is_dir():
    return [], str(rd)
  routes: list[dict[str, Any]] = []
  entries = [e for e in rd.iterdir() if e.is_dir()]
  entries.sort(key=_route_sort_ts, reverse=True)
  for entry in entries:
    qlog = _find_logs(entry, "qlog")
    rlog = _find_logs(entry, "rlog")
    if not qlog and not rlog:
      continue
    routes.append({
      "name": entry.name,
      "path": str(entry),
      "date": _route_date_label(entry),
      "timezone": str(_DEFAULT_TZ),
      "has_qlog": len(qlog) > 0,
      "has_rlog": len(rlog) > 0,
      "qlogs": [str(p) for p in qlog[:5]],
      "rlogs": [str(p) for p in rlog[:3]],
    })
  return routes, str(rd)
