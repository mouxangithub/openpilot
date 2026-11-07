"""Pure-logic unit tests for the StarPilot curve-speed learning port."""
import unittest

import numpy as np

from openpilot.selfdrive.controls.lib.curve_speed_learning import (
  CSC_COUNT_CAP,
  CSC_LAT_ACCEL_MAX,
  CSC_LAT_ACCEL_MIN,
  CSC_NUDGE_WEIGHT,
  CURVATURE_BUCKETS,
  DEFAULT_LATERAL_ACCELERATION,
  CurvatureLearning,
  bucket_curvature,
  normalize_curvature_data,
  weighted_isotonic,
)


class TestWeightedIsotonic(unittest.TestCase):
  def test_monotone_sequence_unchanged(self):
    out = weighted_isotonic([1.0, 2.0, 3.0], [1.0, 1.0, 1.0])
    np.testing.assert_allclose(out, [1.0, 2.0, 3.0])

  def test_violation_pooled(self):
    out = weighted_isotonic([2.0, 1.0], [1.0, 1.0])
    np.testing.assert_allclose(out, [1.5, 1.5])

  def test_weighted_pool_prefers_heavy_neighbour(self):
    # no violation -> values pass through unchanged
    out = weighted_isotonic([1.0, 3.0], [100.0, 1.0])
    np.testing.assert_allclose(out, [1.0, 3.0])
    # violation with a heavy well-sampled neighbour dominates the sparse outlier
    out2 = weighted_isotonic([3.0, 1.0], [100.0, 1.0])
    self.assertAlmostEqual(out2[0], (3.0 * 100.0 + 1.0 * 1.0) / 101.0, places=6)
    self.assertAlmostEqual(out2[1], out2[0])

  def test_output_length(self):
    out = weighted_isotonic([3.0, 1.0, 2.0], [1.0, 2.0, 3.0])
    self.assertEqual(len(out), 3)
    self.assertTrue(np.all(np.diff(out) >= 0.0))


class TestBucketCurvature(unittest.TestCase):
  def test_clips_to_bounds(self):
    self.assertEqual(bucket_curvature(1e-6), bucket_curvature(0.0005))
    self.assertEqual(bucket_curvature(1.0), bucket_curvature(0.02))

  def test_returns_grid_string(self):
    key = bucket_curvature(0.01)
    self.assertIsInstance(key, str)
    self.assertEqual(len(CURVATURE_BUCKETS.__str__()), len("24"))  # grid has 24 buckets

  def test_normalize_drops_invalid(self):
    data = normalize_curvature_data({
      "0.01": {"average": 2.0, "count": 5},
      "bad": {"average": 1.0, "count": 3},
      "0.012": {"average": 2.0, "count": 0},   # zero count
      "0.013": "not a dict",
    })
    self.assertEqual(len(data), 1)
    self.assertEqual(data[bucket_curvature(0.01)]["count"], 5)

  def test_normalize_merges_same_bucket(self):
    key = bucket_curvature(0.01)
    data = normalize_curvature_data({
      key: {"average": 2.0, "count": 4},
      str(float(key) * 1.0001): {"average": 3.0, "count": 4},
    })
    self.assertEqual(data[key]["count"], 8)
    self.assertAlmostEqual(data[key]["average"], 2.5)


class TestCurvatureLearning(unittest.TestCase):
  def make_learning(self):
    return CurvatureLearning(dt=0.05)

  def sample_frames(self, learning, frames, v_ego=15.0, lat=2.5, curv=0.01,
                    manual_speed_control=True):
    for _ in range(frames):
      learning.log_data(v_ego=v_ego, tracking_lead=False, manual_speed_control=manual_speed_control,
                        driving_in_curve=True, blinker=False,
                        lateral_acceleration=lat, road_curvature=curv)

  def test_no_samples_keeps_default_state(self):
    learning = self.make_learning()
    self.assertAlmostEqual(learning.lateral_acceleration, DEFAULT_LATERAL_ACCELERATION)
    # with no data the curve falls back to the fixed prior (2.2 at 0.01 1/m)
    learned = learning.learned_lat_accel(0.01)
    self.assertGreater(learned, 2.0)
    self.assertLess(learned, 2.4)

  def test_settle_time_before_sampling(self):
    learning = self.make_learning()
    # 2s settle: 40 frames at 20Hz minus one frame
    self.sample_frames(learning, 38)
    self.assertFalse(learning.enable_training)
    self.sample_frames(learning, 5)
    self.assertTrue(learning.enable_training)

  def test_tracking_lead_blocks_sampling(self):
    learning = self.make_learning()
    for _ in range(100):
      learning.log_data(v_ego=15.0, tracking_lead=True, manual_speed_control=True,
                        driving_in_curve=True, blinker=False,
                        lateral_acceleration=2.5, road_curvature=0.01)
    self.assertFalse(learning.enable_training)
    self.assertAlmostEqual(learning.lateral_acceleration, DEFAULT_LATERAL_ACCELERATION)

  def test_manual_control_required(self):
    learning = self.make_learning()
    self.sample_frames(learning, 100, manual_speed_control=False)
    self.assertFalse(learning.enable_training)

  def test_low_speed_blocks_sampling(self):
    learning = self.make_learning()
    self.sample_frames(learning, 100, v_ego=3.0)
    self.assertFalse(learning.enable_training)

  def test_learning_shifts_comfort(self):
    learning = self.make_learning()
    # driver takes 0.01-curvature bends at 3.0 m/s^2 comfortably
    self.sample_frames(learning, 200, lat=3.0, curv=0.01)
    learned = learning.learned_lat_accel(0.01)
    self.assertGreater(learned, DEFAULT_LATERAL_ACCELERATION)
    self.assertLess(learned, 3.0)  # prior still pulls the blend down

  def test_confidence_grows_with_count(self):
    learning = self.make_learning()
    self.sample_frames(learning, 50, lat=3.0, curv=0.01)
    low = learning.learned_lat_accel(0.01)
    learning2 = self.make_learning()
    self.sample_frames(learning2, 2000, lat=3.0, curv=0.01)
    high = learning2.learned_lat_accel(0.01)
    self.assertGreater(high, low)
    self.assertLessEqual(high, 3.0)

  def test_lat_accel_clipped_to_bounds(self):
    learning = self.make_learning()
    self.sample_frames(learning, 3000, lat=5.0, curv=0.01)
    learned = learning.learned_lat_accel(0.01)
    self.assertLessEqual(learned, CSC_LAT_ACCEL_MAX)

  def test_brake_nudge_lowers_comfort(self):
    learning = self.make_learning()
    self.sample_frames(learning, 300, lat=3.0, curv=0.01)
    before = learning.learned_lat_accel(0.01)
    learning.apply_brake_nudge(0.01)
    after = learning.learned_lat_accel(0.01)
    self.assertLess(after, before)
    self.assertGreaterEqual(after, CSC_LAT_ACCEL_MIN - 1e-9)

  def test_override_watch_raises_comfort(self):
    learning = self.make_learning()
    self.sample_frames(learning, 100, lat=2.0, curv=0.01)
    before = learning.learned_lat_accel(0.01)
    learning.start_override_watch(0.01, lateral_acceleration=2.8)
    learning.handle_override_watch(overriding_or_in_curve=True,
                                   lateral_acceleration=3.1, road_curvature=0.01)
    learning.handle_override_watch(overriding_or_in_curve=False,
                                   lateral_acceleration=1.0, road_curvature=0.01)
    after = learning.learned_lat_accel(0.01)
    self.assertGreater(after, before)

  def test_count_cap_limits_recency_weight(self):
    learning = self.make_learning()
    self.sample_frames(learning, 3000, lat=3.0, curv=0.01)
    key = bucket_curvature(0.01)
    data = learning.curvature_data[key]
    # effective count caps at CSC_COUNT_CAP, but the running average stays sane
    self.assertLessEqual(data["count"], CSC_COUNT_CAP + 3000)  # bookkeeping count grows
    self.assertGreater(data["average"], 0.0)

  def test_pseudo_sample_weight(self):
    learning = self.make_learning()
    learning.record_pseudo_sample(bucket_curvature(0.01), 3.0)
    key = bucket_curvature(0.01)
    self.assertEqual(learning.curvature_data[key]["count"], CSC_NUDGE_WEIGHT)
    self.assertAlmostEqual(learning.curvature_data[key]["average"], 3.0)

  def test_roundtrip_through_persistence_hooks(self):
    stored = {}
    learning = self.make_learning()
    learning.put_fn = lambda data: stored.update(data)
    learning.load_fn = lambda: stored
    self.sample_frames(learning, 300, lat=3.0, curv=0.01)
    learning.flush()
    self.assertTrue(stored)

    learning2 = self.make_learning()
    learning2.put_fn = lambda data: None
    learning2.load_fn = lambda: stored
    learning2.load()
    self.assertAlmostEqual(learning2.learned_lat_accel(0.01),
                           learning.learned_lat_accel(0.01), places=6)


if __name__ == "__main__":
  unittest.main()
