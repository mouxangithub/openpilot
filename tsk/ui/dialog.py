# tsk/ui/dialog.py
import pyray as rl

from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.button import gui_button, DEFAULT_BUTTON_FONT_SIZE
from openpilot.system.ui.lib.scroll_panel import GuiScrollPanel


class BaseDialog:
  """Base class for full-screen dialogs with a scrollable text area."""

  BORDER_SIZE = 20
  BUTTON_HEIGHT = 80
  BUTTON_WIDTH = 310
  BUTTON_SPACING = 20
  FONT_SIZE = 100
  LINE_HEIGHT = FONT_SIZE * 1.1
  TEXT_PADDING = 10

  def __init__(self, body_text: str, font_size: int = FONT_SIZE, scroll_to_bottom: bool = False):
    self.body_text = body_text
    self.font_size = font_size
    self.scroll_to_bottom = scroll_to_bottom
    self.LINE_HEIGHT = self.font_size * 1.1
    self.textarea_rect = rl.Rectangle(
      self.BORDER_SIZE,
      self.BORDER_SIZE,
      gui_app.width - 2 * self.BORDER_SIZE,
      gui_app.height - 3 * self.BORDER_SIZE - self.BUTTON_HEIGHT  # Account for buttons and spacing
    )
    self.wrapped_lines = self._wrap_text(self.body_text, self.font_size, self.textarea_rect.width - 2 * self.TEXT_PADDING)
    self.content_height = len(self.wrapped_lines) * self.LINE_HEIGHT
    self.content_rect = rl.Rectangle(0, 0, self.textarea_rect.width - 2 * self.TEXT_PADDING, self.content_height)
    self.scroll_panel = GuiScrollPanel(show_vertical_scroll_bar=True)
    self.scroll_offset = rl.Vector2(0, 0) # Store the scroll offset
    self.initial_scroll_applied = False  # Flag to track initial scroll application

  def render_text_area(self):
    """Renders the scrollable text area."""

    scroll = self.scroll_panel.handle_scroll(self.textarea_rect, self.content_rect)
    self.scroll_offset = scroll # Update the scroll offset after handling user input

    # Apply initial scroll to bottom after the first render
    if self.scroll_to_bottom and not self.initial_scroll_applied:
      self.scroll_offset.y = min(0, self.textarea_rect.height - self.content_height - 2 * self.TEXT_PADDING)
      self.initial_scroll_applied = True

    rl.begin_scissor_mode(int(self.textarea_rect.x), int(self.textarea_rect.y), int(self.textarea_rect.width), int(self.textarea_rect.height))
    y_offset = 0
    for line in self.wrapped_lines:
      position = rl.Vector2(self.textarea_rect.x + self.TEXT_PADDING + self.scroll_offset.x, self.textarea_rect.y + self.TEXT_PADDING + self.scroll_offset.y + y_offset)
      if position.y + self.LINE_HEIGHT < self.textarea_rect.y + self.TEXT_PADDING or position.y > self.textarea_rect.y + self.textarea_rect.height - self.TEXT_PADDING:
        y_offset += self.LINE_HEIGHT
        continue
      rl.draw_text_ex(gui_app.font(), line.strip(), position, self.font_size, 0, rl.WHITE)
      y_offset += self.LINE_HEIGHT
    rl.end_scissor_mode()

  def _wrap_text(self, text, font_size, max_width):
    lines = []
    font = gui_app.font()

    # Split the text by newline characters
    for block in text.splitlines():
      if not block:  # Handle empty lines (consecutive newlines)
        lines.append("")  # Add an empty line
        continue

      current_line = ""
      for word in block.split():
        test_line = current_line + word + " "
        if rl.measure_text_ex(font, test_line, font_size, 0).x <= max_width:
          current_line = test_line
        else:
          lines.append(current_line)
          current_line = word + " "
      if current_line:
        lines.append(current_line)

    return lines


class OkayDialog(BaseDialog):
  """A full-screen dialog with a scrollable text area and an Okay button."""

  @staticmethod
  def ask(body_text: str, font_size: int = BaseDialog.FONT_SIZE, scroll_to_bottom: bool = False, okay_text: str = "Okay") -> None:
    """Displays a full-screen Okay dialog."""
    okay_pressed = False

    dialog = OkayDialog(body_text, font_size, scroll_to_bottom)

    def render_dialog():
      nonlocal okay_pressed  # Allow modification of the okay_pressed variable

      dialog.render_text_area()

      # Calculate the available height for the button area
      button_area_height = gui_app.height - dialog.textarea_rect.height - dialog.textarea_rect.y

      # Button position (centered horizontally, vertically centered in the button area)
      button_x = (gui_app.width - BaseDialog.BUTTON_WIDTH) / 2
      button_y = dialog.textarea_rect.y + dialog.textarea_rect.height + (button_area_height - BaseDialog.BUTTON_HEIGHT) / 2

      # Okay Button
      if gui_button(rl.Rectangle(button_x, button_y, BaseDialog.BUTTON_WIDTH, BaseDialog.BUTTON_HEIGHT), okay_text):
        okay_pressed = True

    # Main loop
    while not okay_pressed and not rl.window_should_close():
      rl.begin_drawing()
      rl.clear_background(rl.BLACK)

      render_dialog()

      rl.end_drawing()


class YesNoDialog(BaseDialog):
  """A full-screen dialog with a scrollable text area and Yes/No buttons."""

  @staticmethod
  def ask(body_text: str, font_size: int = BaseDialog.FONT_SIZE, scroll_to_bottom: bool = False, yes_text: str = "Yes", no_text: str = "No") -> bool | None:
    """Displays a full-screen Yes/No dialog and returns a boolean based on the user's choice."""
    result = None  # Use None to indicate the dialog is still active

    dialog = YesNoDialog(body_text, font_size, scroll_to_bottom)

    def render_dialog():
      nonlocal result  # Allow modification of the result variable

      dialog.render_text_area()

      button_top = gui_app.height - BaseDialog.BORDER_SIZE - BaseDialog.BUTTON_HEIGHT
      no_button_x = BaseDialog.BORDER_SIZE
      yes_button_x = gui_app.width - BaseDialog.BORDER_SIZE - BaseDialog.BUTTON_WIDTH

      no_button_rect = rl.Rectangle(no_button_x, button_top, BaseDialog.BUTTON_WIDTH, BaseDialog.BUTTON_HEIGHT)
      yes_button_rect = rl.Rectangle(yes_button_x, button_top, BaseDialog.BUTTON_WIDTH, BaseDialog.BUTTON_HEIGHT)

      if draw_custom_button(no_button_rect, no_text, rl.Color(100, 20, 20, 255)):
        result = False
      if draw_custom_button(yes_button_rect, yes_text, rl.Color(20, 100, 20, 255)):
        result = True

    # Main loop
    while result is None and not rl.window_should_close():
      rl.begin_drawing()
      rl.clear_background(rl.BLACK)

      render_dialog()

      rl.end_drawing()

    return result


def draw_custom_button(rect: rl.Rectangle, text: str, color: rl.Color) -> bool:
  """Draws a custom button with specified color and handles click detection."""
  mouse_pos = rl.get_mouse_position()
  is_hovering = rl.check_collision_point_rec(mouse_pos, rect)
  is_pressed = is_hovering and rl.is_mouse_button_released(rl.MouseButton.MOUSE_BUTTON_LEFT)
  result = False

  rl.draw_rectangle_rec(rect, color)

  # Draw button text (centered)
  font = gui_app.font()
  text_size = rl.measure_text_ex(font, text, DEFAULT_BUTTON_FONT_SIZE, 0)
  text_x = rect.x + (rect.width - text_size.x) / 2
  text_y = rect.y + (rect.height - text_size.y) / 2
  rl.draw_text_ex(font, text, rl.Vector2(text_x, text_y), DEFAULT_BUTTON_FONT_SIZE, 0, rl.WHITE)

  if is_pressed:
    result = True

  return result
