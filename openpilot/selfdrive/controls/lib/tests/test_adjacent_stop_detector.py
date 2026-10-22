"""Pure-logic unit tests for the StarPilot adjacent-lane stopped-vehicle port.

Covers the moving->rest history qualifier, lane geometry, farthest selection
and the queue drop rule. Publishing (radarStateSP) is a separate milestone.
"""
import unittest
from types import SimpleNamespace

import numpy as np

from openpilot.selfdrive.controls.lib.adjacent_stop_detector import (
  ADJACENT_STOP_MAX_D,
  ADJACENT_STOP_MAX_Y,
  ADJACENT_STOP_MIN_Y,
  ADJACENT_STOP_MOVING_FRAMES,
  ADJACENT_STOP_QUEUE_GAP_M,
  ADJACENT_STOP_REST_FRAMES,
  AdjacentStopHistory,
  detect_adjacent_stopped,
  in_adjacent_lane,
  is_adjacent_stopped,
)

# Straight lane lines 2.0 m each side of the model origin
X = np.array([0.0, 120.0])
LEFT_Y = np.array([-2.0, -2.0])   # left boundary: model y < -2.0 is left lane
RIGHT_Y = np.array([2.0, 2.0])    # right boundary: model y > 2.0 is right lane
LANES = (X, LEFT_Y, X, RIGHT_Y)


def make_track(d_rel=40.0, y_rel=-3.0, v_lead=0.0, identifier=1, history=None):
  return SimpleNamespace(dRel=d_rel, yRel=y_rel, vLead=v_lead, identifier=identifier,
                         stop_history=history or AdjacentStopHistory())


def run_history(track, speeds):
  for v in speeds:
    track.stop_history.update_history(v)


class TestAdjacentStopHistory(unittest.TestCase):
  def test_seen_moving_requires_sustained_run(self):
    h = AdjacentStopHistory()
    for _ in range(ADJACENT_STOP_MOVING_FRAMES - 1):
      h.update_history(6.0)
    self.assertFalse(h.seen_moving)
    h.update_history(6.0)
    self.assertTrue(h.seen_moving)

  def test_single_noise_sample_neither_arms_nor_trips(self):
    h = AdjacentStopHistory()
    for _ in range(ADJACENT_STOP_MOVING_FRAMES):
      h.update_history(6.0)
    h.update_history(6.5)  # still moving band
    h.update_history(3.0)  # coasting band resets both runs
    self.assertEqual(h.moving_frames, 0)
    self.assertEqual(h.rest_frames, 0)
    self.assertTrue(h.seen_moving)  # armed stays armed
    self.assertFalse(h.rest_frames >= ADJACENT_STOP_REST_FRAMES)

  def test_rest_frames_accumulate(self):
    h = AdjacentStopHistory()
    for _ in range(ADJACENT_STOP_MOVING_FRAMES):
      h.update_history(6.0)
    for _ in range(ADJACENT_STOP_REST_FRAMES):
      h.update_history(0.5)
    self.assertEqual(h.rest_frames, ADJACENT_STOP_REST_FRAMES)

  def test_parked_car_never_arms(self):
    h = AdjacentStopHistory()
    for _ in range(100):
      h.update_history(0.0)
    self.assertFalse(h.seen_moving)


class TestInAdjacentLane(unittest.TestCase):
  def test_left_lane_qualifies(self):
    # y_rel=-3.0 -> model y=3.0 > right boundary 2.0
    self.assertTrue(in_adjacent_lane(40.0, -3.0, LANES))

  def test_own_lane_rejected(self):
    self.assertFalse(in_adjacent_lane(40.0, -1.0, LANES))

  def test_roadside_rejected(self):
    self.assertFalse(in_adjacent_lane(40.0, -8.5, LANES))

  def test_distance_bounds(self):
    self.assertFalse(in_adjacent_lane(0.0, -3.0, LANES))
    self.assertFalse(in_adjacent_lane(ADJACENT_STOP_MAX_D + 1.0, -3.0, LANES))

  def test_y_bounds(self):
    self.assertFalse(in_adjacent_lane(40.0, -(ADJACENT_STOP_MIN_Y - 0.5), LANES))
    self.assertFalse(in_adjacent_lane(40.0, -(ADJACENT_STOP_MAX_Y + 0.5), LANES))


class TestIsAdjacentStopped(unittest.TestCase):
  def make_qualified(self, **kwargs):
    track = make_track(**kwargs)
    run_history(track, [6.0] * ADJACENT_STOP_MOVING_FRAMES + [0.5] * ADJACENT_STOP_REST_FRAMES)
    return track

  def test_qualified_stopped_vehicle(self):
    self.assertTrue(is_adjacent_stopped(self.make_qualified(), LANES))

  def test_no_history_rejected(self):
    self.assertFalse(is_adjacent_stopped(make_track(), LANES))

  def test_moving_but_not_stopped_rejected(self):
    track = make_track()
    run_history(track, [6.0] * 50)
    self.assertFalse(is_adjacent_stopped(track, LANES))

  def test_own_lead_track_rejected(self):
    track = self.make_qualified(identifier=7)
    self.assertFalse(is_adjacent_stopped(track, LANES, lead_track_ids={7}))

  def test_curved_lane_geometry(self):
    # boundary at 3.0 m: y_rel=-2.5 (model y 2.5) stays inside -> rejected
    curved = (X, LEFT_Y, X, np.array([3.0, 3.0]))
    self.assertFalse(is_adjacent_stopped(self.make_qualified(y_rel=-2.5), curved))


class TestDetectAdjacentStopped(unittest.TestCase):
  def make_qualified(self, **kwargs):
    track = make_track(**kwargs)
    run_history(track, [6.0] * ADJACENT_STOP_MOVING_FRAMES + [0.5] * ADJACENT_STOP_REST_FRAMES)
    return track

  def test_no_candidates(self):
    self.assertFalse(detect_adjacent_stopped([], LANES)["status"])
    self.assertFalse(detect_adjacent_stopped([make_track()], LANES)["status"])

  def test_farthest_qualifier_wins(self):
    near = self.make_qualified(d_rel=30.0, identifier=1)
    far = self.make_qualified(d_rel=60.0, identifier=2)
    result = detect_adjacent_stopped([near, far], LANES)
    self.assertTrue(result["status"])
    self.assertAlmostEqual(result["dRel"], 60.0)
    self.assertEqual(result["radarTrackId"], 2)

  def test_queue_past_furthest_drops_hint(self):
    far = self.make_qualified(d_rel=60.0, identifier=2)
    queue_car = make_track(d_rel=60.0 + ADJACENT_STOP_QUEUE_GAP_M + 1.0, v_lead=0.0, identifier=3)
    run_history(queue_car, [6.0])  # parked: never qualified, but slow + in lane
    self.assertFalse(detect_adjacent_stopped([far, queue_car], LANES)["status"])

  def test_slow_car_before_furthest_does_not_drop(self):
    far = self.make_qualified(d_rel=60.0, identifier=2)
    near_slow = make_track(d_rel=40.0, v_lead=0.0, identifier=3)
    result = detect_adjacent_stopped([far, near_slow], LANES)
    self.assertTrue(result["status"])

  def test_result_fields(self):
    track = self.make_qualified(d_rel=45.0, y_rel=-3.5, identifier=9)
    result = detect_adjacent_stopped([track], LANES)
    self.assertAlmostEqual(result["yRel"], -3.5)


if __name__ == "__main__":
  unittest.main()
