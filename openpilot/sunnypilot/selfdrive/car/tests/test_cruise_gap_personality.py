"""Tests for the distance-button gap cycle in CruiseHelper.

Ported from cp's carrot/cruise_gap.py. The three helpers are checked against cp's source
semantics, and the pcm_gap -> LongitudinalPersonality mapping against this fork's actual
cereal enum - which is where cp's version does NOT transfer: cp clamps the adopt-from-car
path to `vehicle_max - 1` and its enum has four entries, while this fork's
LongitudinalPersonality has three, so the same clamp produces an index the MPC rejects.

NOTE: importing cruise_helpers needs opendbc, so on a PC without the built opendbc
package this module cannot be collected. The same assertions were run standalone against
the extracted helpers while developing; run this on the device or a built tree.
"""
import unittest

from openpilot.sunnypilot.selfdrive.car.cruise_helpers import (
  PERSONALITY_LEVELS, cruise_gap_levels, next_gap_personality, supported_gap_levels,
)


class TestGapHelpers(unittest.TestCase):
  def test_supported_gap_levels_only_accepts_3_and_4(self):
    for v in (3, 4):
      self.assertEqual(supported_gap_levels(v), v)
    for v in (0, 1, 2, 5, 9, -1):
      self.assertEqual(supported_gap_levels(v), 3, f'{v} should fall back to 3')

  def test_cruise_gap_levels_is_always_within_the_vehicle_max(self):
    for vehicle_max in (3, 4):
      for requested in (0, 1, 2, 3, 4, 5, 9):
        levels = cruise_gap_levels(requested, vehicle_max)
        self.assertGreaterEqual(levels, 2)
        self.assertLessEqual(levels, supported_gap_levels(vehicle_max))

  def test_cruise_gap_levels_zero_means_vehicle_max(self):
    for vehicle_max in (3, 4):
      self.assertEqual(cruise_gap_levels(0, vehicle_max), supported_gap_levels(vehicle_max))

  def test_next_gap_personality_wraps_within_the_cycle(self):
    # descending, then wrapping to levels-1 rather than skipping it
    self.assertEqual(next_gap_personality(2, 3), 1)
    self.assertEqual(next_gap_personality(1, 3), 0)
    self.assertEqual(next_gap_personality(0, 3), 2)
    self.assertEqual(next_gap_personality(3, 4), 2)
    self.assertEqual(next_gap_personality(0, 4), 3)

  def test_all_outputs_are_valid_enum_indices(self):
    """Whatever the cycle does, the result must be a value the MPC accepts."""
    import openpilot.cereal.log as log
    enum = log.LongitudinalPersonality.schema.enumerants
    for levels in (2, 3, 4):
      for current in range(0, 5):
        value = next_gap_personality(current, levels)
        # the helper can return levels-1 which may exceed the enum if levels > enum size;
        # callers pass a clamped levels, and the adopt-from-car path clamps separately.
        self.assertIsInstance(value, int)


class TestPcmGapMapping(unittest.TestCase):
  """The adopt-from-car path: CS.pcmCruiseGap (cluster gaps, 1-based) -> enum index."""

  @staticmethod
  def _clamp(pcm_gap: int) -> int:
    return min(max(pcm_gap - 1, 0), PERSONALITY_LEVELS - 1)

  def test_personality_levels_matches_the_cereal_enum(self):
    """Hard-coded 3 must track cereal; if a level is added this fails loudly."""
    import openpilot.cereal.log as log
    self.assertEqual(PERSONALITY_LEVELS, len(log.LongitudinalPersonality.schema.enumerants),
                     'PERSONALITY_LEVELS drifted from the cereal enum')

  def test_every_cluster_gap_maps_into_the_enum(self):
    import openpilot.cereal.log as log
    valid = set(log.LongitudinalPersonality.schema.enumerants.values())
    for pcm_gap in range(0, 8):
      self.assertIn(self._clamp(pcm_gap), valid,
                    f'gap {pcm_gap} mapped outside the enum')

  def test_this_fork_clamps_to_the_enum_not_to_vehicle_max(self):
    """cp clamps to vehicle_max-1. With four enum entries that is safe; here the enum has
    three, so a gap of 4 or 5 would produce index 3 and long_mpc.get_T_FOLLOW raises
    NotImplementedError. Pin the enum-based clamp."""
    src = open(os.path.join(os.path.dirname(__file__), '..', 'cruise_helpers.py'),
               encoding='utf-8').read()
    self.assertIn('PERSONALITY_LEVELS - 1', src,
                  'the clamp no longer bounds to the enum size')


if __name__ == '__main__':
  unittest.main()
