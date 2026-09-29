"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Carrot tuning eGPU / Chestnut status panel.

Mirrors the webui eGPU panel layout: a centered header with title and status
badge, a short description, an optional not-detected warning, and a status
details section with label/value rows.
"""
import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
try:
  from openpilot.selfdrive.ui.ui_state import ChestnutState
except ImportError:
  # Fallback for test environments that mock ui_state without the enum.
  from enum import Enum
  class ChestnutState(Enum):  # type: ignore[no-redef]
    DISCONNECTED = "disconnected"
    UNCOMPILED = "uncompiled"
    READY = "ready"
    LOADING = "loading"
    ACTIVE = "active"
    FAILED = "failed"
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget


class EgpuPanelWidget(Widget):
  """Native GUI eGPU status card matching the webui eGPU panel."""

  def __init__(self):
    super().__init__()
    self._rect = rl.Rectangle(0, 0, 0, self._preferred_height())

  def _preferred_height(self) -> float:
    return 780.0

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def _chestnut_state_key(self) -> tuple[bool, str]:
    """Return (present, webui-style state key) for the current ui_state."""
    present = bool(ui_state.chestnut_present) if hasattr(ui_state, 'chestnut_present') else False
    if not present:
      return False, 'gray'

    state = ui_state.chestnut_state
    mapping = {
      ChestnutState.DISCONNECTED: 'gray',
      ChestnutState.UNCOMPILED: 'failed',
      ChestnutState.READY: 'gray',
      ChestnutState.LOADING: 'loading',
      ChestnutState.ACTIVE: 'green',
      ChestnutState.FAILED: 'failed',
    }
    return True, mapping.get(state, 'gray')

  def _state_label(self, state: str) -> str:
    return {
      'gray': tr("eGPU Not Active"),
      'green': tr("eGPU Active"),
      'failed': tr("eGPU Failed"),
      'loading': tr("eGPU Loading..."),
    }.get(state, state)

  def _state_desc(self, state: str) -> str:
    return {
      'gray': tr("No eGPU (big model) is selected. The default model is running."),
      'green': tr("eGPU big model is running and healthy."),
      'failed': tr("eGPU was selected but failed to start. Check device connection and model files."),
      'loading': tr("eGPU big model is being loaded. This may take a moment."),
    }.get(state, "")

  def _state_colors(self, state: str) -> tuple[rl.Color, rl.Color]:
    """Background and text colors for the status badge."""
    return {
      'gray': (rl.Color(128, 128, 128, 77), rl.Color(170, 170, 170, 255)),
      'green': (rl.Color(0, 180, 80, 77), rl.Color(79, 218, 106, 255)),
      'failed': (rl.Color(220, 50, 50, 77), rl.Color(224, 80, 80, 255)),
      'loading': (rl.Color(0, 130, 230, 77), rl.Color(90, 176, 240, 255)),
    }.get(state, (rl.Color(128, 128, 128, 77), rl.Color(170, 170, 170, 255)))

  def _render(self, _) -> None:
    if not self.is_visible or self._parent_rect is None:
      return
    if (self._rect.y + self._rect.height) <= self._parent_rect.y or self._rect.y >= (self._parent_rect.y + self._parent_rect.height):
      return

    present, state = self._chestnut_state_key()
    label = self._state_label(state)
    desc = self._state_desc(state)
    badge_bg, badge_text = self._state_colors(state)

    x = self._rect.x
    y = self._rect.y + 30
    width = self._rect.width
    pad = 40

    # Header: title + status badge (centered)
    title = tr("eGPU / Big Model")
    title_font = 60
    badge_font = 40
    badge_pad_x = 24
    badge_pad_y = 10

    title_size = measure_text_cached(gui_app.font(FontWeight.BOLD), title, title_font)
    badge_size = measure_text_cached(gui_app.font(), label, badge_font)
    badge_w = badge_size.x + badge_pad_x * 2
    badge_h = badge_size.y + badge_pad_y * 2

    total_header_w = title_size.x + 24 + badge_w
    header_x = x + (width - total_header_w) / 2

    rl.draw_text_ex(gui_app.font(FontWeight.BOLD), title,
                    rl.Vector2(header_x, y + (badge_h - title_size.y) / 2),
                    title_font, 0, rl.WHITE)

    badge_x = header_x + title_size.x + 24
    badge_rect = rl.Rectangle(badge_x, y, badge_w, badge_h)
    rl.draw_rectangle_rounded(badge_rect, 0.25, 12, badge_bg)
    rl.draw_text_ex(gui_app.font(), label,
                    rl.Vector2(badge_x + badge_pad_x, y + badge_pad_y),
                    badge_font, 0, badge_text)
    y += badge_h + 50

    # Description
    desc_color = rl.Color(170, 170, 170, 255)
    self._draw_wrapped_text(desc, x + pad, y, width - pad * 2, 40, desc_color)
    y += 110

    # Warning when chestnut is not detected
    if not present:
      warn = tr("eGPU (Chestnut) not detected. Connect your eGPU hardware to enable.")
      warn_h = 110
      warn_rect = rl.Rectangle(x + pad, y, width - pad * 2, warn_h)
      rl.draw_rectangle_rounded(warn_rect, 0.12, 12, rl.Color(200, 140, 0, 38))
      self._draw_wrapped_text(warn, warn_rect.x + 20, warn_rect.y + 14,
                              warn_rect.width - 40, 40, rl.Color(224, 160, 32, 255))
      y += warn_h + 40

    # Status details section
    section_x = x + pad
    section_w = width - pad * 2
    section_pad = 28
    row_h = 90
    rows = [
      (tr("Current State"), label),
      (tr("eGPU Available"), tr("Yes") if present else tr("No")),
      (tr("Description"), desc),
    ]
    section_h = 70 + len(rows) * row_h + section_pad

    section_rect = rl.Rectangle(section_x, y, section_w, section_h)
    rl.draw_rectangle_rounded(section_rect, 0.08, 12, rl.Color(255, 255, 255, 13))

    y += 24
    title_text = tr("Status Details")
    rl.draw_text_ex(gui_app.font(FontWeight.BOLD), title_text,
                    rl.Vector2(section_x + section_pad, y), 50, 0, rl.WHITE)
    y += 64

    line_color = rl.Color(255, 255, 255, 15)
    label_color = rl.Color(136, 136, 136, 255)
    value_color = rl.Color(255, 255, 255, 255)
    for i, (row_label, row_value) in enumerate(rows):
      row_y = y + i * row_h
      if i > 0:
        line_y = row_y
        rl.draw_rectangle(int(section_x + section_pad), int(line_y),
                          int(section_w - section_pad * 2), 1, line_color)

      label_size = measure_text_cached(gui_app.font(), row_label, 40)
      value_size = measure_text_cached(gui_app.font(), row_value, 40)
      text_y = row_y + (row_h - label_size.y) / 2
      rl.draw_text_ex(gui_app.font(), row_label,
                      rl.Vector2(section_x + section_pad, text_y),
                      40, 0, label_color)

      # Scissor long values to the section width
      max_value_w = section_w - section_pad * 2 - label_size.x - 40
      value_x = section_x + section_w - section_pad - value_size.x
      if value_size.x > max_value_w:
        value_x = section_x + section_pad + label_size.x + 40
        scissor_w = max_value_w
        rl.begin_scissor_mode(int(value_x), int(row_y), int(scissor_w), int(row_h))
        rl.draw_text_ex(gui_app.font(), row_value,
                        rl.Vector2(value_x, text_y),
                        40, 0, value_color)
        rl.end_scissor_mode()
      else:
        rl.draw_text_ex(gui_app.font(), row_value,
                        rl.Vector2(value_x, text_y),
                        40, 0, value_color)

  def _draw_wrapped_text(self, text: str, x: float, y: float, max_width: float,
                         font_size: int, color: rl.Color) -> None:
    """Draw a short paragraph centered, wrapped to max_width."""
    font = gui_app.font()
    words = text.split(' ')
    lines: list[str] = []
    current = ''
    for word in words:
      test = f'{current} {word}'.strip()
      size = measure_text_cached(font, test, font_size)
      if size.x > max_width and current:
        lines.append(current)
        current = word
      else:
        current = test
    if current:
      lines.append(current)

    line_height = font_size + 8
    total_h = len(lines) * line_height
    start_y = y
    for i, line in enumerate(lines):
      size = measure_text_cached(font, line, font_size)
      lx = x + (max_width - size.x) / 2
      ly = start_y + i * line_height
      rl.draw_text_ex(font, line, rl.Vector2(lx, ly), font_size, 0, color)
