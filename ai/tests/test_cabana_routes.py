"""Cabana route date parsing (stdlib only — no openpilot import)."""

from __future__ import annotations

import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path


_ROUTE_DATETIME_RE = re.compile(
  r"^(?P<date>\d{4}-\d{2}-\d{2})--(?P<time>\d{2}-\d{2}-\d{2})",
)
ROUTE_TZ_OFFSET_HOURS = 8


def route_datetime_from_name(name: str) -> datetime | None:
  m = _ROUTE_DATETIME_RE.match(name)
  if not m:
    return None
  try:
    dt = datetime.strptime(
      f"{m.group('date')} {m.group('time').replace('-', ':')}",
      "%Y-%m-%d %H:%M:%S",
    )
    if ROUTE_TZ_OFFSET_HOURS:
      dt += timedelta(hours=ROUTE_TZ_OFFSET_HOURS)
    return dt
  except ValueError:
    return None


def route_sort_ts(path: Path) -> float:
  dt = route_datetime_from_name(path.name)
  if dt is not None:
    return dt.timestamp()
  try:
    return path.stat().st_mtime
  except OSError:
    return 0.0


class CabanaRouteDateTest(unittest.TestCase):
  def test_parse_standard_route_name(self):
    dt = route_datetime_from_name("2026-07-08--14-30-00--abc--0")
    self.assertIsNotNone(dt)
    assert dt is not None
    self.assertEqual(dt, datetime(2026, 7, 8, 22, 30, 0))

  def test_tz_offset_applied(self):
    dt = route_datetime_from_name("2026-07-10--02-10-00--boot--0")
    self.assertIsNotNone(dt)
    assert dt is not None
    self.assertEqual(dt.hour, 10)

  def test_sort_newest_first(self):
    paths = [
      Path("2026-07-01--10-00-00--old--0"),
      Path("2026-07-09--16-20-00--new--0"),
      Path("00000003--53795605c8--18"),
    ]
    ordered = sorted(paths, key=route_sort_ts, reverse=True)
    self.assertEqual(ordered[0].name, "2026-07-09--16-20-00--new--0")
    self.assertEqual(ordered[1].name, "2026-07-01--10-00-00--old--0")


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


class CabanaLogFileTest(unittest.TestCase):
  def test_skip_lock_and_empty(self):
    route = Path(__file__).resolve().parents[2]
    lock = route / "ai" / "tests" / "_tmp_rlog.lock"
    lock.write_text("")
    try:
      self.assertFalse(_is_can_log_file(lock, "rlog"))
    finally:
      lock.unlink(missing_ok=True)


if __name__ == "__main__":
  unittest.main()
