"""Tests for the section (point-to-point average) allowance math.

Pure-class tests ported from the cp speedcam semantics (cb65544e9 /
c777ccfe2) adapted to sp's SectionAverage placement: the caller supplies a
monotonic clock and the wheel-integrated total distance.
"""
import unittest

from openpilot.sunnypilot.carrot.section_average import (
  MAX_ALLOWANCE_KPH, SECTION_END_DEBOUNCE_S,
  SectionAverage,
)


class TestSectionAverage(unittest.TestCase):
  def setUp(self):
    self.sa = SectionAverage()

  # ---- activation / restart ---------------------------------------------

  def test_inactive_by_default(self):
    self.assertFalse(self.sa.active)
    self.assertEqual(self.sa.bank_seconds(100.0, 5000.0, 0.0), 0.0)
    self.assertEqual(self.sa.allowance_kph(100.0, 5000.0, 0.0), 0.0)

  def test_activate_sets_reference_point(self):
    self.sa.update(True, 100.0, 10.0, 1000.0)
    self.assertTrue(self.sa.active)
    self.assertEqual(self.sa.limit_kph, 100.0)
    self.assertEqual(self.sa.start_time, 10.0)
    self.assertEqual(self.sa.start_distance, 1000.0)

  def test_limit_change_restarts_bank(self):
    self.sa.update(True, 100.0, 10.0, 1000.0)
    # 60 s on the road at target pace would bank ~0; a limit change must
    # restart the measurement, not let the old bank leak into the new section.
    self.sa.update(True, 80.0, 70.0, 2000.0)
    self.assertEqual(self.sa.limit_kph, 80.0)
    self.assertEqual(self.sa.start_time, 70.0)
    self.assertEqual(self.sa.start_distance, 2000.0)

  # ---- debounce ----------------------------------------------------------

  def test_single_frame_drop_does_not_end_section(self):
    self.sa.update(True, 100.0, 10.0, 1000.0)
    self.sa.update(False, 0.0, 11.0, 1000.0)
    self.sa.update(True, 100.0, 12.0, 1100.0)
    self.assertTrue(self.sa.active)
    # The bank reference survived the one-frame drop.
    self.assertEqual(self.sa.start_time, 10.0)

  def test_sustained_drop_ends_section_after_debounce(self):
    self.sa.update(True, 100.0, 10.0, 1000.0)
    self.sa.update(False, 0.0, 11.0, 1000.0)
    self.sa.update(False, 0.0, 11.0 + SECTION_END_DEBOUNCE_S, 1100.0)
    self.assertFalse(self.sa.active)

  def test_reactivation_after_end_restarts(self):
    self.test_sustained_drop_ends_section_after_debounce()
    self.sa.update(True, 100.0, 20.0, 2000.0)
    self.assertTrue(self.sa.active)
    self.assertEqual(self.sa.start_time, 20.0)
    self.assertEqual(self.sa.start_distance, 2000.0)

  # ---- bank math ---------------------------------------------------------

  def test_bank_zero_at_target_pace(self):
    # limit 90, margin 0 -> target 25 m/s. 1000 s over 25000 m is exactly on pace.
    self.sa.update(True, 90.0, 0.0, 0.0)
    bank = self.sa.bank_seconds(1000.0, 25000.0, 0.0)
    self.assertAlmostEqual(bank, 0.0, delta=1e-9)
    self.assertEqual(self.sa.allowance_kph(1000.0, 25000.0, 0.0), 0.0)

  def test_bank_positive_in_congestion(self):
    # limit 90, margin 0 -> target 25 m/s. Crawling 5 m/s for 1000 s covers
    # 5000 m: bank = 1000 - 5000/25 = 800 s.
    self.sa.update(True, 90.0, 0.0, 0.0)
    bank = self.sa.bank_seconds(1000.0, 5000.0, 0.0)
    self.assertAlmostEqual(bank, 800.0, delta=1e-9)

  def test_bank_negative_when_speeding(self):
    self.sa.update(True, 90.0, 0.0, 0.0)
    # 30 m/s for 100 s covers 3000 m; on-pace time is 3000/25 = 120 s.
    self.assertLess(self.sa.bank_seconds(100.0, 3000.0, 0.0), 0.0)

  def test_margin_raises_target_and_reduces_bank(self):
    self.sa.update(True, 90.0, 0.0, 0.0)
    # margin 9 -> target 81 kph = 22.5 m/s: bank = 1000 - 5000/22.5 < 800.
    bank0 = self.sa.bank_seconds(1000.0, 5000.0, 0.0)
    bank9 = self.sa.bank_seconds(1000.0, 5000.0, 9.0)
    self.assertLess(bank9, bank0)

  # ---- allowance ---------------------------------------------------------

  def test_no_allowance_below_min_bank(self):
    self.sa.update(True, 90.0, 0.0, 0.0)
    # target 25 m/s; at t=100 s a distance of 2490 m gives bank = 100 - 2490/25
    # = 0.4 s, below MIN_BANK_S (0.5): no allowance even though the bank is
    # technically positive.
    self.assertEqual(self.sa.allowance_kph(100.0, 2490.0, 0.0), 0.0)

  def test_allowance_spend_horizon(self):
    # Bank of 800 s at target 25 m/s: remaining = 40 s over the 1000 m horizon
    # -> 25 m/s... no: remaining_time = 1000/25 - 800 = -760 -> capped at 250.
    self.sa.update(True, 90.0, 0.0, 0.0)
    allowance = self.sa.allowance_kph(1000.0, 5000.0, 0.0)
    self.assertEqual(allowance, MAX_ALLOWANCE_KPH)

  def test_allowance_between_pace_and_cap(self):
    # A modest bank: 26 s over target 25 m/s. remaining = 40 - 26 = 14 s for
    # 1000 m -> 71.4 m/s -> 257 kph -> capped. Use a bigger horizon-relative
    # bank instead: 30 s -> remaining 10 s -> 100 m/s -> 360 -> capped again.
    # The uncapped branch needs remaining > 13.9 s, i.e. bank < 26.1 s.
    self.sa.update(True, 90.0, 0.0, 0.0)
    # Travel exactly on-pace for 974 s, then idle 10 s (traffic) covers 0 m:
    # bank = 10 s -> remaining = 30 s -> 1000/30 = 33.3 m/s = 120 kph.
    self.sa.update(True, 90.0, 984.0, 974.0 * 25.0)
    allowance = self.sa.allowance_kph(984.0, 974.0 * 25.0, 0.0)
    self.assertAlmostEqual(allowance, 1000.0 / 30.0 * 3.6, delta=0.01)

  def test_allowance_never_lowers_cap(self):
    # allowance 0 means the caller keeps the plain section limit.
    self.sa.update(True, 90.0, 0.0, 0.0)
    # Exactly on pace -> no allowance.
    self.assertEqual(self.sa.allowance_kph(100.0, 100.0 * 25.0, 0.0), 0.0)

  # ---- edge inputs -------------------------------------------------------

  def test_update_with_zero_limit_ignored(self):
    self.sa.update(True, 0.0, 10.0, 1000.0)
    self.assertFalse(self.sa.active)


if __name__ == '__main__':
  unittest.main()
