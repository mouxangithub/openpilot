#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Unit tests for the vendored cut-in alert tracker used by the radar tools."""
import unittest

from openpilot.sunnypilot.carrot.radar_motion.cutin_alert import (
  CutinAlertCandidate,
  CutinAlertTracker,
  promoted_cutin_candidates,
)


def candidate(track_id: int, d_rel: float, y_rel: float, v_rel: float = 0.0) -> CutinAlertCandidate:
  return CutinAlertCandidate(track_id, d_rel, y_rel, v_rel)


class TestCutinAlertTracker(unittest.TestCase):
  def test_only_once_for_continuous_candidate(self):
    tracker = CutinAlertTracker()
    self.assertTrue(tracker.update((candidate(10, 20.0, 2.0),)))
    self.assertFalse(tracker.update((candidate(10, 19.7, 1.8),)))

  def test_does_not_repeat_for_continuous_reid(self):
    tracker = CutinAlertTracker()
    self.assertTrue(tracker.update((candidate(10, 20.0, 2.0, -1.0),)))
    self.assertFalse(tracker.update((candidate(11, 19.5, 1.7, -1.1),)))

  def test_repeats_for_new_back_to_back_vehicle(self):
    tracker = CutinAlertTracker()
    self.assertTrue(tracker.update((candidate(2816, 38.0, 0.0, 9.45),)))
    self.assertTrue(tracker.update((candidate(2818, 9.0, -2.75, 8.85),)))

  def test_detects_added_vehicle_while_first_remains(self):
    tracker = CutinAlertTracker()
    first = candidate(10, 20.0, 1.5)
    second = candidate(20, 8.0, -2.5)
    self.assertTrue(tracker.update((first,)))
    self.assertTrue(tracker.update((first, second)))
    self.assertFalse(tracker.update((first, second)))

  def test_resets_when_disabled_or_empty(self):
    tracker = CutinAlertTracker()
    lead = candidate(10, 20.0, 1.5)
    self.assertTrue(tracker.update((lead,)))
    self.assertFalse(tracker.update((lead,), enabled=False))
    self.assertTrue(tracker.update((lead,)))
    self.assertFalse(tracker.update(()))
    self.assertTrue(tracker.update((lead,)))

  def test_waits_until_promoted_to_lead_two(self):
    tracker = CutinAlertTracker()
    detected = candidate(2015, 9.8, -0.13, -1.2)
    self.assertFalse(tracker.update(promoted_cutin_candidates((detected,), None)))
    self.assertTrue(tracker.update(promoted_cutin_candidates((detected,), detected)))
    self.assertFalse(tracker.update(promoted_cutin_candidates((detected,), detected)))

  def test_ignores_lead_two_that_is_not_the_detected_cutin(self):
    detected = candidate(2015, 9.8, -0.13, -1.2)
    other_lead_two = candidate(49, 14.0, 0.0, 0.0)
    self.assertEqual(promoted_cutin_candidates((detected,), other_lead_two), ())

  def test_promotion_rejects_cross_sensor_track_id_collision(self):
    detected = candidate(42, 20.0, 2.0, -1.0)
    other_lead_two = candidate(42, 24.0, 0.0, -1.0)
    self.assertEqual(promoted_cutin_candidates((detected,), other_lead_two), ())


if __name__ == "__main__":
  unittest.main()
