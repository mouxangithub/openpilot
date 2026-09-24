"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Carrot tuning settings.

Uses the same two-level structure as the rest of the sunnypilot settings pages:
the root is a scroller of navigation rows, and each row opens a sub-page that
draws a ``NavButton`` back arrow above its own scroller (see ``steering.py``
opening MADS / Lane Change / Torque, and
``cruise_sub_layouts/speed_limit_settings.py``). Grouping inside a page is done
with ``LineSeparatorSP`` rather than headings, matching ``steering.py`` and
``models.py``.
"""
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

import pyray as rl

from openpilot.selfdrive.ui.sunnypilot.layouts.settings import carrot_tuning_items as carrot_items
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import ButtonActionSP, LineSeparatorSP, ListItemSP, toggle_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.network import NavButton
from openpilot.system.ui.widgets.scroller_tici import Scroller


class CarrotNavRow(ListItemSP):
  """One group entry on the root page.

  Behaves like a normal settings row except that a tap anywhere on it opens the
  group. The stock row would toggle its description instead, but these
  descriptions are always visible - they are the only hint of what each page
  holds - so toggling would only hide the text the user needs.
  """

  def _handle_mouse_release(self, mouse_pos):
    if not self.is_visible or self.callback is None:
      return
    if rl.check_collision_point_rec(mouse_pos, self._rect):
      self.callback()


class CarrotGroupKey(IntEnum):
  START = 0
  CRUISE = 1
  NAVIGATION = 2
  SPEED = 3
  TUNING = 4
  DISPLAY = 5
  VEHICLE = 6
  DEVELOPER = 7


@dataclass(frozen=True)
class CarrotGroup:
  """One settings group. ``title``/``description`` are untranslated lookup keys."""

  title: str
  description: str
  build_items: Callable[[], list]


# Order here drives the order of the rows on the root page.
CARROT_GROUPS: tuple[CarrotGroup, ...] = (
  CarrotGroup(
    title='Start / Engage',
    description='How openpilot engages cruise and which steering wheel buttons control it.',
    build_items=carrot_items.build_start_items,
  ),
  CarrotGroup(
    title='Cruise & Following',
    description='Following distance, longitudinal gains, acceleration limits and cruise behavior.',
    build_items=carrot_items.build_cruise_items,
  ),
  CarrotGroup(
    title='Navigation',
    description='Navigation-based speed control, speed cameras, road limits and speed bumps.',
    build_items=carrot_items.build_navi_items,
  ),
  CarrotGroup(
    title='Turns & Curves',
    description='Automatic turn, fork / merge and curve speed control.',
    build_items=carrot_items.build_speed_items,
  ),
  CarrotGroup(
    title='Lateral Tuning',
    description='Steering geometry, MPC costs, torque tuning, lane change and blind spot.',
    build_items=carrot_items.build_tuning_items,
  ),
  CarrotGroup(
    title='Display & Sound',
    description='Cluster HUD, on-screen overlays, sound, YouTube and map style.',
    build_items=carrot_items.build_display_items,
  ),
  CarrotGroup(
    title='Vehicle',
    description='Vehicle-specific overrides and convenience options.',
    build_items=carrot_items.build_vehicle_items,
  ),
  CarrotGroup(
    title='Developer',
    description='Debug and diagnostic toggles. Use with caution.',
    build_items=carrot_items.build_dev_items,
  ),
)

# Distance the back button sits from the top of the page, and the gap between it
# and the list below. Matches speed_limit_settings.py.
BACK_TOP_MARGIN = 20
LIST_TOP_GAP = 40


class CarrotGroupLayout(Widget):
  """A single Carrot tuning group: back button above a scrolling list of settings."""

  def __init__(self, back_btn_callback: Callable, build_items: Callable[[], list]):
    super().__init__()
    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(back_btn_callback)
    self._scroller = Scroller(build_items(), line_separator=False, spacing=0)

  def _render(self, rect):
    self._back_button.set_position(rect.x, rect.y + BACK_TOP_MARGIN)
    self._back_button.render()

    list_y = self._back_button.rect.height + LIST_TOP_GAP
    self._scroller.render(rl.Rectangle(rect.x, rect.y + list_y, rect.width, rect.height - list_y))

  def show_event(self):
    self._scroller.show_event()

  def hide_event(self):
    self._scroller.hide_event()


class CarrotTuningLayout(Widget):
  """Carrot tuning root page: one navigation row per settings group.

  Used in two places: inside NavigationLayout (with a Back button) and as a
  top-level settings panel (no Back button, because the sidebar close button is the
  way out). ``back_btn_callback=None`` selects the panel form.
  """

  def __init__(self, back_btn_callback: Callable | None):
    super().__init__()
    self._back_button = NavButton(tr("Back")) if back_btn_callback is not None else None
    if self._back_button is not None:
      self._back_button.set_click_callback(back_btn_callback)

    self._carrot_web_enabled = toggle_item_sp(
      title=tr("Carrot Web Panel"),
      description=tr("Serve the carrot tuning page (/nav_params) and four-corner radar "
                      "visualisation (/radar) on port 8088."),
      param="CarrotWebEnabled",
    )

    self._current_group: CarrotGroupKey | None = None
    # Sub-pages are built on first open: the groups hold ~250 items in total and
    # there is no reason to allocate them all when the page is only passed through.
    self._group_layouts: dict[CarrotGroupKey, CarrotGroupLayout] = {}
    self._nav_rows: list = []
    self._scroller = Scroller(self._build_root_items(), line_separator=False, spacing=0)

  def _build_root_items(self) -> list:
    items: list = [self._carrot_web_enabled, LineSeparatorSP(40)]
    # strict=True doubles as the check that CARROT_GROUPS has one entry per key.
    groups = list(zip(CarrotGroupKey, CARROT_GROUPS, strict=True))
    for key, group in groups:
      row = CarrotNavRow(
        title=lambda t=group.title: tr(t),
        description=lambda d=group.description: tr(d),
        action_item=ButtonActionSP(text=lambda: tr("OPEN")),
        callback=self._make_open_callback(key),
      )
      items.append(row)
      self._nav_rows.append(row)
      if key is not groups[-1][0]:
        items.append(LineSeparatorSP(40))
    return items

  def _make_open_callback(self, key: CarrotGroupKey):
    def _open():
      self._set_current_group(key)
    return _open

  def _update_state(self):
    super()._update_state()
    self._carrot_web_enabled.action_item.set_enabled(ui_state.is_offroad())

  def _set_current_group(self, key: CarrotGroupKey | None):
    self._current_group = key
    if key is not None:
      if key not in self._group_layouts:
        self._group_layouts[key] = CarrotGroupLayout(lambda: self._set_current_group(None), CARROT_GROUPS[key].build_items)
      self._group_layouts[key].show_event()

  def _render(self, rect):
    if self._current_group is not None:
      self._group_layouts[self._current_group].render(rect)
      return

    # A top-level panel has no Back button: the sidebar close button is the way out.
    if self._back_button is not None:
      self._back_button.set_position(rect.x, rect.y + BACK_TOP_MARGIN)
      self._back_button.render()
      list_y = self._back_button.rect.height + LIST_TOP_GAP
    else:
      list_y = LIST_TOP_GAP
    self._scroller.render(rl.Rectangle(rect.x, rect.y + list_y, rect.width, rect.height - list_y))

  def show_event(self):
    self._current_group = None
    self._scroller.show_event()
    # Group descriptions are the only hint of what each page holds, so show them
    # up front instead of hiding them behind a tap like a settings row would.
    for row in self._nav_rows:
      row.show_description(True)

  def hide_event(self):
    self._current_group = None
    if self._group_layouts:
      for layout in self._group_layouts.values():
        layout.hide_event()
