"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.input_dialog import InputDialogSP
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.carrot_tuning import CarrotTuningLayout
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp, button_item_sp, simple_button_item_sp
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.list_view import text_item
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller
from enum import IntEnum


class PanelType(IntEnum):
  NAVIGATION = 0
  CARROT_TUNING = 1


class NavigationLayout(Widget):
  def __init__(self):
    super().__init__()

    self._params = Params()
    self._current_panel = PanelType.NAVIGATION
    self._carrot_tuning_layout = CarrotTuningLayout(lambda: self._set_current_panel(PanelType.NAVIGATION))
    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _initialize_items(self):
    self._amap_map_data_enabled = toggle_item_sp(
      title=tr("Enable Amap Map Data"),
      description=tr("Use Amap (Gaode) online map data for speed limits and road names in China."),
      param="AmapMapDataEnabled",
    )

    self._carrot_amap_blind_spot_enabled = toggle_item_sp(
      title=tr("Enable Amap Blind Spot Data"),
      description=tr("Parse blind-spot / LiDAR / extBlinker fields from the 7706 UDP stream."),
      param="CarrotAmapBlindSpotEnabled",
    )

    self._carrot_enabled = toggle_item_sp(
      title=tr("Enable Carrot Navigation"),
      description=tr("Use Carrot navigation data for map-based features."),
      param="CarrotEnabled",
    )

    self._amap_api_key = button_item_sp(
      title=tr("Amap API Key"),
      button_text=tr("EDIT"),
      description=tr("API key for Amap services. Tap EDIT to enter or update the key."),
      callback=self._on_amap_api_key,
    )

    # The curve value now acts on the car: it is folded into SmartCruiseControlMap's
    # target as one of the navigation-deceleration sources, so it needs that controller
    # (and its own master switch) to be on. It is still never a speed-limit sign - it
    # only ever lowers the target. The light count remains display-only and, as of this
    # change, has no consumer yet; its description says so rather than implying it works.
    self._amap_curve_speed = toggle_item_sp(
      title=tr("Amap Curve Speed"),
      description=tr("Slow for curves using the Amap route shape. Only ever lowers the "
                     "target speed; needs Smart Cruise Control - Map to be on as well."),
      param="AmapCurveSpeedEnabled",
    )

    self._amap_traffic_light_hint = toggle_item_sp(
      title=tr("Amap Traffic Light Hint"),
      description=tr("Count traffic lights on the route ahead. Not yet shown anywhere; "
                     "no effect for now."),
      param="AmapTrafficLightHintEnabled",
    )

    self._carrot_navi_v2_enabled = toggle_item_sp(
      title=tr("Enable Carrot Navi v2 (7714)"),
      description=tr("Use the 7714 WebSocket v2 rich navigation stream (traffic, lanes, crossroad images)."),
      param="CarrotNaviV2Enabled",
    )

    self._carrot_web_enabled = toggle_item_sp(
      title=tr("Carrot Web Panel"),
      description=tr("Serve the carrot tuning page (/nav_params) and four-corner radar "
                      "visualisation (/radar) on port 8088."),
      param="CarrotWebEnabled",
    )

    self._car_name = text_item(
      lambda: tr("Car Model"),
      lambda: self._params.get("CarName") or tr("N/A"),
      description=tr("Identified car model, sent automatically with Carrot FTP uploads "
                      "and shown in the companion app."),
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

    self._carrot_tuning_button = simple_button_item_sp(
      button_text=lambda: tr("Carrot Tuning"),
      button_width=800,
      callback=lambda: self._set_current_panel(PanelType.CARROT_TUNING),
    )

    items = [
      self._amap_map_data_enabled,
      self._carrot_amap_blind_spot_enabled,
      self._carrot_enabled,
      self._carrot_navi_v2_enabled,
      self._carrot_web_enabled,
      self._car_name,
      self._amap_api_key,
      self._amap_curve_speed,
      self._amap_traffic_light_hint,
      self._carrot_atc_blinker,
      self._carrot_nav_cruise_speed,
      self._carrot_tuning_button,
    ]
    return items

  def _update_state(self):
    super()._update_state()

    offroad = ui_state.is_offroad()
    self._amap_map_data_enabled.action_item.set_enabled(offroad)
    self._carrot_amap_blind_spot_enabled.action_item.set_enabled(offroad)
    self._carrot_enabled.action_item.set_enabled(offroad)
    self._amap_api_key.action_item.set_enabled(offroad)
    self._carrot_web_enabled.action_item.set_enabled(offroad)

    # The v2 link and the nav-speed limit only mean anything with Carrot on,
    # matching the webui panel's visible_if conditions. Read the param rather than
    # the toggle's cached state so an external change is reflected too.
    carrot_on = self._params.get_bool("CarrotEnabled")
    self._carrot_navi_v2_enabled.set_visible(carrot_on)
    self._carrot_nav_cruise_speed.set_visible(carrot_on)

    current_key = self._params.get("AmapApiKey") or ""
    masked = "" if not current_key else "*" * min(len(current_key), 12)
    self._amap_api_key.action_item.set_value(masked)

  def _on_amap_api_key(self):
    current_key = self._params.get("AmapApiKey") or ""
    dialog = InputDialogSP(
      title=tr("Enter Amap API Key"),
      sub_title=tr("Your key is stored locally and is not uploaded."),
      current_text=current_key,
      param="AmapApiKey",
    )
    dialog.show()

  def _render(self, rect):
    if self._current_panel == PanelType.CARROT_TUNING:
      self._carrot_tuning_layout.render(rect)
    else:
      self._scroller.render(rect)

  def _set_current_panel(self, panel: PanelType):
    self._current_panel = panel
    if panel == PanelType.CARROT_TUNING:
      self._carrot_tuning_layout.show_event()

  def show_event(self):
    self._set_current_panel(PanelType.NAVIGATION)
    self._scroller.show_event()
