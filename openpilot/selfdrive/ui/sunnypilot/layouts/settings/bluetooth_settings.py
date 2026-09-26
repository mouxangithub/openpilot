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
    with urllib.request.urlopen(req, timeout=10) as resp:
      return json.loads(resp.read())
  except Exception as e:
    return {'error': str(e)}


@dataclass
class BTDevice:
  address: str = ''
  name: str = ''
  paired: bool = False
  connected: bool = False
  battery: int | None = None
  enabled: bool = False
  grabbed: bool = False
  profile: str = 'generic'
  mapping: dict = field(default_factory=dict)


class BTPanel(IntEnum):
  DEVICES = 0
  EDITOR = 1


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
  available: bool = False
  radio_enabled: bool = False
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
  Integrates into the Network settings section.
  """

  def __init__(self):
    super().__init__()

    self._state = BTState()
    self._selected_address: str | None = None
    self._draft: BTDevice | None = None
    self._dirty = False
    self._panel = BTPanel.DEVICES
    self._last_fetch = 0.0
    self._fetch_interval = 1.0  # seconds between polls

    # UI dimensions
    self._item_height = 160
    self._btn_height = 80
    self._label_height = 60
    self._mapping_row_height = 80
    self._gesture_col_width = 220
    self._padding = 30
    self._sidebar_width = 900
    self._content_width = 0  # computed from rect

    # Scroll panel for device list
    self._scroll_panel = GuiScrollPanel()

    # Status label
    self._status_text = ''

    # Error label
    self._error_text = ''

    # Poll timer
    self._poll_thread: threading.Thread | None = None
    self._running = True

    # Buttons / toggles
    self._scan_btn = Button(tr("Scan"), self._on_scan_clicked, button_style=ButtonStyle.NORMAL, font_size=60, border_radius=30)
    self._radio_toggle = Toggle(self._state.radio_enabled, self._on_radio_toggled)
    self._save_btn = Button(tr("Save"), self._on_save_clicked, button_style=ButtonStyle.PRIMARY, font_size=45, border_radius=15)
    self._test_btn = Button(tr("Test / Learn"), self._on_test_clicked, button_style=ButtonStyle.NORMAL, font_size=45, border_radius=15)
    self._stop_btn = Button(tr("Stop Test"), self._on_stop_clicked, button_style=ButtonStyle.DANGER, font_size=45, border_radius=15)
    self._back_btn = Button(tr("Back"), self._on_back_clicked, button_style=ButtonStyle.NORMAL, font_size=45, border_radius=15)
    self._connect_btn = Button('', self._on_connect_clicked, button_style=ButtonStyle.PRIMARY, font_size=40, border_radius=15)
    self._forget_btn = Button(tr("Forget"), self._on_forget_clicked, button_style=ButtonStyle.DANGER, font_size=40, border_radius=15)
    self._edit_btn = Button(tr("Edit"), self._on_edit_clicked, button_style=ButtonStyle.NORMAL, font_size=40, border_radius=15)

    # Track last fetched radio state so the toggle only animates on real changes
    self._last_radio_state = self._state.radio_enabled

    # Gesture buttons for mapping
    self._gesture_btns: dict[str, dict[str, Button]] = {}
    for btn_name in MAPPING_BUTTONS:
      self._gesture_btns[btn_name] = {}
      for gesture in GESTURES:
        token = f'{btn_name}_{gesture}'
        b = Button('', lambda _t=token: self._on_mapping_clicked(_t),
                   button_style=ButtonStyle.TRANSPARENT_WHITE_BORDER, font_size=35, border_radius=10)
        self._gesture_btns[btn_name][gesture] = b

    # Profile toggle
    self._profile_toggle: Widget | None = None
    self._enabled_toggle: Widget | None = None

    # Events display
    self._last_event_text = ''
    self._seen_event_ids: set = set()

  def show_event(self) -> None:
    self._running = True
    self._selected_address = None
    self._draft = None
    self._dirty = False
    self._panel = BTPanel.DEVICES
    self._fetch_state()

  def hide_event(self) -> None:
    self._running = False

  def _fetch_state(self) -> None:
    if not self._running:
      return
    try:
      data = _http_get(_api_path())
      self._state = self._parse_state(data)
      self._error_text = ''
      self._update_status_text()
    except Exception as e:
      self._error_text = str(e)
    self._last_fetch = time.monotonic()

  def _parse_state(self, data: dict) -> BTState:
    state = BTState()
    state.available = data.get('available', False)
    state.radio_enabled = data.get('radioEnabled', False)
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
        battery=d.get('battery'),
        enabled=cfg.get('enabled', False),
        grabbed=addr in state.runtime.grabbed,
        profile=cfg.get('profile', 'generic'),
        mapping=cfg.get('mapping', {}),
      )
      state.devices.append(dev)
    state.config_devices = data.get('config', {}).get('devices', {})

    state.prompt = data.get('prompt')

    # Check if discovering
    adapters = data.get('adapters', [])
    state.discovering = any(a.get('discovering', False) for a in adapters)

    return state

  def _update_status_text(self) -> None:
    if not self._state.available:
      self._status_text = tr("Bluetooth adapter unavailable")
    elif not self._state.runtime.stationary:
      self._status_text = tr("Requires stationary & disengaged state")
    elif self._state.discovering:
      self._status_text = tr("Scanning...")
    else:
      self._status_text = tr("Ready")

  def _render(self, rect: rl.Rectangle) -> None:
    self._content_width = rect.width

    # Poll state periodically
    now = time.monotonic()
    if now - self._last_fetch > self._fetch_interval:
      self._fetch_state()

    # Header
    content_top = self._render_header(rect)

    # Content
    if self._panel == BTPanel.DEVICES:
      self._render_devices(rect, content_top)
    else:
      self._render_editor(rect, content_top)

  def _render_header(self, rect: rl.Rectangle) -> float:
    """Render header and return y-coordinate where content should start."""
    y = rect.y

    # Top row: Scan/Stop (left) and Bluetooth radio toggle (right),
    # matching the Network panel header layout.
    top_y = y + 20
    top_h = 100

    can_act = self._state.runtime.stationary and self._state.available

    # Scan / Stop button
    self._scan_btn.set_text(tr("Stop") if self._state.discovering else tr("Scan"))
    self._scan_btn.set_enabled(can_act)
    self._scan_btn.set_rect(rl.Rectangle(rect.x, top_y, 400, top_h))
    self._scan_btn.render()

    # Bluetooth radio toggle
    toggle_x = rect.x + rect.width - 160
    self._radio_toggle.set_rect(rl.Rectangle(toggle_x, top_y, 160, 80))
    self._radio_toggle.set_enabled(can_act)
    if self._state.radio_enabled != self._last_radio_state:
      self._last_radio_state = self._state.radio_enabled
      self._radio_toggle.set_state(self._state.radio_enabled)
    self._radio_toggle.render()

    y += top_h + 40

    # Status
    status_color = rl.Color(200, 200, 0, 255) if 'Scanning' in self._status_text else rl.WHITE
    gui_label(rl.Rectangle(rect.x, y, rect.width, self._label_height), self._status_text, font_size=42, alignment=TextAlignment.CENTER,
              color=status_color)
    y += self._label_height

    # Error
    if self._error_text:
      gui_label(rl.Rectangle(rect.x, y, rect.width, self._label_height), self._error_text[:80], font_size=38, alignment=TextAlignment.CENTER,
                color=rl.Color(255, 80, 80, 255))
      y += self._label_height

    return y + 20

  def _render_devices(self, rect: rl.Rectangle, content_top: float) -> None:
    start_y = content_top

    if self._error_text and not self._state.devices:
      gui_label(rl.Rectangle(rect.x, start_y, rect.width, 100), tr("No devices found"), font_size=45, alignment=TextAlignment.CENTER)
      return

    # Device cards
    total_h = len(self._state.devices) * (self._item_height + 20)
    content_rect = rl.Rectangle(rect.x, rect.y, rect.width, total_h)
    scissor_rect = rl.Rectangle(rect.x, start_y, rect.width, rect.height - (start_y - rect.y))
    offset = self._scroll_panel.update(scissor_rect, content_rect)

    rl.begin_scissor_mode(int(scissor_rect.x), int(scissor_rect.y), int(scissor_rect.width), int(scissor_rect.height))
    for i, dev in enumerate(self._state.devices):
      y_offset = rect.y + i * (self._item_height + 20) + offset
      item_rect = rl.Rectangle(rect.x, y_offset, rect.width, self._item_height)
      if not rl.check_collision_recs(item_rect, scissor_rect):
        continue
      self._render_device_card(item_rect, dev)
    rl.end_scissor_mode()

  def _render_device_card(self, rect: rl.Rectangle, dev: BTDevice) -> None:
    bg_color = rl.Color(40, 40, 40, 255)
    rl.draw_rectangle_rounded(rect, 0.2, 15, bg_color)

    inner_x = rect.x + self._padding
    inner_w = rect.width - self._padding * 2
    text_x = inner_x

    # Device name
    name_size = measure_text_cached(gui_app.font(), dev.name or dev.address, 55)
    rl.draw_text_ex(gui_app.font(), dev.name or dev.address, rl.Vector2(text_x, rect.y + 15), 55, 0, rl.WHITE)

    # Address + status
    status_parts = [dev.address]
    if dev.connected:
      status_parts.append(tr("Connected"))
    elif dev.paired:
      status_parts.append(tr("Paired"))
    if dev.battery is not None:
      status_parts.append(f"Battery {dev.battery}%")
    status_str = ' · '.join(status_parts)
    rl.draw_text_ex(gui_app.font(), status_str, rl.Vector2(text_x, rect.y + 80), 38, 0, rl.Color(160, 160, 160, 255))

    # Mapping status
    if dev.address in self._state.config_devices:
      cfg = self._state.config_devices[dev.address]
      mapping_status = tr("Mapping on") if cfg.get('enabled') else tr("Mapping off")
      if dev.grabbed:
        mapping_status += ' · ' + tr("Receiving input")
      rl.draw_text_ex(gui_app.font(), mapping_status, rl.Vector2(text_x, rect.y + 120), 38, 0, rl.Color(120, 200, 120, 255))

    # Action buttons (right side)
    btn_x = rect.x + rect.width - 280
    btn_y = rect.y + (self._item_height - self._btn_height) // 2

    # Track which buttons were actually rendered for this device so we only
    # handle clicks for the ones currently on screen.
    rendered_buttons: set[str] = set()
    if not dev.paired:
      self._connect_btn.set_text(tr("Pair"))
      self._connect_btn.set_rect(rl.Rectangle(btn_x, btn_y, 250, self._btn_height))
      self._connect_btn.render()
      rendered_buttons.add('connect')
    else:
      # Connect / Disconnect
      btn_w = 110
      self._connect_btn.set_text(tr("Disconnect") if dev.connected else tr("Connect"))
      self._connect_btn.set_rect(rl.Rectangle(btn_x, btn_y, btn_w, self._btn_height))
      self._connect_btn.render()
      rendered_buttons.add('connect')

      # Forget button
      self._forget_btn.set_rect(rl.Rectangle(btn_x + btn_w + 10, btn_y, 110, self._btn_height))
      self._forget_btn.render()
      rendered_buttons.add('forget')

      # Edit button
      self._edit_btn.set_rect(rl.Rectangle(btn_x + btn_w * 2 + 20, btn_y, 90, self._btn_height))
      self._edit_btn.render()
      rendered_buttons.add('edit')

    # Handle clicks only for buttons that were rendered above
    if 'connect' in rendered_buttons and self._connect_btn.is_touched():
      self._on_device_action(dev, 'connect' if not dev.connected else 'disconnect')
    elif 'forget' in rendered_buttons and self._forget_btn.is_touched():
      self._on_device_action(dev, 'forget')
    elif 'edit' in rendered_buttons and self._edit_btn.is_touched():
      self._on_edit_device(dev)

  def _render_editor(self, rect: rl.Rectangle, content_top: float) -> None:
    if self._draft is None:
      return

    y = content_top

    # Device name header
    name = self._draft.name or self._selected_address or ''
    gui_label(rl.Rectangle(rect.x, y, rect.width, 70), name, font_size=55, alignment=TextAlignment.CENTER)
    y += 80

    # Back button
    self._back_btn.set_rect(rl.Rectangle(rect.x + self._padding, y, 200, 70))
    self._back_btn.render()
    y += 90

    # Profile selector
    rl.draw_text_ex(gui_app.font(), tr("Profile"), rl.Vector2(rect.x + self._padding, y + 5), 45, 0, rl.Color(200, 200, 200, 255))
    profile_h = 70
    profile_rect = rl.Rectangle(rect.x + 200, y, 350, profile_h)
    # Show profile name (simplified - in real impl would be a dropdown)
    rl.draw_rectangle_rounded(profile_rect, 0.3, 10, rl.Color(60, 60, 60, 255))
    profile_text = self._draft.profile
    rl.draw_text_ex(gui_app.font(), profile_text, rl.Vector2(profile_rect.x + 15, profile_rect.y + 15), 45, 0, rl.WHITE)
    y += profile_h + 30

    # Enabled toggle
    rl.draw_text_ex(gui_app.font(), tr("Use Carrot mapping"), rl.Vector2(rect.x + self._padding, y + 5), 45, 0, rl.Color(200, 200, 200, 255))
    toggle_x = rect.x + rect.width - 200
    toggle_rect = rl.Rectangle(toggle_x, y, 160, 60)
    # Simple toggle display
    toggle_on = self._draft.enabled
    bg = rl.Color(70, 91, 234, 255) if toggle_on else rl.Color(80, 80, 80, 255)
    rl.draw_rectangle_rounded(toggle_rect, 0.5, 10, bg)
    label = tr("ON") if toggle_on else tr("OFF")
    rl.draw_text_ex(gui_app.font(), label, rl.Vector2(toggle_rect.x + 55, toggle_rect.y + 10), 40, 0, rl.WHITE)
    y += 80

    # Mapping section header
    rl.draw_text_ex(gui_app.font(), tr("Button Mapping"), rl.Vector2(rect.x + self._padding, y), 50, 0, rl.WHITE)
    y += 60

    # Gesture column headers
    col_x = rect.x + 180
    for gesture in GESTURES:
      rl.draw_text_ex(gui_app.font(), tr(GESTURE_LABELS.get(gesture, gesture)), rl.Vector2(col_x, y), 38, 0, rl.Color(150, 150, 150, 255))
      col_x += self._gesture_col_width

    y += 50

    # Mapping rows
    for btn_name in MAPPING_BUTTONS:
      # Button name label
      rl.draw_text_ex(gui_app.font(), tr(btn_name), rl.Vector2(rect.x + self._padding, y + 10), 45, 0, rl.WHITE)

      # Gesture actions
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

    # Action buttons
    btn_y = y
    gap = 20
    btn_w = (rect.width - self._padding * 2 - gap * 3) // 4

    x = rect.x + self._padding
    self._save_btn.set_rect(rl.Rectangle(x, btn_y, btn_w, 80))
    self._save_btn.render()
    x += btn_w + gap

    is_learning = self._state.learning_addr == self._selected_address
    if is_learning:
      self._stop_btn.set_rect(rl.Rectangle(x, btn_y, btn_w, 80))
      self._stop_btn.render()
    else:
      self._test_btn.set_rect(rl.Rectangle(x, btn_y, btn_w, 80))
      self._test_btn.render()
    x += btn_w + gap

    # Last event display
    rl.draw_text_ex(gui_app.font(), self._last_event_text[:60], rl.Vector2(x, btn_y + 20), 38, 0, rl.Color(150, 255, 150, 255))

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

  def _on_scan_clicked(self) -> None:
    operation = 'cancel' if self._state.discovering else 'scan'
    self._http_async(operation)
    self._fetch_state()

  def _on_connect_clicked(self) -> None:
    pass  # handled in render

  def _on_forget_clicked(self) -> None:
    pass  # handled in render

  def _on_edit_clicked(self) -> None:
    pass  # handled in render

  def _on_device_action(self, dev: BTDevice, operation: str) -> None:
    if operation == 'forget':
      self._http_async('forget', {'address': dev.address})
      if self._selected_address == dev.address:
        self._selected_address = None
        self._draft = None
        self._panel = BTPanel.DEVICES
    elif operation in ('connect', 'disconnect'):
      self._http_async(operation, {'address': dev.address})
    else:
      self._http_async(operation, {'address': dev.address})
    time.sleep(0.3)
    self._fetch_state()

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
      self._draft = BTDevice(
        address=dev.address,
        name=dev.name,
        paired=dev.paired,
        connected=dev.connected,
        profile='generic',
        mapping={},
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
    time.sleep(0.3)
    self._fetch_state()

  def _on_test_clicked(self) -> None:
    if self._draft is None or self._selected_address is None:
      return
    self._http_async('learn', {'address': self._selected_address, 'enabled': True})
    time.sleep(0.2)
    self._fetch_state()

  def _on_stop_clicked(self) -> None:
    self._http_async('learn', {'address': self._selected_address, 'enabled': False})
    time.sleep(0.2)
    self._fetch_state()

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
          self._error_text = str(result.get('error', 'Unknown error'))
      except Exception as e:
        self._error_text = str(e)
      self._fetch_state()
    threading.Thread(target=do, daemon=True).start()
