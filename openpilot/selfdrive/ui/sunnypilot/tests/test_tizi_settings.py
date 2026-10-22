"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The tizi (comma three / 3X) settings: the top of Cruise owns the alpha switch
(offroad-only, no status line), which Developer no longer shows, and experimental mode.
Its own module: the big UI is chosen at import, so it cannot share a window with the mici
tests.
"""
import os

os.environ["BIG"] = "1"
os.environ.setdefault("SCALE", "0.5")  # a full-size 2160x1080 hidden window aborts on macOS


def test_alpha_toggle_is_offroad_only(params, monkeypatch):
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import AlphaLongitudinalToggles
  from openpilot.selfdrive.ui.ui_state import ui_state
  layout = AlphaLongitudinalToggles()
  monkeypatch.setattr(ui_state, "started", True)
  assert not layout._alpha_long_toggle.action_item.enabled
  monkeypatch.setattr(ui_state, "started", False)
  assert layout._alpha_long_toggle.action_item.enabled


def test_moved_switches_appear_once(params):
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import AlphaLongitudinalToggles
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.cruise import CruiseLayout
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.developer import DeveloperLayoutSP

  developer = DeveloperLayoutSP()
  assert developer._alpha_long_toggle not in developer._scroller._items
  assert not hasattr(CruiseLayout(), "dec_toggle")

  alpha = AlphaLongitudinalToggles()
  assert [key for key, _ in alpha._refresh_toggles] == [
    "AlphaLongitudinalEnabled", "ExperimentalMode", "ExperimentalModeSetSpeed", "ExperimentalModeLeadGap"]


def test_alpha_longitudinal_heads_cruise(params, monkeypatch):
  from opendbc.car.structs import car
  from openpilot.cereal import custom
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.cruise import CruiseLayout
  from openpilot.selfdrive.ui.ui_state import ui_state

  monkeypatch.setattr(ui_state, "CP", car.CarParams.new_message(alphaLongitudinalAvailable=True, openpilotLongitudinalControl=True))
  monkeypatch.setattr(ui_state, "CP_SP", custom.CarParamsSP.new_message())
  monkeypatch.setattr(ui_state, "has_longitudinal_control", True)
  params.put_bool("ExperimentalModeSetSpeed", True, block=True)
  cruise = CruiseLayout()
  # plain toggles, no sub-panel
  assert cruise._scroller._items[:len(cruise._alpha_long.items)] == cruise._alpha_long.items
  cruise.show_event()
  cruise._update_state()
  assert cruise._alpha_long._alpha_long_toggle.is_visible
  assert cruise._alpha_long._set_speed_toggle.action_item.get_state()
  params.remove("ExperimentalModeSetSpeed")


def test_experimental_toggle_needs_no_confirm(params, monkeypatch):
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import AlphaLongitudinalToggles
  from openpilot.system.ui.lib.application import gui_app

  pushed = []
  monkeypatch.setattr(gui_app, "push_widget", pushed.append)
  layout = AlphaLongitudinalToggles()
  for state in (False, True):
    layout._on_experimental_mode(state)
    assert params.get_bool("ExperimentalMode") is state
  assert not pushed


def test_assists_grey_out_without_long(params, monkeypatch):
  from opendbc.car.structs import car
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import AlphaLongitudinalToggles
  from openpilot.selfdrive.ui.ui_state import ui_state

  monkeypatch.setattr(ui_state, "CP", car.CarParams.new_message(alphaLongitudinalAvailable=True, openpilotLongitudinalControl=True))
  layout = AlphaLongitudinalToggles()
  for has_long in (True, False):
    monkeypatch.setattr(ui_state, "has_longitudinal_control", has_long)
    layout.update_state()
    assert layout._set_speed_toggle.action_item.enabled == has_long
    assert layout._lead_gap_toggle.action_item.enabled == has_long
