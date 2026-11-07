"""Cabana route date parsing tests (against routes_lite, tz-aware UTC)."""

from __future__ import annotations

import ai.tests.bootstrap_pc  # noqa: F401  # PC mocks before ai imports
import unittest
from datetime import timedelta
from pathlib import Path

from ai.services.cabana.routes_lite import (
  _route_date_label,
  _route_datetime_from_name,
  _route_sort_ts,
)


class CabanaRouteDateTest(unittest.TestCase):
  def test_parse_standard_route_name_returns_utc(self):
    dt = _route_datetime_from_name("2026-07-08--14-30-00--abc--0")
    self.assertIsNotNone(dt)
    assert dt is not None
    self.assertIsNotNone(dt.tzinfo)
    self.assertEqual(dt.utcoffset(), timedelta(0))
    self.assertEqual((dt.hour, dt.minute, dt.second), (14, 30, 0))
    self.assertEqual(dt.date().isoformat(), "2026-07-08")

  def test_date_label_converts_utc_to_display_tz(self):
    # UTC 14:30 -> Asia/Shanghai (default display tz) 22:30 same day.
    label = _route_date_label(Path("2026-07-08--14-30-00--abc--0"))
    self.assertIn("22:30", label)
    self.assertIn("2026-07-08", label)

  def test_date_label_offset_route_hour(self):
    # UTC 02:10 -> displayed 10:10 in UTC+8; regression for the old +8 shift bug.
    label = _route_date_label(Path("2026-07-10--02-10-00--boot--0"))
    self.assertIn("10:10", label)

  def test_sort_newest_first(self):
    paths = [
      Path("2026-07-01--10-00-00--old--0"),
      Path("2026-07-09--16-20-00--new--0"),
      Path("00000003--53795605c8--18"),
    ]
    ordered = sorted(paths, key=_route_sort_ts, reverse=True)
    self.assertEqual(ordered[0].name, "2026-07-09--16-20-00--new--0")
    self.assertEqual(ordered[1].name, "2026-07-01--10-00-00--old--0")


class CabanaLogFileTest(unittest.TestCase):
  def test_skip_lock_and_empty(self):
    from ai.services.cabana.routes_lite import _is_can_log_file

    route = Path(__file__).resolve().parents[2]
    lock = route / "ai" / "tests" / "_tmp_rlog.lock"
    lock.write_text("")
    try:
      self.assertFalse(_is_can_log_file(lock, "rlog"))
    finally:
      lock.unlink(missing_ok=True)


if __name__ == "__main__":
  unittest.main()
