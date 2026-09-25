"""移植自 cp cluster 的纯 2D HUD 渲染核（仅保留 2D HUD 部分，3D 场景后续可加）。

Why this exists
---------------
cp (carrotpilot) 的 ClusterUiRenderer（cluster_renderer.py，343KB）能把完整仪表盘离屏渲染到
RGBA 缓冲，但它的 render() 无条件先走 _render_world() —— 那套 3D 场景依赖车型 GLB/GLES
shader，而 sp 用 chestnut USB AI 加速器，物理上不能同时接 USB GPU 屏；且 sp 侧复制过来的
cluster/assets/ 是空目录（无 cybertruck 模型纹理），3D 路径在 sp 的 PC 无头环境跑不起来。

所以这里不复用 ClusterUiRenderer 本体，而是：
  * 复用 cluster_config.py 的纯逻辑（主题/配色/设计常量）—— 纯数据，无 pyray/硬件依赖；
  * 复用 cluster_display.py 的纯逻辑（速度换算 / 距离格式化）—— 纯函数；
  * 用 pyray 离屏 RenderTexture 画一个紧凑的 2D HUD（车速数字 + 巡航状态 + 前车距离 + 导航文本），
    不涉及 3D 场景 / GLB / GLES，可在 PC 离屏验证。

cluster_config/cluster_display 内部使用顶层导入（from cluster_config import ...），与
cluster_run.py 一致：把 cluster 目录加进 sys.path 即可解析。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pyray as rl

# 本地纯逻辑模块（从 cp cluster/ 复制，无任何 USB/GPU 依赖）。
from cluster_config import current_cluster_theme  # noqa: E402
from cluster_display import (  # noqa: E402
  display_speed,
  format_radar_distance,
  format_navi_distance,
  normalize_metric_setting,
  speed_unit,
)

# 默认 HUD 画布尺寸（横版角落 HUD）。由 Widget 决定贴到屏幕哪个角落。
OVERLAY_DESIGN_WIDTH = 640
OVERLAY_DESIGN_HEIGHT = 240

# 配色（与 cp cluster dark 主题对齐）。
_PANEL_ALPHA = 170
_SPEED_FONT_PX = 104
_UNIT_FONT_PX = 44
_TEXT_FONT_PX = 36
_SPEED_COLOR = (255, 255, 255)   # theme.text
_UNIT_COLOR = (190, 200, 215)    # theme.muted
_MUTED_COLOR = (168, 172, 180)   # faint
_ENGAGED_COLOR = (20, 188, 104)  # GREEN
_PAUSED_COLOR = (244, 172, 54)   # AMBER
_RADAR_COLOR = (38, 132, 255)    # BLUE
_NAVI_COLOR = (199, 125, 255)    # VEHICLE_NAVI
_BG_COLOR = (18, 18, 22, _PANEL_ALPHA)
_BORDER_COLOR = (60, 68, 84, 180)


@dataclass
class ClusterOverlayState:
  """仅保留 2D HUD 需要的最小渲染状态（不同于 cp 巨大的 ClusterUiState）。"""
  speed_kph: float = 0.0
  is_metric: bool = True
  cruise_display_state: str = "off"       # off / paused / engaged
  cruise_kph: int | None = None
  lead_distance_m: float | None = None    # radarState.leadOne.dRel
  navi_text_main: str | None = None
  navi_text_sub: str | None = None
  theme_mode: str = "auto"


def _rl_color(color, alpha: int | None = None) -> rl.Color:
  r, g, b, a = int(color[0]), int(color[1]), int(color[2]), 255
  if len(color) >= 4:
    a = int(color[3])
  if alpha is not None:
    a = alpha
  return rl.Color(r, g, b, a)


class ClusterOverlayRenderer:
  """纯 2D HUD 离屏渲染核。不建窗口 / 不碰 USB 屏 / 不碰 3D 场景。"""

  def __init__(self, width: int = OVERLAY_DESIGN_WIDTH, height: int = OVERLAY_DESIGN_HEIGHT):
    self.width = int(width)
    self.height = int(height)
    self._target: object | None = None
    self._own_target = False
    self._font: object | None = None
    self._font_bold: object | None = None
    self._load_fonts()

  @staticmethod
  def _load_font_once(path: Path, size: int):
    if not path.exists():
      return None
    try:
      font = rl.load_font_ex(str(path), size, None, 0)
      return font if getattr(font, "baseSize", 0) != 0 else None
    except Exception:  # pragma: no cover - 无头/路径问题
      return None

  def _load_fonts(self) -> None:
    # 复用 sp 自带 Inter 字体；加载失败退化到 raylib 默认字体（绝不 crash）。
    fonts_dir = Path(__file__).resolve().parents[4] / "selfdrive" / "assets" / "fonts"
    try:
      self._font = self._load_font_once(fonts_dir / "Inter-Medium.ttf", _TEXT_FONT_PX) or rl.get_font_default()
      self._font_bold = self._load_font_once(fonts_dir / "Inter-Bold.ttf", _SPEED_FONT_PX) or self._font
    except Exception:  # pragma: no cover
      self._font = rl.get_font_default()
      self._font_bold = self._font

  def ensure_target(self) -> object:
    if self._target is None:
      self._target = rl.load_render_texture(self.width, self.height)
      self._own_target = True
      rl.set_texture_filter(self._target.texture, rl.TextureFilter.TEXTURE_FILTER_BILINEAR)
    return self._target

  def unload(self) -> None:
    if self._own_target and self._target is not None:
      rl.unload_render_texture(self._target)
    self._target = None
    self._own_target = False

  # -- 文本工具 ------------------------------------------------------------------
  def _text_width(self, font, text: str, size: float) -> float:
    if font is None or not text:
      return 0.0
    return float(rl.measure_text_ex(font, text, size, 0.0).x)

  def _draw_text(self, font, text, x, y, size, color) -> None:
    if font is None or not text:
      return
    rl.draw_text_ex(font, text, rl.Vector2(float(x), float(y)), float(size), 0.0, color)

  # -- 主渲染 ---------------------------------------------------------------------
  def render(self, state: ClusterOverlayState | None = None) -> None:
    """把 state 画进离屏 RenderTexture。调用前必须先 begin_texture_mode(target)。"""
    if state is None:
      state = ClusterOverlayState()

    theme = current_cluster_theme(state.theme_mode)
    theme_text = getattr(theme, "text", _SPEED_COLOR)
    theme_muted = getattr(theme, "muted", _UNIT_COLOR)

    # 面板背景：半透明圆角矩形。
    panel = rl.Rectangle(0.0, 0.0, float(self.width), float(self.height))
    rl.draw_rectangle_rounded(panel, 0.06, 4, _rl_color(_BG_COLOR, _PANEL_ALPHA))
    rl.draw_rectangle_rounded_lines(panel, 0.06, 4, 2, _rl_color(_BORDER_COLOR))

    # 车速（大数字）+ 单位。
    speed_val = display_speed(state.speed_kph, state.is_metric)
    speed_text = f"{int(round(speed_val))}"
    speed_font_px = _SPEED_FONT_PX if len(speed_text) <= 3 else 84.0
    self._draw_text(self._font_bold, speed_text, 36.0, 22.0, speed_font_px, _rl_color(theme_text))
    speed_right = 36.0 + self._text_width(self._font_bold, speed_text, speed_font_px)
    self._draw_text(self._font, speed_unit(state.is_metric), speed_right + 12.0, 96.0, _UNIT_FONT_PX, _rl_color(theme_muted))

    # 巡航状态（右上）。
    cruise_text = ""
    cruise_color = theme_muted
    if state.cruise_display_state == "engaged":
      cruise_text = "AUTO DRIVE"
      cruise_color = _ENGAGED_COLOR
    elif state.cruise_display_state == "paused":
      cruise_text = "CRUISE"
      cruise_color = _PAUSED_COLOR
    if cruise_text:
      self._draw_text(self._font, cruise_text, 388.0, 22.0, _TEXT_FONT_PX, _rl_color(cruise_color))

    # 前车距离。
    y_cursor = 82.0
    if state.lead_distance_m is not None:
      self._draw_text(self._font, "LEAD", 388.0, y_cursor, _TEXT_FONT_PX, _rl_color(theme_muted))
      self._draw_text(self._font, format_radar_distance(state.lead_distance_m, state.is_metric),
                      510.0, y_cursor, _TEXT_FONT_PX, _rl_color(_RADAR_COLOR))
      y_cursor += 52.0

    # 导航文本（主 / 次）。
    if state.navi_text_main:
      self._draw_text(self._font, state.navi_text_main, 388.0, y_cursor, _TEXT_FONT_PX, _rl_color(_NAVI_COLOR))
      if state.navi_text_sub:
        self._draw_text(self._font, state.navi_text_sub, 388.0, y_cursor + 46.0, _TEXT_FONT_PX, _rl_color(theme_muted))

  # -- 离屏 frame 包装 -------------------------------------------------------------
  @contextmanager
  def render_to_target(self, state: ClusterOverlayState | None = None):
    target = self.ensure_target()
    rl.begin_texture_mode(target)
    try:
      rl.clear_background(_rl_color((0, 0, 0, 0)))
      self.render(state)
    finally:
      rl.end_texture_mode()
    yield target