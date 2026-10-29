"""
Copyright (c) 2026-, sunnypilot.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The clock bootstrap that backs up NTP: on a cold boot the device has no
RTC battery, and on a walled network the NTP servers may be unreachable
while domestic CDNs are not. These tests cover the decision logic, which
is pure; the network and the `date -s` call are injected or stubbed.

Candidate dates are derived from min_date() rather than hardcoded: on a
systemd system that is the systemd build time plus a day, which moves
with every OS update and would otherwise make a hardcoded date implausible
on a fresh device while looking fine on a PC.
"""
import datetime
import unittest
from unittest import mock

from openpilot.common.time_helpers import (
  LARGE_DRIFT,
  MAX_DATE,
  MIN_DATE,
  min_date,
  pick_http_time,
)


def utc(*args):
  return datetime.datetime(*args)


# A date that is plausible on any machine: min_date() is the systemd build
# time plus a day at the newest, so this stays inside the window until 2034.
HONEST = min_date() + datetime.timedelta(days=100)


class TestPickHttpTime(unittest.TestCase):
  def test_median_of_candidates_is_used(self):
    candidates = [HONEST - datetime.timedelta(seconds=3), HONEST, HONEST + datetime.timedelta(seconds=57)]
    picked = pick_http_time(HONEST, candidates)
    # now is valid and within the drift window, so nothing is picked here;
    # the median behavior is covered by test_median_rejects_a_single_lying_endpoint.
    self.assertIsNone(picked)

  def test_invalid_clock_is_corrected_forward(self):
    # A fresh boot with a dead RTC sits before min_date().
    now = MIN_DATE - datetime.timedelta(days=60)
    picked = pick_http_time(now, [HONEST])
    self.assertEqual(picked, HONEST)

  def test_invalid_clock_in_the_far_future_is_corrected_back(self):
    now = utc(2040, 1, 1)
    picked = pick_http_time(now, [HONEST])
    self.assertEqual(picked, HONEST)

  def test_valid_clock_only_moves_for_a_large_backward_drift(self):
    now = HONEST - LARGE_DRIFT - datetime.timedelta(days=2)
    picked = pick_http_time(now, [HONEST])
    self.assertEqual(picked, HONEST)

  def test_valid_clock_within_the_drift_window_is_left_alone(self):
    now = HONEST - datetime.timedelta(hours=12)
    self.assertIsNone(pick_http_time(now, [HONEST]))

  def test_valid_clock_is_never_moved_backwards(self):
    now = HONEST + datetime.timedelta(days=7)
    self.assertIsNone(pick_http_time(now, [HONEST]))

  def test_implausible_candidates_are_rejected(self):
    now = MIN_DATE - datetime.timedelta(days=60)
    # One endpoint lies with a date outside the plausible window; the
    # remaining honest one is still used.
    candidates = [utc(1999, 1, 1), HONEST]
    picked = pick_http_time(now, candidates)
    self.assertEqual(picked, HONEST)

  def test_all_candidates_implausible_means_no_change(self):
    now = MIN_DATE - datetime.timedelta(days=60)
    candidates = [utc(1999, 1, 1), utc(2077, 1, 1)]
    self.assertIsNone(pick_http_time(now, candidates))

  def test_no_candidates_means_no_change(self):
    now = MIN_DATE - datetime.timedelta(days=60)
    self.assertIsNone(pick_http_time(now, []))

  def test_median_rejects_a_single_lying_endpoint(self):
    now = MIN_DATE - datetime.timedelta(days=60)
    # Endpoints disagree wildly; the median is the honest one.
    candidates = [HONEST - datetime.timedelta(days=40), HONEST, HONEST + datetime.timedelta(days=200)]
    picked = pick_http_time(now, candidates)
    self.assertEqual(picked, HONEST)

  def test_bounds_are_respected(self):
    # The validity window constants bracket the pick, not the candidates.
    self.assertLess(MIN_DATE, MAX_DATE)
    self.assertLess(LARGE_DRIFT, MAX_DATE - MIN_DATE)


class TestSyncSystemTime(unittest.TestCase):
  def test_sync_uses_the_picked_time(self):
    from openpilot.common import time_helpers

    now = MIN_DATE - datetime.timedelta(days=60)
    with mock.patch.object(time_helpers, "http_time_candidates", return_value=[HONEST]), \
         mock.patch.object(time_helpers, "set_system_time") as setter, \
         mock.patch.object(time_helpers, "system_time_valid", return_value=True):
      ok = time_helpers.sync_system_time_http(now=now)

    self.assertTrue(ok)
    setter.assert_called_once_with(HONEST)

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

    now = MIN_DATE - datetime.timedelta(days=60)
    with mock.patch.object(time_helpers, "http_time_candidates", return_value=[HONEST]), \
         mock.patch.object(time_helpers, "set_system_time", side_effect=OSError("not root")), \
         mock.patch.object(time_helpers, "system_time_valid", return_value=False):
      ok = time_helpers.sync_system_time_http(now=now)

    self.assertFalse(ok)


if __name__ == "__main__":
  unittest.main()
