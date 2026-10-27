"""
Speed-limit source drawer, ported from StarPilot
(``speed_source_drawer.py`` + the source rows of ``slc_speed_limit.py``).

An L-shaped drawer slides out to the right of the speed-limit sign, listing
every enabled source's raw limit reading with the resolver's active source
highlighted.

Data sources (sunnypilot): the SpeedLimitResolver only publishes the aggregate
(``longitudinalPlanSP.speedLimit.resolver``: speedLimit/source/...), so the
per-source readings are taken where the resolver gets them:
- Dashboard: ``carStateSP.speedLimit`` (resolver's ``car`` source)
- Map Data:  ``liveMapDataSP.speedLimit``
- Vision:    memory param ``VisionSpeedLimit`` (only when
  ``VisionSpeedLimitEnabled`` is on)
- Upcoming:  ``liveMapDataSP.speedLimitAhead`` (when valid)
Active source highlight: ``resolver.source`` mapped to the row names.

Mount point: ``HudRendererSP._render`` right after the speed-limit sign; the
sign's rect is recomputed with the same layout rules SpeedLimitRenderer uses
(CarrotPanelSide aware). Gated by the unregistered param
``ShowSpeedLimitSources`` (code default OFF).
"""
import math

import pyray as rl

from openpilot.common.params import Params
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.onroad.hud_renderer import UI_CONFIG
from openpilot.selfdrive.ui.sunnypilot.onroad.param_guards import safe_get_bool, safe_get_float, safe_get_str
from openpilot.selfdrive.ui.sunnypilot.onroad.source_bubble_layout import (
  enabled_source_titles, fit_source_label, source_value_text, visible_source_rows,
)
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

SOURCE_DRAWER_WIDTH = 248
OPEN_SECONDS = 0.18
CLOSE_SECONDS = 0.14
_CONTROL_SEGMENTS = 10
_CONTROL_ROUNDNESS = 0.35
_QUARTER = tuple((math.cos(i * math.pi / (2 * _CONTROL_SEGMENTS)), math.sin(i * math.pi / (2 * _CONTROL_SEGMENTS)))
                 for i in range(_CONTROL_SEGMENTS + 1))

PARAM_REFRESH_INTERVAL = 0.25  # seconds; params are not per-frame data

# Source display metadata: source name, resolver row label, value key in the
# state dict, panel label. Mirrors StarPilot's SOURCE_DEFS minus Mapbox.
SOURCE_DEFS = [
  ("Dashboard", "Dash", "dashboard_sl", "Dashboard"),
  ("Map Data", "MAP", "map_sl", "Map Data"),
  ("Vision", "VISION", "vision_sl", "Vision"),
  ("Upcoming", "NEXT", "next_sl", "Next"),
]

# resolver Source enum -> row title
RESOLVER_SOURCE_TO_TITLE = {
  "car": "Dashboard",
  "map": "Map Data",
}

_WHITE = rl.Color(255, 255, 255, 255)
_ACCENT = rl.Color(160, 96, 230, 230)
_SOURCE_PANEL_PAD_X = 16
_SOURCE_PANEL_PAD_Y = 12
_SOURCE_DIVIDER = rl.Color(_ACCENT.r, _ACCENT.g, _ACCENT.b, 90)
_SOURCE_LABEL_MUTED = rl.Color(170, 179, 174, 255)
_SOURCE_LABEL_SIZE = 26
_SOURCE_VALUE_SIZE = 28
_SOURCE_MIN_LABEL_VALUE_GAP = 12

_FONT_BOLD = None
_FONT_SEMI_BOLD = None


def _get_bold():
  global _FONT_BOLD
  if _FONT_BOLD is None:
    _FONT_BOLD = gui_app.font(FontWeight.BOLD)
  return _FONT_BOLD


def _get_semi_bold():
  global _FONT_SEMI_BOLD
  if _FONT_SEMI_BOLD is None:
    _FONT_SEMI_BOLD = gui_app.font(FontWeight.SEMI_BOLD)
  return _FONT_SEMI_BOLD


def _draw_source_contents(state: dict, panel_rect: rl.Rectangle) -> None:
  """Draw raw source readings; the accepted source is white and bold."""
  font_semi = _get_semi_bold()
  font_bold = _get_bold()
  active_source = state['speed_limit_source']
  enabled_sources = state.get('slc_enabled_sources', ())

  rows = visible_source_rows(SOURCE_DEFS, state, active_source, enabled_sources)

  if not rows:
    # empty state: centred three-line notice
    font = _get_semi_bold()
    font_size = 30
    line_gap = 6.0
    lines = ("NO", "SOURCES", "AVAILABLE")
    line_sizes = [measure_text_cached(font, line, font_size) for line in lines]
    total_h = sum(sz.y for sz in line_sizes) + line_gap * (len(lines) - 1)
    curr_y = round(panel_rect.y + (panel_rect.height - total_h) / 2)
    for line, sz in zip(lines, line_sizes, strict=True):
      pos_x = round(panel_rect.x + (panel_rect.width - sz.x) / 2)
      rl.draw_text_ex(font, line, rl.Vector2(pos_x, curr_y), font_size, 0, _WHITE)
      curr_y += round(sz.y + line_gap)
    return

  row_h = (panel_rect.height - 2 * _SOURCE_PANEL_PAD_Y) / len(rows)
  content_left = panel_rect.x + _SOURCE_PANEL_PAD_X
  content_right = panel_rect.x + panel_rect.width - _SOURCE_PANEL_PAD_X
  for index, (panel_label, value, is_active) in enumerate(rows):
    font = font_bold if is_active else font_semi
    row_y = panel_rect.y + _SOURCE_PANEL_PAD_Y + index * row_h
    if panel_label == "Next" and index:
      rl.draw_line_ex(
        rl.Vector2(content_left, row_y),
        rl.Vector2(content_right, row_y),
        1,
        _SOURCE_DIVIDER,
      )

    value_text = source_value_text(value)
    text_color = _WHITE if is_active else _SOURCE_LABEL_MUTED

    full_label = panel_label
    value_size = measure_text_cached(font, value_text, _SOURCE_VALUE_SIZE)
    max_label_width = max(
      0.0,
      content_right - content_left - _SOURCE_MIN_LABEL_VALUE_GAP - value_size.x,
    )
    label_text = fit_source_label(
      full_label,
      full_label,
      max_label_width,
      lambda text, font=font: measure_text_cached(font, text, _SOURCE_LABEL_SIZE).x,
    )
    label_size = measure_text_cached(font, label_text, _SOURCE_LABEL_SIZE)
    label_pos = rl.Vector2(content_left, round(row_y + (row_h - label_size.y) / 2))
    value_pos = rl.Vector2(round(content_right - value_size.x), round(row_y + (row_h - value_size.y) / 2))
    rl.draw_text_ex(font, label_text, label_pos, _SOURCE_LABEL_SIZE, 0, text_color)
    rl.draw_text_ex(font, value_text, value_pos, _SOURCE_VALUE_SIZE, 0, text_color)


def _outline(rect: rl.Rectangle, drawer_top: float, extension: float) -> list[tuple[float, float]]:
  left, top = rect.x, rect.y
  card_right, bottom = left + rect.width, top + rect.height
  right = card_right + extension
  radius = min(rect.width, rect.height) * _CONTROL_ROUNDNESS / 2
  points = []

  def corner(cx, cy, r, quadrant):
    for x, y in _QUARTER:
      dx, dy = ((-x, -y), (y, -x), (x, y), (-y, x))[quadrant]
      point = (cx + dx * r, cy + dy * r)
      if not points or math.hypot(point[0] - points[-1][0], point[1] - points[-1][1]) > 1e-5:
        points.append(point)

  corner(left + radius, top + radius, radius, 0)
  if drawer_top <= top:
    corner(right - radius, top + radius, radius, 1)
  else:
    corner(card_right - radius, top + radius, radius, 1)
    points.append((card_right, drawer_top))
    tip_radius = min(radius, extension)
    corner(right - tip_radius, drawer_top + tip_radius, tip_radius, 1)
  corner(right - radius, bottom - radius, radius, 2)
  corner(left + radius, bottom - radius, radius, 3)
  return points


class SpeedSourceDrawer:
  """The source drawer's reveal, shared frame, and clipped contents."""

  def __init__(self):
    self._mesh_key = None
    self._fill = None
    self._strokes = {}
    self._points: list[tuple[float, float]] = []
    self._miters: list[tuple[float, float]] = []
    self.reset()

  def reset(self) -> None:
    self.progress = 0.0
    self._open = False
    self._start_progress = 0.0
    self._start_time = 0.0

  @property
  def width(self) -> float:
    return SOURCE_DRAWER_WIDTH * self.progress

  def update(self, opened: bool, now: float) -> None:
    # Sample the old transition first so a second tap reverses without jumping.
    target = float(self._open)
    if self.progress != target:
      duration = OPEN_SECONDS if self._open else CLOSE_SECONDS
      phase = min(1.0, max(0.0, (now - self._start_time) / duration))
      self.progress = target + (self._start_progress - target) * (1 - phase) ** 4
    if opened != self._open:
      self._open = opened
      self._start_progress = self.progress
      self._start_time = now

  def bounds(self, rect: rl.Rectangle, drawer_top: float) -> rl.Rectangle:
    return rl.Rectangle(rect.x + rect.width, drawer_top, self.width, rect.y + rect.height - drawer_top)

  def _prepare_mesh(self, rect: rl.Rectangle, drawer_top: float) -> None:
    key = (rect.x, rect.y, rect.width, rect.height, drawer_top, self.width)
    if key == self._mesh_key:
      return
    points = _outline(rect, drawer_top, self.width)
    # The lower-left interior sees the entire L-shaped outline without overlap.
    center = (rect.x + rect.width / 2, (drawer_top + rect.y + rect.height) / 2)
    self._fill = rl.ffi.new('Vector2[]', [center, *reversed(points), points[-1]])
    self._points = points
    self._miters = []
    for i, (x, y) in enumerate(points):
      px, py = points[i - 1]
      nx, ny = points[(i + 1) % len(points)]
      before, after = math.hypot(x - px, y - py), math.hypot(nx - x, ny - y)
      ax, ay = (y - py) / before, -(x - px) / before
      bx, by = (ny - y) / after, -(nx - x) / after
      denominator = 1 + ax * bx + ay * by
      self._miters.append(((ax + bx) / denominator, (ay + by) / denominator))
    self._strokes.clear()
    self._mesh_key = key

  def draw_border(self, rect: rl.Rectangle, drawer_top: float, width: float, color: rl.Color) -> None:
    self._prepare_mesh(rect, drawer_top)
    if width not in self._strokes:
      vertices = []
      for (x, y), (mx, my) in zip(self._points + [self._points[0]], self._miters + [self._miters[0]], strict=True):
        vertices.extend(((x + mx * width, y + my * width), (x, y)))
      self._strokes[width] = rl.ffi.new('Vector2[]', vertices)
    vertices = self._strokes[width]
    rl.draw_triangle_strip(rl.ffi.cast('Vector2 *', vertices), len(vertices), color)

  def draw_frame(self, rect: rl.Rectangle, drawer_top: float, fill: rl.Color, border: rl.Color) -> None:
    self._prepare_mesh(rect, drawer_top)
    rl.draw_triangle_fan(rl.ffi.cast('Vector2 *', self._fill), len(self._fill), fill)
    self.draw_border(rect, drawer_top, 7, rl.Color(border.r, border.g, border.b, 55))
    self.draw_border(rect, drawer_top, 2, border)

  def draw_contents(self, state: dict, rect: rl.Rectangle, drawer_top: float) -> None:
    bounds = self.bounds(rect, drawer_top)
    panel = rl.Rectangle(bounds.x + bounds.width - SOURCE_DRAWER_WIDTH, bounds.y, SOURCE_DRAWER_WIDTH, bounds.height)
    # Scissor is not stacked in Raylib. This is a top-level HUD widget.
    rl.rl_draw_render_batch_active()
    rl.begin_scissor_mode(math.ceil(bounds.x), math.ceil(bounds.y), math.ceil(bounds.width), math.ceil(bounds.height))
    try:
      _draw_source_contents(state, panel)
      radius = min(rect.width, rect.height) * _CONTROL_ROUNDNESS / 2
      top, bottom = drawer_top + radius, rect.y + rect.height - radius
      cap, width = 16, min(12, bounds.width)
      shade, clear = rl.Color(0, 0, 0, 108), rl.BLANK
      rl.draw_rectangle_gradient_ex(rl.Rectangle(bounds.x, top, width, cap), clear, shade, clear, clear)
      rl.draw_rectangle_gradient_h(math.ceil(bounds.x), math.ceil(top + cap), math.ceil(width), int(bottom - top - 2 * cap), shade, clear)
      rl.draw_rectangle_gradient_ex(rl.Rectangle(bounds.x, bottom - cap, width, cap), shade, clear, clear, clear)
    finally:
      rl.rl_draw_render_batch_active()
      rl.end_scissor_mode()
    rim = rl.Color(230, 218, 246, round(46 * self.progress))
    rl.draw_line_ex(rl.Vector2(bounds.x - 0.5, drawer_top + 16),
                    rl.Vector2(bounds.x - 0.5, rect.y + rect.height - 16), 1, rim)


class SpeedSourceDrawerRenderer(Widget):
  """Param-gated mount that mirrors the speed-limit sign's rect and opens the drawer."""

  def __init__(self):
    super().__init__()
    self._drawer = SpeedSourceDrawer()
    self._enabled = False
    self._last_param_refresh = float("-inf")
    # memory params hold the vision pipeline's transient limit value (same store the resolver reads)
    self._vision_params = Params("/dev/shm/params")
    # SLC priority settings, cached at the same slow cadence as the gate.
    self._primary_priority = "Map Data"
    self._secondary_priority = "None"
    self._vision_enabled = False
    # cached per-frame source state
    self._state: dict | None = None
    self._drawer_hit_rect: rl.Rectangle | None = None
    self.set_visible(lambda: self._enabled)

  def _update_state(self):
    # runs before the visibility gate in Widget.render, so the throttled param
    # read can flip the widget on/off between frames
    self._refresh_params()

  def _refresh_params(self):
    now = rl.get_time()
    if now - self._last_param_refresh < PARAM_REFRESH_INTERVAL:
      return
    self._last_param_refresh = now
    params = ui_state.params
    self._enabled = safe_get_bool(params, "ShowSpeedLimitSources", False)
    self._vision_enabled = safe_get_bool(params, "VisionSpeedLimitEnabled", False)
    self._primary_priority = safe_get_str(params, "SLCPriority1", "Map Data") or "Map Data"
    self._secondary_priority = safe_get_str(params, "SLCPriority2", "None") or "None"

  def _build_state(self) -> dict | None:
    sm = ui_state.sm
    if not sm.valid.get("longitudinalPlanSP", False):
      return None
    if sm.recv_frame["longitudinalPlanSP"] < ui_state.started_frame:
      return None

    speed_conversion = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    resolver = sm["longitudinalPlanSP"].speedLimit.resolver

    dashboard_sl = 0.0
    if sm.valid.get("carStateSP", False):
      dashboard_sl = sm["carStateSP"].speedLimit
    map_sl, map_sl_valid = 0.0, False
    next_sl, next_sl_valid = 0.0, False
    if sm.valid.get("liveMapDataSP", False):
      lmd = sm["liveMapDataSP"]
      map_sl_valid = bool(lmd.speedLimitValid)
      map_sl = lmd.speedLimit if map_sl_valid else 0.0
      next_sl_valid = bool(lmd.speedLimitAheadValid)
      next_sl = lmd.speedLimitAhead if next_sl_valid else 0.0
    vision_sl = 0.0
    if self._vision_enabled:
      # registered memory param written by the vision speed-limit pipeline
      vision_sl = safe_get_float(self._vision_params, "VisionSpeedLimit", 0.0)

    resolver_source = str(resolver.source)
    active_title = RESOLVER_SOURCE_TO_TITLE.get(resolver_source, "")

    # Dashboard availability: the resolver treats a positive carStateSP limit
    # as a usable dashboard reading (same gate speed_limit_resolver uses).
    dashboard_available = dashboard_sl > 0.0

    state = {
      'speed_limit_source': active_title,
      'slc_enabled_sources': enabled_source_titles(
        self._primary_priority,
        self._secondary_priority,
        vision_enabled=self._vision_enabled,
        dashboard_available=dashboard_available,
      ),
      'dashboard_sl': max(0.0, dashboard_sl * speed_conversion),
      'map_sl': max(0.0, map_sl * speed_conversion),
      'vision_sl': max(0.0, vision_sl * speed_conversion),
      'next_sl': max(0.0, next_sl * speed_conversion) if next_sl_valid else 0.0,
    }
    return state

  def _speed_limit_sign_rect(self, rect: rl.Rectangle) -> rl.Rectangle:
    """Same layout rules SpeedLimitRenderer._render uses (CarrotPanelSide aware)."""
    width = UI_CONFIG.set_speed_width_metric if ui_state.is_metric else UI_CONFIG.set_speed_width_imperial
    try:
      panel_side = max(0, min(1, int(ui_state.params.get("CarrotPanelSide", 1))))
    except Exception:
      panel_side = 1

    if panel_side == 0:
      x = rect.x + 60
      y = rect.y + 45 + UI_CONFIG.set_speed_height + 24
    else:
      x = rect.x + 60 + width + 30 - 6
      y = rect.y + 45 - 6

    return rl.Rectangle(x, y, width, UI_CONFIG.set_speed_height + 6 * 2)

  def _render(self, rect: rl.Rectangle):
    self._refresh_params()
    if not self._enabled:
      self._drawer.reset()
      return

    self._state = self._build_state()
    sign_rect = self._speed_limit_sign_rect(rect)
    self._drawer_hit_rect = self._drawer.bounds(sign_rect, sign_rect.y) if self._drawer.width > 0 else None

    opened = self._state is not None
    self._drawer.update(opened, rl.get_time())
    if self._drawer.width <= 0:
      return

    self._drawer.draw_frame(sign_rect, sign_rect.y, rl.Color(0, 0, 0, 166), _ACCENT)
    if self._state is not None:
      self._drawer.draw_contents(self._state, sign_rect, sign_rect.y)

  def is_pressed_in(self, mouse_pos) -> bool:
    """Whether a press landed on the open drawer (keeps taps off the sidebar)."""
    return self._drawer_hit_rect is not None and rl.check_collision_point_rec(mouse_pos, self._drawer_hit_rect)
