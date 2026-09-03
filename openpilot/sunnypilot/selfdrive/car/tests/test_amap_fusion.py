#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import unittest

import openpilot.cereal.messaging as messaging
from openpilot.sunnypilot.selfdrive.car.amap_fusion import merge_amap_blindspot, merge_amap_lane_lines


class TestAmapFusion(unittest.TestCase):
  def _make_amap(self, left: int = 0, right: int = 0, line_valid: bool = False,
                 left_line: int = 0, right_line: int = 0):
    msg = messaging.new_message('amapNaviSP')
    msg.amapNaviSP.leftBlind = left
    msg.amapNaviSP.rightBlind = right
    msg.amapNaviSP.lineValid = line_valid
    msg.amapNaviSP.leftLine = left_line
    msg.amapNaviSP.rightLine = right_line
    return msg.amapNaviSP

  def _make_car_state(self, left: bool = False, right: bool = False):
    msg = messaging.new_message('carState')
    msg.carState.leftBlindspot = left
    msg.carState.rightBlindspot = right
    return msg.carState

  def _make_car_state_sp(self):
    msg = messaging.new_message('carStateSP')
    return msg.carStateSP

  def test_merge_sets_left_blindspot(self):
    CS = self._make_car_state(left=False, right=False)
    merge_amap_blindspot(CS, self._make_amap(left=1, right=0))
    self.assertTrue(CS.leftBlindspot)
    self.assertFalse(CS.rightBlindspot)

  def test_merge_sets_right_blindspot(self):
    CS = self._make_car_state(left=False, right=False)
    merge_amap_blindspot(CS, self._make_amap(left=0, right=2))
    self.assertFalse(CS.leftBlindspot)
    self.assertTrue(CS.rightBlindspot)

  def test_merge_ors_with_existing_blindspot(self):
    CS = self._make_car_state(left=True, right=False)
    merge_amap_blindspot(CS, self._make_amap(left=0, right=1))
    self.assertTrue(CS.leftBlindspot)
    self.assertTrue(CS.rightBlindspot)

  def test_merge_does_not_clear_existing_blindspot(self):
    CS = self._make_car_state(left=True, right=True)
    merge_amap_blindspot(CS, self._make_amap(left=0, right=0))
    self.assertTrue(CS.leftBlindspot)
    self.assertTrue(CS.rightBlindspot)

  def test_merge_lane_lines_copies_types(self):
    CS_SP = self._make_car_state_sp()
    merge_amap_lane_lines(CS_SP, self._make_amap(line_valid=True, left_line=2, right_line=3))
    self.assertTrue(CS_SP.amapLineValid)
    self.assertEqual(CS_SP.amapLeftLineType, 2)
    self.assertEqual(CS_SP.amapRightLineType, 3)

  def test_merge_lane_lines_blocks_solid_lines(self):
    CS_SP = self._make_car_state_sp()
    merge_amap_lane_lines(CS_SP, self._make_amap(line_valid=True, left_line=1, right_line=4))
    self.assertTrue(CS_SP.amapLeftLineBlocked)
    self.assertTrue(CS_SP.amapRightLineBlocked)

  def test_merge_lane_lines_allows_dashed_lines(self):
    CS_SP = self._make_car_state_sp()
    merge_amap_lane_lines(CS_SP, self._make_amap(line_valid=True, left_line=2, right_line=0))
    self.assertFalse(CS_SP.amapLeftLineBlocked)
    self.assertFalse(CS_SP.amapRightLineBlocked)

  def test_merge_lane_lines_invalid_clears_blocked(self):
    CS_SP = self._make_car_state_sp()
    merge_amap_lane_lines(CS_SP, self._make_amap(line_valid=False, left_line=1, right_line=1))
    self.assertFalse(CS_SP.amapLineValid)
    self.assertFalse(CS_SP.amapLeftLineBlocked)
    self.assertFalse(CS_SP.amapRightLineBlocked)


if __name__ == "__main__":
  unittest.main()
