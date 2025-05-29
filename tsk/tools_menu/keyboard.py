# tsk/tools_menu/keyboard.py
import pyray as rl

from openpilot.system.ui.lib.application import gui_app
from tsk.common.key_file_manager import KeyFileManager


class KeyboardDialog:
  """A full-screen keyboard."""

  def __init__(self):
    self.key_file_manager = KeyFileManager()
    self.key_status_text = "Key not installed"
    self.input_text = ""
    self.max_input_length = 32
    self.show_install_button = False
    self.install_success = False  # Added success flag

    # Font and Color Definitions
    self.font_size = 100
    self.key_status_font_size = 90 # Added key status font size
    self.keyboard_bg_color = rl.Color(51, 51, 51, 255)  # Solid dark gray
    self.keyboard_border_color = rl.BLACK
    self.keyboard_border_thickness = 4
    self.x_button_text = " X "  # X with spaces
    self.x_button_text_color = rl.Color(150, 150, 150, 255)  # Brighter gray
    self.input_box_bg_color = rl.BLACK  # Black background
    self.input_box_border_color = rl.WHITE  # White border
    self.input_text_color_1 = rl.Color(120, 120, 120, 255)  # Darker light gray
    self.input_text_color_2 = rl.DARKGRAY

    # Calculate Input Box Dimensions
    widest_char = max("0123456789abcdef", key=lambda c: rl.measure_text_ex(gui_app.font(), c, self.font_size, 0).x)
    self.char_width = rl.measure_text_ex(gui_app.font(), widest_char, self.font_size, 0).x
    self.input_box_width = self.char_width * self.max_input_length

    # Calculate "X" Button Dimensions
    x_text_size = rl.measure_text_ex(gui_app.font(), self.x_button_text, self.font_size, 0)
    self.x_button_width = int(x_text_size.x * 1.2)  # Add some padding
    self.x_button_height = int(x_text_size.y * 1.2)  # Add some padding

    # Define Keyboard Layout and Dimensions
    self.keyboard_layout = ["1234567890", "abcdef<"]
    self.keyboard_button_height = 200
    self.keyboard_spacing = 0
    self.keyboard_button_width_row1 = gui_app.width / len(self.keyboard_layout[0])
    self.keyboard_button_width_row2 = gui_app.width / len(self.keyboard_layout[1])

  def update_key_status(self):
    """Updates the key status text."""
    key = self.key_file_manager.installed_key
    self.key_status_text = f"Key installed: {key}" if key else "Key not installed"

  def draw_x_button(self, rect: rl.Rectangle, text: str) -> bool:
    """Draws the "X" button and handles click detection."""
    is_pressed = rl.check_collision_point_rec(rl.get_mouse_position(), rect) and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)

    # Draw button rectangle
    rl.draw_rectangle_rec(rect, self.keyboard_bg_color)

    # Draw text
    text_size = rl.measure_text_ex(gui_app.font(), text, self.font_size, 0)
    text_x = rect.x + (rect.width - text_size.x) / 2
    text_y = rect.y + (rect.height - text_size.y) / 2
    rl.draw_text_ex(gui_app.font(), text, rl.Vector2(text_x, text_y), self.font_size, 0, self.x_button_text_color)

    return is_pressed

  def draw_keyboard(self, rect: rl.Rectangle) -> None:
    """Draws the on-screen keyboard."""
    start_x = rect.x
    start_y = rect.y

    for row_index, row in enumerate(self.keyboard_layout):
      button_width = self.keyboard_button_width_row1 if row_index == 0 else self.keyboard_button_width_row2
      for key_index, key in enumerate(row):
        button_x = start_x + key_index * (button_width + self.keyboard_spacing)
        button_y = start_y + row_index * (self.keyboard_button_height + self.keyboard_spacing)
        button_rect = rl.Rectangle(button_x, button_y, button_width, self.keyboard_button_height)

        is_pressed = rl.check_collision_point_rec(rl.get_mouse_position(), button_rect) and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)

        # Draw button rectangle
        rl.draw_rectangle_rec(button_rect, self.keyboard_bg_color)
        rl.draw_rectangle_lines_ex(button_rect, self.keyboard_border_thickness, self.keyboard_border_color)

        # Draw text
        text_size = rl.measure_text_ex(gui_app.font(), key, self.font_size, 0)
        text_x = button_x + (button_width - text_size.x) / 2
        text_y = button_y + (self.keyboard_button_height - text_size.y) / 2
        rl.draw_text_ex(gui_app.font(), key, rl.Vector2(text_x, text_y), self.font_size, 0, rl.LIGHTGRAY)

        if is_pressed:
          if key == "<":
            self.input_text = self.input_text[:-1]
          else:
            if len(self.input_text) < self.max_input_length:
              self.input_text += key
          self.show_install_button = len(self.input_text) == self.max_input_length
          self.install_success = False # Reset success flag when input changes

  @staticmethod
  def ask():
    """Displays the TSK Keyboard dialog."""
    dialog_open = True
    dialog = KeyboardDialog()

    # Get the current key and set it as the default text
    installed_key = dialog.key_file_manager.installed_key
    if installed_key:
      dialog.input_text = installed_key
      dialog.show_install_button = len(dialog.input_text) == dialog.max_input_length

    dialog.update_key_status()  # Initial key status update

    def render_dialog():
      nonlocal dialog_open

      # Calculate vertical centering
      keyboard_height = 2 * dialog.keyboard_button_height
      available_height = gui_app.height - keyboard_height
      total_content_height = 0

      # Key Status Label
      dialog.update_key_status()
      key_status_text_size = rl.measure_text_ex(gui_app.font(), dialog.key_status_text, dialog.key_status_font_size, 0)
      total_content_height += key_status_text_size.y

      # Input Box
      input_box_height = dialog.font_size * 1.5
      total_content_height += input_box_height

      # Remaining Characters Label / Install Button / Success Label
      total_content_height += dialog.font_size # Approximate height

      vertical_offset = (available_height - total_content_height) / 2

      # Key Status Label
      key_status_text_x = (gui_app.width - key_status_text_size.x) / 2
      key_status_text_y = 20 + vertical_offset # Apply vertical offset
      rl.draw_text_ex(gui_app.font(), dialog.key_status_text, rl.Vector2(key_status_text_x, key_status_text_y), dialog.key_status_font_size, 0, rl.LIGHTGRAY) # Light gray

      # Input Box
      input_box_x = (gui_app.width - dialog.input_box_width) / 2
      input_box_y = key_status_text_y + key_status_text_size.y + 20 # Apply vertical offset
      rl.draw_rectangle(int(input_box_x), int(input_box_y), int(dialog.input_box_width), int(input_box_height), dialog.input_box_bg_color)
      rl.draw_rectangle_lines(int(input_box_x), int(input_box_y), int(dialog.input_box_width), int(input_box_height), dialog.input_box_border_color)

      # Draw input text with color cycling
      input_text_x = input_box_x + 5
      input_text_y = input_box_y + (input_box_height - rl.measure_text_ex(gui_app.font(), "A", dialog.font_size, 0).y) / 2
      x_offset = 0
      for i, char in enumerate(dialog.input_text):
        color = dialog.input_text_color_1 if (i // 4) % 2 == 0 else dialog.input_text_color_2
        char_width = rl.measure_text_ex(gui_app.font(), char, dialog.font_size, 0).x
        rl.draw_text_ex(gui_app.font(), char, rl.Vector2(input_text_x + x_offset, input_text_y), dialog.font_size, 0, color)
        x_offset += char_width

      # Remaining Characters Label / Install Button / Success Label
      remaining_chars = dialog.max_input_length - len(dialog.input_text)
      remaining_text_y = input_box_y + input_box_height + 10 # Apply vertical offset

      if dialog.install_success:
        # Success Label
        success_text = "Success!"
        success_text_size = rl.measure_text_ex(gui_app.font(), success_text, dialog.font_size, 0)
        success_text_x = (gui_app.width - success_text_size.x) / 2
        rl.draw_text_ex(gui_app.font(), success_text, rl.Vector2(success_text_x, remaining_text_y), dialog.font_size, 0, rl.GREEN)

      elif dialog.show_install_button:
        # Install Button
        install_text = "Install this key"
        install_text_size = rl.measure_text_ex(gui_app.font(), install_text, dialog.font_size, 0)
        install_button_width = install_text_size.x + 40  # Add some padding
        install_button_height = install_text_size.y + 20 # Add some padding
        install_button_x = (gui_app.width - install_button_width) / 2
        install_button_rect = rl.Rectangle(install_button_x, remaining_text_y, install_button_width, install_button_height)
        if rl.check_collision_point_rec(rl.get_mouse_position(), install_button_rect) and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
          # Install key
          dialog.key_file_manager.install_key(dialog.input_text)
          dialog.install_success = True
          dialog.show_install_button = False

        rl.draw_rectangle_rec(install_button_rect, dialog.keyboard_bg_color) # Keyboard background color
        install_text_x = install_button_x + (install_button_width - install_text_size.x) / 2
        install_text_y = remaining_text_y + (install_button_height - install_text_size.y) / 2
        rl.draw_text_ex(gui_app.font(), install_text, rl.Vector2(install_text_x, install_text_y), dialog.font_size, 0, rl.LIGHTGRAY) # Light gray text

      else:
        # Remaining Characters Label
        remaining_text = f"{remaining_chars} characters left"
        remaining_text_size = rl.measure_text_ex(gui_app.font(), remaining_text, dialog.font_size, 0)
        remaining_text_x = (gui_app.width - remaining_text_size.x) / 2
        rl.draw_text_ex(gui_app.font(), remaining_text, rl.Vector2(remaining_text_x, remaining_text_y), dialog.font_size, 0, rl.DARKGRAY)

      # "X" Button (Top Right - All the way to the edge)
      button_x = gui_app.width - dialog.x_button_width
      button_y = 0
      if dialog.draw_x_button(rl.Rectangle(button_x, button_y, dialog.x_button_width, dialog.x_button_height), dialog.x_button_text):
        dialog_open = False

      # Keyboard
      keyboard_x = 0
      keyboard_y = gui_app.height - 2 * dialog.keyboard_button_height
      keyboard_width = gui_app.width
      keyboard_height = 2 * dialog.keyboard_button_height
      dialog.draw_keyboard(rl.Rectangle(keyboard_x, keyboard_y, keyboard_width, keyboard_height))

    # Main loop
    while dialog_open and not rl.window_should_close():
      rl.begin_drawing()
      rl.clear_background(rl.BLACK)

      render_dialog()

      rl.end_drawing()
