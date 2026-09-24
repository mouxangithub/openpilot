"""Headless render smoke test for the Carrot tuning layout.

Why this exists
---------------
CarrotTuningLayout crashed the UI with

    AttributeError: 'CarrotTuningLayout' object has no attribute '_font'

because Widget.__init__ never defines _font. That bug was invisible to
py_compile and to reading the diff: it only fires when the widget tree is
actually walked by render(). The same class of bug (undefined attribute, wrong
signature, bad name) stays hidden in any widget that was never rendered.

So instead of trusting a diff review, drive the real code with a fake raylib and
a fake gui_app. Everything under test is real: Widget.render, Scroller,
ListItemSP, NavButton, measure_text_cached, the root navigation rows, and every
group sub-page returned by carrot_tuning_items.build_*_items().

It also pins the typography to the sunnypilot design tokens. The page this
replaced mixed 24px tab labels in with 40/50px settings text, which read as
"fonts all different sizes"; that is exactly the kind of drift an assertion
catches and a screenshot does not.

Run from the repo root (no display, no capnp, no zmq needed):

    PYTHONPATH=. python openpilot/selfdrive/ui/tests/carrot_tuning_render_smoke.py

Exit status is 0 when every check passes.

NOTE: deliberately NOT named test_*.py. install_stubs() replaces
openpilot.system.ui.lib.application, pyray and openpilot.common.params in
sys.modules, so pytest must not collect it into a shared session - doing so
would poison every other test that imports the UI stack.
"""


from __future__ import annotations

import re
import sys
import types
from collections import namedtuple
from pathlib import Path
from typing import Any

# Repo root, so the script works regardless of the caller's cwd.
REPO_ROOT = Path(__file__).resolve().parents[4]
PO_PATH = REPO_ROOT / "openpilot" / "selfdrive" / "ui" / "translations" / "app_zh-CHS.po"

# ---------------------------------------------------------------------------
# Fake pyray
# ---------------------------------------------------------------------------


class Rect:
  def __init__(self, x=0.0, y=0.0, width=0.0, height=0.0):
    self.x, self.y, self.width, self.height = float(x), float(y), float(width), float(height)

  def __repr__(self):
    return f"Rect({self.x}, {self.y}, {self.width}, {self.height})"


class Vec2:
  def __init__(self, x=0.0, y=0.0):
    self.x, self.y = float(x), float(y)

  def __repr__(self):
    return f"Vec2({self.x}, {self.y})"


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


# Average glyph advance as a fraction of font size, used to give measured text a
# plausible width. Wrapping and eliding only get exercised if text is wide enough
# to overflow, so this must not return something trivially small.
_ADVANCE = 0.55
# Screens are 2160x1080 on a C3; the settings content panel is ~1600 wide.
DRAWN: list[tuple] = []


class _FakeModule(types.ModuleType):
  """Module that fabricates any attribute it does not define explicitly."""

  def __getattr__(self, name: str) -> Any:
    if name.startswith("__"):
      raise AttributeError(name)
    value = _AnyCall()
    setattr(self, name, value)
    return value


class _AnyCall:
  def __call__(self, *a, **k):
    return None

  def __getattr__(self, name):
    if name.startswith("__"):
      raise AttributeError(name)
    return _AnyCall()


def _measure_text_ex(font, text, size, spacing):
  return Vec2(len(text) * size * _ADVANCE, size * 1.15)


def _measure_text(text, size):
  return len(text) * size * _ADVANCE


def _draw_text_ex(font, text, pos, size, spacing, color):
  DRAWN.append((getattr(font, "texture", None) and font.texture.id, text, pos.x, pos.y, size))


def _draw_text(text, x, y, size, color):
  DRAWN.append(("DEFAULT_FONT", text, x, y, size))


def _check_collision_point_rec(point, rect):
  """Real raylib semantics: inclusive on both edges."""
  return (rect.x <= point.x <= rect.x + rect.width and
          rect.y <= point.y <= rect.y + rect.height)


def build_fake_pyray() -> types.ModuleType:
  m = _FakeModule("pyray")
  m.Rectangle = Rect
  m.Rectangle.__module__ = "pyray"
  m.Vector2 = Vec2
  m.Color = Color
  m.Font = Font
  m.Texture = Texture
  m.Rectangle.__qualname__ = "Rectangle"
  m.Vector2.__qualname__ = "Vector2"
  m.WHITE = Color(255, 255, 255, 255)
  m.BLACK = Color(0, 0, 0, 255)
  m.BLANK = Color(0, 0, 0, 0)
  m.measure_text_ex = _measure_text_ex
  m.measure_text = _measure_text
  m.draw_text_ex = _draw_text_ex
  m.draw_text = _draw_text
  m.load_font = lambda path: Font(1)
  m.load_font_ex = lambda *a, **k: Font(1)
  m.get_font_default = lambda: Font(0)
  m.gen_texture_mipmaps = lambda *a, **k: None
  m.set_texture_filter = lambda *a, **k: None
  m.get_time = lambda: 0.0
  m.get_mouse_position = lambda: Vec2(-1000, -1000)
  m.is_mouse_button_pressed = lambda *a, **k: False
  m.is_mouse_button_down = lambda *a, **k: False
  m.get_mouse_wheel_move = lambda: 0.0
  # A real hit test, not a "False" stub. Widgets and GuiScrollPanel gate input on
  # this, so stubbing it to False would make every tap test silently vacuous.
  m.check_collision_point_rec = _check_collision_point_rec
  m.get_collision_rec = lambda a, b: Rect(a.x, a.y, a.width, a.height)
  m.ffi = _AnyCall()
  m.MouseButton = types.SimpleNamespace(MOUSE_BUTTON_LEFT=0, MOUSE_BUTTON_RIGHT=1, MOUSE_BUTTON_MIDDLE=2)
  m.TextureFilter = types.SimpleNamespace(TEXTURE_FILTER_BILINEAR=0, TEXTURE_FILTER_TRILINEAR=1)
  m.ConfigFlags = types.SimpleNamespace(FLAG_MSAA_4X_HINT=0, FLAG_VSYNC_HINT=0)
  return m


# ---------------------------------------------------------------------------
# Fake openpilot.system.ui.lib.application
# ---------------------------------------------------------------------------

FONT_WEIGHTS: dict[str, str] = {}


class FakeGuiApp:
  def __init__(self):
    self._font_cache: dict = {}
    self.target_fps = 60
    self.show_touches = False
    self.width, self.height = 2160, 1080
    self._textures: dict = {}
    # Widget._process_mouse_events iterates this every render; an empty list is
    # exactly the "no touch this frame" case.
    self._mouse_events: list = []

  @property
  def mouse_events(self):
    return self._mouse_events

  def font(self, weight=None):
    # Mirror GuiApplication.font: return a per-weight object that carries the
    # weight, so a stale-cache bug (reusing the wrong weight) would show up.
    key = str(weight)
    FONT_WEIGHTS[key] = FONT_WEIGHTS.get(key, 0) + 1
    return self._font_cache.setdefault(key, Font(100 + len(self._font_cache)))

  def fallback_font(self, text: str = ""):
    return self._font_cache.setdefault("__fallback__", Font(999))

  def texture(self, path, w=0, h=0):
    return Texture()

  def big_ui(self):
    return False

  # Modules branch on this at import time to pick the sunnypilot UI paths.
  def sunnypilot_ui(self):
    return True

  def render(self):
    return iter(())


def build_fake_application() -> types.ModuleType:
  m = _FakeModule("openpilot.system.ui.lib.application")
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
  m.MousePos = Vec2  # NamedTuple of (x, y) - a Vec2 is a faithful stand-in
  m.MouseEvent = types.SimpleNamespace
  m.requires_font_fallback = lambda: True
  m.font_fallback = lambda font, text="": font
  return m


# ---------------------------------------------------------------------------
# Fake multilang + Params
# ---------------------------------------------------------------------------


def build_fake_multilang() -> types.ModuleType:
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


def build_fake_params() -> types.ModuleType:
  m = types.ModuleType("openpilot.common.params")
  store: dict[str, Any] = {}

  class Params:
    def get(self, key, return_default=False):
      return store.get(key, 0 if return_default else None)

    def get_bool(self, key):
      return bool(store.get(key, False))

    def put(self, key, value, block=False):
      store[key] = value

    def put_bool(self, key, value):
      store[key] = value

    def remove(self, key):
      store.pop(key, None)

  m.Params = Params
  m.store = store
  return m


def install_stubs() -> None:
  import importlib

  # carrot_tuning.py needs ui_state.is_offroad() for the offroad-only toggle.
  _ui_mod = types.ModuleType('openpilot.selfdrive.ui.ui_state')

  class _FakeUiState:
    @staticmethod
    def is_offroad() -> bool:
      return True

    @staticmethod
    def update_params() -> None:
      return None

  _ui_mod.ui_state = _FakeUiState()
  sys.modules['openpilot.selfdrive.ui.ui_state'] = _ui_mod

  fake_pyray = build_fake_pyray()
  sys.modules["pyray"] = fake_pyray
  # openpilot imports `import pyray as rl`, and some modules use `rl.` helpers that
  # reach back into openpilot; keep the fake self-contained.

  sys.modules["openpilot.system.ui.lib.application"] = build_fake_application()
  sys.modules["openpilot.system.ui.lib.multilang"] = build_fake_multilang()
  sys.modules["openpilot.common.params"] = build_fake_params()

  # swaglog pulls in zmq, and wifi_manager pulls in jeepney + dbus; neither is
  # present on a PC and neither is exercised by a layout render.
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

  # Make sure `from openpilot.system.ui.lib.application import X` resolves the
  # parent packages to the real (empty) __init__ modules, not to a fabricated one.
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
    except Exception as exc:  # pragma: no cover - diagnostic only
      print(f"  [warn] could not import {pkg}: {exc}")


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------


def main() -> int:
  install_stubs()

  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.carrot_tuning import (  # noqa: E402
    CARROT_GROUPS, CarrotGroupKey, CarrotTuningLayout,
  )
  from openpilot.system.ui.sunnypilot.lib.styles import style  # noqa: E402
  from openpilot.system.ui.sunnypilot.widgets.list_view import LineSeparatorSP  # noqa: E402

  failures: list[str] = []
  checks = 0

  def check(label, fn):
    nonlocal checks
    checks += 1
    try:
      fn()
      print(f"  ok  {label}")
    except Exception as exc:  # noqa: BLE001
      failures.append(f"{label}: {type(exc).__name__}: {exc}")
      print(f"  FAIL {label}: {type(exc).__name__}: {exc}")

  content = Rect(0, 0, 1600, 900)

  # --- root page ------------------------------------------------------------
  print("== root page ==")
  root = CarrotTuningLayout(lambda: None)
  root.set_parent_rect(content)
  root.show_event()

  def root_renders():
    DRAWN.clear()
    root.render(content)
    assert DRAWN, "root page drew nothing"
    assert root._current_group is None, "root must start on the group list"

  check("renders without crashing", root_renders)

  def root_lists_every_group():
    root.render(content)
    items = root._scroller._items
    rows = root._nav_rows
    seps = [i for i in items if isinstance(i, LineSeparatorSP)]
    assert len(rows) == len(CARROT_GROUPS), f"{len(rows)} rows for {len(CARROT_GROUPS)} groups"
    # 7 dividers between the 8 groups plus 1 divider below the Carrot Web Panel toggle.
    expected_seps = len(CARROT_GROUPS)
    assert len(seps) == expected_seps, f"expected {expected_seps} dividers, got {len(seps)}"
    assert not isinstance(items[0], LineSeparatorSP), "list must not start with a divider"

    # Render into a viewport tall enough for every row: the real panel is 900px
    # and culls off-screen items, which would hide the rows we want to check.
    DRAWN.clear()
    root.render(Rect(0, 0, content.width, 6000))
    drawn = {d[1] for d in DRAWN}
    missing = [g.title for g in CARROT_GROUPS if g.title not in drawn]
    assert not missing, f"group titles not drawn: {missing}"
    root.render(content)

  check("one navigation row per group, divided by separators", root_lists_every_group)

  def root_shows_group_descriptions():
    # Group descriptions are the only hint of page contents, so they must be
    # visible without a tap (unlike a settings row's description).
    hidden = [g.title for g, row in zip(CARROT_GROUPS, root._nav_rows, strict=True) if not row.description_visible]
    assert not hidden, f"descriptions hidden for: {hidden}"

  check("group descriptions visible without a tap", root_shows_group_descriptions)

  # --- every group sub-page -------------------------------------------------
  print("== group sub-pages ==")
  for key, group in zip(CarrotGroupKey, CARROT_GROUPS, strict=True):
    def page_works(key=key, group=group):
      root._set_current_group(key)
      assert root._current_group == key, "navigation did not open the group"

      page = root._group_layouts[key]
      items = page._scroller._items
      dividers = [i for i in items if isinstance(i, LineSeparatorSP)]
      settings = [i for i in items if not isinstance(i, LineSeparatorSP)]
      assert settings, "group page has no settings items"
      assert not isinstance(items[0], LineSeparatorSP), "page must not start with a divider"
      assert not isinstance(items[-1], LineSeparatorSP), "page must not end with a divider"

      DRAWN.clear()
      root.render(content)   # renders the group page
      assert DRAWN, "group page drew nothing"

      # Going back must return to the row list.
      root._set_current_group(None)
      assert root._current_group is None
      DRAWN.clear()
      root.render(content)
      assert DRAWN, "root page did not come back"

    check(f"{key.name:11s} ({group.title}) items render + back works", page_works)

  # --- typography conformance ----------------------------------------------
  print("== typography ==")
  # Every size must come from a shared sunnypilot token. This is the assertion
  # that catches the previous design's drift (24px tab labels among 40/50px rows).
  from openpilot.system.ui.widgets.list_view import BUTTON_FONT_SIZE  # noqa: E402
  from openpilot.system.ui.sunnypilot.widgets.option_control import (  # noqa: E402
    BUTTON_FONT_SIZE as OPTION_BUTTON_FONT_SIZE,
  )
  allowed_sizes = {
    style.ITEM_DESC_FONT_SIZE,          # 40 - item description
    style.ITEM_TEXT_FONT_SIZE,          # 50 - item title / option value
    BUTTON_FONT_SIZE,                   # 35 - list action button label
    OPTION_BUTTON_FONT_SIZE,            # 60 - option +/- button glyph
  }

  def collect_sizes():
    sizes = {}
    root.show_event()
    root.render(content)
    for font_id, text, _x, _y, size in DRAWN:
      sizes.setdefault(int(size), set()).add(text[:24])
    for key in CarrotGroupKey:
      root._set_current_group(key)
      DRAWN.clear()
      root.render(content)
      for font_id, text, _x, _y, size in DRAWN:
        sizes.setdefault(int(size), set()).add(text[:24])
    root._set_current_group(None)
    return sizes

  sizes = collect_sizes()
  for size in sorted(sizes):
    sample = sorted(sizes[size])[:2]
    print(f"  size {size:>3}px  ({len(sizes[size])} strings)  e.g. {sample}")

  def sizes_are_tokens():
    unexpected = sorted(set(sizes) - allowed_sizes)
    assert not unexpected, f"font sizes outside the sunnypilot token set {sorted(allowed_sizes)}: {unexpected}"
    assert 24 not in sizes, "the 24px tab-label size must be gone"

  check(f"font sizes limited to {sorted(allowed_sizes)}", sizes_are_tokens)

  # --- input handling -------------------------------------------------------
  # These drive synthetic touch sequences through the real Scroller +
  # Widget._process_mouse_events path. Geometry is re-read after every reset:
  # a scrolled list moves its rows, and a stale rect would make a tap "fail" for
  # the wrong reason.
  print("== input handling ==")

  from openpilot.system.ui.lib.application import gui_app  # noqa: E402
  Event = namedtuple("Event", "pos slot left_pressed left_released left_down t")

  def frame(events):
    gui_app._mouse_events = events
    root.render(content)

  def settle(frames=60):
    for _ in range(frames):
      frame([])

  def reset():
    """Back to the root page, scrolled to the top, with inertia decayed."""
    root.show_event()
    settle()

  def tap(x, y, steps=3):
    for i in range(steps):
      frame([Event(Rect(x, y), 0, i == 0, i == steps - 1, i != steps - 1, i / 60)])

  def drag(x, y, dy, steps=6):
    for i in range(steps):
      frame([Event(Rect(x, y + dy * i / (steps - 1)), 0, i == 0, i == steps - 1, i != steps - 1, i / 60)])

  def row_tap_point(row):
    return row.rect.x + 120, row.rect.y + row.rect.height / 2

  def row_tap_opens():
    reset()
    tap(*row_tap_point(root._nav_rows[0]))
    assert root._current_group == CarrotGroupKey.START, f"tap did not open the group: {root._current_group}"

  check("tapping a row opens the group", row_tap_opens)

  def drag_scroll_does_not_navigate():
    reset()
    row = root._nav_rows[0]
    x, y = row_tap_point(row)
    before = root._scroller.scroll_panel.offset
    drag(x, y, dy=-60)
    assert root._current_group is None, f"a scroll gesture navigated: {root._current_group}"
    # Guard the guard: if the drag did not actually scroll, the assertion above
    # would pass for the wrong reason.
    after = root._scroller.scroll_panel.offset
    assert after != before, f"the drag did not scroll ({before:.0f} -> {after:.0f}), so this check proves nothing"

  check("drag-scrolling a row scrolls instead of navigating", drag_scroll_does_not_navigate)

  def open_button_opens():
    reset()
    row = root._nav_rows[0]
    btn = row.action_item._button.rect
    assert root._scroller.scroll_panel.is_touch_valid(), "scroll inertia must be settled before tapping"
    tap(btn.x + btn.width / 2, btn.y + btn.height / 2)
    assert root._current_group == CarrotGroupKey.START, f"OPEN did nothing: {root._current_group}"

  check("the OPEN button opens the group", open_button_opens)

  def reopen_after_back():
    reset()
    tap(*row_tap_point(root._nav_rows[0]))
    first = root._current_group
    root._set_current_group(None)
    settle()
    tap(*row_tap_point(root._nav_rows[0]))
    assert first == CarrotGroupKey.START and root._current_group == CarrotGroupKey.START, \
      f"first={first} second={root._current_group}"

  check("open, back, open again", reopen_after_back)

  def all_rows_tappable():
    bad = []
    for i in range(len(root._nav_rows)):
      reset()
      tap(*row_tap_point(root._nav_rows[i]))
      if root._current_group != CarrotGroupKey(i):
        bad.append((i, root._current_group))
    assert not bad, f"rows that did not navigate: {bad}"

  check(f"all {len(root._nav_rows)} rows navigate", all_rows_tappable)

  def back_button_returns():
    reset()
    tap(*row_tap_point(root._nav_rows[0]))
    page = root._group_layouts[CarrotGroupKey.START]
    assert page._back_button._click_callback is not None, "sub-page back button has no callback"
    page._back_button._click_callback()
    assert root._current_group is None, f"back did not return to the root: {root._current_group}"

  check("the sub-page back button returns to the root", back_button_returns)

  # --- translations ---------------------------------------------------------
  print("== translations ==")
  new_strings = [g.title for g in CARROT_GROUPS] + [g.description for g in CARROT_GROUPS] + ["OPEN", "Back", "Carrot Web Panel"]

  # Group headings inside each page must be translated too, otherwise a Chinese
  # UI falls back to English for every section label.
  import re as _re
  _items_src = (REPO_ROOT / "openpilot" / "selfdrive" / "ui" / "sunnypilot" / "layouts" /
                "settings" / "carrot_tuning_items.py").read_text(encoding="utf-8")
  headings = sorted(set(_re.findall(r"section_heading_sp\(tr\('([^']+)'\)\)", _items_src)))
  assert headings, "no section headings found in carrot_tuning_items.py"
  # Every user-visible native label, not just the headings: a missing entry makes
  # the Chinese UI fall back to English for that row.
  titles = sorted(set(_re.findall(r"title=tr\('([^']+)'\)", _items_src)))
  # The label set shrank when the params with no consumer were hidden from the UI;
  # the floor guards against an accidental empty/mis-parsed file rather than a count.
  # Lowered from 80 to 70 when the 20 Cluster* rows were removed: sp has no cluster
  # subsystem, so every one of them was registered, exposed in both UIs, and read by
  # nothing. 73 are visible now, so the floor stays clear of ordinary churn.
  assert len(titles) >= 70, f"expected the visible carrot label set, got {len(titles)}"
  new_strings = new_strings + headings + titles

  for lang in ("zh-CHS", "zh-CHT"):
    def translated(lang=lang):
      po = (REPO_ROOT / "openpilot" / "selfdrive" / "ui" / "translations" / f"app_{lang}.po").read_text(encoding="utf-8")
      existing = set(re.findall(r'^msgid "(.+?)"$', po, re.M))
      missing = [s for s in new_strings if s not in existing]
      assert not missing, f"{lang} missing: {missing}"

    check(f"{lang} covers all {len(new_strings)} root-page strings", translated)

  print()
  if failures:
    print(f"FAILED {len(failures)}/{checks} checks:")
    for f in failures:
      print(f"  - {f}")
    return 1
  print(f"PASSED {checks}/{checks} checks")
  return 0


if __name__ == "__main__":
  sys.exit(main())
