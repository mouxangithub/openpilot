"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.input_dialog import InputDialogSP
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp, option_item_sp, button_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller


class NavigationLayout(Widget):
  def __init__(self):
    super().__init__()

    self._params = Params()
    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _initialize_items(self):
    self._amap_enabled = toggle_item_sp(
      title=tr("Enable Amap Navigation"),
      description=tr("Use Amap (Gaode) navigation data for map-based features."),
      param="AmapEnabled",
    )

    self._carrot_enabled = toggle_item_sp(
      title=tr("Enable Carrot Navigation"),
      description=tr("Use Carrot navigation data for map-based features."),
      param="CarrotEnabled",
    )

    self._amap_udp_port = option_item_sp(
      title=tr("Amap Navi UDP Port"),
      param="AmapNaviUdpPort",
      min_value=1024, max_value=65535, value_change_step=1,
      description=tr("UDP port used to receive Amap navigation instructions."),
      inline=True,
    )

    self._amap_api_key = button_item_sp(
      title=tr("Amap API Key"),
      button_text=tr("EDIT"),
      description=tr("API key for Amap services. Tap EDIT to enter or update the key."),
      callback=self._on_amap_api_key,
    )

    items = [
      self._amap_enabled,
      self._carrot_enabled,
      self._amap_udp_port,
      self._amap_api_key,
    ]
    return items

  def _update_state(self):
    super()._update_state()

    offroad = ui_state.is_offroad()
    self._amap_enabled.action_item.set_enabled(offroad)
    self._carrot_enabled.action_item.set_enabled(offroad)
    self._amap_udp_port.action_item.set_enabled(offroad)
    self._amap_api_key.action_item.set_enabled(offroad)

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
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
