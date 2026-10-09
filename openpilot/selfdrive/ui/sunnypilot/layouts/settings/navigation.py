"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json

from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp, button_item_sp, option_item_sp, multiple_button_item_sp
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller


class NavigationLayout(Widget):
  def __init__(self):
    super().__init__()

    self._params = Params()
    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _initialize_items(self):
    self._osm_map_data_enabled = toggle_item_sp(
      title=tr("Enable OSM Map Data"),
      description=tr("Use offline OSM map data for speed limits and road names. Turn off "
                     "to ignore the offline map entirely - useful when navigation is the "
                     "source you trust, since the offline data can be out of date."),
      param="OsmMapDataEnabled",
    )

    self._carrot_amap_blind_spot_enabled = toggle_item_sp(
      title=tr("Enable Carrot Blind Spot Data"),
      description=tr("Parse blind-spot / LiDAR / extBlinker fields from the 7706 UDP stream."),
      param="CarrotAmapBlindSpotEnabled",
    )

    self._carrot_enabled = toggle_item_sp(
      title=tr("Enable Carrot Navigation"),
      description=tr("Use Carrot navigation data for map-based features."),
      param="CarrotEnabled",
    )

    # Behaviour switch, not a process gate: carrot_navi (TCP 7714) is always_run,
    # matching CarrotPilot, so the link is always reachable. This only decides
    # whether what it produces is merged into the driving stack (card.py).
    self._carrot_navi_v2_enabled = toggle_item_sp(
      title=tr("Enable Carrot Navi v2 (7714)"),
      description=tr("Use the 7714 WebSocket v2 rich navigation stream (traffic, lanes, crossroad images). "
                     "The 7714 link always runs; this only decides whether its data is used."),
      param="CarrotNaviV2Enabled",
    )

    # OFF by default: this lets a navigation packet synthesise a turn signal, and the
    # synthetic blinker reaches the vehicle's own turn-signal CAN message.
    self._carrot_atc_blinker = toggle_item_sp(
      title=tr("Carrot ATC Turn Signal"),
      description=tr("Let the Carrot app's turn instruction act as a turn signal. "
                     "This reaches the car's real turn signal, so it is off by default."),
      param="CarrotAtcBlinkerEnabled",
    )

    self._carrot_nav_cruise_speed = toggle_item_sp(
      title=tr("Navigation Cruise Speed"),
      description=tr("Use navigation desired speed to limit cruise speed."),
      param="CarrotNavCruiseSpeedEnabled",
    )

    self._haptic_speed_camera = option_item_sp(
      title=tr("Haptic Feedback (Speed Camera)"),
      description=tr("Steering-wheel nudge when carrot decelerates for a speed camera."),
      param="HapticFeedbackWhenSpeedCamera",
      min_value=0, max_value=2, value_change_step=1,
    )

    self._carrot_navi_debug = button_item_sp(
      title=tr("Carrot Navi Debug"),
      button_text=tr("VIEW"),
      description=tr("View the last navigation event summary handled by CarrotManager."),
      callback=self._on_carrot_navi_debug,
    )

    items = [
      self._osm_map_data_enabled,
      self._carrot_enabled,
      self._carrot_navi_v2_enabled,
      self._carrot_atc_blinker,
      self._carrot_nav_cruise_speed,
      self._haptic_speed_camera,
      self._carrot_amap_blind_spot_enabled,
      self._carrot_navi_debug,
    ]
    return items

  def _update_state(self):
    super()._update_state()

    offroad = ui_state.is_offroad()
    self._carrot_amap_blind_spot_enabled.action_item.set_enabled(offroad)
    self._carrot_enabled.action_item.set_enabled(offroad)

    # The v2 link and the nav-speed limit only mean anything with Carrot on,
    # matching the webui panel's visible_if conditions. Read the param rather than
    # the toggle's cached state so an external change is reflected too.
    carrot_on = self._params.get_bool("CarrotEnabled")
    self._carrot_navi_v2_enabled.set_visible(carrot_on)
    self._carrot_nav_cruise_speed.set_visible(carrot_on)
    self._haptic_speed_camera.set_visible(carrot_on)

  def _on_carrot_navi_debug(self):
    # CarrotNaviDebug is registered as a JSON param (params_keys.h), so Params.get()
    # already decodes it to a dict. carrot_man's _merge_navi_debug also tolerates a
    # raw str/bytes for an unset or legacy value, so accept all three shapes here.
    raw = self._params.get("CarrotNaviDebug")
    if isinstance(raw, (bytes, bytearray)):
      raw = raw.decode("utf-8", errors="replace")

    if isinstance(raw, dict):
      debug = raw
    elif isinstance(raw, str) and raw.strip():
      try:
        parsed = json.loads(raw)
      except Exception:
        self._push_navi_debug(raw)
        return
      debug = parsed if isinstance(parsed, dict) else {}
    else:
      debug = {}

    if not debug:
      message = tr("No navigation event received yet.")
    else:
      lines = [
        f"Type: {debug.get('type', '')}",
        f"Event Time: {debug.get('eventTimeMs', 0)} ms",
        f"Received At: {debug.get('receivedAt', '')}",
        "",
      ]
      summary = debug.get('summary')
      if isinstance(summary, dict) and summary:
        lines.append(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
      # The 10 Hz snapshot writer fills these keys instead of `summary`; show them
      # rather than render an empty body for a snapshot-only payload.
      snapshot = {k: v for k, v in debug.items() if k not in ('summary', 'title', 'lines')}
      if snapshot:
        lines.append(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True, default=str))
      message = "\n".join(lines)

    self._push_navi_debug(message)

  def _push_navi_debug(self, message: str):
    # Same scrollable dialog the error/alarm viewer uses: rich mode routes the body
    # through Scroller + HtmlRenderer, so long navigation-debug dumps can be scrolled
    # instead of overflowing the fixed-size alert box.
    gui_app.push_widget(ConfirmDialog(message, tr("OK"), cancel_text="", rich=True))

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
