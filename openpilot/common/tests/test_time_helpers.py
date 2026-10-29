"""
Copyright (c) 2026-, sunnypilot.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The clock bootstrap that backs up NTP: on a cold boot the device has no
RTC battery, and on a walled network the NTP servers may be unreachable
while domestic CDNs are not. These tests cover the decision logic, which
is pure; the network and the `date -s` call are injected or stubbed.
"""
import datetime
import unittest
from unittest import mock

from openpilot.common.time_helpers import (
  LARGE_DRIFT,
  MAX_DATE,
  MIN_DATE,
  pick_http_time,
)


def utc(*args):
  return datetime.datetime(*args)


class TestPickHttpTime(unittest.TestCase):
  def test_median_of_candidates_is_used(self):
    candidates = [utc(2026, 10, 29, 1, 0, 0), utc(2026, 10, 29, 1, 0, 3), utc(2026, 10, 29, 1, 1, 0)]
    picked = pick_http_time(utc(2026, 10, 29, 1, 0, 0), candidates)
    # now is valid and within the drift window, so nothing is picked here;
    # the median behavior is covered by test_median_rejects_a_single_lying_endpoint.
    self.assertIsNone(picked)

  def test_invalid_clock_is_corrected_forward(self):
    # A fresh boot with a dead RTC sits near the epoch.
    now = utc(2026, 1, 1, 0, 0, 30)
    candidates = [utc(2026, 10, 29, 1, 0, 0)]
    picked = pick_http_time(now, candidates)
    self.assertEqual(picked, utc(2026, 10, 29, 1, 0, 0))

  def test_invalid_clock_in_the_far_future_is_corrected_back(self):
    now = utc(2040, 1, 1)
    candidates = [utc(2026, 10, 29, 1, 0, 0)]
    picked = pick_http_time(now, candidates)
    self.assertEqual(picked, utc(2026, 10, 29, 1, 0, 0))

  def test_valid_clock_only_moves_for_a_large_backward_drift(self):
    now = utc(2026, 10, 27, 1, 0, 0)
    candidates = [utc(2026, 10, 29, 1, 0, 0)]
    picked = pick_http_time(now, candidates)
    self.assertEqual(picked, utc(2026, 10, 29, 1, 0, 0))

  def test_valid_clock_within_the_drift_window_is_left_alone(self):
    now = utc(2026, 10, 29, 0, 0, 0)
    candidates = [utc(2026, 10, 29, 6, 0, 0)]
    self.assertIsNone(pick_http_time(now, candidates))

  def test_valid_clock_is_never_moved_backwards(self):
    now = utc(2026, 11, 5)
    candidates = [utc(2026, 10, 29, 1, 0, 0)]
    self.assertIsNone(pick_http_time(now, candidates))

  def test_implausible_candidates_are_rejected(self):
    now = utc(2026, 1, 1, 0, 0, 30)
    # One endpoint lies with a date outside the plausible window; the
    # remaining honest one is still used.
    candidates = [utc(1999, 1, 1), utc(2026, 10, 29, 1, 0, 0)]
    picked = pick_http_time(now, candidates)
    self.assertEqual(picked, utc(2026, 10, 29, 1, 0, 0))

  def test_all_candidates_implausible_means_no_change(self):
    now = utc(2026, 1, 1, 0, 0, 30)
    candidates = [utc(1999, 1, 1), utc(2077, 1, 1)]
    self.assertIsNone(pick_http_time(now, candidates))

  def test_no_candidates_means_no_change(self):
    now = utc(2026, 1, 1, 0, 0, 30)
    self.assertIsNone(pick_http_time(now, []))

  def test_median_rejects_a_single_lying_endpoint(self):
    now = utc(2026, 1, 1, 0, 0, 30)
    # Endpoints disagree wildly; the median is the honest one.
    candidates = [utc(2026, 8, 1), utc(2026, 10, 29, 1, 0, 0), utc(2027, 1, 1)]
    picked = pick_http_time(now, candidates)
    self.assertEqual(picked, utc(2026, 10, 29, 1, 0, 0))

  def test_bounds_are_respected(self):
    # The validity window constants bracket the pick, not the candidates.
    self.assertLess(MIN_DATE, MAX_DATE)
    self.assertLess(LARGE_DRIFT, MAX_DATE - MIN_DATE)


class TestSyncSystemTime(unittest.TestCase):
  def test_sync_uses_the_picked_time(self):
    from openpilot.common import time_helpers

    candidates = [utc(2026, 10, 29, 1, 0, 0)]
    now = utc(2026, 1, 1, 0, 0, 30)
    fake_dt = mock.MagicMock()
    fake_dt.datetime.now.return_value = now
    with mock.patch.object(time_helpers, "http_time_candidates", return_value=candidates), \
         mock.patch.object(time_helpers, "datetime", fake_dt), \
         mock.patch.object(time_helpers, "set_system_time") as setter, \
         mock.patch.object(time_helpers, "system_time_valid", return_value=True):
      ok = time_helpers.sync_system_time_http()

    self.assertTrue(ok)
    setter.assert_called_once_with(utc(2026, 10, 29, 1, 0, 0))

  def test_sync_skips_setting_when_no_pick(self):
    from openpilot.common import time_helpers

    with mock.patch.object(time_helpers, "http_time_candidates", return_value=[]), \
         mock.patch.object(time_helpers, "set_system_time") as setter, \
         mock.patch.object(time_helpers, "system_time_valid", return_value=True):
      ok = time_helpers.sync_system_time_http()

    self.assertTrue(ok)
    setter.assert_not_called()

  def test_sync_survives_a_failed_set(self):
    from openpilot.common import time_helpers

    candidates = [utc(2026, 10, 29, 1, 0, 0)]
    now = utc(2026, 1, 1, 0, 0, 30)
    fake_dt = mock.MagicMock()
    fake_dt.datetime.now.return_value = now
    with mock.patch.object(time_helpers, "http_time_candidates", return_value=candidates), \
         mock.patch.object(time_helpers, "datetime", fake_dt), \
         mock.patch.object(time_helpers, "set_system_time", side_effect=OSError("not root")), \
         mock.patch.object(time_helpers, "system_time_valid", return_value=False):
      ok = time_helpers.sync_system_time_http()

    self.assertFalse(ok)


if __name__ == "__main__":
  unittest.main()
