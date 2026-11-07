"""Pure-logic unit tests for the StarPilot duplicate-lead guard port.

Covers near-duplicate detection, source hysteresis bias, identical-radar
source hold and the ratcheted duplicate-vision comfort filters.
"""
import unittest
from types import SimpleNamespace


from openpilot.selfdrive.controls.lib.lead_duplicate_policy import (
  DUPLICATE_VISION_LEAD_FILTER_TIME,
  NEAR_DUPLICATE_IDENTICAL_RADAR_SOURCE_KEEP_MARGIN,
  NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MAX,
  NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MIN,
  NEAR_DUPLICATE_LEAD_SOURCE_MAX_VREL_DIFF,
  DuplicateVisionLeadFilters,
  identical_radar_duplicate_source_hold,
  leads_are_near_duplicates,
  leads_share_identical_radar_track,
  near_duplicate_lead_source_hysteresis,
)

DT = 0.05


def make_lead(radar=False, d_rel=50.0, v_rel=0.0, a_lead=0.0, prob=0.99,
              track_id=-1, present=True):
  return SimpleNamespace(present=present, status=present, radar=radar, dRel=d_rel,
                         vRel=v_rel, aLeadK=a_lead, modelProb=prob, radarTrackId=track_id)


class TestLeadsShareIdenticalRadarTrack(unittest.TestCase):
  def test_same_track_id(self):
    a = make_lead(track_id=7)
    b = make_lead(track_id=7)
    self.assertTrue(leads_share_identical_radar_track(a, b))

  def test_different_track_id(self):
    a = make_lead(track_id=7)
    b = make_lead(track_id=8)
    self.assertFalse(leads_share_identical_radar_track(a, b))

  def test_invalid_track_id(self):
    a = make_lead(track_id=-1)
    b = make_lead(track_id=-1)
    self.assertFalse(leads_share_identical_radar_track(a, b))

  def test_none_lead(self):
    self.assertFalse(leads_share_identical_radar_track(None, make_lead(track_id=1)))


class TestLeadsAreNearDuplicates(unittest.TestCase):
  def test_identical_radar_pair_within_tolerance(self):
    a = make_lead(radar=True, d_rel=50.0, v_rel=1.0, track_id=3)
    b = make_lead(radar=True, d_rel=50.8, v_rel=1.2, track_id=3)
    self.assertTrue(leads_are_near_duplicates(a, b, v_ego=20.0))

  def test_identical_radar_pair_too_far_apart(self):
    a = make_lead(radar=True, d_rel=50.0, track_id=3)
    b = make_lead(radar=True, d_rel=53.0, track_id=3)
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=20.0))

  def test_identical_radar_low_speed_rejected(self):
    a = make_lead(radar=True, d_rel=50.0, track_id=3)
    b = make_lead(radar=True, d_rel=50.0, track_id=3)
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=9.0))

  def test_vision_pair(self):
    a = make_lead(radar=False, d_rel=40.0, v_rel=0.5, prob=0.95)
    b = make_lead(radar=False, d_rel=40.8, v_rel=0.6, prob=0.95)
    self.assertTrue(leads_are_near_duplicates(a, b, v_ego=15.0))

  def test_vision_pair_one_radar_rejected(self):
    a = make_lead(radar=True, d_rel=40.0, prob=0.95)
    b = make_lead(radar=False, d_rel=40.5, prob=0.95)
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=15.0))

  def test_vision_pair_low_prob_rejected(self):
    a = make_lead(radar=False, d_rel=40.0, prob=0.85)
    b = make_lead(radar=False, d_rel=40.5, prob=0.95)
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=15.0))

  def test_vision_pair_braking_lead_rejected(self):
    a = make_lead(radar=False, d_rel=40.0, a_lead=-0.5)
    b = make_lead(radar=False, d_rel=40.5, a_lead=0.0)
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=15.0))

  def test_vision_pair_low_speed_rejected(self):
    a = make_lead(radar=False, d_rel=40.0)
    b = make_lead(radar=False, d_rel=40.5)
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=3.0))

  def test_vision_min_speed_override(self):
    a = make_lead(radar=False, d_rel=40.0)
    b = make_lead(radar=False, d_rel=40.5)
    # default min speed is 4.0 -> 3.0 m/s rejected
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=3.0))
    # lowered threshold accepts the same pair
    self.assertTrue(leads_are_near_duplicates(a, b, v_ego=3.0, vision_min_speed=2.0))

  def test_inactive_lead_rejected(self):
    a = make_lead(present=False)
    b = make_lead()
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=20.0))

  def test_vrel_tolerance(self):
    a = make_lead(radar=False, d_rel=40.0, v_rel=0.0)
    b = make_lead(radar=False, d_rel=40.5, v_rel=NEAR_DUPLICATE_LEAD_SOURCE_MAX_VREL_DIFF + 0.01)
    self.assertFalse(leads_are_near_duplicates(a, b, v_ego=15.0))


class TestNearDuplicateSourceHysteresis(unittest.TestCase):
  def make_vision_pair(self):
    return make_lead(radar=False, d_rel=40.0), make_lead(radar=False, d_rel=40.5)

  def test_no_prev_source_gives_no_bias(self):
    a, b = self.make_vision_pair()
    self.assertEqual(near_duplicate_lead_source_hysteresis(None, a, b, 20.0), (0.0, 0.0))

  def test_lead0_hold_biases_lead1(self):
    a, b = self.make_vision_pair()
    bias0, bias1 = near_duplicate_lead_source_hysteresis("lead0", a, b, 20.0)
    self.assertEqual(bias0, 0.0)
    self.assertGreater(bias1, 0.0)

  def test_lead1_hold_biases_lead0(self):
    a, b = self.make_vision_pair()
    bias0, bias1 = near_duplicate_lead_source_hysteresis("lead1", a, b, 20.0)
    self.assertGreater(bias0, 0.0)
    self.assertEqual(bias1, 0.0)

  def test_hysteresis_scales_with_speed(self):
    a, b = self.make_vision_pair()
    low = near_duplicate_lead_source_hysteresis("lead0", a, b, 4.0)[1]
    high = near_duplicate_lead_source_hysteresis("lead0", a, b, 35.0)[1]
    self.assertAlmostEqual(low, NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MIN, places=6)
    self.assertAlmostEqual(high, NEAR_DUPLICATE_LEAD_SOURCE_HYSTERESIS_MAX, places=6)

  def test_not_duplicates_gives_no_bias(self):
    a = make_lead(radar=False, d_rel=40.0)
    b = make_lead(radar=False, d_rel=80.0)
    self.assertEqual(near_duplicate_lead_source_hysteresis("lead0", a, b, 20.0), (0.0, 0.0))


class TestIdenticalRadarSourceHold(unittest.TestCase):
  def test_holds_within_margin(self):
    a = make_lead(track_id=5)
    b = make_lead(track_id=5)
    hold = identical_radar_duplicate_source_hold("lead0", a, b, 100.0, 100.2)
    self.assertEqual(hold, "lead0")

  def test_releases_when_profiles_diverge(self):
    a = make_lead(track_id=5)
    b = make_lead(track_id=5)
    hold = identical_radar_duplicate_source_hold(
      "lead0", a, b, 100.0, 100.0 + NEAR_DUPLICATE_IDENTICAL_RADAR_SOURCE_KEEP_MARGIN + 0.1)
    self.assertIsNone(hold)

  def test_no_hold_without_prev_source(self):
    a = make_lead(track_id=5)
    b = make_lead(track_id=5)
    self.assertIsNone(identical_radar_duplicate_source_hold(None, a, b, 100.0, 100.0))

  def test_no_hold_for_different_tracks(self):
    a = make_lead(track_id=5)
    b = make_lead(track_id=6)
    self.assertIsNone(identical_radar_duplicate_source_hold("lead0", a, b, 100.0, 100.0))


class TestDuplicateVisionLeadFilters(unittest.TestCase):
  def test_first_update_initializes_directly(self):
    filters = DuplicateVisionLeadFilters(DT)
    x, v, a = filters.apply(0, 50.0, 20.0, 0.0)
    self.assertAlmostEqual(x, 50.0)
    self.assertAlmostEqual(v, 20.0)
    self.assertAlmostEqual(a, 0.0)

  def test_smoothing_lags_input(self):
    filters = DuplicateVisionLeadFilters(DT)
    filters.apply(0, 50.0, 20.0, 0.0)
    # distance *increases* -> smoothed value lags behind the jump
    x, _, _ = filters.apply(0, 55.0, 20.0, 0.0)
    self.assertLess(x, 55.0)
    self.assertGreater(x, 50.0)
    # distance *decreases* -> ratchet passes closers through instantly
    x, _, _ = filters.apply(0, 48.0, 20.0, 0.0)
    self.assertAlmostEqual(x, 48.0)

  def test_ratchet_lets_closer_distance_through(self):
    filters = DuplicateVisionLeadFilters(DT)
    filters.apply(0, 50.0, 20.0, 0.0)
    x, _, _ = filters.apply(0, 30.0, 20.0, 0.0)  # sudden closer measurement
    self.assertAlmostEqual(x, 30.0)

  def test_invalidate_resets_to_raw(self):
    filters = DuplicateVisionLeadFilters(DT)
    filters.apply(0, 50.0, 20.0, 0.0)
    filters.invalidate()
    x, v, a = filters.apply(0, 42.0, 18.0, -0.5)
    self.assertAlmostEqual(x, 42.0)
    self.assertAlmostEqual(v, 18.0)
    self.assertAlmostEqual(a, -0.5)

  def test_filters_are_per_lead(self):
    filters = DuplicateVisionLeadFilters(DT)
    filters.apply(0, 50.0, 20.0, 0.0)
    x1, _, _ = filters.apply(1, 70.0, 25.0, 0.0)
    self.assertAlmostEqual(x1, 70.0)  # lead1 filter untouched by lead0 history

  def test_filter_time_constant(self):
    self.assertEqual(DUPLICATE_VISION_LEAD_FILTER_TIME, 0.15)


if __name__ == "__main__":
  unittest.main()
