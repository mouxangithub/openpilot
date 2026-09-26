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
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.keyboard import Keyboard
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
  has_uart: bool = False
  has_btpower: bool = False
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

    # Must be initialized here (not only in show_event) because _fetch_state()
    # checks self._running at the top of its body, before any rendering happens.
    # If render() is called before show_event() (e.g. a timing edge case in the
    # settings panel manager), an AttributeError: "_running" would crash the UI.
    self._running = False
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

    # Scanning is only "active" for the UI while we expect it to be. This
    # prevents the status line from getting stuck on "Scanning..." when BlueZ
    # leaves the adapter discovering flag set after a timeout/edge case.
    self._scanning_until = 0.0

    # Pairing prompt handling: remember dismissed prompt ids so we don't
    # repeatedly push dialog widgets for the same prompt.
    self._dismissed_prompt_ids: set[str] = set()
    self._keyboard = Keyboard(max_text_size=16, min_text_size=1)

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
    self._name_action_btn = Button(tr("Edit"), self._on_name_action_clicked, button_style=ButtonStyle.NORMAL, font_size=40, border_radius=15)
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
    self._scanning_until = 0.0
    self._dismissed_prompt_ids.clear()
    self._fetch_state()

  def hide_event(self) -> None:
    self._running = False

  def _is_scanning_active(self, state: BTState) -> bool:
    """True only while we believe a scan is still in progress."""
    return state.discovering and time.monotonic() < self._scanning_until

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
    if not state.has_uart and not state.has_btpower:
      return tr("Bluetooth radio hardware not detected")
    if not state.has_uart:
      return tr("Bluetooth UART not exposed by this AGNOS kernel")
    if not state.has_btpower:
      return tr("Bluetooth power node not detected")
    if not state.available:
      return tr("No Bluetooth adapter found")
    if not state.runtime.stationary:
      return tr("Requires stationary & disengaged state")
    if self._is_scanning_active(state):
      return tr("Scanning...")
    if not state.radio_enabled:
      return tr("Bluetooth disabled")
    return tr("Ready")

  def _parse_state(self, data: dict) -> BTState:
    state = BTState()
    state.has_bluez = data.get('hasBluez', False)
    state.service_running = data.get('serviceRunning', False)
    state.available = data.get('available', False)
    state.has_uart = data.get('hasUart', False)
    state.has_btpower = data.get('hasBtpower', False)
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
      self._handle_prompt(state)

    self._maybe_auto_scan(state)

  def _maybe_auto_scan(self, state: BTState) -> None:
    if self._auto_scanned:
      return
    if not state.available or not state.radio_enabled or not state.runtime.stationary:
      return
    self._auto_scanned = True
    self._scanning_until = time.monotonic() + 32
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

    # Required hardware nodes missing (e.g. this device/AGNOS variant has no ttyHS1)
    if not state.has_uart or not state.has_btpower:
      if not state.has_uart and not state.has_btpower:
        title = tr("Bluetooth radio hardware not detected")
        desc = tr("This device or AGNOS build lacks the required Bluetooth UART and power nodes.")
      elif not state.has_uart:
        title = tr("Bluetooth UART not available")
        desc = tr("This AGNOS kernel does not expose /dev/ttyHS1. Reflash to a Bluetooth-capable AGNOS build.")
      else:
        title = tr("Bluetooth power node not detected")
        desc = tr("This device or AGNOS build lacks /dev/btpower.")
      self._render_empty_state(rect, icon='📵', title=title, desc=desc, btn=self._retry_btn)
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
    discovering = self._is_scanning_active(state)

    # Scan / Stop button
    self._scan_btn.set_text(tr("Stop") if discovering else tr("Scan"))
    self._scan_btn.set_enabled(can_act and (discovering or state.radio_enabled))
    self._scan_btn.set_rect(rl.Rectangle(rect.x, y, 400, top_h))
    self._scan_btn.render()

    # Advanced button
    self._adv_btn.set_enabled(can_act)
    self._adv_btn.set_rect(rl.Rectangle(rect.x + rect.width - 320, y, 320, top_h))
    self._adv_btn.render()

    y += top_h + 40

    # Status
    status_color = rl.Color(255, 220, 80, 255) if discovering else rl.WHITE
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
    rl.draw_rectangle_rounded(rect, 0.15, 12, bg_color)

    mouse_pos = rl.get_mouse_position()
    clicked = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)
    btn_gap = 16

    # Action buttons on the far right. Compute widths first.
    if not dev.paired:
      pair_w = max(160, int(measure_text_cached(gui_app.font(), tr("Pair"), 38).x + 60))
      action_btns = [
        (self._connect_btn, pair_w, tr("Pair"), ButtonStyle.PRIMARY, lambda: self._confirm_pair(dev)),
      ]
    else:
      conn_label = tr("Disconnect") if dev.connected else tr("Connect")
      conn_w = max(160, int(measure_text_cached(gui_app.font(), conn_label, 38).x + 60))
      edit_w = max(120, int(measure_text_cached(gui_app.font(), tr("Edit"), 38).x + 50))
      forget_w = max(120, int(measure_text_cached(gui_app.font(), tr("Forget"), 38).x + 50))
      action_btns = [
        (self._connect_btn, conn_w, conn_label,
         ButtonStyle.NORMAL if dev.connected else ButtonStyle.PRIMARY,
         lambda: self._on_device_action(dev, 'connect' if not dev.connected else 'disconnect')),
        (self._edit_btn, edit_w, tr("Edit"), ButtonStyle.NORMAL, lambda: self._on_edit_device(dev)),
        (self._forget_btn, forget_w, tr("Forget"), ButtonStyle.DANGER, lambda: self._confirm_forget(dev)),
      ]

    total_action_w = sum(w for _, w, _, _, _ in action_btns) + btn_gap * (len(action_btns) - 1)
    action_right = rect.x + rect.width - self._padding

    # RSSI sits immediately to the left of the action buttons.
    rssi_str = ''
    rssi_w = 0
    if dev.rssi is not None:
      rssi_str = f"{dev.rssi} dBm"
      rssi_size = measure_text_cached(gui_app.font(), rssi_str, 34)
      rssi_w = rssi_size.x
    rssi_col_w = max(120, rssi_w + 20)
    rssi_right = action_right - total_action_w - self._padding

    # Main text area is everything left of the RSSI column; scissor it so long
    # names never draw over the signal/action area.
    main_right = rssi_right - rssi_col_w - self._padding
    text_x = rect.x + self._padding
    rl.begin_scissor_mode(int(rect.x), int(rect.y), int(max(0, main_right - rect.x)), int(rect.height))

    rl.draw_text_ex(gui_app.font(), dev.name or dev.address, rl.Vector2(text_x, rect.y + 18), 55, 0, rl.WHITE)

    status_parts = [dev.address]
    if dev.connected:
      status_parts.append(tr("Connected"))
    elif dev.paired:
      status_parts.append(tr("Paired"))
    if dev.battery is not None:
      status_parts.append(f"{tr('Battery')} {dev.battery}%")
    status_str = ' · '.join(status_parts)
    rl.draw_text_ex(gui_app.font(), status_str, rl.Vector2(text_x, rect.y + 78), 38, 0, rl.Color(160, 160, 160, 255))

    if dev.address in state.config_devices:
      cfg = state.config_devices[dev.address]
      mapping_status = tr("Mapping on") if cfg.get('enabled') else tr("Mapping off")
      if dev.grabbed:
        mapping_status += ' · ' + tr("Receiving input")
      rl.draw_text_ex(gui_app.font(), mapping_status, rl.Vector2(text_x, rect.y + 118), 38, 0, rl.Color(120, 200, 120, 255))

    rl.end_scissor_mode()

    # Draw RSSI
    if dev.rssi is not None:
      rssi_y = rect.y + (self._item_height - 34) / 2
      rl.draw_text_ex(gui_app.font(), rssi_str, rl.Vector2(rssi_right - rssi_w, rssi_y),
                      34, 0, rl.Color(120, 180, 255, 255))

    # Draw action buttons and handle clicks
    x = action_right - total_action_w
    for btn, w, label, style, cb in action_btns:
      btn.set_text(label)
      btn.set_button_style(style)
      btn.set_enabled(True)
      btn.set_touch_valid_callback(lambda: self._scroll_panel.is_touch_valid())
      btn_rect = rl.Rectangle(x, rect.y + (self._item_height - self._btn_height) // 2, w, self._btn_height)
      btn.set_rect(btn_rect)
      btn.render()
      if clicked and rl.check_collision_point_rec(mouse_pos, btn_rect):
        cb()
      x += w + btn_gap

  def _confirm_pair(self, dev: BTDevice) -> None:
    def on_result(result: DialogResult):
      if result == DialogResult.CONFIRM:
        self._scanning_until = time.monotonic() + 32
        self._http_async('pair', {'address': dev.address})
    dialog = ConfirmDialog("", tr("Pair"), tr("Cancel"), callback=on_result)
    dialog.set_text(tr('Pair with "{}"?').format(dev.name or dev.address))
    gui_app.push_widget(dialog)

  def _confirm_forget(self, dev: BTDevice) -> None:
    def on_result(result: DialogResult):
      if result == DialogResult.CONFIRM:
        self._on_device_action(dev, 'forget')
    dialog = ConfirmDialog("", tr("Forget"), tr("Cancel"), callback=on_result)
    dialog.set_text(tr('Forget "{}"?').format(dev.name or dev.address))
    gui_app.push_widget(dialog)

  def _handle_prompt(self, state: BTState) -> None:
    prompt = state.prompt
    if not prompt:
      self._dismissed_prompt_ids.clear()
      return
    pid = prompt.get('id')
    if not pid or pid in self._dismissed_prompt_ids:
      return
    self._dismissed_prompt_ids.add(pid)

    kind = prompt.get('kind', '')
    value = prompt.get('value', '')

    if kind in ('DisplayPinCode', 'DisplayPasskey'):
      dialog = ConfirmDialog("", tr("OK"), cancel_text="", callback=None)
      dialog.set_text(tr("Pairing code: {}").format(value))
      gui_app.push_widget(dialog)
      return

    if kind in ('RequestConfirmation', 'RequestAuthorization', 'AuthorizeService'):
      def on_confirm(result: DialogResult):
        self._http_async('answer', {'id': pid, 'value': result == DialogResult.CONFIRM})
      dialog = ConfirmDialog("", tr("Confirm"), tr("Cancel"), callback=on_confirm)
      dialog.set_text(tr("Confirm pairing with \"{}\"?").format(value))
      gui_app.push_widget(dialog)
      return

    if kind == 'RequestPinCode':
      def on_pin(result: DialogResult):
        self._http_async('answer', {'id': pid, 'value': False if result != DialogResult.CONFIRM else self._keyboard.text})
      self._keyboard.reset(min_text_size=1)
      self._keyboard.set_title(tr("Enter PIN"), tr("for \"{}\"").format(value) if value else "")
      self._keyboard.set_text("")
      self._keyboard.set_callback(on_pin)
      gui_app.push_widget(self._keyboard)
      return

    if kind == 'RequestPasskey':
      def on_passkey(result: DialogResult):
        self._http_async('answer', {'id': pid, 'value': False if result != DialogResult.CONFIRM else self._keyboard.text})
      self._keyboard.reset(min_text_size=1)
      self._keyboard.set_title(tr("Enter passkey"), tr("for \"{}\"").format(value) if value else "")
      self._keyboard.set_text("")
      self._keyboard.set_callback(on_passkey)
      gui_app.push_widget(self._keyboard)

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
    y = rect.y + 20

    self._back_btn.set_rect(rl.Rectangle(rect.x + self._padding, y, 200, 70))
    self._back_btn.render()
    y += 100

    can_act = state.runtime.stationary and state.available
    row_h = 120
    gap = 24

    # Bluetooth master toggle
    y = self._render_advanced_row(
      rect, y, row_h,
      tr("Bluetooth"), tr("Turn Bluetooth radio on or off."),
      self._radio_toggle, state.radio_enabled, can_act, self._on_radio_toggled,
      self._last_radio_state,
    )
    self._last_radio_state = state.radio_enabled
    y += gap

    # Discoverable toggle
    y = self._render_advanced_row(
      rect, y, row_h,
      tr("Discoverable"), tr("Allow other devices to find this device."),
      self._discoverable_toggle, state.discoverable, can_act and state.radio_enabled,
      self._on_discoverable_toggled, self._last_discoverable_state,
    )
    self._last_discoverable_state = state.discoverable
    y += gap

    # Device name
    y = self._render_name_row(rect, y, state, can_act)
    y += gap + 20

    # Reset section
    y += 30
    y = self._render_reset_section(rect, y, state, can_act)

  def _render_advanced_row(self, rect: rl.Rectangle, y: float, row_h: float,
                           title: str, desc: str, toggle: Toggle, value: bool,
                           enabled: bool, callback: Callable[[bool], None],
                           last_state: bool) -> float:
    toggle_w, toggle_h = 160, 70
    toggle_rect = rl.Rectangle(rect.x + rect.width - self._padding - toggle_w,
                               y + (row_h - toggle_h) / 2, toggle_w, toggle_h)

    title_rect = rl.Rectangle(rect.x + self._padding, y,
                              rect.width - self._padding * 2 - toggle_w - 20, 50)
    gui_label(title_rect, title, font_size=46, alignment=TextAlignment.LEFT)

    desc_rect = rl.Rectangle(rect.x + self._padding, y + 48,
                             rect.width - self._padding * 2 - toggle_w - 20, 40)
    gui_label(desc_rect, desc, font_size=32, alignment=TextAlignment.LEFT,
              color=rl.Color(170, 170, 170, 255))

    if value != last_state:
      toggle.set_state(value)
    toggle.set_rect(toggle_rect)
    toggle.set_enabled(enabled)
    toggle.render()
    return y + row_h

  def _render_name_row(self, rect: rl.Rectangle, y: float, state: BTState, can_act: bool) -> float:
    row_h = 120
    btn_w = max(160, int(measure_text_cached(gui_app.font(), tr("Save"), 40).x + 50),
                int(measure_text_cached(gui_app.font(), tr("Edit"), 40).x + 50))
    gap = 20
    control_w = btn_w + gap
    control_x = rect.x + rect.width - self._padding - btn_w
    control_y = y + (row_h - 70) / 2

    title_rect = rl.Rectangle(rect.x + self._padding, y,
                              rect.width - self._padding * 2 - control_w - 20, 50)
    gui_label(title_rect, tr("Device name"), font_size=46, alignment=TextAlignment.LEFT)
    desc_rect = rl.Rectangle(rect.x + self._padding, y + 48,
                             rect.width - self._padding * 2 - control_w - 20, 40)
    gui_label(desc_rect, tr("Name shown to other Bluetooth devices."), font_size=32,
              alignment=TextAlignment.LEFT, color=rl.Color(170, 170, 170, 255))

    # Name value sits to the left of the single action button.
    name_max_w = control_x - gap - (rect.x + self._padding)
    name_rect = rl.Rectangle(rect.x + self._padding, control_y, name_max_w, 70)
    rl.draw_rectangle_rounded(name_rect, 0.2, 10, rl.Color(50, 50, 50, 255))

    name_text = self._name_input
    name_size = measure_text_cached(gui_app.font(), name_text, 40)
    text_x = name_rect.x + 15
    text_y = name_rect.y + (70 - name_size.y) / 2
    if name_size.x > name_max_w - 30:
      rl.begin_scissor_mode(int(name_rect.x), int(name_rect.y), int(name_max_w), int(70))
      rl.draw_text_ex(gui_app.font(), name_text, rl.Vector2(text_x, text_y), 40, 0, rl.WHITE)
      rl.end_scissor_mode()
    else:
      rl.draw_text_ex(gui_app.font(), name_text, rl.Vector2(text_x, text_y), 40, 0, rl.WHITE)

    # Single button toggles between Edit (name matches saved) and Save (name modified).
    has_changes = self._name_input != state.local_name
    btn_label = tr("Save") if has_changes else tr("Edit")
    btn_style = ButtonStyle.PRIMARY if has_changes else ButtonStyle.NORMAL
    self._name_action_btn.set_text(btn_label)
    self._name_action_btn.set_button_style(btn_style)
    self._name_action_btn.set_rect(rl.Rectangle(control_x, control_y, btn_w, 70))
    self._name_action_btn.set_enabled(can_act)
    self._name_action_btn.render()

    return y + row_h

  def _render_reset_section(self, rect: rl.Rectangle, y: float, state: BTState, can_act: bool) -> float:
    title_h = 60
    gui_label(rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, title_h),
              tr("Reset Bluetooth"), font_size=44, alignment=TextAlignment.LEFT)
    y += title_h + 10

    gui_label(rl.Rectangle(rect.x + self._padding, y, rect.width - self._padding * 2, 60),
              tr("Remove all pairings and restart the Bluetooth service."), font_size=34,
              alignment=TextAlignment.LEFT, color=rl.Color(170, 170, 170, 255))
    y += 80

    self._reset_btn.set_rect(rl.Rectangle(rect.x + self._padding, y, 360, 90))
    self._reset_btn.set_enabled(can_act)
    self._reset_btn.render()
    return y + 110

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
      discovering = self._is_scanning_active(self._state)
    if discovering:
      self._scanning_until = 0.0
      self._http_async('cancel')
    else:
      self._scanning_until = time.monotonic() + 32
      self._http_async('scan')

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

  def _on_name_action_clicked(self) -> None:
    with self._state_lock:
      saved_name = self._state.local_name
    if self._name_input != saved_name:
      name = self._name_input.strip()
      if name:
        self._http_async('name', {'name': name})
      return

    def update_name(result: DialogResult):
      if result == DialogResult.CONFIRM:
        self._name_input = self._keyboard.text.strip() or self._name_input
    self._keyboard.reset(min_text_size=1)
    self._keyboard.set_title(tr("Device name"), "")
    self._keyboard.set_text(self._name_input)
    self._keyboard.set_callback(update_name)
    gui_app.push_widget(self._keyboard)

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
