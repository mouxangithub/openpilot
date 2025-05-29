# tsk/ui/header.py
from typing import Optional

import pyray as rl

from openpilot.system.ui.lib.application import gui_app
from tsk.common.key_file_manager import KeyFileManager
from tsk.ui.layout import Theme  # Import Theme


class Header:
  """Renders the top navigation bar with title and key status."""

  def __init__(self):
    """Initializes the Header."""
    self.key_manager = KeyFileManager()

  def _draw_title(self, rect: rl.Rectangle, current_menu: int) -> None:
    """Draws the title strip."""
    title_text_color = Theme.brighten_color(Theme.title_bg_color, Theme.brighten_amount)

    menu_name = Theme.menu_names.get(current_menu, "Unknown Menu")
    full_title_text = "TSK Manager: " + menu_name
    full_title_text_size = rl.measure_text_ex(gui_app.font(), full_title_text, Theme.title_font_size, 1.0)

    title_text_prefix_size = rl.measure_text_ex(gui_app.font(), "TSK Manager: ", Theme.title_font_size, 1.0)
    menu_name_x = gui_app.width * Theme.title_prefix_x_offset_percent + title_text_prefix_size.x + Theme.title_x_offset
    text_y = (self._calculate_height() - full_title_text_size.y) / 2

    rl.draw_text_ex(gui_app.font(), "TSK Manager: ", rl.Vector2(gui_app.width * Theme.title_prefix_x_offset_percent + Theme.title_x_offset, text_y),
                    Theme.title_font_size, 1.0, title_text_color)

    rl.draw_text_ex(gui_app.font(), menu_name, rl.Vector2(menu_name_x, text_y), Theme.title_font_size, 1.0, title_text_color)

  def _draw_navigation_buttons(self, rect: rl.Rectangle, current_menu: int) -> Optional[int]:
    """Draws the navigation buttons and handles button clicks."""
    nav_button_width = self._calculate_nav_button_width()

    left_button_x = 0
    left_button_rect = rl.Rectangle(left_button_x, 0, nav_button_width, rect.height)
    right_button_x = gui_app.width - nav_button_width
    right_button_rect = rl.Rectangle(right_button_x, 0, nav_button_width, rect.height)

    new_menu = None

    def handle_button(button_rect: rl.Rectangle, text: str, target_menu: int) -> Optional[int]:
      """Handles drawing, input, and logic for a single navigation button."""
      mouse_pos = rl.get_mouse_position()
      is_hovering = rl.check_collision_point_rec(mouse_pos, button_rect)
      is_pressed = is_hovering and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)

      rl.draw_rectangle_rec(button_rect, Theme.button_color)

      lines = text.splitlines()
      total_text_height = len(lines) * rl.measure_text_ex(gui_app.font(), "A", Theme.nav_button_font_size, 1.0).y
      start_y = rect.y + (rect.height - total_text_height) / 2

      for i, line in enumerate(lines):
        text_size = rl.measure_text_ex(gui_app.font(), line, Theme.nav_button_font_size, 1.0)
        text_x = button_rect.x + (button_rect.width - text_size.x) / 2
        text_y = start_y + i * text_size.y
        font_color = Theme.brighten_color(rl.Color(100, 100, 100, 255), Theme.brighten_amount)  # Use the same color as other buttons
        rl.draw_text_ex(gui_app.font(), line, rl.Vector2(text_x, text_y), Theme.nav_button_font_size, 1.0, font_color)

      if is_pressed:
        return target_menu
      return None
    if current_menu == Theme.menu_reboot:
      new_menu = handle_button(left_button_rect, Theme.nav_button_text_left, Theme.menu_tools)

      # --- Handle Right Button ---
    if current_menu == Theme.menu_tools:
      right_menu = handle_button(right_button_rect, Theme.nav_button_text_right, Theme.menu_reboot)
      if new_menu is None:
        new_menu = right_menu

    return new_menu

  def _draw_key_status(self, rect: rl.Rectangle) -> None:
    """Draws the key status label."""
    key_status_text = f"Key installed: {self.key_manager.installed_key}" if self.key_manager.installed_key else "Key not installed"
    status_text_x = (gui_app.width - rl.measure_text_ex(gui_app.font(), key_status_text, Theme.key_status_font_size, 1.0).x) / 2
    status_text_y = rect.y + (rect.height - rl.measure_text_ex(gui_app.font(), key_status_text, Theme.key_status_font_size, 1.0).y) / 2  # Use rect.y
    rl.draw_text_ex(gui_app.font(), key_status_text, rl.Vector2(status_text_x, status_text_y), Theme.key_status_font_size, 1.0, Theme.key_text_color)

  def _calculate_height(self) -> float:
    """Calculates the height of the header."""
    title_text_prefix = "TSK Manager: "
    return rl.measure_text_ex(gui_app.font(), title_text_prefix, Theme.title_font_size, 1.0).y * 1.5

  def _calculate_nav_button_width(self) -> float:
    """Calculates the width of the navigation buttons."""
    return max(rl.measure_text_ex(gui_app.font(), Theme.nav_button_text_left, Theme.nav_button_font_size, 1.0).x,
               rl.measure_text_ex(gui_app.font(), Theme.nav_button_text_right, Theme.nav_button_font_size, 1.0).x) + 10

  def render(self, rect: rl.Rectangle, current_menu: int) -> Optional[int]:
    """Renders the top strip with the title and menu navigation."""

    title_height = self._calculate_height()
    key_status_height = Theme.key_status_font_size * 1.5  # Approximate height

    # --- Draw Title Strip ---
    title_rect = rl.Rectangle(0, 0, gui_app.width, title_height)
    rl.draw_rectangle_rec(title_rect, Theme.title_bg_color)
    self._draw_title(rect, current_menu)

    # --- Draw Key Status Strip ---
    key_status_y = title_height
    key_status_rect = rl.Rectangle(0, key_status_y, gui_app.width, key_status_height)
    rl.draw_rectangle_rec(key_status_rect, Theme.nav_bg_color)  # Use nav_bg_color for key status
    self._draw_key_status(key_status_rect)

    # --- Draw Navigation Buttons (Overlapping) ---
    nav_rect = rl.Rectangle(0, 0, gui_app.width, title_height + key_status_height) # Overlap both
    new_menu = self._draw_navigation_buttons(nav_rect, current_menu)

    if new_menu is not None:
      return new_menu
    return None
