"""sp onroad 主屏的 Cluster HUD overlay Widget。

把 cp cluster 的纯 2D HUD 渲染核（ClusterOverlayRenderer）叠加到 sp 自带屏的 onroad 主屏
右下角。融合统一、不搞两套：复用一个渲染核，由 sp 的 pyray/GPU 消费离屏 RGBA 纹理。

开关：Params "ClusterHud"（已在 sp 的 carrot config 注册）。默认关闭，打开后只在 onroad
主屏显示，不遮挡关键信息。
"""

from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.common.params import Params

from openpilot.sunnypilot.carrot.cluster_view.cluster_overlay_renderer import (
  ClusterOverlayRenderer,
  ClusterOverlayState,
)

# HUD 在 onroad 主屏的占屏比例（宽）。portrait 屏上按此宽度等比缩放出高度。
_OVERLAY_WIDTH_FRAC = 0.52
_OVERLAY_MARGIN = 24.0

_THEME_MODE_BY_PARAM = {
  0: "auto",
  1: "dark",
  2: "light",
}


class ClusterOverlay(Widget):
  def __init__(self, width: int = 640, height: int = 240):
    super().__init__()
    self._params = Params()
    self._renderer = ClusterOverlayRenderer(width, height)
    self._state = ClusterOverlayState()
    self.set_visible(False)

  def _theme_mode(self) -> str:
    try:
      v = self._params.get("ClusterHudTheme")
      if v is None:
        return "auto"
      if isinstance(v, bytes):
        v = v.decode("utf-8", "ignore")
      return _THEME_MODE_BY_PARAM.get(int(v), "auto")
    except Exception:
      return "auto"

  def _is_metric(self) -> bool:
    try:
      return bool(self._params.get_bool("IsMetric"))
    except Exception:
      return True

  def _read_int(self, key: str, default: int = 0) -> int:
    try:
      v = self._params.get(key)
      if v is None:
        return default
      if isinstance(v, bytes):
        v = v.decode("utf-8", "ignore")
      return int(float(v))
    except Exception:
      return default

  def _update_state(self) -> None:
    # 开关：Params 控制可见性（关闭时 _render 不会执行）。
    try:
      enabled = bool(self._params.get_bool("ClusterHud"))
    except Exception:
      enabled = False
    self.set_visible(enabled)
    if not enabled:
      return

    sm = ui_state.sm
    state = ClusterOverlayState(
      is_metric=self._is_metric(),
      theme_mode=self._theme_mode(),
      brightness=self._read_int("ClusterHudBrightness", 100),
      mirror=bool(self._params.get_bool("ClusterHudMirror")),
      orientation=self._read_int("ClusterHudOrientation", 0),
      show_radar=bool(self._params.get_bool("ClusterHudRadarDisplay")),
    )

    def _service(name: str):
      """防御性取消息：service 未订阅 / 不存在都返回 None，绝不因一条消息崩 UI。"""
      try:
        if name in sm.services:
          return sm[name]
      except Exception:
        return None
      return None

    try:
      car = _service("carState")
      if car is not None:
        # vEgo 单位 m/s；仪表习惯显示 kph。优先 vEgoCluster（已有则用）。
        v = getattr(car, "vEgoCluster", 0.0) or 0.0
        if not v:
          v = getattr(car, "vEgo", 0.0) or 0.0
        state.speed_kph = float(v) * 3.6

      cruise = _service("cruiseState")
      if cruise is not None:
        v_cruise = getattr(cruise, "vCruise", 0.0) or 0.0
        if v_cruise:
          state.cruise_kph = int(round(float(v_cruise) * 3.6))
        enabled = bool(getattr(cruise, "enabled", False))
        available = bool(getattr(cruise, "available", False))
        state.cruise_display_state = "engaged" if enabled else ("paused" if available else "off")

      radar = _service("radarState")
      if radar is not None:
        lead = getattr(radar, "leadOne", None)
        if lead is not None:
          d_rel = float(getattr(lead, "dRel", 0.0) or 0.0)
          state.lead_distance_m = d_rel if d_rel > 0.0 else None

      nav = _service("navigationState")
      if nav is not None:
        state.navi_text_main = getattr(nav, "maneuverText", None) or None
        dist = getattr(nav, "distanceToManeuver", 0.0) or 0.0
        if dist:
          from openpilot.sunnypilot.carrot.cluster_view.cluster_overlay_renderer import format_navi_distance
          sub = format_navi_distance(float(dist), state.is_metric)
          state.navi_text_sub = sub if state.navi_text_main else None
    except Exception:
      # 任一段读取失败都保留默认状态，绝不连带崩 onroad UI。
      pass

    self._state = state

  def _render(self, rect: rl.Rectangle, /) -> None:
    target = self._renderer.ensure_target()
    rl.begin_texture_mode(target)
    try:
      rl.clear_background(rl.Color(0, 0, 0, 0))
      self._renderer.render(self._state)
    finally:
      rl.end_texture_mode()

    source = rl.Rectangle(0.0, 0.0, float(target.texture.width), float(target.texture.height))

    # ClusterHudMirror：水平翻转（origin.x 移到 rect 右侧）。
    dest = rect
    if self._state.mirror:
      dest = rl.Rectangle(
        rect.x + rect.width,
        rect.y,
        -rect.width,
        rect.height,
      )

    # ClusterHudOrientation：0=正常, 1=上下翻转, 2=左转90°, 3=右转90°。
    rotation = {0: 0.0, 1: 180.0, 2: 90.0, 3: -90.0}.get(self._state.orientation, 0.0)
    # 旋转时以中心为原点。
    origin = rl.Vector2(rect.width * 0.5, rect.height * 0.5)
    # 旋转后需要调整 dest 位置使面板仍在屏幕内。
    if rotation != 0.0:
      dest = rl.Rectangle(rect.x, rect.y, rect.width, rect.height)

    # Brightness 控制整体透明度。
    alpha = max(1, min(255, int(255 * self._state.brightness / 100.0)))
    tint = rl.Color(255, 255, 255, alpha)

    rl.draw_texture_pro(
      target.texture,
      source,
      dest,
      origin,
      rotation,
      tint,
    )
    return None

  def overlay_rect(self, content_rect: rl.Rectangle) -> rl.Rectangle:
    """计算 onroad 主屏右下角的 HUD 目标矩形（等比缩放自设计画布）。"""
    width = content_rect.width * _OVERLAY_WIDTH_FRAC
    height = width * (self._renderer.height / self._renderer.width)
    x = content_rect.x + content_rect.width - width - _OVERLAY_MARGIN
    y = content_rect.y + content_rect.height - height - _OVERLAY_MARGIN
    return rl.Rectangle(x, y, width, height)