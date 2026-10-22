"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import requests
import threading
import time
import pyray as rl

from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.ui.sunnypilot.lib.drive_stats import refresh_local_drive_stats, fetch_cloud_drive_stats
from openpilot.selfdrive.ui.ui_state import ui_state, device
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget


class TripsLayout(Widget):
  DATA_SOURCE_PARAM = "TripsDataSource"
  LOCAL_KEY = "LocalDriveStats"
  UPDATE_INTERVAL = 30  # seconds

  TOGGLE_HEIGHT = 80
  TOGGLE_WIDTH = 400
  TOGGLE_Y_OFFSET = 30

  def __init__(self):
    super().__init__()
    self._params = Params()
    self._session = requests.Session()
    self._data_source = self._get_data_source()
    self._stats = self._get_local_stats() if self._data_source == "local" else {}

    self._icon_distance = gui_app.texture("icons/road.png", 100, 100, keep_aspect_ratio=True)
    self._icon_drives = gui_app.texture("icons_mici/wheel.png", 80, 80, keep_aspect_ratio=True)
    self._icon_hours = gui_app.texture("../../sunnypilot/selfdrive/assets/icons/clock.png", 80, 80, keep_aspect_ratio=True)

    self._local_btn_rect = rl.Rectangle(0, 0, 0, 0)
    self._cloud_btn_rect = rl.Rectangle(0, 0, 0, 0)

    self._running = True
    self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
    self._update_thread.start()

  def show_event(self):
    super().show_event()
    if self._data_source == "cloud" or not self._stats.get("all"):
      threading.Thread(target=self._refresh_drive_stats, daemon=True).start()

  def __del__(self):
    self._running = False
    try:
      if self._update_thread and self._update_thread.is_alive():
        self._update_thread.join(timeout=1.0)
    except Exception:
      pass

  def _get_data_source(self):
    return self._params.get(self.DATA_SOURCE_PARAM) or "local"

  def _set_data_source(self, source: str):
    self._data_source = source
    self._params.put(self.DATA_SOURCE_PARAM, source)
    threading.Thread(target=self._refresh_drive_stats, daemon=True).start()

  def _get_local_stats(self):
    stats = self._params.get(self.LOCAL_KEY)
    if not stats:
      return {}
    return stats

  def _refresh_drive_stats(self):
    # Always keep local stats up to date in the background
    refresh_local_drive_stats(self._params, self.LOCAL_KEY)
    if self._data_source == "cloud":
      cloud_stats = fetch_cloud_drive_stats(self._params, self._session)
      if "error" not in cloud_stats:
        self._stats = cloud_stats
    else:
      self._stats = self._get_local_stats()

  def _update_loop(self):
    while self._running:
      if not ui_state.started and device._awake:
        self._refresh_drive_stats()
      time.sleep(self.UPDATE_INTERVAL)

  def _handle_mouse_release(self, mouse_pos):
    if rl.check_collision_point_rec(mouse_pos, self._local_btn_rect) and self._data_source != "local":
      self._set_data_source("local")
    elif rl.check_collision_point_rec(mouse_pos, self._cloud_btn_rect) and self._data_source != "cloud":
      self._set_data_source("cloud")

  def _render_stat_group(self, x, y, width, height, title, data, is_metric):
    # Card Background
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, width, height), 0.05, 10, rl.Color(30, 30, 30, 255))

    # Title
    title_font = gui_app.font(FontWeight.BOLD)
    rl.draw_text_ex(title_font, title, rl.Vector2(x + 60, y + 30), 50 * FONT_SCALE, 0, rl.Color(200, 200, 200, 255))

    # Internal content area
    # Center the content block (Icon + Value + Unit) vertically
    content_y = y + (height / 2) - (140 * FONT_SCALE)
    col_width = width / 3

    # Values
    number_font = gui_app.font(FontWeight.BOLD)
    unit_font = gui_app.font(FontWeight.NORMAL)
    number_base_size = 92
    unit_base_size = 55
    number_size = number_base_size * FONT_SCALE
    unit_size = unit_base_size * FONT_SCALE
    color_unit = rl.Color(160, 160, 160, 255)

    routes = int(data.get("routes", 0))
    distance = data.get("distance", 0)
    distance_str = str(int(distance * CV.MPH_TO_KPH)) if is_metric else str(int(distance))
    hours = int(data.get("minutes", 0) / 60)

    dist_unit = tr("KM") if is_metric else tr("Miles")

    def draw_col(col_idx, icon, value, unit):
      col_x = x + (col_width * col_idx)
      center_x = col_x + (col_width / 2)

      # Icon
      icon_x = center_x - (icon.width / 2)
      icon_y = content_y + 60
      rl.draw_texture_ex(icon, rl.Vector2(icon_x, icon_y), 0.0, 1.0, rl.WHITE)

      # Value
      val_size = measure_text_cached(number_font, value, number_base_size)
      rl.draw_text_ex(number_font, value, rl.Vector2(center_x - val_size.x / 1.65, content_y + 145 * FONT_SCALE), number_size, 0, rl.WHITE)

      # Unit
      unit_size_vec = measure_text_cached(unit_font, unit, unit_base_size)
      rl.draw_text_ex(unit_font, unit, rl.Vector2(center_x - unit_size_vec.x / 1.65, content_y + 255 * FONT_SCALE), unit_size, 0, color_unit)

    draw_col(0, self._icon_drives, str(routes), tr("Drives"))
    draw_col(1, self._icon_distance, distance_str, dist_unit)
    draw_col(2, self._icon_hours, str(hours), tr("Hours"))

    return y + height

  def _render_toggle(self, x, y, width):
    font = gui_app.font(FontWeight.BOLD)
    text_size = 40 * FONT_SCALE
    toggle_bg_color = rl.Color(50, 50, 50, 255)
    toggle_active_color = rl.Color(80, 80, 80, 255)
    text_color = rl.WHITE

    toggle_x = x + (width - self.TOGGLE_WIDTH) / 2
    toggle_rect = rl.Rectangle(toggle_x, y, self.TOGGLE_WIDTH, self.TOGGLE_HEIGHT)
    rl.draw_rectangle_rounded(toggle_rect, 0.5, 10, toggle_bg_color)

    half_w = self.TOGGLE_WIDTH / 2
    local_rect = rl.Rectangle(toggle_x, y, half_w, self.TOGGLE_HEIGHT)
    cloud_rect = rl.Rectangle(toggle_x + half_w, y, half_w, self.TOGGLE_HEIGHT)

    # Highlight selected
    if self._data_source == "local":
      rl.draw_rectangle_rounded(local_rect, 0.5, 10, toggle_active_color)
    else:
      rl.draw_rectangle_rounded(cloud_rect, 0.5, 10, toggle_active_color)

    def draw_centered_text(rect, label):
      size = measure_text_cached(font, label, int(text_size))
      pos = rl.Vector2(
        rect.x + (rect.width - size.x) / 2,
        rect.y + (rect.height - size.y) / 2
      )
      rl.draw_text_ex(font, label, pos, text_size, 0, text_color)

    draw_centered_text(local_rect, tr("Local"))
    draw_centered_text(cloud_rect, tr("Cloud"))

    self._local_btn_rect = local_rect
    self._cloud_btn_rect = cloud_rect

    return y + self.TOGGLE_HEIGHT

  def _render(self, rect: rl.Rectangle):
    x = rect.x
    y = rect.y
    w = rect.width

    spacing = 30
    toggle_area = self.TOGGLE_HEIGHT + self.TOGGLE_Y_OFFSET
    available_h = rect.height - spacing - toggle_area
    card_height = available_h / 2

    is_metric = self._params.get_bool("IsMetric")

    # Refresh data source from param in case it was changed externally
    self._data_source = self._get_data_source()

    y += self.TOGGLE_Y_OFFSET
    y = self._render_toggle(x, y, w)
    y += spacing

    all_time = self._stats.get("all", {})
    week = self._stats.get("week", {})

    y = self._render_stat_group(x, y, w, card_height, tr("ALL TIME"), all_time, is_metric)
    y += spacing
    y = self._render_stat_group(x, y, w, card_height, tr("PAST WEEK"), week, is_metric)
