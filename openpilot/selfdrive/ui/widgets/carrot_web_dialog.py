import pyray as rl

from openpilot.selfdrive.ui.carrot_web import CarrotWebQrSession, fit_single_line_font_size
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, MousePos, gui_app, TextAlignment, TextAlignmentVertical
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import gui_label

# Dialog canvas: 536x240 design units, scaled to fit the screen. Three service
# columns share it - QR on top, service name and address below.
DIALOG_WIDTH = 536
DIALOG_HEIGHT = 240
COLUMN_WIDTH = DIALOG_WIDTH / 3
QR_SIZE = 138


class CarrotWebDialog(Widget):
  def __init__(self):
    super().__init__()
    # UIState only exposes `params` (a Params() handle); there is no separate
    # params_memory. NetworkAddress is a persistent param, so the regular store
    # is the correct one for the QR address anyway.
    self._session = CarrotWebQrSession(ui_state.params)

  def show_event(self):
    super().show_event()
    self._session.open(rl.get_time())

  def _update_state(self):
    if self._session.update(rl.get_time()):
      gui_app.pop_widget()

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._session.can_close(rl.get_time()):
      gui_app.pop_widget()

  def _render(self, rect: rl.Rectangle):
    rl.clear_background(rl.BLACK)

    scale = min(rect.width / DIALOG_WIDTH, rect.height / DIALOG_HEIGHT)
    content_x = rect.x + (rect.width - DIALOG_WIDTH * scale) / 2
    content_y = rect.y + (rect.height - DIALOG_HEIGHT * scale) / 2

    for index, service in enumerate(self._session.services):
      self._render_service(
        rl.Rectangle(
          content_x + index * COLUMN_WIDTH * scale,
          content_y,
          COLUMN_WIDTH * scale,
          DIALOG_HEIGHT * scale,
        ),
        scale,
        service,
      )

    if self._session.updated_time is not None:
      footer_rect = rl.Rectangle(content_x, content_y + (DIALOG_HEIGHT - 22) * scale, DIALOG_WIDTH * scale, 20 * scale)
      gui_label(
        footer_rect,
        self._session.updated_time,
        int(14 * scale),
        rl.Color(135, 135, 135, 255),
        alignment=TextAlignment.LEFT,
      )
      gui_label(
        footer_rect,
        f"{self._session.seconds_until_close(rl.get_time())}s",
        int(14 * scale),
        rl.Color(135, 135, 135, 255),
        alignment=TextAlignment.RIGHT,
      )

  def _render_service(self, column: rl.Rectangle, scale: float, service) -> None:
    qr_size = QR_SIZE * scale
    qr_rect = rl.Rectangle(
      column.x + (column.width - qr_size) / 2,
      column.y + 12 * scale,
      qr_size,
      qr_size,
    )

    if not service.qr.render(qr_rect):
      rl.draw_rectangle_rounded(qr_rect, 0.04, 8, rl.Color(38, 38, 38, 255))
      gui_label(qr_rect, tr("Offline"), int(24 * scale), rl.Color(175, 175, 175, 255))

    name_rect = rl.Rectangle(column.x + 6 * scale, qr_rect.y + qr_rect.height + 8 * scale, column.width - 12 * scale, 32 * scale)
    gui_label(
      name_rect,
      service.label,
      int(24 * scale),
      rl.WHITE,
      alignment=TextAlignment.CENTER,
      font_weight=FontWeight.BOLD,
    )

    address_text = (service.url or tr("Offline")).removeprefix("http://")
    address_rect = rl.Rectangle(column.x + 4 * scale, name_rect.y + name_rect.height + 2 * scale, column.width - 8 * scale, 26 * scale)
    preferred_address_size = int(15 * scale)
    address_font = gui_app.font()
    measured = measure_text_cached(address_font, address_text, preferred_address_size).x
    address_size = fit_single_line_font_size(preferred_address_size, measured, address_rect.width)
    while address_size > 1 and measure_text_cached(address_font, address_text, address_size).x > address_rect.width:
      address_size -= 1

    gui_label(
      address_rect,
      address_text,
      address_size,
      rl.Color(205, 205, 205, 255),
      alignment=TextAlignment.CENTER,
      alignment_vertical=TextAlignmentVertical.TOP,
      elide_right=False,
    )

  def __del__(self):
    self._session.destroy()
