import os
import struct
import time
import unittest
from unittest import mock

from openpilot.common import watchdog


class TestWatchdogPath(unittest.TestCase):
  def test_the_path_carries_the_pid(self):
    self.assertTrue(watchdog.watchdog_path(1234).endswith("wd_1234"))

  def test_the_prefix_is_the_shared_memory_one(self):
    # The C++ side writes the same prefix, so a mismatch would mean the
    # manager never sees the heartbeat.
    self.assertIn("/wd_", watchdog.WATCHDOG_FN)


class TestKickAndRead(unittest.TestCase):
  def setUp(self):
    self._tmpdir = f"/tmp/wd_test_{os.getpid()}"
    os.makedirs(self._tmpdir, exist_ok=True)
    self._patch = mock.patch.object(watchdog, "WATCHDOG_FN", f"{self._tmpdir}/wd_")
    self._patch.start()
    watchdog._last_kick = 0.0

  def tearDown(self):
    self._patch.stop()
    for name in os.listdir(self._tmpdir):
      os.unlink(os.path.join(self._tmpdir, name))
    os.rmdir(self._tmpdir)

  def test_a_kick_writes_a_heartbeat(self):
    self.assertTrue(watchdog.kick_watchdog())
    self.assertIsNotNone(watchdog.read_watchdog_time(os.getpid()))

  def test_a_fresh_heartbeat_is_not_a_timeout(self):
    watchdog.kick_watchdog()
    self.assertIsNone(watchdog.watchdog_timed_out(os.getpid(), 10))

  def test_a_stale_heartbeat_is_a_timeout(self):
    # Write a heartbeat that is one hour old.
    stale_ns = watchdog._now_ns() - int(3600 * 1e9)
    with open(watchdog.watchdog_path(os.getpid()), "wb") as f:
      f.write(struct.pack("<Q", stale_ns))
    dt = watchdog.watchdog_timed_out(os.getpid(), 10)
    self.assertIsNotNone(dt)
    self.assertGreater(dt, 3000)

  def test_a_missing_heartbeat_is_not_a_timeout(self):
    # A process that has not reported yet must not be restarted in a loop.
    self.assertIsNone(watchdog.watchdog_timed_out(999999, 10))

  def test_no_threshold_means_no_watch(self):
    watchdog.kick_watchdog()
    self.assertIsNone(watchdog.watchdog_timed_out(os.getpid(), None))

  def test_a_truncated_heartbeat_is_ignored(self):
    with open(watchdog.watchdog_path(os.getpid()), "wb") as f:
      f.write(b"\x01\x02")
    self.assertIsNone(watchdog.read_watchdog_time(os.getpid()))

  def test_clear_removes_the_heartbeat(self):
    watchdog.kick_watchdog()
    watchdog.clear_watchdog(os.getpid())
    self.assertIsNone(watchdog.read_watchdog_time(os.getpid()))

  def test_clearing_a_missing_file_is_harmless(self):
    watchdog.clear_watchdog(999999)

  def test_the_kick_is_throttled(self):
    self.assertTrue(watchdog.kick_watchdog())
    first = watchdog.read_watchdog_time(os.getpid())
    self.assertTrue(watchdog.kick_watchdog())
    second = watchdog.read_watchdog_time(os.getpid())
    # The second call was inside the throttle window, so nothing was written.
    self.assertEqual(first, second)


class TestClockConsistency(unittest.TestCase):
  """Both sides must use the same clock.

  The C++ side writes nanos_since_boot(), which is CLOCK_BOOTTIME. Python's
  time.monotonic() is CLOCK_MONOTONIC; the two differ by any time the device
  spent suspended. A heartbeat written on one clock and compared against the
  other would time out by an unknown amount.
  """

  def test_the_python_clock_is_boottime(self):
    if not hasattr(time, "CLOCK_BOOTTIME"):
      self.skipTest("CLOCK_BOOTTIME is not available on this platform")
    expected = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    got = watchdog._now_ns()
    # They are read microseconds apart, so allow a generous window.
    self.assertLess(abs(got - expected), int(5e9))

  def test_it_falls_back_when_boottime_is_missing(self):
    # Windows and macOS have no CLOCK_BOOTTIME. The helper must still work.
    with mock.patch.object(time, "clock_gettime_ns", side_effect=OSError("no clock"), create=True), \
         mock.patch.object(time, "monotonic_ns", return_value=123456789):
      self.assertEqual(watchdog._now_ns(), 123456789)

  def test_it_falls_back_when_the_attribute_is_absent(self):
    with mock.patch.object(time, "clock_gettime_ns", None, create=True), \
         mock.patch.object(time, "monotonic_ns", return_value=42):
      # A missing attribute raises AttributeError, not OSError.
      try:
        got = watchdog._now_ns()
      except AttributeError:
        self.fail("_now_ns must not raise when CLOCK_BOOTTIME is absent")
      self.assertEqual(got, 42)


if __name__ == "__main__":
  unittest.main()


class TestSweep(unittest.TestCase):
  def setUp(self):
    self._tmpdir = f"/tmp/wd_sweep_{os.getpid()}"
    os.makedirs(self._tmpdir, exist_ok=True)
    self._patch = mock.patch.object(watchdog, "WATCHDOG_FN", f"{self._tmpdir}/wd_")

  def tearDown(self):
    self._patch.stop()
    for name in os.listdir(self._tmpdir):
      os.unlink(os.path.join(self._tmpdir, name))
    os.rmdir(self._tmpdir)

  def _make(self, pid, name=None):
    path = os.path.join(self._tmpdir, name or f"wd_{pid}")
    with open(path, "wb") as f:
      f.write(struct.pack("Q", 1))
    return path

  def test_a_dead_pids_heartbeat_is_removed(self):
    self._patch.start()
    # pid 0 can never be a live process we created, and /proc/0 does not exist
    path = self._make(0)
    self.assertEqual(watchdog.sweep_stale_heartbeats(), 1)
    self.assertFalse(os.path.exists(path))

  def test_a_live_pids_heartbeat_is_kept(self):
    self._patch.start()
    path = self._make(os.getpid())
    self.assertEqual(watchdog.sweep_stale_heartbeats(), 0)
    self.assertTrue(os.path.exists(path))

  def test_unrelated_files_are_untouched(self):
    self._patch.start()
    other = os.path.join(self._tmpdir, "not_a_heartbeat")
    with open(other, "wb") as f:
      f.write(b"x")
    watchdog.sweep_stale_heartbeats()
    self.assertTrue(os.path.exists(other))

  def test_a_name_that_is_not_a_pid_is_untouched(self):
    self._patch.start()
    path = self._make(0, name="wd_notapid")
    watchdog.sweep_stale_heartbeats()
    self.assertTrue(os.path.exists(path))

  def test_a_missing_directory_is_harmless(self):
    self._patch.start()
    with mock.patch.object(watchdog, "WATCHDOG_FN", f"{self._tmpdir}/nope/wd_"):
      self.assertEqual(watchdog.sweep_stale_heartbeats(), 0)
