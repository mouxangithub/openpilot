"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable

import pyray as rl

from openpilot.system.ui.lib.application import gui_app, MousePos, TextAlignment
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.scroll_panel import GuiScrollPanel
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.system.ui.widgets.label import gui_label
from openpilot.system.ui.widgets.toggle import Toggle

# Supported actions for button mapping
ACTIONS = (
  'none', 'accelCruise', 'decelCruise', 'gapAdjustCruise', 'lfaButton', 'cancel',
  'accelCruiseLong', 'decelCruiseLong', 'gapAdjustCruiseLong', 'lfaButtonLong', 'cancelLong',
  'laneLeft', 'laneRight', 'paddleDecel', 'carrotCruise',
)

MAPPING_BUTTONS = ('up', 'down', 'left', 'right', 'center', '1', '2')
GESTURES = ('single', 'double', 'long')
GESTURE_LABELS = {'single': 'Short', 'double': 'Double', 'long': 'Long'}

# Default single-press mapping expanded to all gesture tokens for the Yiser-J6 preset.
BT_DEFAULTS = {
  'up_single': 'accelCruise', 'up_double': 'none', 'up_long': 'none',
  'down_single': 'decelCruise', 'down_double': 'none', 'down_long': 'none',
  'left_single': 'laneLeft', 'left_double': 'none', 'left_long': 'none',
  'right_single': 'laneRight', 'right_double': 'none', 'right_long': 'none',
  'center_single': 'paddleDecel', 'center_double': 'none', 'center_long': 'none',
  '1_single': 'gapAdjustCruise', '1_double': 'none', '1_long': 'none',
  '2_single': 'none', '2_double': 'none', '2_long': 'none',
}

_CONFIG_PATH = '/data/params/d/CarrotBluetooth'
_RUNTIME_PATH = '/dev/shm/carrot-bluetooth'

API_BASE = 'http://127.0.0.1:5080'


def _api_path(operation: str | None = None) -> str:
  base = f'{API_BASE}/api/opui/bluetooth'
  return f'{base}/{operation}' if operation else base


def _http_get(path: str) -> dict:
  import urllib.request
  try:
    with urllib.request.urlopen(path, timeout=5) as resp:
      import json
      return json.loads(resp.read())
  except Exception:
    return {}


def _http_post(operation: str, data: dict | None = None) -> dict:
  import json
  import urllib.request
  try:
    body = b'{}' if data is None else json.dumps(data).encode()
    req = urllib.request.Request(_api_path(operation), data=body,
                                headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as resp:
      return json.loads(resp.read())
  except Exception as e:
    return {'error': str(e)}


@dataclass
class BTDevice:
  address: str = ''
  name: str = ''
  paired: bool = False
  connected: bool = False
  rssi: int | None = None
  battery: int | None = None
  enabled: bool = False
  grabbed: bool = False
  profile: str = 'generic'
  mapping: dict = field(default_factory=dict)


class BTPanel(IntEnum):
  DEVICES = 0
  EDITOR = 1
  ADVANCED = 2


@dataclass
class BTRuntime:
  alive: bool = False
  stationary: bool = False
  grabbed: list = field(default_factory=list)
  learning: dict | None = None
  errors: dict = field(default_factory=dict)
  recent_events: list = field(default_factory=list)


@dataclass
class BTState:
  has_bluez: bool = False
  service_running: bool = False
  available: bool = False
  radio_enabled: bool = False
  discoverable: bool = False
  local_name: str = ''
  discovering: bool = False
  runtime: BTRuntime = field(default_factory=BTRuntime)
  devices: list[BTDevice] = field(default_factory=list)
  config_devices: dict = field(default_factory=dict)
  error: str = ''
  prompt: dict | None = None
  learning_addr: str | None = None


class CarrotBluetoothLayout(Widget):
  """
  Native GUI panel for Carrot Bluetooth HID remote configuration.
  """

  def __init__(self):
    super().__init__()

    self._state = BTState()
    self._state_lock = threading.Lock()
    self._selected_address: str | None = None
    self._draft: BTDevice | None = None
    self._dirty = False
    self._panel = BTPanel.DEVICES
    self._last_fetch = 0.0
    self._fetch_interval = 1.0
    self._auto_scanned = False
    self._installing = False

    # UI dimensions
    self._item_height = 160
    self._btn_height = 80
    self._label_height = 60
    self._mapping_row_height = 80
    self._gesture_col_width = 220
    self._padding = 30
    self._content_width = 0

    # Scroll panel for device list
    self._scroll_panel = GuiScrollPanel()

    # Status / error labels
    self._status_text = ''
    self._error_text = ''

    # Buttons / toggles
    self._scan_btn = Button(tr("Scan"), self._on_scan_clicked, button_style=ButtonStyle.NORMAL, font_size=60, border_radius=30)
    self._adv_btn = Button(tr("Advanced"), self._on_advanced_clicked, button_style=ButtonStyle.NORMAL, font_size=46, border_radius=30)
    self._install_btn = Button(tr("Install Bluetooth"), self._on_install_clicked, button_style=ButtonStyle.PRIMARY, font_size=52, border_radius=24)
    self._enable_btn = Button(tr("Enable Bluetooth"), self._on_enable_service_clicked, button_style=ButtonStyle.PRIMARY, font_size=52, border_radius=24)
    self._retry_btn = Button(tr("Retry"), self._on_retry_clicked, button_style=ButtonStyle.PRIMARY, font_size=52, border_radius=24)
    self._radio_toggle = Toggle(self._state.radio_enabled, self._on_radio_toggled)
    self._discoverable_toggle = Toggle(False, self._on_discoverable_toggled)
    self._save_btn = Button(tr("Save"), self._on_save_clicked, button_style=ButtonStyle.PRIMARY, font_size=45, border_radius=15)
    self._save_name_btn = Button(tr("Save"), self._on_save_name_clicked, button_style=ButtonStyle.PRIMARY, font_size=40, border_radius=15)
    self._reset_btn = Button(tr("Reset Bluetooth"), self._on_reset_clicked, button_style=ButtonStyle.DANGER, font_size=45, border_radius=15)
    self._test_btn = Button(tr("Test / Learn"), self._on_test_clicked, button_style=ButtonStyle.NORMAL, font_size=45, border_radius=15)
    self._stop_btn = Button(tr("Stop Test"), self._on_stop_clicked, button_style=ButtonStyle.DANGER, font_size=45, border_radius=15)
    self._back_btn = Button(tr("Back"), self._on_back_clicked, button_style=ButtonStyle.NORMAL, font_size=45, border_radius=15)
    self._connect_btn = Button('', self._on_connect_clicked, button_style=ButtonStyle.PRIMARY, font_size=40, border_radius=15)
    self._forget_btn = Button(tr("Forget"), self._on_forget_clicked, button_style=ButtonStyle.DANGER, font_size=40, border_radius=15)
    self._edit_btn = Button(tr("Edit"), self._on_edit_clicked, button_style=ButtonStyle.NORMAL, font_size=40, border_radius=15)

    self._last_radio_state = self._state.radio_enabled
    self._last_discoverable_state = self._state.discoverable

    # Gesture buttons for mapping
    self._gesture_btns: dict[str, dict[str, Button]] = {}
    for btn_name in MAPPING_BUTTONS:
      self._gesture_btns[btn_name] = {}
      for gesture in GESTURES:
        token = f'{btn_name}_{gesture}'
        b = Button('', lambda _t=token: self._on_mapping_clicked(_t),
                   button_style=ButtonStyle.TRANSPARENT_WHITE_BORDER, font_size=35, border_radius=10)
        self._gesture_btns[btn_name][gesture] = b

    # Device name input
    self._name_input = ''
    self._name_focused = False

    # Events display
    self._last_event_text = ''
    self._seen_event_ids: set = set()

  def show_event(self) -> None:
    self._running = True
    self._selected_address = None
    self._draft = None
    self._dirty = False
    self._panel = BTPanel.DEVICES
    self._auto_scanned = False
    self._installing = False
    self._fetch_state()

  def hide_event(self) -> None:
    self._running = False

  def _fetch_state(self) -> None:
    if not self._running:
      return
    try:
      data = _http_get(_api_path())
      state = self._parse_state(data)
      with self._state_lock:
        self._state = state
        self._error_text = state.error
        self._status_text = self._status_for_state(state)
    except Exception as e:
      with self._state_lock:
        self._error_text = str(e)
    self._last_fetch = time.monotonic()

  def _status_for_state(self, state: BTState) -> str:
    if not state.has_bluez:
      return tr("Bluetooth is not installed")
    if not state.service_running:
      return tr("Bluetooth service is stopped")
    if not state.available:
      return tr("No Bluetooth adapter found")
    if not state.runtime.stationary:
      return tr("Requires stationary & disengaged state")
    if state.discovering:
      return tr("Scanning...")
    if not state.radio_enabled:
      return tr("Bluetooth disabled")
    return tr("Ready")

  def _parse_state(self, data: dict) -> BTState:
    state = BTState()
    state.has_bluez = data.get('hasBluez', False)
    state.service_running = data.get('serviceRunning', False)
    state.available = data.get('available', False)
    state.radio_enabled = data.get('radioEnabled', False)
    state.discoverable = data.get('discoverable', False)
    state.local_name = data.get('localName', '') or ''
    state.error = data.get('error', '') or ''

    rt = data.get('runtime', {})
    state.runtime = BTRuntime(
      alive=rt.get('alive', False),
      stationary=rt.get('stationary', False),
      grabbed=rt.get('grabbed', []),
      errors=rt.get('errors', {}),
    )
    lr = rt.get('learning')
    state.learning_addr = lr.get('address') if lr else None

    state.devices = []
    for d in data.get('devices', []):
      addr = d.get('address', '')
      cfg = data.get('config', {}).get('devices', {}).get(addr, {})
      dev = BTDevice(
        address=addr,
        name=d.get('name', addr),
        paired=d.get('paired', False),
        connected=d.get('connected', False),
        rssi=d.get('rssi'),
        battery=d.get('battery'),
        enabled=cfg.get('enabled', False),
        grabbed=addr in state.runtime.grabbed,
        profile=cfg.get('profile', 'generic'),
        mapping=cfg.get('mapping', {}),
      )
      state.devices.append(dev)
    state.config_devices = data.get('config', {}).get('devices', {})

    state.prompt = data.get('prompt')

    adapters = data.get('adapters', [])
    state.discovering = any(a.get('discovering', False) for a in adapters)

    return state

  def _render(self, rect: rl.Rectangle) -> None:
    self._content_width = rect.width

    now = time.monotonic()
    if now - self._last_fetch > self._fetch_interval:
      self._fetch_state()

    with self._state_lock:
      state = self._state
      error_text = self._error_text
      status_text = self._status_text

    if self._panel == BTPanel.EDITOR and self._draft is not None:
      self._render_editor(rect, state)
    elif self._panel == BTPanel.ADVANCED:
      self._render_advanced(rect, state)
    else:
      self._render_main(rect, state, error_text, status_text)

    self._maybe_auto_scan(state)

  def _maybe_auto_scan(self, state: BTState) -> None:
    if self._auto_scanned:
      return
    if not state.available or not state.radio_enabled or not state.runtime.stationary:
      return
    self._auto_scanned = True
    self._http_async('scan')

  def _render_main(self, rect: rl.Rectangle, state: BTState, error_text: str, status_text: str) -> None:
    y = rect.y

    # Not installed
    if not state.has_bluez:
      self._render_empty_state(rect, icon='📡', title=tr("Bluetooth is not installed"),
                               desc=tr("Install BlueZ to enable Bluetooth HID remotes and device management."),
                               btn=self._install_btn, btn_label=tr("Installing...") if self._installing else None)
      return

    # Service not running
    if not state.service_running:
      self._render_empty_state(rect, icon='🔘', title=tr("Bluetooth service is stopped"),
                               desc=tr("Start the Bluetooth service to scan and pair devices."),
                               btn=self._enable_btn)
      return

    # No adapter
    if not state.available:
      self._render_empty_state(rect, icon='📵', title=tr("No Bluetooth adapter found"),
                               desc=tr("Flash an AGNOS with Bluetooth support or plug in a USB Bluetooth dongle."),
                               btn=self._retry_btn)
      return

    # Normal device list UI
    content_top = self._render_header(rect, state, error_text, status_text)
    self._render_devices(rect, content_top, state)

  def _render_empty_state(self, rect: rl.Rectangle, icon: str, title: str, desc: str,
                          btn: Button, btn_label: str | None = None) -> None:
    y = rect.y + 120
    gui_label(rl.Rectangle(rect.x, y, rect.width, 120), icon, font_size=110, alignment=TextAlignment.CENTER)
    y += 140
    gui_label(rl.Rectangle(rect.x, y, rect.width, 80), title, font_size=52, alignment=TextAlignment.CENTER)
    y += 90
    gui_label(rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, 120), desc,
              font_size=38, alignment=TextAlignment.CENTER, color=rl.Color(170, 170, 170, 255))
    y += 160
    if btn_label:
      btn.set_text(btn_label)
      btn.set_enabled(False)
    else:
      btn.set_enabled(True)
    btn_w = min(520, rect.width - self._padding * 2)
    btn.set_rect(rl.Rectangle(rect.x + (rect.width - btn_w) / 2, y, btn_w, 110))
    btn.render()

  def _render_header(self, rect: rl.Rectangle, state: BTState, error_text: str, status_text: str) -> float:
    y = rect.y + 20
    top_h = 100
    can_act = state.runtime.stationary and state.available

    # Scan / Stop button
    self._scan_btn.set_text(tr("Stop") if state.discovering else tr("Scan"))
    self._scan_btn.set_enabled(can_act and (state.discovering or state.radio_enabled))
    self._scan_btn.set_rect(rl.Rectangle(rect.x, y, 400, top_h))
    self._scan_btn.render()

    # Advanced button
    self._adv_btn.set_enabled(can_act)
    self._adv_btn.set_rect(rl.Rectangle(rect.x + rect.width - 320, y, 320, top_h))
    self._adv_btn.render()

    y += top_h + 40

    # Status
    status_color = rl.Color(255, 220, 80, 255) if 'Scanning' in status_text else rl.WHITE
    gui_label(rl.Rectangle(rect.x, y, rect.width, self._label_height), status_text, font_size=42,
              alignment=TextAlignment.CENTER, color=status_color)
    y += self._label_height

    # Error
    if error_text:
      gui_label(rl.Rectangle(rect.x, y, rect.width, self._label_height), error_text[:80], font_size=38,
                alignment=TextAlignment.CENTER, color=rl.Color(255, 80, 80, 255))
      y += self._label_height

    return y + 20

  def _render_devices(self, rect: rl.Rectangle, content_top: float, state: BTState) -> None:
    start_y = content_top

    paired = [d for d in state.devices if d.paired]
    found = sorted([d for d in state.devices if not d.paired], key=lambda d: d.rssi or -1000, reverse=True)

    if not paired and not found:
      gui_label(rl.Rectangle(rect.x, start_y + 80, rect.width, 80), tr("No devices found"),
                font_size=45, alignment=TextAlignment.CENTER, color=rl.Color(150, 150, 150, 255))
      return

    row_h = self._item_height + 20
    group_title_h = 60
    total_h = 0
    if paired:
      total_h += group_title_h + len(paired) * row_h
    if found:
      total_h += group_title_h + len(found) * row_h

    content_rect = rl.Rectangle(rect.x, rect.y, rect.width, total_h)
    scissor_rect = rl.Rectangle(rect.x, start_y, rect.width, rect.height - (start_y - rect.y))
    offset = self._scroll_panel.update(scissor_rect, content_rect)

    rl.begin_scissor_mode(int(scissor_rect.x), int(scissor_rect.y), int(scissor_rect.width), int(scissor_rect.height))
    y = rect.y + offset
    if paired:
      gui_label(rl.Rectangle(rect.x, y, rect.width, group_title_h), tr("Paired devices"),
                font_size=36, alignment=TextAlignment.LEFT, color=rl.Color(150, 150, 150, 255))
      y += group_title_h
      for dev in paired:
        item_rect = rl.Rectangle(rect.x, y, rect.width, self._item_height)
        if rl.check_collision_recs(item_rect, scissor_rect):
          self._render_device_card(item_rect, dev, state)
        y += row_h

    if found:
      gui_label(rl.Rectangle(rect.x, y, rect.width, group_title_h), tr("Available devices"),
                font_size=36, alignment=TextAlignment.LEFT, color=rl.Color(150, 150, 150, 255))
      y += group_title_h
      for dev in found:
        item_rect = rl.Rectangle(rect.x, y, rect.width, self._item_height)
        if rl.check_collision_recs(item_rect, scissor_rect):
          self._render_device_card(item_rect, dev, state)
        y += row_h

    rl.end_scissor_mode()

  def _render_device_card(self, rect: rl.Rectangle, dev: BTDevice, state: BTState) -> None:
    bg_color = rl.Color(69, 96, 230, 40) if dev.paired else rl.Color(40, 40, 40, 255)
    rl.draw_rectangle_rounded(rect, 0.2, 15, bg_color)

    text_x = rect.x + self._padding
    name_size = measure_text_cached(gui_app.font(), dev.name or dev.address, 55)
    rl.draw_text_ex(gui_app.font(), dev.name or dev.address, rl.Vector2(text_x, rect.y + 15), 55, 0, rl.WHITE)

    status_parts = [dev.address]
    if dev.connected:
      status_parts.append(tr("Connected"))
    elif dev.paired:
      status_parts.append(tr("Paired"))
    if dev.battery is not None:
      status_parts.append(f"{tr('Battery')} {dev.battery}%")
    status_str = ' · '.join(status_parts)
    rl.draw_text_ex(gui_app.font(), status_str, rl.Vector2(text_x, rect.y + 80), 38, 0, rl.Color(160, 160, 160, 255))

    # RSSI
    if dev.rssi is not None:
      rssi_str = f"{dev.rssi} dBm"
      rssi_w = measure_text_cached(gui_app.font(), rssi_str, 34)
      rl.draw_text_ex(gui_app.font(), rssi_str, rl.Vector2(rect.x + rect.width - self._padding - rssi_w, rect.y + 22),
                      34, 0, rl.Color(120, 180, 255, 255))

    if dev.address in state.config_devices:
      cfg = state.config_devices[dev.address]
      mapping_status = tr("Mapping on") if cfg.get('enabled') else tr("Mapping off")
      if dev.grabbed:
        mapping_status += ' · ' + tr("Receiving input")
      rl.draw_text_ex(gui_app.font(), mapping_status, rl.Vector2(text_x, rect.y + 120), 38, 0, rl.Color(120, 200, 120, 255))

    btn_x = rect.x + rect.width - 420
    btn_y = rect.y + (self._item_height - self._btn_height) // 2
    rendered: set[str] = set()

    mouse_pos = rl.get_mouse_position()
    clicked = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)

    if not dev.paired:
      pair_rect = rl.Rectangle(btn_x + 180, btn_y, 200, self._btn_height)
      self._connect_btn.set_text(tr("Pair"))
      self._connect_btn.set_rect(pair_rect)
      self._connect_btn.render()
      if clicked and rl.check_collision_point_rec(mouse_pos, pair_rect):
        self._on_device_action(dev, 'pair')
    else:
      conn_rect = rl.Rectangle(btn_x, btn_y, 160, self._btn_height)
      self._connect_btn.set_text(tr("Disconnect") if dev.connected else tr("Connect"))
      self._connect_btn.set_rect(conn_rect)
      self._connect_btn.render()
      if clicked and rl.check_collision_point_rec(mouse_pos, conn_rect):
        self._on_device_action(dev, 'connect' if not dev.connected else 'disconnect')

      forget_rect = rl.Rectangle(btn_x + 170, btn_y, 120, self._btn_height)
      self._forget_btn.set_rect(forget_rect)
      self._forget_btn.render()
      if clicked and rl.check_collision_point_rec(mouse_pos, forget_rect):
        self._on_device_action(dev, 'forget')

      edit_rect = rl.Rectangle(btn_x + 300, btn_y, 100, self._btn_height)
      self._edit_btn.set_rect(edit_rect)
      self._edit_btn.render()
      if clicked and rl.check_collision_point_rec(mouse_pos, edit_rect):
        self._on_edit_device(dev)

  def _render_editor(self, rect: rl.Rectangle, state: BTState) -> None:
    if self._draft is None:
      return

    y = rect.y + 20
    name = self._draft.name or self._selected_address or ''
    gui_label(rl.Rectangle(rect.x, y, rect.width, 70), name, font_size=55, alignment=TextAlignment.CENTER)
    y += 90

    self._back_btn.set_rect(rl.Rectangle(rect.x + self._padding, y, 200, 70))
    self._back_btn.render()
    y += 100

    rl.draw_text_ex(gui_app.font(), tr("Profile"), rl.Vector2(rect.x + self._padding, y + 5), 45, 0, rl.Color(200, 200, 200, 255))
    profile_h = 70
    profile_rect = rl.Rectangle(rect.x + 220, y, 380, profile_h)
    rl.draw_rectangle_rounded(profile_rect, 0.3, 10, rl.Color(60, 60, 60, 255))
    profile_text = self._draft.profile
    rl.draw_text_ex(gui_app.font(), profile_text, rl.Vector2(profile_rect.x + 15, profile_rect.y + 15), 45, 0, rl.WHITE)
    y += profile_h + 30

    rl.draw_text_ex(gui_app.font(), tr("Use Carrot mapping"), rl.Vector2(rect.x + self._padding, y + 5), 45, 0, rl.Color(200, 200, 200, 255))
    toggle_x = rect.x + rect.width - 200
    toggle_rect = rl.Rectangle(toggle_x, y, 160, 60)
    toggle_on = self._draft.enabled
    bg = rl.Color(70, 91, 234, 255) if toggle_on else rl.Color(80, 80, 80, 255)
    rl.draw_rectangle_rounded(toggle_rect, 0.5, 10, bg)
    label = tr("ON") if toggle_on else tr("OFF")
    rl.draw_text_ex(gui_app.font(), label, rl.Vector2(toggle_rect.x + 55, toggle_rect.y + 10), 40, 0, rl.WHITE)
    if rl.check_collision_point_rec(rl.get_mouse_position(), toggle_rect) and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
      self._draft.enabled = not self._draft.enabled
      self._dirty = True
    y += 90

    rl.draw_text_ex(gui_app.font(), tr("Button Mapping"), rl.Vector2(rect.x + self._padding, y), 50, 0, rl.WHITE)
    y += 60

    col_x = rect.x + 180
    for gesture in GESTURES:
      rl.draw_text_ex(gui_app.font(), tr(GESTURE_LABELS.get(gesture, gesture)), rl.Vector2(col_x, y), 38, 0, rl.Color(150, 150, 150, 255))
      col_x += self._gesture_col_width
    y += 50

    for btn_name in MAPPING_BUTTONS:
      rl.draw_text_ex(gui_app.font(), tr(btn_name), rl.Vector2(rect.x + self._padding, y + 10), 45, 0, rl.WHITE)
      col_x = rect.x + 180
      for gesture in GESTURES:
        token = f'{btn_name}_{gesture}'
        action = self._draft.mapping.get(token, 'none')
        btn = self._gesture_btns[btn_name][gesture]
        btn.set_text(self._action_label(action))
        btn.set_rect(rl.Rectangle(col_x, y, self._gesture_col_width - 10, self._mapping_row_height))
        btn.render()
        col_x += self._gesture_col_width
      y += self._mapping_row_height + 15

    y += 10
    btn_y = y
    gap = 20
    btn_w = (rect.width - self._padding * 2 - gap * 3) // 4
    x = rect.x + self._padding
    self._save_btn.set_rect(rl.Rectangle(x, btn_y, btn_w, 80))
    self._save_btn.render()
    x += btn_w + gap

    is_learning = state.learning_addr == self._selected_address
    if is_learning:
      self._stop_btn.set_rect(rl.Rectangle(x, btn_y, btn_w, 80))
      self._stop_btn.render()
    else:
      self._test_btn.set_rect(rl.Rectangle(x, btn_y, btn_w, 80))
      self._test_btn.render()
    x += btn_w + gap

    rl.draw_text_ex(gui_app.font(), self._last_event_text[:60], rl.Vector2(x, btn_y + 20), 38, 0, rl.Color(150, 255, 150, 255))

  def _render_advanced(self, rect: rl.Rectangle, state: BTState) -> None:
    mouse_pos = rl.get_mouse_position()
    clicked = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)
    y = rect.y + 20

    self._back_btn.set_rect(rl.Rectangle(rect.x + self._padding, y, 200, 70))
    self._back_btn.render()
    y += 100

    can_act = state.runtime.stationary and state.available

    # Bluetooth master toggle
    gui_label(rl.Rectangle(rect.x + self._padding, y, 400, 60), tr("Bluetooth"), font_size=46, alignment=TextAlignment.LEFT)
    self._radio_toggle.set_rect(rl.Rectangle(rect.x + rect.width - 180, y, 160, 70))
    self._radio_toggle.set_enabled(can_act)
    if state.radio_enabled != self._last_radio_state:
      self._last_radio_state = state.radio_enabled
      self._radio_toggle.set_state(state.radio_enabled)
    self._radio_toggle.render()
    gui_label(rl.Rectangle(rect.x + self._padding, y + 55, rect.width - self._padding * 2, 40),
              tr("Turn Bluetooth radio on or off."), font_size=32, alignment=TextAlignment.LEFT, color=rl.Color(170, 170, 170, 255))
    y += 110

    # Discoverable toggle
    gui_label(rl.Rectangle(rect.x + self._padding, y, 400, 60), tr("Discoverable"), font_size=46, alignment=TextAlignment.LEFT)
    self._discoverable_toggle.set_rect(rl.Rectangle(rect.x + rect.width - 180, y, 160, 70))
    self._discoverable_toggle.set_enabled(can_act and state.radio_enabled)
    if state.discoverable != self._last_discoverable_state:
      self._last_discoverable_state = state.discoverable
      self._discoverable_toggle.set_state(state.discoverable)
    self._discoverable_toggle.render()
    gui_label(rl.Rectangle(rect.x + self._padding, y + 55, rect.width - self._padding * 2, 40),
              tr("Allow other devices to find this device."), font_size=32, alignment=TextAlignment.LEFT, color=rl.Color(170, 170, 170, 255))
    y += 110

    # Device name
    gui_label(rl.Rectangle(rect.x + self._padding, y, 400, 60), tr("Device name"), font_size=46, alignment=TextAlignment.LEFT)
    input_w = rect.width - self._padding * 2 - 180
    name_rect = rl.Rectangle(rect.x + self._padding, y + 60, input_w, 70)
    rl.draw_rectangle_rounded(name_rect, 0.2, 10, rl.Color(50, 50, 50, 255))
    rl.draw_text_ex(gui_app.font(), self._name_input, rl.Vector2(name_rect.x + 15, name_rect.y + 15), 42, 0, rl.WHITE)
    self._save_name_btn.set_rect(rl.Rectangle(rect.x + rect.width - self._padding - 160, y + 60, 160, 70))
    self._save_name_btn.set_enabled(can_act)
    self._save_name_btn.render()
    gui_label(rl.Rectangle(rect.x + self._padding, y + 140, rect.width - self._padding * 2, 40),
              tr("Name shown to other Bluetooth devices."), font_size=32, alignment=TextAlignment.LEFT, color=rl.Color(170, 170, 170, 255))
    y += 190

    # Paired devices
    gui_label(rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, 50),
              tr("Paired devices"), font_size=44, alignment=TextAlignment.LEFT)
    y += 60

    paired = [d for d in state.devices if d.paired]
    if not paired:
      gui_label(rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, 60),
                tr("No paired devices"), font_size=38, alignment=TextAlignment.LEFT, color=rl.Color(150, 150, 150, 255))
      y += 70
    else:
      for dev in paired:
        item_rect = rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, 100)
        rl.draw_rectangle_rounded(item_rect, 0.2, 10, rl.Color(45, 45, 45, 255))
        rl.draw_text_ex(gui_app.font(), dev.name or dev.address, rl.Vector2(item_rect.x + 20, item_rect.y + 15), 42, 0, rl.WHITE)
        rl.draw_text_ex(gui_app.font(), dev.address, rl.Vector2(item_rect.x + 20, item_rect.y + 55), 32, 0, rl.Color(150, 150, 150, 255))
        forget_rect = rl.Rectangle(item_rect.x + item_rect.width - 140, item_rect.y + 15, 120, 70)
        self._forget_btn.set_rect(forget_rect)
        self._forget_btn.render()
        if clicked and rl.check_collision_point_rec(mouse_pos, forget_rect):
          self._http_async('forget', {'address': dev.address})
        y += 115

    # Reset section
    y += 30
    gui_label(rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, 50),
              tr("Reset Bluetooth"), font_size=44, alignment=TextAlignment.LEFT)
    y += 60
    gui_label(rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, 60),
              tr("Remove all pairings and restart the Bluetooth service."), font_size=34, alignment=TextAlignment.LEFT, color=rl.Color(170, 170, 170, 255))
    y += 80
    self._reset_btn.set_rect(rl.Rectangle(rect.x + self._padding, y, 360, 90))
    self._reset_btn.set_enabled(can_act)
    self._reset_btn.render()

  def _action_label(self, action: str) -> str:
    labels = {
      'none': tr('None'),
      'accelCruise': tr('Cruise +'),
      'decelCruise': tr('Cruise −'),
      'accelCruiseLong': tr('Cruise + Long'),
      'decelCruiseLong': tr('Cruise − Long'),
      'gapAdjustCruise': tr('Gap'),
      'lfaButton': tr('LFA'),
      'lfaButtonLong': tr('LFA Long'),
      'cancel': tr('Cancel'),
      'cancelLong': tr('Cancel Long'),
      'laneLeft': tr('Lane Left'),
      'laneRight': tr('Lane Right'),
      'paddleDecel': tr('Paddle −'),
      'carrotCruise': tr('CarrotCruise'),
    }
    return labels.get(action, action)

  def _on_radio_toggled(self, enabled: bool) -> None:
    if enabled == self._state.radio_enabled:
      return
    self._http_async('radio', {'enabled': enabled})

  def _on_discoverable_toggled(self, enabled: bool) -> None:
    self._http_async('discoverable', {'enabled': enabled})

  def _on_scan_clicked(self) -> None:
    with self._state_lock:
      discovering = self._state.discovering
    operation = 'cancel' if discovering else 'scan'
    self._http_async(operation)

  def _on_advanced_clicked(self) -> None:
    with self._state_lock:
      name = self._state.local_name
    self._name_input = name
    self._panel = BTPanel.ADVANCED

  def _on_install_clicked(self) -> None:
    if self._installing:
      return
    self._installing = True

    def do():
      try:
        result = _http_post('install')
        if result.get('error') and not result.get('ok'):
          with self._state_lock:
            self._error_text = str(result.get('error', 'Unknown error'))
      except Exception as e:
        with self._state_lock:
          self._error_text = str(e)
      finally:
        self._installing = False
        self._fetch_state()
    threading.Thread(target=do, daemon=True).start()

  def _on_enable_service_clicked(self) -> None:
    self._http_async('service', {'start': True})

  def _on_retry_clicked(self) -> None:
    self._fetch_state()

  def _on_connect_clicked(self) -> None:
    pass

  def _on_forget_clicked(self) -> None:
    pass

  def _on_edit_clicked(self) -> None:
    pass

  def _on_device_action(self, dev: BTDevice, operation: str) -> None:
    if operation == 'forget':
      self._http_async('forget', {'address': dev.address})
      if self._selected_address == dev.address:
        self._selected_address = None
        self._draft = None
        self._panel = BTPanel.DEVICES
    else:
      self._http_async(operation, {'address': dev.address})

  def _on_edit_device(self, dev: BTDevice) -> None:
    self._selected_address = dev.address
    cfg = self._state.config_devices.get(dev.address)
    if cfg:
      self._draft = BTDevice(
        address=dev.address,
        name=dev.name,
        paired=dev.paired,
        connected=dev.connected,
        profile=cfg.get('profile', 'generic'),
        mapping=cfg.get('mapping', {}),
        enabled=cfg.get('enabled', False),
      )
    else:
      is_yiser = 'yiser-j6' in (dev.name or '').lower()
      self._draft = BTDevice(
        address=dev.address,
        name=dev.name,
        paired=dev.paired,
        connected=dev.connected,
        profile='yiser-j6' if is_yiser else 'generic',
        mapping={**BT_DEFAULTS} if is_yiser else {},
        enabled=False,
      )
    self._dirty = False
    self._panel = BTPanel.EDITOR
    self._last_event_text = ''

  def _on_back_clicked(self) -> None:
    self._panel = BTPanel.DEVICES
    self._draft = None
    self._dirty = False

  def _on_save_clicked(self) -> None:
    if self._draft is None or self._selected_address is None:
      return
    self._http_async('device-config', {
      'address': self._selected_address,
      'device': {
        'name': self._draft.name,
        'profile': self._draft.profile,
        'mapping': self._draft.mapping,
        'enabled': self._draft.enabled,
      }
    })
    self._dirty = False

  def _on_save_name_clicked(self) -> None:
    name = self._name_input.strip()
    if not name:
      return
    self._http_async('name', {'name': name})

  def _on_reset_clicked(self) -> None:
    def do():
      try:
        for dev in [d for d in self._state.devices if d.paired]:
          _http_post('forget', {'address': dev.address})
        _http_post('service', {'start': False})
        _http_post('service', {'start': True})
      except Exception as e:
        with self._state_lock:
          self._error_text = str(e)
      self._fetch_state()
    threading.Thread(target=do, daemon=True).start()

  def _on_test_clicked(self) -> None:
    if self._draft is None or self._selected_address is None:
      return
    self._http_async('learn', {'address': self._selected_address, 'enabled': True})

  def _on_stop_clicked(self) -> None:
    self._http_async('learn', {'address': self._selected_address, 'enabled': False})

  def _on_mapping_clicked(self, token: str) -> None:
    if self._draft is None:
      return
    current = self._draft.mapping.get(token, 'none')
    idx = ACTIONS.index(current) if current in ACTIONS else 0
    next_idx = (idx + 1) % len(ACTIONS)
    self._draft.mapping[token] = ACTIONS[next_idx]
    self._dirty = True

  def _http_async(self, operation: str, data: dict | None = None) -> None:
    def do():
      try:
        result = _http_post(operation, data)
        if result.get('error') and not result.get('ok'):
          with self._state_lock:
            self._error_text = str(result.get('error', 'Unknown error'))
      except Exception as e:
        with self._state_lock:
          self._error_text = str(e)
      self._fetch_state()
    threading.Thread(target=do, daemon=True).start()
