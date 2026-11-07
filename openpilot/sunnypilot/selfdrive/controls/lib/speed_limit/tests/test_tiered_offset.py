"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tiered speed-limit offsets: the band table and the resolver wiring.

Two things are locked here:

  * the band table itself (which limit belongs to which band), because the UI
    labels and the resolver both read it and a disagreement would show the
    user the wrong row for the limit they are driving on;
  * the resolver's use of it, including the unit handling and the "no limit
    yet" case.
"""

import unittest

from openpilot.common.constants import CV
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.tiered_offset import (
  TIER_COUNT,
  TIER_EDGES_KPH,
  TIER_EDGES_MPH,
  TIER_HIGHEST,
  TIER_KEY_SUFFIXES,
  TIER_LOWEST,
  tier_edges,
  tier_for_limit,
  tier_label,
  tier_range_kph,
  tiered_offset_ms,
)


class TestTierTable(unittest.TestCase):
  def test_band_edges_and_count(self):
    # Seven bands: the lowest one, one per remaining edge, and the open-ended top.
    self.assertEqual(len(TIER_EDGES_KPH), 6)
    self.assertEqual(TIER_COUNT, 7)
    self.assertEqual(len(TIER_KEY_SUFFIXES), TIER_COUNT)

  def test_lowest_band_covers_up_to_first_edge(self):
    for limit in (1, 15, 29, 30):
      self.assertEqual(tier_for_limit(limit), TIER_LOWEST, limit)

  def test_limit_exactly_on_an_edge_stays_in_that_band(self):
    # A 60 km/h sign is the 60 band, not the 80 one.
    self.assertEqual(tier_for_limit(60), tier_for_limit(59))
    self.assertEqual(tier_for_limit(80), tier_for_limit(79))
    self.assertEqual(tier_for_limit(120), tier_for_limit(119))
    # ... and the next value up moves to the next band.
    self.assertNotEqual(tier_for_limit(61), tier_for_limit(60))

  def test_a_limit_on_an_edge_survives_float_conversion(self):
    # 60 km/h -> m/s -> km/h is 60.00000000000001, which would land in the
    # next band without a tolerance. A sign on the edge must use the band it
    # names, or the driver gets the wrong offset on exactly the roads where
    # the band boundary is drawn.
    ms = 60 * CV.KPH_TO_MS
    self.assertGreater(ms * CV.MS_TO_KPH, 60.0)
    self.assertEqual(tier_for_limit(ms * CV.MS_TO_KPH, is_metric=True), tier_for_limit(60, is_metric=True))
    self.assertEqual(tier_for_limit(ms * CV.MS_TO_KPH, is_metric=True), 2)

  def test_every_edge_survives_the_round_trip(self):
    for edge in TIER_EDGES_KPH:
      ms = edge * CV.KPH_TO_MS
      self.assertEqual(tier_for_limit(ms * CV.MS_TO_KPH, is_metric=True),
                       tier_for_limit(edge, is_metric=True), edge)

  def test_top_band_is_open_ended(self):
    for limit in (121, 150, 300):
      self.assertEqual(tier_for_limit(limit), TIER_HIGHEST, limit)
    low, high = tier_range_kph(TIER_HIGHEST)
    self.assertIsNone(high)
    self.assertEqual(low, float(TIER_EDGES_KPH[-1]))

  def test_every_band_is_reachable(self):
    # No band may be dead: a limit that maps to nothing would silently read
    # an offset that does not exist.
    used = {tier_for_limit(v) for v in range(1, 250)}
    self.assertEqual(used, set(range(TIER_COUNT)))

  def test_limit_always_inside_its_own_band(self):
    for limit in list(range(1, 150)) + [200, 250]:
      tier = tier_for_limit(limit)
      low, high = tier_range_kph(tier)
      if high is None:
        self.assertGreaterEqual(limit, low)
      else:
        self.assertGreaterEqual(limit, low)
        self.assertLessEqual(limit, high)

  def test_bands_do_not_overlap(self):
    for tier in range(TIER_COUNT - 1):
      low, high = tier_range_kph(tier)
      next_low, _ = tier_range_kph(tier + 1)
      self.assertEqual(high, next_low, tier)

  def test_label_mentions_the_band(self):
    self.assertIn("30", tier_label(TIER_LOWEST))
    self.assertIn("30-50", tier_label(1))
    self.assertIn("120", tier_label(TIER_HIGHEST))


class TestTieredOffsetMs(unittest.TestCase):
  """The offset the resolver applies, exercised as a pure function.

  The resolver itself pulls in cereal, which cannot be imported on a PC host
  without the compiled msgq module, so the arithmetic lives here where both
  the PC and the device can run it.
  """

  def test_no_limit_means_no_offset(self):
    self.assertEqual(tiered_offset_ms(0.0, [5] * TIER_COUNT, is_metric=True), 0.0)

  def test_empty_tier_list_means_no_offset(self):
    self.assertEqual(tiered_offset_ms(60 * CV.KPH_TO_MS, [], is_metric=True), 0.0)

  def test_picks_the_band_of_the_posted_limit(self):
    # 60 km/h is in the 50-60 band, which is tier 2.
    values = [0, 0, 7, 0, 0, 0, 0]
    self.assertEqual(tier_for_limit(60, is_metric=True), 2)
    self.assertAlmostEqual(
      tiered_offset_ms(60 * CV.KPH_TO_MS, values, is_metric=True),
      7 * CV.KPH_TO_MS, places=6,
    )

  def test_a_different_band_gets_its_own_value(self):
    # 40 km/h is in the 30-50 band (tier 1), which has no value set here.
    values = [0, 0, 7, 0, 0, 0, 0]
    self.assertEqual(tier_for_limit(40, is_metric=True), 1)
    self.assertEqual(tiered_offset_ms(40 * CV.KPH_TO_MS, values, is_metric=True), 0.0)

  def test_uses_the_imperial_unit_when_not_metric(self):
    # 100 mph is above every mph edge, so the top band applies.
    values = [0, 0, 0, 0, 0, 0, 5]
    self.assertAlmostEqual(
      tiered_offset_ms(100 * CV.MPH_TO_MS, values, is_metric=False),
      5 * CV.MPH_TO_MS, places=6,
    )

  def test_the_same_road_lands_in_the_same_band_in_either_unit(self):
    # 60 km/h is 37.3 mph. The metric table puts 60 in the 50-60 band (tier
    # 2); the imperial table puts 37 in the 35-45 band (tier 2 as well). The
    # band is a property of the road, so both must agree on the tier.
    self.assertEqual(tier_for_limit(60, is_metric=True), 2)
    self.assertEqual(tier_for_limit(60 * CV.KPH_TO_MS * CV.MS_TO_MPH, is_metric=False), 2)

  def test_the_two_unit_tables_have_the_same_number_of_bands(self):
    self.assertEqual(len(TIER_EDGES_KPH), len(TIER_EDGES_MPH))
    self.assertEqual(len(tier_edges(True)), len(tier_edges(False)))

  def test_metric_and_imperial_pick_the_same_band_for_the_same_road(self):
    # 60 km/h is 37.3 mph. The metric table puts 60 in the 50-60 band (tier
    # 2); the imperial table puts 37 in the 35-45 band (tier 2 as well). The
    # band is a property of the road, so both must agree on the tier.
    values = [0, 0, 3, 0, 0, 0, 0]
    metric = tiered_offset_ms(60 * CV.KPH_TO_MS, values, is_metric=True)
    imperial = tiered_offset_ms(60 * CV.KPH_TO_MS, values, is_metric=False)
    self.assertAlmostEqual(metric, 3 * CV.KPH_TO_MS, places=6)
    self.assertAlmostEqual(imperial, 3 * CV.MPH_TO_MS, places=6)

  def test_negative_offset_is_allowed(self):
    values = [0, 0, -5, 0, 0, 0, 0]
    self.assertAlmostEqual(
      tiered_offset_ms(60 * CV.KPH_TO_MS, values, is_metric=True),
      -5 * CV.KPH_TO_MS, places=6,
    )


if __name__ == "__main__":
  unittest.main()
