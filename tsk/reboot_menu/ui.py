# tsk/reboot_menu/ui.py
import pyray as rl
from openpilot.system.ui.lib.application import gui_app

from tsk.common.env import RECOMMENDED_OP_USER, RECOMMENDED_OP_BRANCH, ALTERNATE_OP_USER, ALTERNATE_OP_BRANCH
from tsk.reboot_menu.actions import Rebooter  # Import the class
from tsk.ui.button import Button
from tsk.ui.header import Header
from tsk.ui.layout import Layout, Theme  # Import Theme


class RebootMenuUI:
  """Manages the Restart Menu and its state."""

  def __init__(self):
    self.rebooter = Rebooter()  # Create an instance here

    self.header = Header()
    header_height = self.header._calculate_height()
    key_status_height = Theme.key_status_font_size * 1.5  # Approximate height
    combined_header_height = header_height + key_status_height

    rect = rl.Rectangle(0, 0, gui_app.width, gui_app.height)  # Dummy rectangle for initial calculations
    # Calculate button height using the same function as in tools.py
    button_height = Layout.calculate_button_dimensions(rect.height, combined_header_height)

    # Calculate start_y to position the buttons correctly
    start_x, start_y = Layout.calculate_button_positions(rect, combined_header_height, 3)

    # Button positions
    button1_x = start_x
    button2_x = start_x + 600 + 80
    button3_x = start_x + 2 * (600 + 80)

    button_y = start_y

    self.recommended_button = Button(self.rebooter.recommended_action, [  # Call the method on the instance
      {"text": "Install", "x_offset": 70, "y_offset": 40},
      {"text": f"{RECOMMENDED_OP_USER}/", "x_offset": 70, "y_offset": 140},
      {"text": f"{RECOMMENDED_OP_BRANCH}", "x_offset": 70, "y_offset": 240},
    ], 600, button_height, button1_x, button_y, 90)

    self.alternate_button = Button(self.rebooter.alternate_action, [  # Call the method on the instance
      {"text": "Install", "x_offset": 70, "y_offset": 40},
      {"text": f"{ALTERNATE_OP_USER}/", "x_offset": 70, "y_offset": 140},
      {"text": f"{ALTERNATE_OP_BRANCH}", "x_offset": 70, "y_offset": 240},
    ], 600, button_height, button2_x, button_y, 90)

    self.bail_button = Button(self.rebooter.bail_action, [  # Call the method on the instance
      {"text": "Install a", "x_offset": 70, "y_offset": 40},
      {"text": "different", "x_offset": 70, "y_offset": 140},
      {"text": "fork/branch", "x_offset": 70, "y_offset": 240},
    ], 600, button_height, button3_x, button_y, 90)

    # Add the "Retry" button
    retry_button_width = 3 * 600 + 2 * 80
    retry_button_x = (rect.width - retry_button_width) / 2 + rect.x
    retry_button_y = button_y + button_height + 80

    self.retry_button = Button(self.rebooter.retry_action, [  # Call the method on the instance
      {"text": "Reboot to try again",
       "x_offset": (retry_button_width - rl.measure_text_ex(gui_app.font(), "Reboot to try again", 90, 1.0).x) / 2,
       "y_offset": 60},
    ], retry_button_width, 200, retry_button_x, retry_button_y, 90)

  def render(self, rect: rl.Rectangle):
    """Renders the Restart Menu."""

    self.recommended_button.render()
    self.alternate_button.render()
    self.bail_button.render()
    self.retry_button.render()
