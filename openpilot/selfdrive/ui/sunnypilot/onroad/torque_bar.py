"""
StarPilot torque bar, ported to sunnypilot.

Original: StarPilot ``selfdrive/ui/onroad/starpilot/torque_bar.py`` - a curved
white arc at the bottom-centre of the road view whose lit span (and fade to
orange) tracks steering torque utilisation.

Adaptations for sunnypilot:
- ``rivian_lateral_mode`` does not exist here, so the angle-mode fallback uses
  the same lateral-acceleration estimate the mici TorqueBar uses
  (``lateralControlState`` angle/curvature + road roll), keyed off the live
  control state only.
- ``blend_colors`` comes from the mici onroad helpers (same implementation
  contract as StarPilot's ``starpilot_visuals.blend_colors``).
- Gated by the unregistered param ``ShowTorqueBar`` (code default OFF).
  This is independent of the pre-existing mici ``TorqueBar`` behind the
  registered ``TorqueBar`` param.
"""
from functools import wraps
import math
from collections import OrderedDict

import numpy as np
import pyray as rl
from opendbc.car import ACCELERATION_DUE_TO_GRAVITY
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.ui.mici.onroad import blend_colors
from openpilot.selfdrive.ui.sunnypilot.onroad.param_guards import safe_get_bool
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.shader_polygon import draw_polygon, Gradient
from openpilot.system.ui.widgets import Widget

# TODO: arc_bar_pts doesn't consider rounded end caps part of the angle span
TORQUE_ANGLE_SPAN = 12.7

PARAM_REFRESH_INTERVAL = 0.25  # seconds; params are not per-frame data

DEFAULT_MAX_LAT_ACCEL = 3.0  # m/s^2


def quantized_lru_cache(maxsize=128):
  def decorator(func):
    cache = OrderedDict()

    @wraps(func)
    def wrapper(r_mid, thickness, a0_deg, a1_deg, **kwargs):
      # Quantize inputs: balanced for smoothness vs cache effectiveness
      key = (round(r_mid),
             round(thickness),           # 1px precision for smoother height transitions
             round(a0_deg * 10) / 10,    # 0.1° precision for smoother angle transitions
             round(a1_deg * 10) / 10,
             tuple(sorted(kwargs.items())))

      if key in cache:
        cache.move_to_end(key)
      else:
        if len(cache) >= maxsize:
          cache.popitem(last=False)

        result = func(r_mid, thickness, a0_deg, a1_deg, **kwargs)
        cache[key] = result
      return cache[key]
    return wrapper
  return decorator


@quantized_lru_cache(maxsize=256)
def arc_bar_pts(r_mid: float, thickness: float,
                a0_deg: float, a1_deg: float,
                *, max_points: int = 100, cap_segs: int = 10,
                cap_radius: float = 7, px_per_seg: float = 2.0) -> np.ndarray:
  """Return Nx2 np.float32 points for a single closed polygon (rounded thick arc), centered at origin."""

  def get_cap(left: bool, a_deg: float):
    # end cap at a1: center (a1), sweep a1→a1+180 (skip endpoints to avoid dupes)
    # quarter arc (outer corner) at a1 with fixed pixel radius cap_radius

    nx, ny = math.cos(math.radians(a_deg)), math.sin(math.radians(a_deg))  # outward normal
    tx, ty = -ny, nx  # tangent (CCW)

    mx, my = nx * r_mid, ny * r_mid  # mid-point at a1

    ex = mx + nx * (half - cap_radius)
    ey = my + ny * (half - cap_radius)

    # sweep 90° in the local (t,n) frame: from outer edge toward inside
    if not left:
      alpha = np.deg2rad(np.linspace(90, 0, cap_segs + 2))[1:-1]
    else:
      alpha = np.deg2rad(np.linspace(180, 90, cap_segs + 2))[1:-1]
    cap_end = np.c_[ex + np.cos(alpha) * cap_radius * tx + np.sin(alpha) * cap_radius * nx,
                    ey + np.cos(alpha) * cap_radius * ty + np.sin(alpha) * cap_radius * ny]

    # bottom quarter (inner corner) at a1
    ex2 = mx + nx * (-half + cap_radius)
    ey2 = my + ny * (-half + cap_radius)

    if not left:
      alpha2 = np.deg2rad(np.linspace(0, -90, cap_segs + 1))[:-1]  # include 0 once, exclude -90
    else:
      alpha2 = np.deg2rad(np.linspace(90 - 90 - 90, 0 - 90 - 90, cap_segs + 1))[:-1]
    cap_end_bot = np.c_[ex2 + np.cos(alpha2) * cap_radius * tx + np.sin(alpha2) * cap_radius * nx,
                        ey2 + np.cos(alpha2) * cap_radius * ty + np.sin(alpha2) * cap_radius * ny]

    # append to the top quarter
    if not left:
      cap_end = np.vstack((cap_end, cap_end_bot))
    else:
      cap_end = np.vstack((cap_end_bot, cap_end))

    return cap_end

  if a1_deg < a0_deg:
    a0_deg, a1_deg = a1_deg, a0_deg
  half = thickness * 0.5

  cap_radius = min(cap_radius, half)

  span = max(1e-3, a1_deg - a0_deg)

  # pick arc segment count from arc length, clamp to shader points[] budget
  arc_len = r_mid * math.radians(span)
  arc_segs = max(6, int(arc_len / px_per_seg))
  max_arc = (max_points - (4 * cap_segs + 3)) // 2
  arc_segs = max(6, min(arc_segs, max_arc))

  # outer arc a0→a1
  ang_o = np.deg2rad(np.linspace(a0_deg, a1_deg, arc_segs + 1))
  outer = np.c_[np.cos(ang_o) * (r_mid + half),
                np.sin(ang_o) * (r_mid + half)]

  # end cap at a1
  cap_end = get_cap(False, a1_deg)

  # inner arc a1→a0
  ang_i = np.deg2rad(np.linspace(a1_deg, a0_deg, arc_segs + 1))
  inner = np.c_[np.cos(ang_i) * (r_mid - half),
                np.sin(ang_i) * (r_mid - half)]

  # start cap at a0
  cap_start = get_cap(True, a0_deg)

  pts = np.vstack((outer, cap_end, inner, cap_start, outer[:1])).astype(np.float32)

  # Rotate to start from middle of cap for proper triangulation
  pts = np.roll(pts, cap_segs, axis=0)

  return pts


class StarPilotTorqueBar(Widget):
  """The StarPilot bottom-centre torque arc, param-gated to OFF by default."""

  def __init__(self):
    super().__init__()
    self._enabled = False
    self._last_param_refresh = float("-inf")
    self._torque_filter = FirstOrderFilter(0, 0.1, 1 / gui_app.target_fps)
    self._torque_line_alpha_filter = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)
    self.set_visible(lambda: self._enabled)

  def _refresh_params(self):
    now = rl.get_time()
    if now - self._last_param_refresh < PARAM_REFRESH_INTERVAL:
      return
    self._last_param_refresh = now
    self._enabled = safe_get_bool(ui_state.params, "ShowTorqueBar", False)

  def _update_state(self):
    self._refresh_params()
    if not self._enabled:
      return

    # Angle/curvature-controlled cars use a lateral-acceleration estimate for
    # the bar; torque-controlled cars read the actual applied torque.
    # (StarPilot also consults its Rivian angle-mode detector here; sunnypilot
    # has no such module, so the live control state alone decides.)
    if ui_state.sm['controlsState'].lateralControlState.which() in ('angleState', 'curvatureState'):
      controls_state = ui_state.sm['controlsState']
      car_state = ui_state.sm['carState']
      # vehicleParameters (not liveParameters) is what the UI SubMaster carries;
      # same roll source the mici torque bar uses
      vehicle_parameters = ui_state.sm['vehicleParameters']
      car_control = ui_state.sm['carControl']

      # Include lateral accel error in estimated torque utilization
      actual_lateral_accel = controls_state.curvature * car_state.vEgo ** 2
      desired_lateral_accel = controls_state.desiredCurvature * car_state.vEgo ** 2
      accel_diff = (desired_lateral_accel - actual_lateral_accel)

      # Include road roll in estimated torque utilization
      # Roll is less accurate near standstill, so reduce its effect at low speed
      roll_compensation = vehicle_parameters.roll * ACCELERATION_DUE_TO_GRAVITY * \
        np.interp(car_state.vEgo, [5, 15], [0.0, 1.0])
      lateral_acceleration = actual_lateral_accel - roll_compensation
      max_lateral_acceleration = ui_state.CP.maxLateralAccel if ui_state.CP else DEFAULT_MAX_LAT_ACCEL

      if not car_control.latActive:
        self._torque_filter.update(0.0)
      else:
        self._torque_filter.update(np.clip((lateral_acceleration + accel_diff) / max_lateral_acceleration, -1, 1))
    else:
      self._torque_filter.update(-ui_state.sm['carOutput'].actuatorsOutput.torque)

  def _render(self, rect: rl.Rectangle) -> None:
    SCALE = rect.height / 240.0 * (rect.width / gui_app.width)
    # adjust y pos with torque
    torque_line_offset = np.interp(abs(self._torque_filter.x), [0.5, 1], [22 * SCALE, 26 * SCALE])
    torque_line_height = np.interp(abs(self._torque_filter.x), [0.5, 1], [14 * SCALE, 56 * SCALE])
    lateral_ui_active = ui_state.status == UIStatus.ENGAGED or \
      bool(getattr(ui_state, 'always_on_lateral_active', False))

    # animate alpha and angle span
    self._torque_line_alpha_filter.update(lateral_ui_active or ui_state.status == UIStatus.OVERRIDE)

    torque_line_bg_alpha = np.interp(abs(self._torque_filter.x), [0.5, 1.0], [0.25, 0.5])
    torque_line_bg_color = rl.Color(255, 255, 255, int(255 * torque_line_bg_alpha * self._torque_line_alpha_filter.x))
    if not lateral_ui_active and ui_state.status != UIStatus.OVERRIDE:
      torque_line_bg_color = rl.Color(255, 255, 255, int(255 * 0.15 * self._torque_line_alpha_filter.x))

    # draw curved line polygon torque bar
    torque_line_radius = 1200 * SCALE
    top_angle = -90
    torque_bg_angle_span = self._torque_line_alpha_filter.x * TORQUE_ANGLE_SPAN
    torque_start_angle = top_angle - torque_bg_angle_span / 2
    torque_end_angle = top_angle + torque_bg_angle_span / 2
    # centerline radius & center
    mid_r = torque_line_radius + torque_line_height / 2

    cx = rect.x + rect.width / 2 + 8  # offset 8px to right of camera feed
    cy = rect.y + rect.height + torque_line_radius - torque_line_offset
    offset = np.array([cx, cy], dtype=np.float32)

    # draw bg torque indicator line
    bg_pts = arc_bar_pts(mid_r, torque_line_height, torque_start_angle, torque_end_angle) + offset
    draw_polygon(rect, bg_pts, color=torque_line_bg_color)

    # draw torque indicator line
    a0s = top_angle
    a1s = a0s + torque_bg_angle_span / 2 * self._torque_filter.x
    sl_pts = arc_bar_pts(mid_r, torque_line_height, a0s, a1s) + offset

    # draw gradient from center to 65% of the bg torque bar width
    start_grad_pt = cx / rect.width
    if self._torque_filter.x < 0:
      end_grad_pt = (cx * (1 - 0.65) + (min(bg_pts[:, 0]) * 0.65)) / rect.width
    else:
      end_grad_pt = (cx * (1 - 0.65) + (max(bg_pts[:, 0]) * 0.65)) / rect.width

    # fade to orange as we approach max torque
    start_color = blend_colors(
      rl.Color(255, 255, 255, int(255 * 0.9 * self._torque_line_alpha_filter.x)),
      rl.Color(255, 200, 0, int(255 * self._torque_line_alpha_filter.x)),  # yellow
      max(0, abs(self._torque_filter.x) - 0.75) * 4,
    )
    end_color = blend_colors(
      rl.Color(255, 255, 255, int(255 * 0.9 * self._torque_line_alpha_filter.x)),
      rl.Color(255, 115, 0, int(255 * self._torque_line_alpha_filter.x)),  # orange
      max(0, abs(self._torque_filter.x) - 0.75) * 4,
    )

    if not lateral_ui_active and ui_state.status != UIStatus.OVERRIDE:
      start_color = end_color = rl.Color(255, 255, 255, int(255 * 0.35 * self._torque_line_alpha_filter.x))

    gradient = Gradient(
      start=(start_grad_pt, 0),
      end=(end_grad_pt, 0),
      colors=[
        start_color,
        end_color,
      ],
      stops=[0.0, 1.0],
    )

    draw_polygon(rect, sl_pts, gradient=gradient)

    # draw center torque bar dot
    if abs(self._torque_filter.x) < 0.5:
      dot_y = self._rect.y + self._rect.height - torque_line_offset - torque_line_height / 2
      rl.draw_circle(int(cx), int(dot_y), (10 * SCALE) / 2,
                     rl.Color(182, 182, 182, int(255 * 0.9 * self._torque_line_alpha_filter.x)))
