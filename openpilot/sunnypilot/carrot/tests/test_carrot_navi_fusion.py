#!/usr/bin/env python3
"""
Offline unit tests for sunnypilot/carrot/carrot_navi_fusion.py.

These tests run WITHOUT building cereal/gen (they avoid importing any
pycapnp-dependent modules), so they can be executed on a stock Windows
workstation.  They verify that lane-change block hints are derived correctly
from the 7714 v2 laneCurrent.available list semantics.
"""
import importlib.util
import pathlib
import sys
import unittest
from types import ModuleType


# Stub opendbc.car.structs so we can import carrot_navi_fusion without
# building the full openpilot tree.
_car = ModuleType("opendbc")
_car.car = ModuleType("opendbc.car")
_car.car.structs = ModuleType("opendbc.car.structs")


class _FakeCarState:
  def __init__(self):
    self.leftBlindspot = False
    self.rightBlindspot = False


class _FakeCarStateSP:
  def __init__(self):
    self.carrotLaneValid = False
    self.carrotLeftLineBlocked = False
    self.carrotRightLineBlocked = False


_car.car.structs.car = ModuleType("opendbc.car.structs.car")
_car.car.structs.car.CarState = _FakeCarState
sys.modules["opendbc"] = _car
sys.modules["opendbc.car"] = _car.car
sys.modules["opendbc.car.structs"] = _car.car.structs
sys.modules["opendbc.car.structs.car"] = _car.car.structs.car

_SRC = pathlib.Path(__file__).resolve().parent.parent / "carrot_navi_fusion.py"
_spec = importlib.util.spec_from_file_location("carrot_navi_fusion_under_test", _SRC)
carrot_navi_fusion = importlib.util.module_from_spec(_spec)
sys.modules["carrot_navi_fusion_under_test"] = carrot_navi_fusion
_spec.loader.exec_module(carrot_navi_fusion)


def _make_lane(count: int, current_lane: int, available: list[int], present: bool = True):
  class _Meta:
    pass

  meta = _Meta()
  meta.present = present

  class _Lane:
    pass

  lane = _Lane()
  lane.meta = meta
  lane.count = count
  lane.currentLane = current_lane
  lane.available = available
  return lane


def _make_carrot_navi(lane=None):
  class _Navi:
    pass

  navi = _Navi()
  navi.laneCurrent = lane
  return navi


class TestCarrotNaviLaneFusion(unittest.TestCase):
  def test_no_lane_data_clears_all(self):
    cs_sp = _FakeCarStateSP()
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, None)
    self.assertFalse(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertFalse(cs_sp.carrotRightLineBlocked)

  def test_single_lane_blocks_both_sides(self):
    cs_sp = _FakeCarStateSP()
    lane = _make_lane(count=1, current_lane=1, available=[1])
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane))
    self.assertTrue(cs_sp.carrotLaneValid)
    self.assertTrue(cs_sp.carrotLeftLineBlocked)
    self.assertTrue(cs_sp.carrotRightLineBlocked)

  def test_three_lanes_center_allows_both_sides(self):
    cs_sp = _FakeCarStateSP()
    lane = _make_lane(count=3, current_lane=2, available=[1, 1, 1])
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane))
    self.assertTrue(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertFalse(cs_sp.carrotRightLineBlocked)

  def test_left_lane_blocks_left_allows_right(self):
    cs_sp = _FakeCarStateSP()
    lane = _make_lane(count=3, current_lane=1, available=[1, 1, 0])
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane))
    self.assertTrue(cs_sp.carrotLaneValid)
    self.assertTrue(cs_sp.carrotLeftLineBlocked)
    self.assertFalse(cs_sp.carrotRightLineBlocked)

  def test_right_lane_blocks_right_allows_left(self):
    cs_sp = _FakeCarStateSP()
    lane = _make_lane(count=3, current_lane=3, available=[0, 1, 1])
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane))
    self.assertTrue(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertTrue(cs_sp.carrotRightLineBlocked)

  def test_adjacent_unavailable_blocks_side(self):
    cs_sp = _FakeCarStateSP()
    lane = _make_lane(count=3, current_lane=2, available=[1, 1, 0])
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane))
    self.assertTrue(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertTrue(cs_sp.carrotRightLineBlocked)

  def test_invalid_data_treated_as_blocked(self):
    cs_sp = _FakeCarStateSP()
    lane = _make_lane(count=3, current_lane=2, available=[1], present=True)
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane))
    self.assertTrue(cs_sp.carrotLaneValid)
    # Right adjacent index (2) is out of available range -> treated blocked.
    self.assertTrue(cs_sp.carrotRightLineBlocked)


class TestNavLaneGuideBlocks(unittest.TestCase):
  """7706 navLaneGuide -> lane blocking (App field list §2.2)."""

  def test_left_only_guidance_blocks_right(self):
    left, right = carrot_navi_fusion.nav_lane_guide_blocks("L,SL")
    self.assertFalse(left)
    self.assertTrue(right)

  def test_right_only_guidance_blocks_left(self):
    left, right = carrot_navi_fusion.nav_lane_guide_blocks("R")
    self.assertTrue(left)
    self.assertFalse(right)

  def test_both_directions_constrain_neither(self):
    left, right = carrot_navi_fusion.nav_lane_guide_blocks("L,R")
    self.assertFalse(left)
    self.assertFalse(right)

  def test_straight_only_constrains_neither(self):
    left, right = carrot_navi_fusion.nav_lane_guide_blocks("S")
    self.assertFalse(left)
    self.assertFalse(right)

  def test_json_array_payload_is_parsed(self):
    left, right = carrot_navi_fusion.nav_lane_guide_blocks('["L","SL"]')
    self.assertFalse(left)
    self.assertTrue(right)

  def test_empty_or_malformed_is_noop(self):
    for payload in ("", None, "[]", "not json", "  "):
      self.assertEqual(carrot_navi_fusion.nav_lane_guide_blocks(payload), (False, False))

  def test_truncated_array_is_rejected(self):
    # Declared 3 entries but only 2 present -> discard rather than guess.
    left, right = carrot_navi_fusion.nav_lane_guide_blocks("L,SL", declared_count=3)
    self.assertFalse(left)
    self.assertFalse(right)

  def test_matching_count_is_accepted(self):
    left, right = carrot_navi_fusion.nav_lane_guide_blocks("L,SL", declared_count=2)
    self.assertFalse(left)
    self.assertTrue(right)


class TestNavLaneGuideMerge(unittest.TestCase):
  """The 7706 guide must share the one merge path and only ever add blocking."""

  def test_gate_off_means_no_effect(self):
    cs_sp = _FakeCarStateSP()
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, None, "L,SL", 2, use_nav_lane_guide=False)
    self.assertFalse(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertFalse(cs_sp.carrotRightLineBlocked)

  def test_gate_on_blocks_without_7714_data(self):
    cs_sp = _FakeCarStateSP()
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, None, "L,SL", 2, use_nav_lane_guide=True)
    self.assertTrue(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertTrue(cs_sp.carrotRightLineBlocked)

  def test_guide_adds_to_7714_result(self):
    cs_sp = _FakeCarStateSP()
    lane = _make_lane(count=3, current_lane=2, available=[1, 1, 1])
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane), "L", 1, use_nav_lane_guide=True)
    self.assertTrue(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertTrue(cs_sp.carrotRightLineBlocked)

  def test_guide_never_clears_a_7714_block(self):
    cs_sp = _FakeCarStateSP()
    # 7714 says the right lane is unavailable.
    lane = _make_lane(count=3, current_lane=2, available=[1, 1, 0])
    # Guide steers right, which would "allow" the right side on its own.
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, _make_carrot_navi(lane), "R", 1, use_nav_lane_guide=True)
    self.assertTrue(cs_sp.carrotRightLineBlocked, "guide must not clear the 7714 block")

  def test_no_guide_and_no_navi_clears_all(self):
    cs_sp = _FakeCarStateSP()
    carrot_navi_fusion.merge_carrot_navi_lanes(cs_sp, None, "", 0, use_nav_lane_guide=True)
    self.assertFalse(cs_sp.carrotLaneValid)
    self.assertFalse(cs_sp.carrotLeftLineBlocked)
    self.assertFalse(cs_sp.carrotRightLineBlocked)


if __name__ == "__main__":
  unittest.main()
