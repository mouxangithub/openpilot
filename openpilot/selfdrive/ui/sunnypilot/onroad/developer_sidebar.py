"""
StarPilot developer sidebar, ported to sunnypilot.

Original: StarPilot ``selfdrive/ui/onroad/starpilot/developer_sidebar.py`` - up
to seven user-configured diagnostic metric cards stacked along the right edge
of the road view.

Adaptations for sunnypilot:
- StarPilot's remote toggle bridge (``ui_state.starpilot_toggles``) does not
  exist here; all gating comes from params only, read through a 1 s cache.
- Torque estimation lives in ``lateralTorqueParameters`` (sunnypilot's service
  name) instead of ``liveTorqueParameters``.
- Metrics backed by StarPilot-only plan fields (ACCEL JERK / DANGER JERK /
  SPEED JERK / DANGER %) read the equivalent LongitudinalPlanSP fields when
  present and otherwise report "N/A" instead of crashing.
- Metric 17 (model name) uses UIStateZP's ``home_model_name`` when available.
- Gating params (unregistered, code defaults, all OFF):
  ``DeveloperSidebar`` master switch and ``DeveloperSidebarMetric1..7``
  (0 = slot off, 1..17 = metric id).
"""
import re
import time

import pyray as rl

from openpilot.selfdrive.ui.sunnypilot.onroad.param_guards import safe_get_bool, safe_get_float, safe_get_int
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

SIDEBAR_WIDTH = 300
METRIC_HEIGHT = 126
METRIC_WIDTH = 275
METRIC_MARGIN = 12
FONT_SIZE = 35
METER_TO_FOOT = 3.28084
_WHITE_DIM = rl.Color(255, 255, 255, 85)
_LOCKED_VALUE_COLOR = rl.Color(34, 197, 94, 255)
_AUTO_TUNE_COLOR = rl.Color(59, 130, 246, 255)
_FLM_OVERRIDE_COLOR = rl.Color(239, 68, 68, 255)

METRIC_CACHE_INTERVAL = 1.0  # seconds; mirror StarPilot's slow toggle cache


def resolve_effective_torque_value(custom_enabled: bool, custom_value: float,
                                   live_enabled: bool, live_value: float,
                                   stock_value: float, configured_value: float) -> float:
  """Mirror controlsd torque-param precedence for the onroad diagnostics."""
  if custom_enabled:
    return custom_value
  if live_enabled:
    return live_value
  return stock_value if stock_value != 0.0 else configured_value


def _setting_changed(value: float, reference: float) -> bool:
  return round(value, 2) != round(reference, 2)


class DeveloperSidebar(Widget):
  """Configurable onroad diagnostics sidebar (right edge of the road view)."""

  def __init__(self):
    super().__init__()
    self._font_bold = gui_app.font(FontWeight.SEMI_BOLD)
    self._last_toggles_check = 0.0
    self._cached_metrics = [0] * 7
    self._cached_force_auto_tune_off = False
    self._cached_force_auto_tune = False
    self._cached_flm_trial_applied = False
    self._cached_use_auto_steer_delay = True
    self._cached_delay_stock = 0.0
    self._cached_delay = 0.0
    self._cached_friction_stock = 0.0
    self._cached_friction = 0.0
    self._cached_lat_stock = 0.0
    self._cached_lat = 0.0
    self._cached_ratio_stock = 0.0
    self._cached_ratio = 0.0
    self._flm_generic_param_keys: set[str] = set()

    self.lateral_engagement_time = 0
    self.longitudinal_engagement_time = 0
    self.total_engagement_time = 0
    self.max_acceleration = 0.0
    self.max_steer_angle = 0
    self.max_torque = 0
    self.torque_timer_start = 0.0

    self._visible = False
    self._metric_color = rl.WHITE
    self._active_ids: list[int] = []
    self._metric_colors: dict[int, rl.Color] = {}
    self._metrics: dict[int, tuple[str, str]] = {}

  @property
  def visible(self) -> bool:
    return self._visible

  def reset_variables(self):
    self.lateral_engagement_time = 0
    self.longitudinal_engagement_time = 0
    self.total_engagement_time = 0
    self.max_acceleration = 0.0
    self.max_steer_angle = 0
    self.max_torque = 0
    self.torque_timer_start = 0.0

  def _refresh_cache(self):
    now = time.monotonic()
    if now - self._last_toggles_check < METRIC_CACHE_INTERVAL:
      return
    self._last_toggles_check = now
    params = ui_state.params
    self._cached_metrics = [safe_get_int(params, f"DeveloperSidebarMetric{i}", 0) for i in range(1, 8)]
    self._visible = safe_get_bool(params, "DeveloperSidebar", False)
    self._cached_force_auto_tune_off = safe_get_bool(params, "ForceAutoTuneOff", False)
    self._cached_force_auto_tune = safe_get_bool(params, "ForceAutoTune", False)
    self._cached_flm_trial_applied = safe_get_bool(params, "FLMTrialApplied", False)
    self._cached_use_auto_steer_delay = safe_get_bool(params, "UseAutoSteerDelay", True)
    self._cached_delay_stock = safe_get_float(params, "SteerDelayStock", 0.0)
    self._cached_delay = safe_get_float(params, "SteerDelay", 0.0)
    self._cached_friction_stock = safe_get_float(params, "SteerFrictionStock", 0.0)
    self._cached_friction = safe_get_float(params, "SteerFriction", 0.0)
    self._cached_lat_stock = safe_get_float(params, "SteerLatAccelStock", 0.0)
    self._cached_lat = safe_get_float(params, "SteerLatAccel", 0.0)
    self._cached_ratio_stock = safe_get_float(params, "SteerRatioStock", 0.0)
    self._cached_ratio = safe_get_float(params, "SteerRatio", 0.0)
    self._flm_generic_param_keys = self._read_flm_generic_param_keys() if self._cached_flm_trial_applied else set()

  def _read_flm_generic_param_keys(self) -> set[str]:
    import json

    try:
      raw = ui_state.params.get("FLMTrialBaseline", encoding="utf-8") or "{}"
      snapshot = raw if isinstance(raw, dict) else json.loads(raw)
      applied = snapshot.get("appliedGenericParams", {}) if isinstance(snapshot, dict) else {}
      return set(applied.keys()) if isinstance(applied, dict) else set()
    except Exception:
      return set()

  def _flm_changed(self, *keys: str) -> bool:
    return self._cached_flm_trial_applied and any(key in self._flm_generic_param_keys for key in keys)

  def _tuning_color(self, *, auto: bool = False, flm: bool = False) -> rl.Color:
    if flm:
      return _FLM_OVERRIDE_COLOR
    return _AUTO_TUNE_COLOR if auto else _LOCKED_VALUE_COLOR

  def _draw_metric(self, sidebar_rect: rl.Rectangle, label_first: str, label_second: str, color: rl.Color, y: float):
    card_x = int(sidebar_rect.x + sidebar_rect.width) - METRIC_MARGIN - METRIC_WIDTH
    metric_rect = rl.Rectangle(card_x, y, METRIC_WIDTH, METRIC_HEIGHT)

    edge_rect = rl.Rectangle(metric_rect.x + METRIC_WIDTH - 4 - 100, metric_rect.y + 4, 100, 118)
    rl.draw_rectangle_rounded(edge_rect, 0.3, 10, color)
    accent_x = metric_rect.x + METRIC_WIDTH - 4 - 18
    rl.draw_rectangle_rec(
      rl.Rectangle(edge_rect.x, metric_rect.y, accent_x - edge_rect.x, metric_rect.height),
      rl.BLACK,
    )

    rl.draw_rectangle_rounded_lines_ex(metric_rect, 0.3, 10, 2, _WHITE_DIM)

    max_w = metric_rect.width - 22
    text_size = measure_text_cached(self._font_bold, label_first, FONT_SIZE)
    pos = rl.Vector2(metric_rect.x, metric_rect.y + (metric_rect.height - text_size.y) / 2)
    if label_second:
      second_size = measure_text_cached(self._font_bold, label_second, FONT_SIZE)
      pos = rl.Vector2(metric_rect.x, metric_rect.y + (metric_rect.height - text_size.y - second_size.y) / 3)
      rl.draw_text_ex(self._font_bold, label_first, pos, FONT_SIZE, 0, rl.WHITE)
      rl.draw_text_ex(
        self._font_bold, label_second,
        rl.Vector2(metric_rect.x, pos.y + text_size.y),
        FONT_SIZE, 0, rl.WHITE,
      )
      return
    # Single-line label, right-aligned within the card so long names stay visible.
    if text_size.x > max_w:
      pos.x = metric_rect.x + max_w - text_size.x
    rl.draw_text_ex(self._font_bold, label_first, pos, FONT_SIZE, 0, rl.WHITE)

  def update(self):
    self._refresh_cache()
    if not self._visible:
      return

    if ui_state.sm.frame < ui_state.started_frame + 2:
      self.reset_variables()

    self._active_ids = [val for val in self._cached_metrics if val > 0]
    if len(self._active_ids) == 0:
      return

    sm = ui_state.sm
    car_state = sm["carState"] if sm.valid.get("carState", False) else None
    car_control = sm["carControl"] if sm.valid.get("carControl", False) else None
    live_delay = sm["liveDelay"] if sm.valid.get("liveDelay", False) else None
    # liveParameters is not in the UI SubMaster's service list; fall back to the
    # subscribed carParams snapshot (same steerRatio / stiffnessFactor fields).
    live_parameters = None
    try:
      live_parameters = sm["liveParameters"] if sm.valid.get("liveParameters", False) else None
    except KeyError:
      live_parameters = None
    live_torque_parameters = sm["lateralTorqueParameters"] if sm.valid.get("lateralTorqueParameters", False) else None

    is_metric = ui_state.is_metric
    accel_unit = " m/s²" if is_metric else " ft/s²"
    accel_conv = 1.0 if is_metric else METER_TO_FOOT

    a_ego = car_state.aEgo if car_state else 0.0
    accel_val = a_ego * accel_conv
    gas_pressed = car_state.gasPressed if car_state else False
    if not gas_pressed:
      self.max_acceleration = max(self.max_acceleration, accel_val)

    lat_active = car_control.latActive if car_control else False
    long_active = car_control.longActive if car_control else False
    standstill = car_state.standstill if car_state else False
    # capnp enum readers compare cleanly against their name (see carrot's
    # "cs.gearShifter != 'drive'" pattern)
    reverse = car_state.gearShifter == 'reverse' if car_state else False

    self.lateral_engagement_time += 1 if (lat_active and not standstill and not reverse) else 0
    self.longitudinal_engagement_time += 1 if (long_active and not standstill and not reverse) else 0
    self.total_engagement_time += 1 if ((not standstill and not reverse) or self.total_engagement_time == 0) else 0

    curr_steer = int(abs(car_state.steeringAngleDeg)) if car_state else 0
    curr_torque = int(abs(car_control.actuators.torque * 100)) if (car_control and hasattr(car_control.actuators, 'torque')) else 0

    now = time.monotonic()
    if curr_torque >= 50:
      self.max_steer_angle = max(self.max_steer_angle, curr_steer)
      self.max_torque = max(self.max_torque, curr_torque)
      self.torque_timer_start = now
    elif self.torque_timer_start > 0.0 and (now - self.torque_timer_start >= 10.0):
      self.max_torque = 0
      self.max_steer_angle = 0
      self.torque_timer_start = 0.0

    steer_label = f"{curr_steer}°"
    torque_label = f"{curr_torque}%"
    if curr_torque >= 50 or self.torque_timer_start > 0.0:
      steer_label += f" - ({self.max_steer_angle}°)"
      torque_label += f" - ({self.max_torque}%)"

    force_auto_tune_off = self._cached_force_auto_tune_off
    force_auto_tune = self._cached_force_auto_tune
    use_params = live_torque_parameters.useParams if (live_torque_parameters and hasattr(live_torque_parameters, 'useParams')) else False
    using_live_torque = live_torque_parameters is not None and not force_auto_tune_off and (use_params or force_auto_tune)
    live_friction = live_torque_parameters.frictionCoefficientFiltered if (live_torque_parameters and hasattr(live_torque_parameters, 'frictionCoefficientFiltered')) else 0.0
    live_lat_factor = live_torque_parameters.latAccelFactorFiltered if (live_torque_parameters and hasattr(live_torque_parameters, 'latAccelFactorFiltered')) else 0.0
    custom_friction = self._cached_friction
    custom_lat_factor = self._cached_lat
    fallback_use_custom_friction = force_auto_tune_off or (_setting_changed(self._cached_friction, self._cached_friction_stock) and not force_auto_tune)
    fallback_use_custom_lat_factor = force_auto_tune_off or (_setting_changed(self._cached_lat, self._cached_lat_stock) and not force_auto_tune)
    use_custom_friction = fallback_use_custom_friction
    use_custom_lat_factor = fallback_use_custom_lat_factor

    friction_coeff = resolve_effective_torque_value(
      use_custom_friction,
      custom_friction,
      using_live_torque,
      live_friction,
      self._cached_friction_stock,
      self._cached_friction,
    )
    lat_factor = resolve_effective_torque_value(
      use_custom_lat_factor,
      custom_lat_factor,
      using_live_torque,
      live_lat_factor,
      self._cached_lat_stock,
      self._cached_lat,
    )

    use_auto_steer_delay = self._cached_use_auto_steer_delay
    if use_auto_steer_delay:
      lat_delay = live_delay.lateralDelay if live_delay else (
        self._cached_delay_stock if self._cached_delay_stock != 0.0 else self._cached_delay)
    else:
      lat_delay = self._cached_delay if self._cached_delay != 0.0 else (
        self._cached_delay_stock if self._cached_delay_stock != 0.0 else 0.0)

    tot_time = max(1, self.total_engagement_time)
    lat_pct = (self.lateral_engagement_time / tot_time) * 100.0
    long_pct = (self.longitudinal_engagement_time / tot_time) * 100.0

    # LongitudinalPlanSP carries none of StarPilot's jerk/danger diagnostics;
    # surface them as N/A unless a future publisher adds the fields.
    plan_sp = sm["longitudinalPlanSP"] if sm.valid.get("longitudinalPlanSP", False) else None
    accel_jerk = getattr(plan_sp, "accelerationJerk", None)
    danger_factor = getattr(plan_sp, "dangerFactor", None)
    danger_jerk = getattr(plan_sp, "dangerJerk", None)
    speed_jerk = getattr(plan_sp, "speedJerk", None)
    act_accel = ((car_control.actuators.accel if (car_control and hasattr(car_control.actuators, 'accel')) else 0.0)) * accel_conv

    fallback_use_custom_steer_ratio = force_auto_tune_off or (_setting_changed(self._cached_ratio, self._cached_ratio_stock) and not force_auto_tune)
    use_custom_steer_ratio = fallback_use_custom_steer_ratio
    custom_steer_ratio = self._cached_ratio
    if use_custom_steer_ratio and custom_steer_ratio != 0.0:
      steer_ratio = custom_steer_ratio
    elif live_parameters is not None:
      steer_ratio = live_parameters.steerRatio
    elif ui_state.CP is not None:
      steer_ratio = ui_state.CP.steerRatio
    else:
      steer_ratio = self._cached_ratio_stock if self._cached_ratio_stock != 0.0 else self._cached_ratio
    if live_parameters is not None:
      stiff_factor = 1.0 if force_auto_tune_off else live_parameters.stiffnessFactor
    elif ui_state.CP is not None:
      stiff_factor = 1.0 if force_auto_tune_off else ui_state.CP.stiffnessFactor
    else:
      stiff_factor = 1.0

    force_auto_tune_flm = self._flm_changed("ForceAutoTune", "ForceAutoTuneOff")
    self._metric_colors = {
      3: self._tuning_color(
        auto=use_auto_steer_delay and live_delay is not None,
        flm=self._flm_changed("SteerDelay", "UseAutoSteerDelay"),
      ),
      4: self._tuning_color(
        auto=using_live_torque and not use_custom_friction,
        flm=self._flm_changed("SteerFriction") or (force_auto_tune_flm and (using_live_torque or use_custom_friction)),
      ),
      5: self._tuning_color(
        auto=using_live_torque and not use_custom_lat_factor,
        flm=self._flm_changed("SteerLatAccel") or (force_auto_tune_flm and (using_live_torque or use_custom_lat_factor)),
      ),
      6: self._tuning_color(
        auto=live_parameters is not None and not use_custom_steer_ratio,
        flm=self._flm_changed("SteerRatio") or (force_auto_tune_flm and use_custom_steer_ratio),
      ),
      7: self._tuning_color(
        auto=live_parameters is not None and not force_auto_tune_off,
        flm=force_auto_tune_flm and force_auto_tune_off,
      ),
    }

    model_name = getattr(ui_state, "home_model_name", None) or "N/A"
    model_name = re.sub(r'\(.*\)', '', model_name)
    model_name = re.sub(r'[^a-zA-Z0-9 \-\.:]', '', model_name).strip() or "N/A"

    def fmt(value, suffix):
      return "N/A" if value is None else f"{value}{suffix}"

    self._metrics = {
      1: ("ACCEL", f"{accel_val:.2f}{accel_unit}"),
      2: ("MAX ACCEL", f"{self.max_acceleration:.2f}{accel_unit}"),
      3: ("STEER DELAY", f"{lat_delay:.5f}"),
      4: ("FRICTION", f"{friction_coeff:.5f}"),
      5: ("LAT ACCEL", f"{lat_factor:.5f}"),
      6: ("STEER RATIO", f"{steer_ratio:.5f}"),
      7: ("STEER STIFF", f"{stiff_factor:.5f}"),
      8: ("LATERAL %", f"{lat_pct:.2f}%"),
      9: ("LONG %", f"{long_pct:.2f}%"),
      10: ("STEER ANGLE", steer_label),
      11: ("TORQUE %", torque_label),
      12: ("ACT ACCEL", f"{act_accel:.2f}{accel_unit}"),
      13: ("DANGER %", fmt(None if danger_factor is None else danger_factor * 100.0, "%")),
      14: ("ACCEL JERK", fmt(accel_jerk, "")),
      15: ("DANGER JERK", fmt(danger_jerk, "")),
      16: ("SPEED JERK", fmt(speed_jerk, "")),
      17: (model_name, ""),
    }

  def _render(self, sidebar_rect: rl.Rectangle):
    self.update()
    if not self._visible:
      return

    count = len(self._active_ids)
    if count == 0:
      return

    rl.draw_rectangle_rec(sidebar_rect, rl.BLACK)

    spacing = max(1, (int(sidebar_rect.height) - (count * METRIC_HEIGHT)) // max(1, (count + 1)))
    y = sidebar_rect.y + spacing

    for metric_id in self._active_ids:
      if metric_id <= 0 or metric_id not in self._metrics:
        continue
      label_first, label_second = self._metrics[metric_id]
      self._draw_metric(sidebar_rect, label_first, label_second, self._metric_colors.get(metric_id, self._metric_color), y)
      y += METRIC_HEIGHT + spacing
