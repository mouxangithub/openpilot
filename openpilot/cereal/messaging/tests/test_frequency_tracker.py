import unittest

from openpilot.cereal.messaging import FrequencyTracker


class TestFrequencyTracker(unittest.TestCase):
  def _tracker(self, service_freq=20.0, update_freq=100.0, is_poll=True):
    return FrequencyTracker(service_freq, update_freq, is_poll)

  def test_no_samples_is_invalid_without_divide(self):
    tr = self._tracker()
    self.assertFalse(tr.valid)

  def test_first_message_alone_is_invalid(self):
    tr = self._tracker()
    tr.record_recv_time(1.0)
    self.assertFalse(tr.valid)

  def test_same_timestamp_burst_does_not_divide_by_zero(self):
    # cold start: a service flushes two messages in the same update, dt == 0.
    # This used to make valid compute 1/0 and crash the ui process.
    tr = self._tracker()
    tr.record_recv_time(2.0)
    tr.record_recv_time(2.0)
    self.assertFalse(tr.valid)

  def test_zero_then_normal_interval_recovers(self):
    tr = self._tracker(service_freq=20.0, update_freq=100.0, is_poll=True)
    tr.record_recv_time(3.0)
    tr.record_recv_time(3.0)  # zero-dt burst
    self.assertFalse(tr.valid)
    dt = 1.0 / 20.0
    for _ in range(30):
      tr.record_recv_time(tr.prev_time + dt)
    self.assertTrue(tr.valid)

  def test_non_positive_and_nan_like_windows_are_safe(self):
    # many identical timestamps keep the average pinned at zero
    tr = self._tracker()
    for _ in range(50):
      tr.record_recv_time(7.0)
    self.assertFalse(tr.valid)


if __name__ == "__main__":
  unittest.main()
