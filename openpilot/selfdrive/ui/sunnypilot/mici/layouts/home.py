"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import math

import pyray as rl

from openpilot.selfdrive.ui.mici.layouts.home import MiciHomeLayout
from openpilot.selfdrive.ui.sunnypilot.longitudinal_mode import EXPERIMENTAL_ICON
from openpilot.selfdrive.ui.ui_state import ui_state, ChestnutState
from openpilot.system.ui.lib.application import FontWeight
from openpilot.system.ui.widgets.icon_widget import IconWidget
from openpilot.system.ui.widgets.label import UnifiedLabel


class MiciHomeLayoutSP(MiciHomeLayout):
  def __init__(self):
    super().__init__()
    self._openpilot_label = UnifiedLabel("zoompilot", font_size=88, font_weight=FontWeight.AUDIOWIDE, max_width=480, wrap_text=False)
    # zoompilot keeps upstream's retired long press to switch experimental mode
    self.set_long_press_callback(self._toggle_experimental_mode)
    # upstream's status bar icon, after the network icon, retired with chill mode
    self._experimental_icon = IconWidget(EXPERIMENTAL_ICON, (48, 48))
    self._experimental_icon.set_visible(lambda: ui_state.has_longitudinal_control and ui_state.experimental_mode)
    self._status_bar_layout.add_widget(self._experimental_icon)
    self._status_bar_layout.widgets.insert(2, self._status_bar_layout.widgets.pop())

  @staticmethod
  def _toggle_experimental_mode():
    if ui_state.has_longitudinal_control:
      ui_state.set_experimental_mode(not ui_state.experimental_mode)

  def _set_chestnut_visibility(self):
    usb_connected = ui_state.usb_connected
    usb_unknown = ui_state.usb_unknown
    chestnut_state = ui_state.chestnut_state
    loading = chestnut_state == ChestnutState.LOADING
    # ready, and only a swap window away: steady rather than the loading pulse,
    # dim rather than the solid green of a model that is driving
    waiting = chestnut_state == ChestnutState.WAITING

    # the port is known while Jetlink holds it, whatever enumerated
    self._usb_icon.set_visible(usb_connected and usb_unknown and not ui_state.adb_blocked)
    self._chestnut_loading_icon.set_opacity(0.35 + 0.65 * (0.5 - 0.5 * math.cos(rl.get_time() * 6.0)))
    self._chestnut_loading_icon.set_visible(not usb_unknown and loading)
    self._chestnut_icon.set_opacity(0.5 if waiting else 1.0)
    self._chestnut_icon.set_visible(not usb_unknown and not loading and
                                    chestnut_state in (ChestnutState.READY, ChestnutState.ACTIVE,
                                                       ChestnutState.WAITING))
    self._chestnut_failed_icon.set_visible(not usb_unknown and chestnut_state in (ChestnutState.UNCOMPILED, ChestnutState.FAILED))
