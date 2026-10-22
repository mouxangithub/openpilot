#!/usr/bin/env python3
"""What a late frame costs, and what a broken timebase costs.

`locationdTemporaryError` follows deviceMotion.inputsOK, which follows the
per-service invalid counter. A frame whose stamp is far from its publish time is
dropped -- that is a transport hiccup, and a handful of them per drive must not
latch the alert for the rest of it. A timebase that is actually wrong must still
latch, and a wrong *sample* (INPUT_INVALID) must count at once.
"""
from collections import defaultdict
import unittest

from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.locationd.locationd import (
  HandleLogResult, LocationEstimator, MAX_SENSOR_TIME_DIFF, update_observation_invalid)

FREQ = 104.0          # accelerometer
LIMIT = 10            # round(INPUT_INVALID_LIMIT * FREQ / 20)
THRESHOLD = LIMIT - 0.5
DECAY = dict.fromkeys(("accelerometer",), 0.99995068)
GRACE = dict.fromkeys(("accelerometer",), max(1, round(0.5 * FREQ)))


def drive(results):
  """Feed results through the counter; return (bucket, index it crossed threshold)."""
  bucket, run = defaultdict(float), defaultdict(int)
  latched = None
  for i, res in enumerate(results):
    update_observation_invalid(res, "accelerometer", bucket, run, DECAY, GRACE)
    if bucket["accelerometer"] >= THRESHOLD and latched is None:
      latched = i
  return bucket["accelerometer"], latched


class TestSensorTimeWindow(OpenpilotTestCase):
  """The check itself is stateless and absolute: same clock, close in time."""

  def _est(self) -> LocationEstimator:
    return LocationEstimator.__new__(LocationEstimator)

  def test_a_frame_in_the_window_is_usable(self):
    assert self._est()._validate_sensor_time(10.002, 10.0)

  def test_a_late_frame_is_dropped(self):
    assert not self._est()._validate_sensor_time(10.0 + MAX_SENSOR_TIME_DIFF + 0.05, 10.0)

  def test_a_frame_ahead_of_the_log_time_is_dropped(self):
    assert not self._est()._validate_sensor_time(10.0 - MAX_SENSOR_TIME_DIFF - 0.05, 10.0)

  def test_an_empty_reading_is_dropped(self):
    assert not self._est()._validate_sensor_time(0.0, 10.0)


class TestInvalidCounter(OpenpilotTestCase):
  def test_isolated_late_frames_never_latch(self):
    for pct in (1, 3, 5):
      res = [HandleLogResult.SUCCESS] * 4000
      for i in range(0, 4000, max(1, 100 // pct)):
        res[i] = HandleLogResult.TIMING_INVALID
      bucket, latched = drive(res)
      self.assertIsNone(latched, f"{pct}% late frames latched (bucket={bucket})")

  def test_a_burst_shorter_than_the_grace_never_latches(self):
    res = [HandleLogResult.SUCCESS] * 100 + [HandleLogResult.TIMING_INVALID] * (int(0.5 * FREQ) - 1) + \
          [HandleLogResult.SUCCESS] * 100
    _, latched = drive(res)
    self.assertIsNone(latched)

  def test_a_sustained_timebase_fault_still_latches(self):
    res = [HandleLogResult.SUCCESS] * 500 + [HandleLogResult.TIMING_INVALID] * 2000
    _, latched = drive(res)
    self.assertIsNotNone(latched, "a broken timebase must still raise the alert")
    self.assertGreater(latched, 500, "must not latch before the fault starts")

  def test_a_wrong_sample_counts_at_once(self):
    res = [HandleLogResult.SUCCESS] * 20 + [HandleLogResult.INPUT_INVALID] * 20
    _, latched = drive(res)
    self.assertIsNotNone(latched, "a wrong sample is a fault, not a hiccup")

  def test_success_clears_the_consecutive_run(self):
    res = ([HandleLogResult.TIMING_INVALID] * (int(0.5 * FREQ) - 2) + [HandleLogResult.SUCCESS]) * 8
    _, latched = drive(res)
    self.assertIsNone(latched, "runs interrupted by a good frame must not accumulate")

  def test_the_counter_falls_once_good_frames_return(self):
    # the decay is multiplicative and upstream's: a fault that lasted long enough
    # to cross the limit leaves a high reading that comes down slowly. What must
    # hold is that it comes down at all while good frames flow.
    res = [HandleLogResult.TIMING_INVALID] * 400 + [HandleLogResult.SUCCESS] * 2000
    bucket, _ = drive(res)
    during_fault, _ = drive([HandleLogResult.TIMING_INVALID] * 400 + [HandleLogResult.SUCCESS] * 200)
    self.assertLess(bucket, during_fault, "the counter must fall once the fault clears")


if __name__ == "__main__":
  unittest.main()
