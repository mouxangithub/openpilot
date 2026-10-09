"""Headless render smoke test for the Carrot Bluetooth settings layout.

Mirrors the carrot_tuning render smoke approach: stub raylib, gui_app and
network calls, then drive CarrotBluetoothLayout through main/advanced/editor
panels. This catches import-time / attribute / signature bugs that py_compile
misses.

Run from the repo root:

    PYTHONPATH=. python openpilot/selfdrive/ui/tests/bluetooth_render_smoke.py
"""

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class Rect:
  def __init__(self, x=0.0, y=0.0, width=0.0, height=0.0):
    self.x, self.y, self.width, self.height = float(x), float(y), float(width), float(height)


class Vec2:
  def __init__(self, x=0.0, y=0.0):
    self.x, self.y = float(x), float(y)


class Color:
  def __init__(self, r=0, g=0, b=0, a=255):
    self.r, self.g, self.b, self.a = r, g, b, a


class Texture:
  def __init__(self, tid=1):
    self.id = tid
    self.width, self.height = 64, 64


class Font:
  def __init__(self, tid=1):
    self.texture = Texture(tid)
    self.baseSize = 48


_ADVANCE = 0.55


class _AnyCall:
  def __call__(self, *a, **k):
    return None

  def __getattr__(self, name):
    if name.startswith("__"):
      raise AttributeError(name)
    return _AnyCall()


class _FakeModule(types.ModuleType):
  def __getattr__(self, name: str):
    if name.startswith("__"):
      raise AttributeError(name)
    value = _AnyCall()
    setattr(self, name, value)
    return value


def _measure_text_ex(font, text, size, spacing):
  return Vec2(len(text or "") * size * _ADVANCE, size * 1.15)


def _measure_text(text, size):
  return len(text or "") * size * _ADVANCE


# Record every draw_text_ex call so we can assert no text is drawn twice (ghosting).
DRAWN: list[tuple] = []


def _draw_text_ex(font, text, pos, size, spacing, color):
  DRAWN.append((str(text), pos.x, pos.y, size))


def build_fake_pyray():
  m = _FakeModule("pyray")
  m.Rectangle = Rect
  m.Vector2 = Vec2
  m.Color = Color
  m.Font = Font
  m.Texture = Texture
  m.WHITE = Color(255, 255, 255, 255)
  m.BLACK = Color(0, 0, 0, 255)
  m.BLANK = Color(0, 0, 0, 0)
  m.LIGHTGRAY = Color(200, 200, 200, 255)
  m.measure_text_ex = _measure_text_ex
  m.measure_text = _measure_text
  m.load_font = lambda path: Font(1)
  m.load_font_ex = lambda *a, **k: Font(1)
  m.draw_text_ex = _draw_text_ex
  m.get_font_default = lambda: Font(0)
  m.gen_texture_mipmaps = lambda *a, **k: None
  m.set_texture_filter = lambda *a, **k: None
  m.get_time = lambda: 0.0
  m.get_frame_time = lambda: 0.016
  m.get_mouse_position = lambda: Vec2(-1000, -1000)
  m.is_mouse_button_pressed = lambda *a, **k: False
  m.is_mouse_button_down = lambda *a, **k: False
  m.get_mouse_wheel_move = lambda: 0.0
  m.check_collision_point_rec = lambda p, r: (r.x <= p.x <= r.x + r.width and r.y <= p.y <= r.y + r.height)
  m.get_collision_rec = lambda a, b: Rect(a.x, a.y, a.width, a.height)
  m.check_collision_recs = lambda a, b: True
  m.ffi = _AnyCall()
  m.MouseButton = types.SimpleNamespace(MOUSE_BUTTON_LEFT=0, MOUSE_BUTTON_RIGHT=1, MOUSE_BUTTON_MIDDLE=2)
  m.TextureFilter = types.SimpleNamespace(TEXTURE_FILTER_BILINEAR=0, TEXTURE_FILTER_TRILINEAR=1)
  m.ConfigFlags = types.SimpleNamespace(FLAG_MSAA_4X_HINT=0, FLAG_VSYNC_HINT=0)
  m.begin_scissor_mode = lambda *a, **k: None
  m.end_scissor_mode = lambda: None
  m.draw_rectangle_rounded = lambda *a, **k: None
  m.draw_rectangle = lambda *a, **k: None
  m.draw_line = lambda *a, **k: None
  m.draw_texture_v = lambda *a, **k: None
  return m


def build_fake_application():
  m = _FakeModule("openpilot.system.ui.lib.application")

  class FakeGuiApp:
    def __init__(self):
      self._font_cache = {}
      self.target_fps = 60
      self.show_touches = False
      self.width, self.height = 2160, 1080
      self._mouse_events = []

    @property
    def mouse_events(self):
      return self._mouse_events

    def font(self, weight=None):
      return self._font_cache.setdefault(str(weight), Font(100 + len(self._font_cache)))

    def fallback_font(self, text=""):
      return self._font_cache.setdefault("__fallback__", Font(999))

    def texture(self, path, w=0, h=0):
      return Texture()

    def big_ui(self):
      return False

    def sunnypilot_ui(self):
      return True

    def render(self):
      return iter(())

  app = FakeGuiApp()
  m.gui_app = app
  m.FontWeight = types.SimpleNamespace(
    NORMAL="Inter-Medium.ttf", MEDIUM="Inter-Medium.ttf", BOLD="Inter-Bold.ttf",
    SEMI_BOLD="Inter-SemiBold.ttf", UNIFONT="OpFont-Regular-Labels.fnt", AUDIOWIDE="Audiowide-Regular.ttf",
    DISPLAY_REGULAR="Inter-Regular.ttf", ROMAN="Inter-Regular.ttf", DISPLAY="Inter-Bold.ttf",
  )
  m.TextAlignment = types.SimpleNamespace(LEFT=0, CENTER=1, RIGHT=2)
  m.TextAlignmentVertical = types.SimpleNamespace(TOP=0, MIDDLE=1, BOTTOM=2)
  m.FONT_SCALE = 1.16
  m.DEFAULT_TEXT_SIZE = 60
  m.DEFAULT_TEXT_COLOR = Color(255, 255, 255, 230)
  m.MAX_TOUCH_SLOTS = 2
  m.MousePos = Vec2
  m.MouseEvent = types.SimpleNamespace
  m.requires_font_fallback = lambda: True
  m.font_fallback = lambda font, text="": font
  return m


def build_fake_multilang():
  m = _FakeModule("openpilot.system.ui.lib.multilang")
  m.language = "zh-CHS"
  m.languages = {"en": "English", "zh-CHS": "简体中文"}
  m.codes = {v: k for k, v in m.languages.items()}
  m.tr = lambda s: s
  m.trn = lambda s, p, n: s if n == 1 else p
  m.tr_noop = lambda s: s
  m.requires_font_fallback = lambda: True
  m.change_language = lambda code: None
  m.init = lambda: None
  return m


def build_fake_params():
  m = types.ModuleType("openpilot.common.params")

  class Params:
    def get(self, key, return_default=False):
      return 0 if return_default else None

    def get_bool(self, key):
      return False

    def put(self, key, value, block=False):
      pass

    def put_bool(self, key, value):
      pass

    def remove(self, key):
      pass

  m.Params = Params
  return m


def install_stubs():
  import importlib

  _ui_mod = types.ModuleType('openpilot.selfdrive.ui.ui_state')

  class _FakeUiState:
    @staticmethod
    def is_offroad():
      return True

    @staticmethod
    def update_params():
      return None

  _ui_mod.ui_state = _FakeUiState()
  sys.modules['openpilot.selfdrive.ui.ui_state'] = _ui_mod

  sys.modules["pyray"] = build_fake_pyray()
  sys.modules["openpilot.system.ui.lib.application"] = build_fake_application()
  sys.modules["openpilot.system.ui.lib.multilang"] = build_fake_multilang()
  sys.modules["openpilot.common.params"] = build_fake_params()

  swaglog = _FakeModule("openpilot.common.swaglog")
  swaglog.cloudlog = _AnyCall()
  sys.modules["openpilot.common.swaglog"] = swaglog

  wifi = _FakeModule("openpilot.system.ui.lib.wifi_manager")
  wifi.WifiManager = type("WifiManager", (), {"__init__": lambda self, *a, **k: None,
                                              "set_active": lambda self, v: None})
  wifi.SecurityType = _AnyCall()
  wifi.Network = _AnyCall()
  wifi.MeteredType = _AnyCall()
  wifi.normalize_ssid = lambda s: s
  sys.modules["openpilot.system.ui.lib.wifi_manager"] = wifi

  for name in ("jeepney", "jeepney.io", "jeepney.io.blocking", "jeepney.io.threading",
               "jeepney.bus_messages", "jeepney.low_level", "jeepney.wrappers"):
    sys.modules.setdefault(name, _FakeModule(name))

  # Stub urllib so the panel can fetch state without a real server.
  import json
  real_urlopen = None
  try:
    import urllib.request as _ur
    real_urlopen = _ur.urlopen
  except Exception:
    pass

  class _FakeResponse:
    def __init__(self, data):
      self._data = data

    def read(self):
      return self._data

    def __enter__(self):
      return self

    def __exit__(self, *a):
      pass

  def _fake_urlopen(url, *args, **kwargs):
    # Always return a ready Bluetooth state with two sample devices.
    data = {
      "hasBluez": True,
      "serviceRunning": True,
      "available": True,
      "hasUart": True,
      "hasBtpower": True,
      "radioEnabled": True,
      "discoverable": False,
      "localName": "openpilot",
      "adapters": [],
      "devices": [
        {"address": "AA:BB:CC:DD:EE:01", "name": "Yiser-J6", "paired": True, "connected": True, "rssi": -55, "battery": 80},
        {"address": "AA:BB:CC:DD:EE:02", "name": "Phone", "paired": False, "connected": False, "rssi": -72},
      ],
      "config": {"devices": {"AA:BB:CC:DD:EE:01": {"enabled": True, "profile": "yiser-j6", "mapping": {}}}},
      "runtime": {"alive": True, "stationary": True, "grabbed": ["AA:BB:CC:DD:EE:01"], "errors": {}, "learning": None},
    }
    return _FakeResponse(json.dumps(data).encode())

  def _fake_request_init(self, url, data=None, headers=None, method="GET"):
    self.full_url = url
    self.data = data
    self.headers = headers or {}
    self.method = method

  import urllib.request
  urllib.request.urlopen = _fake_urlopen
  urllib.request.Request.__init__ = _fake_request_init

  for pkg in ("openpilot", "openpilot.system", "openpilot.system.ui", "openpilot.system.ui.lib",
              "openpilot.system.ui.widgets", "openpilot.system.ui.sunnypilot",
              "openpilot.system.ui.sunnypilot.widgets", "openpilot.common",
              "openpilot.selfdrive", "openpilot.selfdrive.ui",
              "openpilot.selfdrive.ui.sunnypilot",
              "openpilot.selfdrive.ui.sunnypilot.layouts",
              "openpilot.selfdrive.ui.sunnypilot.layouts.settings"):
    if pkg in sys.modules:
      continue
    try:
      importlib.import_module(pkg)
    except Exception as exc:
      print(f"  [warn] could not import {pkg}: {exc}")


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def main():
  install_stubs()

  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.bluetooth_settings import CarrotBluetoothLayout, BTPanel

  layout = CarrotBluetoothLayout()
  layout.show_event()

  rect = Rect(0, 0, 1600, 900)

  # Main device list panel
  layout._render(rect)
  assert layout._panel == BTPanel.DEVICES

  # Ghosting regression check: each device name must be drawn exactly once.
  # A duplicated name (once from the row Button, once from draw_text_ex) at
  # different vertical offsets is the exact "重影" symptom that was reported.
  from collections import Counter
  drawn_names = Counter(t for t, x, y, s in DRAWN if t in ("Yiser-J6", "Phone"))
  assert drawn_names.get("Yiser-J6", 0) == 1, f"Yiser-J6 drawn {drawn_names.get('Yiser-J6')} times"
  assert drawn_names.get("Phone", 0) == 1, f"Phone drawn {drawn_names.get('Phone')} times"

  # Row buttons must cover only the left text area, NOT the whole row. If a row
  # button spanned the full width it would swallow taps meant for the Pair /
  # Connect / Forget action buttons and (worse) open the editor instead of
  # confirming a pairing.
  for addr in ("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"):
    row_btn = layout._device_btns.get(addr)
    assert row_btn is not None and row_btn.rect.width < rect.width, \
      f"row button for {addr} must not span the whole row"

  # Advanced panel with toggles + name row + reset
  layout._on_advanced_clicked()
  layout._render(rect)
  assert layout._panel == BTPanel.ADVANCED

  # Editor panel for the first device
  dev = layout._state.devices[0]
  layout._on_edit_device(dev)
  layout._render(rect)
  assert layout._panel == BTPanel.EDITOR
  assert layout._draft is not None

  # Back to device list
  layout._on_back_clicked()
  layout._render(rect)
  assert layout._panel == BTPanel.DEVICES

  print("ok  CarrotBluetoothLayout renders main / advanced / editor without crashing")
  return 0


if __name__ == "__main__":
  sys.exit(main())
