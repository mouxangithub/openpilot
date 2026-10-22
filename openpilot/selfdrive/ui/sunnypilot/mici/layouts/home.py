"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import math
import time

import pyray as rl

from openpilot.selfdrive.ui.mici.layouts.home import MiciHomeLayout
from openpilot.selfdrive.ui.ui_state import ui_state, ChestnutState
from openpilot.system.ui.lib.application import FontWeight, MousePos
from openpilot.system.ui.widgets.label import UnifiedLabel


class MiciHomeLayoutSP(MiciHomeLayout):
  def __init__(self):
    super().__init__()
    self._openpilot_label = UnifiedLabel("zoompilot", font_size=88, font_weight=FontWeight.AUDIOWIDE, max_width=480, wrap_text=False)
    self._mouse_down_t: float | None = None
    self._did_long_press = False
    self._is_pressed_prev = False

  def _update_state(self):
    # zoompilot keeps upstream's retired long press: hold 0.5 s to switch experimental mode
    if self.is_pressed and not self._is_pressed_prev:
      self._mouse_down_t = time.monotonic()
    elif not self.is_pressed and self._is_pressed_prev:
      self._mouse_down_t = None
    self._is_pressed_prev = self.is_pressed

    if self._mouse_down_t is not None and time.monotonic() - self._mouse_down_t > 0.5:
      if ui_state.has_longitudinal_control:
        ui_state.set_experimental_mode(not ui_state.experimental_mode)
      self._mouse_down_t = None
      self._did_long_press = True

  def _handle_mouse_release(self, mouse_pos: MousePos):
    # the release that ends a long press opens nothing
    if not self._did_long_press:
      super()._handle_mouse_release(mouse_pos)
    self._did_long_press = False

  def _set_chestnut_visibility(self):
    usb_connected = ui_state.usb_connected
    usb_unknown = ui_state.usb_unknown
    chestnut_state = ui_state.chestnut_state
    loading = chestnut_state == ChestnutState.LOADING
    # ready, and only a swap window away: steady rather than the loading pulse,
    # dim rather than the solid green of a model that is driving
    waiting = chestnut_state == ChestnutState.WAITING

    self._usb_icon.set_visible(usb_connected and usb_unknown)
    self._chestnut_loading_icon.set_opacity(0.35 + 0.65 * (0.5 - 0.5 * math.cos(rl.get_time() * 6.0)))
    self._chestnut_loading_icon.set_visible(not usb_unknown and loading)
    self._chestnut_icon.set_opacity(0.5 if waiting else 1.0)
    self._chestnut_icon.set_visible(not usb_unknown and not loading and
                                    chestnut_state in (ChestnutState.READY, ChestnutState.ACTIVE,
                                                       ChestnutState.WAITING))
    self._chestnut_failed_icon.set_visible(not usb_unknown and chestnut_state in (ChestnutState.UNCOMPILED, ChestnutState.FAILED))
