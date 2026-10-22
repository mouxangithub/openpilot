"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the adjacent-lane width estimator (cp lane_math/side_state port)."""
from types import SimpleNamespace
import unittest

import numpy as np

from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.selfdrive.modeld.lane_width import (
  LaneWidthEstimator,
  OUTER_LINE_PROB_MIN,
  SMOOTHING_WINDOW,
  calculate_lane_width,
  outer_line_valid,
)


def make_lane(offset_m: float):
  """A lane whose y(t) = t + offset_m, so interp(1.0) is exact and the gap
  between two such lanes is the offset difference at every t."""
  return SimpleNamespace(y=np.asarray(ModelConstants.T_IDXS, dtype=float) + offset_m)


class TestCalculateLaneWidth(unittest.TestCase):
  def test_gap_to_outer_line(self):
    # ego lane bounded by lines at +1 / -1; outer left line at +4 -> width 3 m
    width = calculate_lane_width(make_lane(4.0), make_lane(1.0), make_lane(100.0))
    self.assertAlmostEqual(width, 3.0, places=6)

  def test_clamped_by_road_edge(self):
    # road edge closer than the outer lane line -> edge gap wins
    width = calculate_lane_width(make_lane(4.0), make_lane(1.0), make_lane(2.0))
    self.assertAlmostEqual(width, 1.0, places=6)


class TestOuterLineValid(unittest.TestCase):
  def test_threshold(self):
    self.assertTrue(outer_line_valid(OUTER_LINE_PROB_MIN + 0.01))
    self.assertFalse(outer_line_valid(OUTER_LINE_PROB_MIN - 0.01))
    self.assertFalse(outer_line_valid(0.0))


class TestLaneWidthEstimator(unittest.TestCase):
  def test_first_update_returns_raw_width(self):
    est = LaneWidthEstimator()
    width = est.update(make_lane(4.0), 0.9, make_lane(1.0), make_lane(100.0))
    self.assertAlmostEqual(width, 3.0, places=6)

  def test_running_mean_converges_over_window(self):
    est = LaneWidthEstimator()
    for _ in range(SMOOTHING_WINDOW):
      est.update(make_lane(4.0), 0.9, make_lane(1.0), make_lane(100.0))
    # constant input -> running mean equals the raw width
    self.assertAlmostEqual(est.update(make_lane(4.0), 0.9, make_lane(1.0), make_lane(100.0)), 3.0, places=6)

  def test_step_change_smooths_over_window(self):
    est = LaneWidthEstimator()
    for _ in range(SMOOTHING_WINDOW):
      est.update(make_lane(4.0), 0.9, make_lane(1.0), make_lane(100.0))
    # step to a 6 m width: a single frame moves the mean only partway
    width_one = est.update(make_lane(7.0), 0.9, make_lane(1.0), make_lane(100.0))
    self.assertGreater(width_one, 3.0)
    self.assertLess(width_one, 6.0)
    # a full window later the mean has fully converged
    for _ in range(SMOOTHING_WINDOW):
      est.update(make_lane(7.0), 0.9, make_lane(1.0), make_lane(100.0))
    self.assertAlmostEqual(est.update(make_lane(7.0), 0.9, make_lane(1.0), make_lane(100.0)), 6.0, places=6)


if __name__ == "__main__":
  unittest.main()
