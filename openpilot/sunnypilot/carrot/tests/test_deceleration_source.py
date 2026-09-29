"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Tests for the deceleration-source taxonomy.

The label set must stay in step with the tokens ``carrot_serv`` actually publishes,
so the first job here is to fail if a source appears that has no mapping. That is
the realistic regression: someone adds a speed source and the HUD silently shows a
trimmed internal token instead of a reason.
"""
import re
import unittest

from openpilot.sunnypilot.carrot.deceleration_source import (
  COLOR_APPLY,
  COLOR_EXTERNAL_NAVI,
  COLOR_VEHICLE_NAVI,
  DECELERATION_SOURCE_LABELS,
  EXTERNAL_NAVI_SOURCES,
  VEHICLE_NAVI_SOURCES,
  deceleration_source_presentation,
  external_navigation_connected,
  is_vehicle_navigation_source,
  navigation_status_presentation,
)

# Tokens this fork actually puts into `desired_source`: the speed_n_sources labels
# plus the three display-only ones assigned by carrot_serv's cruise-advisory chain
# (sdi -> turn -> limit). Kept here as the contract this module serves; the live
# check at the bottom reads the real list out of carrot_serv.
PUBLISHED_SOURCES = {
  "atc", "atc2", "sdi", "hda", "hda_bump", "school", "hda_section", "road",
  "route", "vturn", "turn", "limit",
}


class TestPresentation(unittest.TestCase):
  def test_empty_source_reads_as_apply(self):
    self.assertEqual(deceleration_source_presentation(""), ("apply", COLOR_APPLY))
    self.assertEqual(deceleration_source_presentation(None), ("apply", COLOR_APPLY))

  def test_vehicle_navi_is_its_own_colour(self):
    for src in VEHICLE_NAVI_SOURCES:
      _, mode = deceleration_source_presentation(src)
      self.assertEqual(mode, COLOR_VEHICLE_NAVI, src)

  def test_external_navi_is_its_own_colour(self):
    for src in sorted(EXTERNAL_NAVI_SOURCES):
      _, mode = deceleration_source_presentation(src)
      self.assertEqual(mode, COLOR_EXTERNAL_NAVI, src)

  def test_case_and_whitespace_are_normalised(self):
    self.assertEqual(
      deceleration_source_presentation("  ATC  "),
      deceleration_source_presentation("atc"))

  def test_atc_and_atc2_share_the_turn_label(self):
    self.assertEqual(deceleration_source_presentation("atc")[0], "turn")
    self.assertEqual(deceleration_source_presentation("atc2")[0], "turn")

  def test_suffix_n_marks_external(self):
    label, mode = deceleration_source_presentation("cam:n")
    self.assertEqual(label, "cam")
    self.assertEqual(mode, COLOR_EXTERNAL_NAVI)

  def test_suffix_v_marks_vehicle_for_camera_family(self):
    self.assertEqual(deceleration_source_presentation("cam:v")[1], COLOR_VEHICLE_NAVI)
    self.assertEqual(deceleration_source_presentation("bump:v")[1], COLOR_VEHICLE_NAVI)
    # A non-camera base under :v falls back to the normal mode.
    self.assertEqual(deceleration_source_presentation("route:v")[1], COLOR_APPLY)

  def test_suffix_c_is_normal_colour(self):
    self.assertEqual(deceleration_source_presentation("cam:c")[1], COLOR_APPLY)

  def test_unknown_token_is_passed_through_not_dropped(self):
    label, mode = deceleration_source_presentation("brandnewthing")
    self.assertEqual(label, "brandnew")
    self.assertEqual(mode, COLOR_APPLY)

  def test_every_published_source_has_a_label(self):
    """Guard: a new speed source must be added to the taxonomy, not left raw."""
    missing = [s for s in sorted(PUBLISHED_SOURCES) if s not in DECELERATION_SOURCE_LABELS]
    self.assertEqual(missing, [], f"unmapped deceleration sources: {missing}")

  def test_label_table_matches_the_documented_families(self):
    self.assertTrue(EXTERNAL_NAVI_SOURCES <= set(DECELERATION_SOURCE_LABELS))
    self.assertTrue(VEHICLE_NAVI_SOURCES <= set(DECELERATION_SOURCE_LABELS))


class TestVehicleNaviDetection(unittest.TestCase):
  def test_plain_names(self):
    for src in ("hda", "hda_section", "hda_bump", "school"):
      self.assertTrue(is_vehicle_navigation_source(src), src)

  def test_v_suffixed_names(self):
    for src in ("cam:v", "bump:v", "school:v"):
      self.assertTrue(is_vehicle_navigation_source(src), src)

  def test_phone_sources_are_not_vehicle(self):
    for src in ("cam", "atc", "route", "road", "sdi", ""):
      self.assertFalse(is_vehicle_navigation_source(src), src)


class TestBadges(unittest.TestCase):
  def test_external_wins_over_vehicle(self):
    self.assertEqual(navigation_status_presentation(True, True), ("NAVI", COLOR_EXTERNAL_NAVI))

  def test_vehicle_only(self):
    self.assertEqual(navigation_status_presentation(True, False), ("vNAVI", COLOR_VEHICLE_NAVI))

  def test_neither(self):
    self.assertIsNone(navigation_status_presentation(False, False))

  def test_connectivity_ignores_speed_control(self):
    self.assertTrue(external_navigation_connected("1.2.3.4", False))
    self.assertTrue(external_navigation_connected("", True))
    self.assertFalse(external_navigation_connected("", False))
    self.assertFalse(external_navigation_connected("   ", False))


class TestContractWithCarrotServ(unittest.TestCase):
  """Read the real source labels out of carrot_serv and check they are all mapped.

  This is the check that fails when a new speed source is added upstream but not
  added to the taxonomy - the failure mode this module exists to prevent.
  """
  def test_live_speed_n_sources_are_all_known(self):
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    serv = os.path.join(root, "carrot_serv.py")
    with open(serv, encoding="utf-8") as f:
      text = f.read()
    block = re.search(r"speed_n_sources\s*=\s*\[(.*?)\n\s*\]", text, re.S)
    self.assertIsNotNone(block, "could not locate speed_n_sources")
    labels = set(re.findall(r'[,(]\s*"([a-z_0-9]+)"\s*\)', block.group(1)))
    self.assertTrue(labels, "no labels parsed from speed_n_sources")
    unknown = sorted(l for l in labels if l not in DECELERATION_SOURCE_LABELS)
    self.assertEqual(unknown, [], f"speed sources missing from the taxonomy: {unknown}")


if __name__ == "__main__":
  unittest.main()
