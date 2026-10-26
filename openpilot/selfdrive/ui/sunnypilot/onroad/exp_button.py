"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

The tizi onroad experimental mode button: comma's ExpButton, which upstream retired with chill
mode, writing zoompilot's switch (selfdrived_zp) with no confirmation gate.
"""
import time

import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets import Widget

EXP_ICON = "../../sunnypilot/selfdrive/assets/icons/experimental.png"


class ExpButton(Widget):
  def __init__(self, button_size: int, icon_size: int):
    super().__init__()
    self._experimental_mode: bool = False
    self._engageable: bool = False

    # the tapped mode shows until selfdrived publishes it
    self._hold_duration = 2.0  # seconds
    self._held_mode: bool | None = None
    self._hold_end_time: float | None = None

    self._white_color: rl.Color = rl.Color(255, 255, 255, 255)
    self._black_bg: rl.Color = rl.Color(0, 0, 0, 166)
    self._txt_wheel: rl.Texture = gui_app.texture('icons/chffr_wheel.png', icon_size, icon_size)
    self._txt_exp: rl.Texture = gui_app.texture(EXP_ICON, icon_size, icon_size)
    self._rect = rl.Rectangle(0, 0, button_size, button_size)

  def set_rect(self, rect: rl.Rectangle) -> None:
    self._rect.x, self._rect.y = rect.x, rect.y

  def _update_state(self) -> None:
    selfdrive_state = ui_state.sm["selfdriveState"]
    self._experimental_mode = ui_state.experimental_mode
    self._engageable = selfdrive_state.engageable or selfdrive_state.enabled

  def _handle_mouse_release(self, _):
    super()._handle_mouse_release(_)
    if ui_state.has_longitudinal_control:
      new_mode = not self._experimental_mode
      ui_state.set_experimental_mode(new_mode)
      self._held_mode = new_mode
      self._hold_end_time = time.monotonic() + self._hold_duration

  def _render(self, rect: rl.Rectangle) -> None:
    center_x = int(self._rect.x + self._rect.width // 2)
    center_y = int(self._rect.y + self._rect.height // 2)

    self._white_color.a = 180 if self.is_pressed or not self._engageable else 255

    texture = self._txt_exp if self._held_or_actual_mode() else self._txt_wheel
    rl.draw_circle(center_x, center_y, self._rect.width / 2, self._black_bg)
    rl.draw_texture_ex(texture, rl.Vector2(center_x - texture.width / 2, center_y - texture.height / 2), 0.0, 1.0, self._white_color)

  def _held_or_actual_mode(self) -> bool:
    now = time.monotonic()
    if self._hold_end_time and now < self._hold_end_time:
      return bool(self._held_mode)

    if self._hold_end_time and now >= self._hold_end_time:
      self._hold_end_time = self._held_mode = None

    return self._experimental_mode
