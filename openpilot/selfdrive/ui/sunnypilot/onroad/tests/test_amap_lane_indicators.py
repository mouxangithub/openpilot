#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import pyray as rl


def _install_mocks():
  """Install lightweight mocks for the heavy UI/raylib/cereal dependencies."""
  ui_state_mod = types.ModuleType("openpilot.selfdrive.ui.ui_state")
  ui_state_mod.ui_state = MagicMock()
  ui_state_mod.UIStatus = MagicMock()
  sys.modules["openpilot.selfdrive.ui.ui_state"] = ui_state_mod

  app_mod = types.ModuleType("openpilot.system.ui.lib.application")
  app_mod.gui_app = MagicMock()
  app_mod.gui_app.target_fps = 60
  sys.modules["openpilot.system.ui.lib.application"] = app_mod

  def _make_filter(x0, _y, _z):
    f = MagicMock()
    f.x = x0
    f.update = lambda v: setattr(f, "x", v)
    return f

  filter_mod = types.ModuleType("openpilot.common.filter_simple")
  filter_mod.FirstOrderFilter = _make_filter
  sys.modules["openpilot.common.filter_simple"] = filter_mod


# Install mocks before the first import of the module under test.
_install_mocks()

from openpilot.selfdrive.ui.sunnypilot.onroad.amap_lane_indicators import AmapLaneIndicators


class _FakeCarStateSP:
  def __init__(self, line_valid=False, left_blocked=False, right_blocked=False):
    self.amapLineValid = line_valid
    self.amapLeftLineBlocked = left_blocked
    self.amapRightLineBlocked = right_blocked


class _FakeSubMaster:
  def __init__(self, car_state_sp=None, started_frame=10):
    self._cs_sp = car_state_sp
    self.recv_frame = {"carStateSP": started_frame}

  def __getitem__(self, key):
    if key == "carStateSP":
      return self._cs_sp
    raise KeyError(key)


class TestAmapLaneIndicators(unittest.TestCase):
  def setUp(self):
    self.ui_state = sys.modules["openpilot.selfdrive.ui.ui_state"].ui_state
    self.ui_state.amap_enabled = True
    self.ui_state.started_frame = 10
    self.ui_state.sm = _FakeSubMaster(_FakeCarStateSP(line_valid=True))

  def test_disabled_when_amap_not_enabled(self):
    self.ui_state.amap_enabled = False
    self.ui_state.sm = _FakeSubMaster(_FakeCarStateSP(line_valid=True))
    indicator = AmapLaneIndicators()
    indicator.update()
    self.assertFalse(indicator.visible)

  def test_visible_when_data_valid(self):
    self.ui_state.amap_enabled = True
    self.ui_state.sm = _FakeSubMaster(_FakeCarStateSP(line_valid=True))
    indicator = AmapLaneIndicators()
    indicator.update()
    self.assertTrue(indicator.visible)

  def test_hidden_before_started_frame(self):
    self.ui_state.amap_enabled = True
    self.ui_state.sm = _FakeSubMaster(_FakeCarStateSP(line_valid=True), started_frame=0)
    self.ui_state.started_frame = 10
    indicator = AmapLaneIndicators()
    indicator.update()
    self.assertFalse(indicator.visible)

  def test_render_skips_when_invalid(self):
    self.ui_state.amap_enabled = True
    self.ui_state.sm = _FakeSubMaster(_FakeCarStateSP(line_valid=False))
    indicator = AmapLaneIndicators()
    indicator.update()
    with patch.object(rl, "draw_rectangle_rounded") as mock_draw:
      indicator.render(rl.Rectangle(0, 0, 100, 100))
      mock_draw.assert_not_called()

  def test_render_draws_both_sides_when_valid(self):
    self.ui_state.amap_enabled = True
    self.ui_state.sm = _FakeSubMaster(_FakeCarStateSP(line_valid=True, left_blocked=True, right_blocked=False))
    indicator = AmapLaneIndicators()
    indicator.update()
    with patch.object(rl, "draw_rectangle_rounded") as mock_draw:
      indicator.render(rl.Rectangle(0, 0, 100, 100))
      self.assertEqual(mock_draw.call_count, 2)


if __name__ == "__main__":
  unittest.main()
