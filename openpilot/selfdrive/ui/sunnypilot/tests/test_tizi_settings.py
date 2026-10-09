"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The tizi (comma three / 3X) settings: the top of Cruise owns the alpha switch
(offroad-only) and experimental mode, which Developer and Toggles no longer show. Ported from
zoompilot's pytest version; this fork has no pytest, so it is a plain unittest.
"""
import os
import unittest

os.environ.setdefault("SCALE", "1")  # the ui import probes the monitor for its scale otherwise

from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.common.test import OpenpilotTestCase

# the window's own params, for whatever it reads while it comes up; every test then runs
# under its own prefix
_window_prefix = OpenpilotPrefix()


def setUpModule():
  """A hidden raylib window, once for the module: widgets need textures."""
  import pyray as rl
  from openpilot.system.ui.lib.application import gui_app
  _window_prefix.__enter__()
  rl.set_config_flags(rl.FLAG_WINDOW_HIDDEN)
  gui_app.init_window("test_tizi_settings", fps=30)


def tearDownModule():
  from openpilot.system.ui.lib.application import gui_app
  gui_app.close()
  _window_prefix.__exit__(None, None, None)


class UITest(OpenpilotTestCase):
  def setUp(self):
    super().setUp()
    from openpilot.selfdrive.ui.ui_state import ui_state
    self.params = Params()
    ui_state.params = self.params
    ui_state.update_params()

  def patch_ui_state(self, **fields):
    """Set ui_state attributes for the test and put them back after."""
    from openpilot.selfdrive.ui.ui_state import ui_state
    saved = {name: getattr(ui_state, name) for name in fields}
    for name, value in fields.items():
      setattr(ui_state, name, value)

    def restore():
      for name, value in saved.items():
        setattr(ui_state, name, value)
    return restore


class TestAlphaLongitudinalPanel(UITest):
  def test_alpha_toggle_is_offroad_only(self):
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import AlphaLongitudinalToggles
    from openpilot.selfdrive.ui.ui_state import ui_state
    layout = AlphaLongitudinalToggles()
    restore = self.patch_ui_state(started=False)
    self.addCleanup(restore)
    # offroad: the switch can be used
    self.assertTrue(layout._alpha_long_toggle.action_item.enabled)
    # driving: it greys out
    ui_state.started = True
    self.assertFalse(layout._alpha_long_toggle.action_item.enabled)

  def test_moved_switches_appear_once(self):
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import AlphaLongitudinalToggles
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.cruise import CruiseLayout
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.developer import DeveloperLayoutSP
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.toggles import TogglesLayoutSP

    developer, toggles = DeveloperLayoutSP(), TogglesLayoutSP()
    self.assertNotIn(developer._alpha_long_toggle, developer._scroller._items)
    self.assertFalse(toggles._toggles["ExperimentalMode"].is_visible)
    self.assertFalse(hasattr(CruiseLayout(), "dec_toggle"))

    alpha = AlphaLongitudinalToggles()
    self.assertEqual([key for key, _ in alpha._refresh_toggles],
                     ["AlphaLongitudinalEnabled", "ExperimentalMode", "ExperimentalModeSetSpeed",
                      "ExperimentalModeLeadGap", "DynamicExperimentalControl"])

  def test_alpha_longitudinal_heads_cruise(self):
    from opendbc.car.structs import car
    from openpilot.cereal import custom
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.cruise import CruiseLayout

    restore = self.patch_ui_state(CP=car.CarParams.new_message(alphaLongitudinalAvailable=True, openpilotLongitudinalControl=True),
                                  CP_SP=custom.CarParamsSP.new_message(), has_longitudinal_control=True)
    self.addCleanup(restore)
    self.params.put_bool("ExperimentalModeSetSpeed", True, block=True)
    self.addCleanup(self.params.remove, "ExperimentalModeSetSpeed")

    cruise = CruiseLayout()
    # plain toggles, no sub-panel
    self.assertEqual(cruise._scroller._items[:len(cruise._alpha_long.items)], cruise._alpha_long.items)
    cruise.show_event()
    cruise._update_state()
    self.assertTrue(cruise._alpha_long._alpha_long_toggle.is_visible)
    self.assertTrue(cruise._alpha_long._set_speed_toggle.action_item.get_state())

  def test_experimental_mode_text_matches_upstream(self):
    # upstream writes this text inline in TogglesLayout._update_toggles; the panel keeps a copy
    from opendbc.car.structs import car
    from openpilot.selfdrive.ui.layouts.settings.toggles import TogglesLayout
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import EXPERIMENTAL_MODE_DESCRIPTION

    restore = self.patch_ui_state(CP=car.CarParams.new_message(openpilotLongitudinalControl=True),
                                  has_longitudinal_control=True, update_params=lambda: None)
    self.addCleanup(restore)
    toggles = TogglesLayout()
    toggles._update_toggles()
    self.assertEqual(toggles._toggles["ExperimentalMode"].description, EXPERIMENTAL_MODE_DESCRIPTION)

  def test_set_speed_greys_out_under_dec(self):
    from opendbc.car.structs import car
    from openpilot.selfdrive.ui.sunnypilot.layouts.settings.alpha_longitudinal_toggles import AlphaLongitudinalToggles

    restore = self.patch_ui_state(CP=car.CarParams.new_message(alphaLongitudinalAvailable=True, openpilotLongitudinalControl=True),
                                  has_longitudinal_control=True)
    self.addCleanup(restore)
    layout = AlphaLongitudinalToggles()
    layout._dec_toggle.action_item.set_state(False)
    layout.update_state()
    self.assertTrue(layout._set_speed_toggle.action_item.enabled)
    layout._dec_toggle.action_item.set_state(True)
    layout.update_state()
    self.assertFalse(layout._set_speed_toggle.action_item.enabled)


if __name__ == "__main__":
  unittest.main()
