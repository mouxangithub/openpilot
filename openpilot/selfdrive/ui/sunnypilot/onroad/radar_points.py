"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
See the LICENSE.md file in the root directory for more details.
"""
"""Draws the measured front-radar points as a display-only overlay.

Ported from carrot's ``_draw_radar_info_carrot``. The point selection and the
projection geometry live in ``ui.radar_display`` so they stay importable
without a raylib context; this module only does the drawing.

Nothing here feeds control: the points are a developer view of what radard is
tracking, and the overlay is off by default.

Level scale follows carrot's ``ShowRadarInfo`` param: 0=off, 1=speed box only,
2=+ lateral offset / distance, 3=+ static returns drawn as "*". Divergence from
carrot: its levels 1/2 fall back to labelling the control lead groups, which
duplicates the chevron lead indicator here, so this port keeps labelling the
measured points and only prunes the clutter instead.
"""
import pyray as rl
from openpilot.selfdrive.ui.radar_display import (
  RADAR_MIN_DRAW_DISTANCE_M, RADAR_MIN_MOVING_SPEED_MS, RADAR_POINTS_LEVEL, combined_speed,
  predicted_offset, radar_point_z, select_radar_display_points, speed_text,
)
from openpilot.selfdrive.ui.signal_status import (
  POINT_COLOR_APPROACHING, POINT_COLOR_RECEDING, POINT_COLOR_SHADOW, point_box_color,
)
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached


def radar_info_level() -> int:
  """Effective overlay level, clamped to carrot's 0-3 scale."""
  try:
    level = int(getattr(ui_state, "radar_info_level", 0) or 0)
  except (TypeError, ValueError):
    level = 0
  if level <= 0 and getattr(ui_state, "carrot_radar_points", False):
    # legacy boolean writers (tests, stale params state) keep the old full view
    return 3
  return max(0, min(level, 3))


class RadarPointsRenderer:
  """Projects the current display points into the road view."""

  def __init__(self):
    self._font = gui_app.font(FontWeight.SEMI_BOLD)

  def render(self, sm, rect: rl.Rectangle, lane_points, project) -> None:
    """`project` maps (d_rel, y_rel, z) in car space to screen pixels, or None."""
    level = radar_info_level()
    if level <= 0:
      return
    if not sm.valid['modelV2']:
      return

    points = select_radar_display_points(sm, RADAR_POINTS_LEVEL, started_frame=ui_state.started_frame)
    if not points:
      return

    for point in points:
      d_rel = float(point.dRel)
      if d_rel <= RADAR_MIN_DRAW_DISTANCE_M:
        continue
      z = radar_point_z(lane_points, d_rel)
      if z is None:
        continue
      y_rel = float(point.yRel)
      screen = project(d_rel, -y_rel, z)
      if screen is None:
        continue
      self._draw_point(rect, screen, point, d_rel, y_rel, z, project, level)

  def _draw_point(self, rect: rl.Rectangle, screen, point, d_rel: float, y_rel: float, z: float, project, level: int) -> None:
    x, y = float(screen[0]), float(screen[1])
    v = float(point.vLeadK)
    v_lat = float(point.vLat)
    v_abs, v_sum = combined_speed(v, v_lat)

    if v_abs <= RADAR_MIN_MOVING_SPEED_MS:
      if level >= 3:
        self._draw_text(rect, "*", x, y, 40)
      return

    # where the point will be shortly: carrot's lateral preview vector
    a_d_rel, a_y_rel = predicted_offset(d_rel, y_rel, v, v_lat)
    ahead = project(a_d_rel, -a_y_rel, z)
    color = rl.Color(*(POINT_COLOR_APPROACHING if v_sum > 0.0 else POINT_COLOR_RECEDING))
    if ahead is not None:
      rl.draw_line_ex(rl.Vector2(x, y), rl.Vector2(float(ahead[0]), float(ahead[1])), 3.0, color)
      rl.draw_circle(int(ahead[0]), int(ahead[1]), 10.0, color)

    box_color = point_box_color(v_sum, bool(point.radar), float(point.modelProb))
    self._draw_text_box(rect, x, y, speed_text(v_sum, ui_state.is_metric), 40, rl.Color(*box_color))
    if level >= 2:
      self._draw_text(rect, f"{y_rel:.1f}", x, y - 40, 30)
      self._draw_text(rect, f"{d_rel:.1f}", x, y + 30, 30)

  def _draw_text_box(self, rect: rl.Rectangle, x: float, y: float, text: str, font_size: int, box_color: rl.Color) -> None:
    width = max(40, int(len(text) * font_size * 0.8))
    box = rl.Rectangle(x - width / 2, y - 20, float(width), 42.0)
    rl.draw_rectangle_rounded(box, 0.15, 12, box_color)
    self._draw_text(rect, text, x, y, font_size)

  def _draw_text(self, rect: rl.Rectangle, text: str, cx: float, cy: float, font_size: int) -> None:
    width = measure_text_cached(self._font, text, font_size, 0).x
    x = min(max(cx - width / 2, rect.x), max(rect.x, rect.x + rect.width - width))
    pos = rl.Vector2(x, cy - font_size / 2)
    rl.draw_text_ex(self._font, text, rl.Vector2(pos.x + 2, pos.y + 2), font_size, 0, rl.Color(*POINT_COLOR_SHADOW))
    rl.draw_text_ex(self._font, text, pos, font_size, 0, rl.WHITE)
