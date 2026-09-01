"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from collections.abc import Callable

import pyray as rl
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import option_item_sp, simple_button_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.network import NavButton
from openpilot.system.ui.widgets.scroller_tici import Scroller


class LongitudinalMpcTuningLayout(Widget):
  def __init__(self, back_btn_callback: Callable):
    super().__init__()
    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(back_btn_callback)

    # value is stored scaled x100 (use_float_scaling); (control, default_internal)
    self._option_items: list = []
    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=False, spacing=0)

  def _opt(self, title, param, min_value, max_value, step, digits):
    item = option_item_sp(
      title=lambda t=title: tr(t),
      param=param,
      min_value=min_value,
      max_value=max_value,
      value_change_step=step,
      use_float_scaling=True,
      label_callback=lambda v, d=digits: f"{v / 100.0:.{d}f}",
    )
    self._option_items.append(item)
    return item

  def _initialize_items(self):
    self._comfort_brake = self._opt(tr_noop("Comfort Brake"), "LongitudinalMpcTuningComfortBrake", 150, 450, 5, 2)
    self._stop_distance = self._opt(tr_noop("Stop Distance"), "LongitudinalMpcTuningStopDistance", 200, 1200, 50, 1)
    self._t_follow_relaxed = self._opt(tr_noop("Follow Time - Relaxed"), "LongitudinalMpcTuningTFollowRelaxed", 100, 250, 5, 2)
    self._t_follow_standard = self._opt(tr_noop("Follow Time - Standard"), "LongitudinalMpcTuningTFollowStandard", 100, 220, 5, 2)
    self._t_follow_aggressive = self._opt(tr_noop("Follow Time - Aggressive"), "LongitudinalMpcTuningTFollowAggressive", 80, 180, 5, 2)
    self._x_ego_obstacle_cost = self._opt(tr_noop("Distance Cost"), "LongitudinalMpcTuningXEgoObstacleCost", 50, 600, 25, 2)
    self._j_ego_cost = self._opt(tr_noop("Jerk Cost"), "LongitudinalMpcTuningJEgoCost", 100, 1500, 50, 2)
    self._a_change_cost = self._opt(tr_noop("Acceleration Change Cost"), "LongitudinalMpcTuningAChangeCost", 5000, 60000, 500, 0)
    self._danger_zone_cost = self._opt(tr_noop("Danger Zone Cost"), "LongitudinalMpcTuningDangerZoneCost", 0, 50000, 500, 0)
    self._lead_danger_factor = self._opt(tr_noop("Lead Danger Factor"), "LongitudinalMpcTuningLeadDangerFactor", 25, 150, 5, 2)

    self._reset_button = simple_button_item_sp(
      button_text=lambda: tr("Reset to Defaults"),
      button_width=720,
      callback=self._reset_defaults,
    )

    return [*self._option_items, self._reset_button]

  def _reset_defaults(self):
    # (control, default value scaled x100)
    defaults = [
      (self._comfort_brake, 250),
      (self._stop_distance, 600),
      (self._t_follow_relaxed, 175),
      (self._t_follow_standard, 145),
      (self._t_follow_aggressive, 125),
      (self._x_ego_obstacle_cost, 300),
      (self._j_ego_cost, 500),
      (self._a_change_cost, 20000),
      (self._danger_zone_cost, 10000),
      (self._lead_danger_factor, 75),
    ]
    for ctrl, internal in defaults:
      ctrl.action_item.set_value(internal)

  def _render(self, rect):
    self._back_button.set_position(self._rect.x, self._rect.y + 20)
    self._back_button.render()

    content_rect = rl.Rectangle(
      rect.x,
      rect.y + self._back_button.rect.height + 40,
      rect.width,
      rect.height - self._back_button.rect.height - 40,
    )
    self._scroller.render(content_rect)

  def show_event(self):
    self._scroller.show_event()

  def _update_state(self):
    super()._update_state()
    has_long = ui_state.CP is not None and ui_state.has_longitudinal_control
    for item in self._option_items:
      item.action_item.set_enabled(has_long)
