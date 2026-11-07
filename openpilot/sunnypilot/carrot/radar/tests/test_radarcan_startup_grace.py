"""The radarcan startup grace keeps drive-start transients off the fault wire.

Ignition CAN floods and card warm-up trip the join watchdog (stateOverflow /
staleEgoState / processingTimeout) for the first seconds of a drive. Publishing
those as errors.canError made selfdrived raise a SOFT_DISABLE "CAN bus error"
at every drive start (2026-10-31 route 58 seg 0: 407 alert frames). The grace
window converts in-window trips into healthy-empty liveTracks frames.
"""

import unittest

from openpilot.sunnypilot.carrot.radar.can_batch import MAX_STARTUP_GRACE_NS, in_startup_grace

S = 1_000_000_000


class TestStartupGrace(unittest.TestCase):
  def test_trips_inside_the_window_are_in_grace(self):
    start = 100 * S
    for offset_s in (0, 1, 5, 15, 19.9):
      self.assertTrue(in_startup_grace(start, start + int(offset_s * S), MAX_STARTUP_GRACE_NS),
                      f"offset {offset_s}s must be inside the grace window")

  def test_trips_after_the_window_publish_the_fault(self):
    start = 100 * S
    for offset_s in (20, 20.1, 60, 3600):
      self.assertFalse(in_startup_grace(start, start + int(offset_s * S), MAX_STARTUP_GRACE_NS),
                       f"offset {offset_s}s must be outside the grace window")

  def test_grace_disabled_by_zero_or_negative_window(self):
    start = 100 * S
    for grace in (0, -1):
      self.assertFalse(in_startup_grace(start, start, grace),
                       "a disabled window must never be in grace (replay fidelity)")

  def test_clock_regression_is_not_grace(self):
    start = 100 * S
    self.assertFalse(in_startup_grace(start, start - S, MAX_STARTUP_GRACE_NS),
                     "a now before start must not read as in-grace")


if __name__ == '__main__':
  unittest.main()
