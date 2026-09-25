"""无头冒烟测试：ClusterOverlay 在 onroad 主屏的 overlay。

验证三件事：
  1. ClusterOverlayRenderer 能对空状态离屏渲染不崩（方案X 的渲染核无 3D/GLB/GLES 依赖）；
  2. ClusterOverlay 在 ClusterHud=false 时不可见、render() 不画任何东西；
  3. ClusterOverlay 在 ClusterHud=true + 空状态时能完整走 render()（_update_state -> _render
     -> draw_texture_pro 叠加）不崩。

用 fake pyray + fake ui_state + fake openpilot.common.params（pattern 同
carrot_tuning_render_smoke.py）。复用的 cluster_config/cluster_display 为纯逻辑模块，
import 时会随 cluster_overlay_renderer 触发 —— 因此本测试同样不能叫 test_*.py，避免 pytest
共享会话被污染。

Run from the repo root (no display):

    PYTHONPATH=. python openpilot/selfdrive/ui/tests/cluster_overlay_smoke.py

Exit status is 0 when every check passes.
"""


from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# Fake pyray（最小可用的离屏渲染相关接口）
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
  def __init__(self, tid=1, width=640, height=240):
    self.id = tid
    self.width, self.height = width, height


class RenderTexture:
  def __init__(self, tid=1, width=640, height=240):
    self.texture = Texture(tid, width, height)
    self.id = tid
    self.depth = None


class Font:
  def __init__(self, tid=1, base_size=48):
    self.texture = Texture(tid)
    self.baseSize = base_size


# 记录绘制调用；draw_texture_pro 用真实 hit 记录，便于断言 overlay 叠加发生。
DRAWN: list[tuple] = []
GT_MODE = 0  # 0=window, 1=render_texure 内


def _draw_text_ex(font, text, pos, size, spacing, color):
  DRAWN.append(("text", getattr(font, "baseSize", 0), text, pos.x, pos.y, size))


def _measure_text_ex(font, text, size, spacing):
  return Vec2(len(text) * size * 0.55, size * 1.1)


def _draw_texture_pro(texture, source, dest, origin, rotation, tint):
  DRAWN.append(("tex", texture.id, dest.x, dest.y, dest.width, dest.height, rotation))


def _begin_texture_mode(target):
  global GT_MODE
  GT_MODE = 1
  DRAWN.append(("begin_texture", target.id))


def _end_texture_mode():
  global GT_MODE
  GT_MODE = 0
  DRAWN.append(("end_texture",))


def _get_font_default():
  return Font(0, 48)


def _load_render_texture(*a, **k):
  return RenderTexture(len(DRAWN) + 100, 640, 240)


def build_fake_pyray() -> types.ModuleType:
  m = types.ModuleType("pyray")
  m.Rectangle = Rect
  m.Vector2 = Vec2
  m.Color = Color
  m.Texture = Texture
  m.RenderTexture = RenderTexture
  m.Font = Font
  m.WHITE = Color(255, 255, 255, 255)
  m.BLACK = Color(0, 0, 0, 255)
  m.load_font_ex = lambda *a, **k: Font(len(DRAWN) + 400, 48)
  m.get_font_default = _get_font_default
  m.load_render_texture = _load_render_texture
  m.unload_render_texture = lambda *a, **k: None
  m.begin_texture_mode = _begin_texture_mode
  m.end_texture_mode = _end_texture_mode
  m.clear_background = lambda *a, **k: DRAWN.append(("clear",))
  m.set_texture_filter = lambda *a, **k: None
  m.measure_text_ex = _measure_text_ex
  m.draw_text_ex = _draw_text_ex
  m.draw_rectangle_rounded = lambda *a, **k: DRAWN.append(("rounded",))
  m.draw_rectangle_rounded_lines = lambda *a, **k: DRAWN.append(("rounded_lines",))
  m.draw_texture_pro = _draw_texture_pro
  m.TextureFilter = types.SimpleNamespace(TEXTURE_FILTER_BILINEAR=0)
  return m


# ---------------------------------------------------------------------------
# Fake ui_state + params
# ---------------------------------------------------------------------------


class FakeSM:
  services = ("carState", "cruiseState", "radarState")

  def __init__(self, data=None):
    self._data = data or {}

  def __getitem__(self, name):
    if name not in self.services:
      raise KeyError(name)
    return self._data.get(name, _EmptyMsg())


class _EmptyMsg:
  """任何属性都返回空值，模拟"字段缺失"的空 cereal 消息。"""

  def __getattr__(self, name):
    return 0  # 数值字段默认 0；getattr 为 0 即视为"无"。布尔用 bool() 亦安全。


def build_fake_application():
  m = types.ModuleType("openpilot.system.ui.lib.application")

  class FakeGuiApp:
    def __init__(self):
      self.show_touches = False
      self._mouse_events = []

    def sunnypilot_ui(self):
      return True

    def push_widget(self, w):
      pass

    @property
    def mouse_events(self):
      return self._mouse_events

  m.gui_app = FakeGuiApp()
  m.MousePos = Vec2
  m.MouseEvent = types.SimpleNamespace
  m.MAX_TOUCH_SLOTS = 2
  return m


def build_fake_ui_state(store=None):
  m = types.ModuleType("openpilot.selfdrive.ui.ui_state")
  m.Params = None
  store = store if store is not None else {}
  params_mod = types.ModuleType("openpilot.common.params")

  class Params:
    def __init__(self):
      self.store = store

    def get_bool(self, key):
      return bool(self.store.get(key, False))

    def get(self, key, default=0):
      return self.store.get(key, default)

  params_mod.Params = Params
  sys.modules["openpilot.common.params"] = params_mod

  class Device:
    awake = True

  class FakeUiState:
    def __init__(self):
      self.sm = FakeSM()
      self.params = Params()
      self.started = True

  m.device = Device()
  m.ui_state = FakeUiState()
  sys.modules["openpilot.selfdrive.ui.ui_state"] = m
  return m, store


def install_stubs(store) -> dict:
  sys.modules["pyray"] = build_fake_pyray()
  sys.modules["openpilot.system.ui.lib.application"] = build_fake_application()
  _, param_store = build_fake_ui_state(store)
  import importlib
  # cluster_view/ 的纯逻辑子模块（cluster_config, cluster_display）使用顶层 import，
  # 需要把 cluster_view/ 目录加入 sys.path 才能解析。
  cluster_view_dir = str(REPO_ROOT / "openpilot" / "sunnypilot" / "carrot" / "cluster_view")
  if cluster_view_dir not in sys.path:
    sys.path.insert(0, cluster_view_dir)
  for pkg in ("openpilot", "openpilot.sunnypilot", "openpilot.sunnypilot.carrot",
              "openpilot.system", "openpilot.system.ui", "openpilot.system.ui.widgets"):
    if pkg not in sys.modules:
      try:
        importlib.import_module(pkg)
      except Exception as exc:  # pragma: no cover
        print(f"  [warn] could not import {pkg}: {exc}")
  return param_store


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------


def main() -> int:
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

  # === 渲染核空状态渲染不崩（方案X） ===
  _store = install_stubs({})
  from openpilot.sunnypilot.carrot.cluster_view.cluster_overlay_renderer import (  # noqa: E402
    ClusterOverlayRenderer, ClusterOverlayState,
  )

  def renderer_empty_state_ok():
    DRAWN.clear()
    r = ClusterOverlayRenderer(640, 240)
    assert r.width == 640 and r.height == 240
    with r.render_to_target(ClusterOverlayState()):
      pass
    kinds = {k[0] for k in DRAWN}
    assert {"rounded", "rounded_lines", "begin_texture", "end_texture", "text"} <= kinds, \
      f"rendered kinds missing: {sorted(kinds)}"
    r.unload()

  check("renderer renders an empty state to a target", renderer_empty_state_ok)

  # === ClusterOverlay：ClusterHud=false 不可见/不画 ===
  from openpilot.sunnypilot.carrot.cluster_view.cluster_overlay import ClusterOverlay  # noqa: E402

  def overlay_hidden_when_disabled():
    _store.clear()
    DRAWN.clear()
    o = ClusterOverlay(640, 240)
    corner = Rect(700, 500, 500, 187)
    o.render(corner)
    assert not o.is_visible, "ClusterHud=false, overlay should be invisible"
    assert not any(k[0] == "tex" for k in DRAWN), "overlay must not draw texture when disabled"

  check("ClusterHud=false -> hidden, draws nothing", overlay_hidden_when_disabled)

  # === ClusterOverlay：ClusterHud=true 空状态走完整渲染不崩 ===
  def overlay_renders_when_enabled():
    _store.clear()
    _store["ClusterHud"] = True
    _store["IsMetric"] = True
    DRAWN.clear()
    o = ClusterOverlay(640, 240)
    corner = Rect(700, 500, 500, 187)
    o.render(corner)
    tex_calls = [k for k in DRAWN if k[0] == "tex"]
    assert o.is_visible, "ClusterHud=true, overlay should be visible"
    assert tex_calls, "overlay must draw_texture_pro onto the onroad screen"
    # 叠加发生在 begin/end_texture_mode 之后（离屏渲染完再贴）。
    assert DRAWN.index(("end_texture",)) < DRAWN.index(tex_calls[0]), "texture draw must follow offscreen render"

  check("ClusterHud=true -> renders overlay onto corner", overlay_renders_when_enabled)

  # === overlay_rect 几何：落在 content rect 右下角内 ===
  def overlay_rect_within_corner():
    _store.clear()
    o = ClusterOverlay(640, 240)
    content = Rect(0, 0, 1000, 1800)
    r = o.overlay_rect(content)
    assert r.x > 0 and r.y > 0, f"overlay must sit inside screen, got ({r.x:.0f},{r.y:.0f})"
    assert r.x + r.width <= content.x + content.width + 0.01
    assert r.y + r.height <= content.y + content.height + 0.01
    assert r.width < content.width and r.height < content.height

  check("overlay_rect stays inside bottom-right", overlay_rect_within_corner)

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