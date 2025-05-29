# tsk/tools_menu/ui.py
import pyray as rl

from openpilot.system.ui.lib.application import gui_app
from tsk.tools_menu.actions import tsk_extractor_action, tsk_guide_action, tsk_uninstaller_action  # Import actions
from tsk.tools_menu.keyboard import KeyboardDialog
from tsk.ui.button import Button
from tsk.ui.header import Header
from tsk.ui.layout import Layout, Theme  # Import Theme


class ToolsMenuUI:
  """Renders the Tools Menu with buttons for TSK actions."""

  def __init__(self):
    """Initializes the Tools Menu."""
    self.header = Header()
    header_height = self.header._calculate_height()
    key_status_height = Theme.key_status_font_size * 1.5  # Approximate height
    combined_header_height = header_height + key_status_height

    rect = rl.Rectangle(0, 0, gui_app.width, gui_app.height)  # Dummy rectangle for initial calculations
    button_height = Layout.calculate_button_dimensions(rect.height, combined_header_height)

    # --- Calculate Positions for the Three Main Buttons ---
    start_x, start_y = Layout.calculate_button_positions(rect, combined_header_height, 3)

    button1_x = start_x
    button2_x = start_x + (600 + 80)
    button3_x = start_x + 2 * (600 + 80)

    button_y = start_y

    # --- Create the Three Main Buttons ---
    self.extractor_button = Button(tsk_extractor_action,
                                   [{"text": "TSK Extractor", "x_offset": 55, "y_offset": (button_height / 2) - 45}],
                                   600, button_height, button1_x, button_y, 90)
    self.keyboard_button = Button(KeyboardDialog.ask,
                                  [{"text": "TSK Keyboard", "x_offset": 45, "y_offset": (button_height / 2) - 45}], 600,
                                  button_height, button2_x, button_y, 90)
    self.uninstaller_button = Button(tsk_uninstaller_action, [
      {"text": "TSK Uninstaller", "x_offset": 25, "y_offset": (button_height / 2) - 45}], 600, button_height, button3_x,
                                     button_y, 90)

    # --- Create the "Tell me what to do next" Button ---
    guide_button_width = (3 * 600) + (2 * 80)
    guide_button_height = 200
    guide_button_x = start_x
    guide_button_y = button_y + button_height + 80

    self.guide_button = Button(tsk_guide_action, [
      {
        "text": "Tell me what to do next",
        "x_offset": (guide_button_width - rl.measure_text_ex(gui_app.font(), "Tell me what to do next", 90, 1.0).x) / 2,
        "y_offset": 60,
      }
    ], guide_button_width, guide_button_height, guide_button_x, guide_button_y, 90)

  def render(self, rect: rl.Rectangle) -> None:
    """Renders the Tools Menu."""

    self.extractor_button.render()
    self.keyboard_button.render()
    self.uninstaller_button.render()
    self.guide_button.render()
