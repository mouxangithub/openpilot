"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import threading
import time
from enum import IntEnum

import pyray as rl

from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.system.ui.widgets.network import NetworkUI
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.bluetooth_settings import CarrotBluetoothLayout


class NetworkUIPanel(IntEnum):
  WIFI = 0
  ADVANCED = 1
  BLUETOOTH = 2


class NetworkUISP(NetworkUI):
  def __init__(self, wifi_manager):
    super().__init__(wifi_manager)

    self.scan_button = Button(tr("Scan"), self._scan_clicked, button_style=ButtonStyle.NORMAL, font_size=60, border_radius=30)
    self.scan_button.set_rect(rl.Rectangle(0, 0, 400, 100))

    self._scanning = False
    self._wifi_manager.add_callbacks(networks_updated=self._on_networks_updated)

    # Bluetooth panel
    self._bluetooth_panel = self._child(CarrotBluetoothLayout())

    # Override _current_panel to use our extended enum (starts at WIFI)
    self._current_panel = NetworkUIPanel.WIFI

  def _scan_clicked(self):
    self._scanning = True
    self.scan_button.set_text(tr("Scanning..."))
    self.scan_button.set_enabled(False)

    threading.Thread(target=self._wifi_manager._update_networks, daemon=True).start()
    self._wifi_manager._request_scan()
    self._wifi_manager._last_network_update = time.monotonic()

  def _on_networks_updated(self, networks):
    if self._scanning:
      self._scanning = False
      self.scan_button.set_text(tr("Scan"))
      self.scan_button.set_enabled(True)

  def _cycle_panel(self):
    # Cycle through: WIFI → ADVANCED → BLUETOOTH → WIFI
    current = NetworkUIPanel(self._current_panel)
    if current == NetworkUIPanel.WIFI:
      self._set_current_panel(NetworkUIPanel.ADVANCED)
    elif current == NetworkUIPanel.ADVANCED:
      self._set_current_panel(NetworkUIPanel.BLUETOOTH)
    else:
      self._set_current_panel(NetworkUIPanel.WIFI)

  def show_event(self):
    super().show_event()
    self._set_current_panel(NetworkUIPanel.WIFI)
    self._bluetooth_panel.show_event()

  def _render(self, _):
    # Subtract button
    nav_btn_texts = {NetworkUIPanel.WIFI: tr("Advanced"), NetworkUIPanel.ADVANCED: tr("Bluetooth"), NetworkUIPanel.BLUETOOTH: tr("Back")}
    content_rect = rl.Rectangle(
      self._rect.x,
      self._rect.y + self._nav_button.rect.height + 40,
      self._rect.width,
      self._rect.height - self._nav_button.rect.height - 40,
    )

    current = NetworkUIPanel(self._current_panel)
    self._nav_button.text = nav_btn_texts.get(current, tr("Back"))

    # Position nav button
    if current == NetworkUIPanel.WIFI:
      self._nav_button.set_position(self._rect.x + self._rect.width - self._nav_button.rect.width, self._rect.y + 20)
    elif current == NetworkUIPanel.ADVANCED:
      self._nav_button.set_position(self._rect.x, self._rect.y + 20)
    else:
      self._nav_button.set_position(self._rect.x, self._rect.y + 20)

    if current == NetworkUIPanel.WIFI:
      self._wifi_panel.render(content_rect)
      self.scan_button.set_position(self._rect.x, self._rect.y + 20)
      self.scan_button.render()
    elif current == NetworkUIPanel.ADVANCED:
      self._advanced_panel.render(content_rect)
    else:
      self._bluetooth_panel.render(content_rect)

    self._nav_button.render()

  def _set_current_panel(self, panel: NetworkUIPanel):
    self._current_panel = panel
