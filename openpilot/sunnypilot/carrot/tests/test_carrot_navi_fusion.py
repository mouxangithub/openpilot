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


if __name__ == "__main__":
  unittest.main()
