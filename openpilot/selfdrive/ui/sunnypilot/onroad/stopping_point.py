"""
StarPilot stopping-point marker, ported to sunnypilot.

Original: StarPilot ``selfdrive/ui/onroad/starpilot/stopping_point.py``
(shows a red octagon "STOP" sign anchored to the projected model path when the
planner reports a red light ahead).

sunnypilot has no ``starpilotPlan`` message, so the data sources were adapted:

- Red-light gate: ``longitudinalPlanSP.signalAssistAction == 1`` (the field is
  documented in cereal/custom.capnp as "current observed light evidence for the
  onroad HUD (0 unknown, 1 red, 2 green, 3 mixed)").
- Stopping distance: sunnypilot publishes no planner stop length, so the
  distance is approximated from physics - ``vEgo^2 / (2 * |aEgo|)`` while the
  car is braking, clamped to a comfortable minimum deceleration, and forced to
  0 at standstill (same behaviour as the original's standstill branch).
- Path anchor: the original reads ``renderer._path.projected_points``, which
  lives on the ModelRenderer inside AugmentedRoadView - out of reach for a HUD
  member (the two renderers are siblings with no shared reference, and both
  files are outside this fork's file domain). Instead the marker is drawn on a
  virtual centre-lane line at the bottom of the road view, with the height
  above the bottom edge mapped from the stopping distance, which preserves the
  visual intent (sign sits on the road ahead, further up the closer the stop).

Gating params (unregistered, code defaults, both default OFF):
- ``ShowStoppingPoint``: master switch.
- ``ShowStoppingPointMetrics``: additionally show the approximated stopping
  distance above the sign, honouring the IsMetric unit setting.
"""
import math

import pyray as rl

from openpilot.selfdrive.ui.sunnypilot.onroad.param_guards import safe_get_bool
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

# Red-light evidence value of longitudinalPlanSP.signalAssistAction.
SIGNAL_ASSIST_RED = 1

PARAM_REFRESH_INTERVAL = 0.25  # seconds; params are not per-frame data

STOP_SIGN_RADIUS = 35.0
STOP_SIGN_SIDES = 8
STOP_SIGN_FONT_SIZE = 18
STOP_DISTANCE_FONT_SIZE = 24

# How far up the road view the marker travels with the approximated stopping
# distance: 0 m sits near the bottom edge, STOP_DISTANCE_MAX_M reaches
# STOP_MARKER_MAX_FRACTION of the view height (roughly where the projected
# path's midpoint lands on the original).
STOP_DISTANCE_MAX_M = 120.0
STOP_MARKER_MAX_FRACTION = 0.55
STOP_MARKER_MIN_FRACTION = 0.08

STOP_SIGN_COLOR = rl.Color(196, 30, 58, 255)
STOP_SIGN_OUTLINE = rl.Color(255, 255, 255, 200)


def _draw_poly_outline(cx: float, cy: float, sides: int, radius: float, rotation: float, thickness: float, color: rl.Color):
  """Draw a clean polygon outline as connected line segments."""
  for i in range(sides):
    a1 = math.radians(rotation + i * 360.0 / sides)
    a2 = math.radians(rotation + ((i + 1) % sides) * 360.0 / sides)
    p1 = rl.Vector2(int(cx + radius * math.cos(a1)), int(cy + radius * math.sin(a1)))
    p2 = rl.Vector2(int(cx + radius * math.cos(a2)), int(cy + radius * math.sin(a2)))
    rl.draw_line_ex(p1, p2, thickness, color)


class StoppingPointRenderer(Widget):
  """Red-light stop marker drawn over the road view."""

  def __init__(self):
    super().__init__()
    self._font = gui_app.font(FontWeight.SEMI_BOLD)
    self._enabled = False
    self._show_metrics = False
    self._last_param_refresh = float("-inf")
    self.set_visible(lambda: self._enabled)

  def _refresh_params(self):
    now = rl.get_time()
    if now - self._last_param_refresh < PARAM_REFRESH_INTERVAL:
      return
    self._last_param_refresh = now
    self._enabled = safe_get_bool(ui_state.params, "ShowStoppingPoint", False)
    self._show_metrics = safe_get_bool(ui_state.params, "ShowStoppingPointMetrics", False)

  def _update_state(self):
    self._refresh_params()

  def _red_light_detected(self) -> bool:
    sm = ui_state.sm
    if not sm.valid.get("longitudinalPlanSP", False):
      return False
    if sm.recv_frame["longitudinalPlanSP"] < ui_state.started_frame:
      return False
    plan_sp = sm["longitudinalPlanSP"]
    return int(getattr(plan_sp, "signalAssistAction", 0)) == SIGNAL_ASSIST_RED

  @staticmethod
  def _approx_stopping_distance_m() -> float:
    """Approximate the remaining stop distance from current speed and decel.

    sunnypilot's planner does not publish a stop length, so this mirrors the
    original's "distance to the stop line" with a constant-deceleration
    estimate. Braking comfortably starts around 0.6 m/s^2; standstill shows 0.
    """
    sm = ui_state.sm
    if not sm.valid.get("carState", False) or sm.recv_frame["carState"] < ui_state.started_frame:
      return 0.0
    car_state = sm["carState"]
    if car_state.standstill:
      return 0.0
    v_ego = max(0.0, car_state.vEgo)
    decel = -car_state.aEgo
    if decel <= 0.1:
      # not braking yet: use the distance covered by a comfortable stop
      decel = 0.6
    return v_ego * v_ego / (2.0 * max(decel, 0.6))

  def _render(self, rect: rl.Rectangle):
    if not self._red_light_detected():
      return

    stopping_distance = self._approx_stopping_distance_m()

    # Virtual centre-lane anchor: horizontally centred, height above the bottom
    # edge grows with the stopping distance (see module docstring).
    fraction = STOP_MARKER_MIN_FRACTION + (STOP_MARKER_MAX_FRACTION - STOP_MARKER_MIN_FRACTION) * \
      min(1.0, stopping_distance / STOP_DISTANCE_MAX_M)
    cx = rect.x + rect.width / 2.0
    cy = rect.y + rect.height - fraction * rect.height

    self._draw_stop_sign(cx, cy)
    if self._show_metrics:
      self._draw_distance(cx, cy, stopping_distance)

  def _draw_stop_sign(self, cx: float, cy: float):
    radius = STOP_SIGN_RADIUS
    # Draw red octagon body
    rl.draw_poly(rl.Vector2(int(cx), int(cy - radius)), STOP_SIGN_SIDES, radius, 22.5, STOP_SIGN_COLOR)
    # Draw clean thin white outline
    _draw_poly_outline(cx, cy - radius, STOP_SIGN_SIDES, radius, 22.5, 1.5, STOP_SIGN_OUTLINE)

    font_size = STOP_SIGN_FONT_SIZE
    lbl_sz = measure_text_cached(self._font, "STOP", font_size)
    rl.draw_text_ex(
      self._font, "STOP",
      rl.Vector2(int(cx - lbl_sz.x / 2), int(cy - radius - lbl_sz.y / 2)),
      font_size, 0, rl.WHITE
    )

  def _draw_distance(self, cx: float, cy: float, stopping_distance: float):
    if ui_state.is_metric:
      dist_text = f"{int(round(stopping_distance))} m"
    else:
      dist_text = f"{int(round(stopping_distance * 3.28084))} ft"

    font = self._font
    font_size = STOP_DISTANCE_FONT_SIZE
    text_sz = measure_text_cached(font, dist_text, font_size)
    tx = cx - text_sz.x / 2
    ty = cy - STOP_SIGN_RADIUS * 2 - text_sz.y - 5

    # Draw black outline/shadow text
    rl.draw_text_ex(font, dist_text, rl.Vector2(int(tx - 1), int(ty - 1)), font_size, 0, rl.BLACK)
    rl.draw_text_ex(font, dist_text, rl.Vector2(int(tx + 1), int(ty - 1)), font_size, 0, rl.BLACK)
    rl.draw_text_ex(font, dist_text, rl.Vector2(int(tx - 1), int(ty + 1)), font_size, 0, rl.BLACK)
    rl.draw_text_ex(font, dist_text, rl.Vector2(int(tx + 1), int(ty + 1)), font_size, 0, rl.BLACK)
    # Draw white text
    rl.draw_text_ex(font, dist_text, rl.Vector2(int(tx), int(ty)), font_size, 0, rl.WHITE)
