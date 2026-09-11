#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from __future__ import annotations

import time
import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.common.filter_simple import FirstOrderFilter


class AmapLaneIndicators:
  """Onroad overlay showing Amap navigation lane-line state.

  Displays small coloured bars along the left/right screen edges when
  ``AmapEnabled`` is true and ``carStateSP.amapLineValid`` is true:

  - Red/orange: the corresponding lane line is considered blocked
    (solid white/yellow, double yellow, or road edge).
  - White/green: the line is valid and not blocked.

  The bars fade smoothly in/out via first-order filters.
  """

  def __init__(self):
    self._left_alpha_filter = FirstOrderFilter(0, 0.15, 1 / gui_app.target_fps)
    self._right_alpha_filter = FirstOrderFilter(0, 0.15, 1 / gui_app.target_fps)

  def update(self) -> None:
    sm = ui_state.sm
    enabled = ui_state.amap_enabled
    valid = enabled and sm.recv_frame["carStateSP"] >= ui_state.started_frame
    if not valid:
      self._left_alpha_filter.update(0.0)
      self._right_alpha_filter.update(0.0)
      return

    cs_sp = sm["carStateSP"]
    line_valid = cs_sp.amapLineValid
    self._left_alpha_filter.update(1.0 if line_valid else 0.0)
    self._right_alpha_filter.update(1.0 if line_valid else 0.0)

  @property
  def visible(self) -> bool:
    return self._left_alpha_filter.x > 0.01 or self._right_alpha_filter.x > 0.01

  def render(self, rect: rl.Rectangle) -> None:
    """Render the compact semi-transparent glass navigation card.

    Slim three-zone layout (turn icon | TBT + ETA/destination | distance +
    countdown, then a badge row) that stays clear of the top speed cluster:
    the speed-limit circle and road-name chip already live next to the
    cluster speed, so the card no longer repeats them as large blocks.
    """
    if not self.visible:
      return

    c = self._cache
    if not c["carrotManAlive"]:
      return

    opacity = min(1.0, max(0.0, self._panel_opacity / 100.0))
    a = self._alpha_filter.x * opacity
    if a < 0.05:
      return

    # Panel geometry - slim glass card, horizontally centered and raised
    # above the steering torque arc band (bottom 180px), so it never overlaps
    # the arc or the top speed cluster. CarrotPanelSide is intentionally
    # ignored — the user prefers a fixed centered card.
    panel_w = 560
    panel_h = 150
    panel_x = int(rect.x + (rect.width - panel_w) / 2)
    panel_y = int(rect.y + rect.height - panel_h - 280)
    panel = rl.Rectangle(panel_x, panel_y, panel_w, panel_h)

    # Glass background: dark, semi-transparent, thin light border.
    rl.draw_rectangle_rounded(panel, 0.16, 24, rl.Color(10, 16, 24, int(140 * a)))
    rl.draw_rectangle_rounded_lines_ex(
      panel, 0.16, 24, 1, rl.Color(255, 255, 255, int(30 * a)),
    )

    ai = int(255 * a)   # primary text alpha
    ad = int(185 * a)   # secondary text alpha

    # --- head row: turn icon | TBT + ETA/destination | distance + countdown
    icon_x = panel_x + 16
    icon_y = panel_y + 14
    icon_sz = 56
    if c["xTurnInfo"] > 0:
      if c["atcType"]:
        atc_alpha = int(90 * a) if "prepare" in c["atcType"] else int(217 * a)
        rl.draw_rectangle_rounded(
          rl.Rectangle(icon_x - 4, icon_y - 4, icon_sz + 8, icon_sz + 8), 0.24, 12,
          rl.Color(22, 200, 122, atc_alpha),
        )
      icon = self.turn_icons.get(c["xTurnInfo"])
      if icon is not None:
        rl.draw_texture_ex(icon, rl.Vector2(icon_x, icon_y), 0.0, icon_sz / 128.0,
                           rl.Color(255, 255, 255, ai))
      else:
        label = "TG" if c["xTurnInfo"] == 6 else ("目的地" if c["xTurnInfo"] == 8 else f"减速:{c['xTurnInfo']}")
        label = self._truncate_text(label, icon_sz + 8, 16)
        ls = measure_text_cached(self.font_bold, label, 16)
        rl.draw_text_ex(self.font_bold, label,
                        rl.Vector2(icon_x - 4 + (icon_sz + 8 - ls.x) / 2, icon_y - 4 + (icon_sz + 8 - ls.y) / 2),
                        16, 0, rl.Color(255, 255, 255, ai))

    text_x = panel_x + 92
    max_text_w = panel_w - 92 - 110
    if c["szTBTMainText"]:
      tbt = c["szTBTMainText"]
      if c["szNearDirName"]:
        tbt += " -> " + c["szNearDirName"]
      tbt = self._truncate_text(tbt, max_text_w, 30)
      rl.draw_text_ex(self.font_bold, tbt, rl.Vector2(text_x, panel_y + 14), 30, 0,
                      rl.Color(255, 255, 255, ai))

    sub = ""
    if c["nGoPosDist"] > 0 and c["nGoPosTime"] > 0:
      remaining = c["nGoPosTime"] / 60
      now = time.localtime()
      total_min = now.tm_min + int(remaining)
      hh = (now.tm_hour + total_min // 60) % 24
      mm = total_min % 60
      if remaining >= 60:
        eta = f"剩余 {remaining // 60}h{remaining % 60:.0f}m({hh:02d}:{mm:02d})"
      else:
        eta = f"剩余 {remaining:.0f}min({hh:02d}:{mm:02d})"
      sub = f"{eta} · {self._format_distance(c['nGoPosDist'])}"
      if c["szGoalName"]:
        sub += " \U0001F3C1 " + c["szGoalName"]
    elif c["szGoalName"]:
      sub = "\U0001F3C1 " + c["szGoalName"]
    if sub:
      sub = self._truncate_text(sub, max_text_w, 20)
      rl.draw_text_ex(self.font_demi, sub, rl.Vector2(text_x, panel_y + 50), 20, 0,
                      rl.Color(255, 255, 255, ad))

    if c["xDistToTurn"] > 0:
      dist_text = self._format_distance(c["xDistToTurn"])
      ds = measure_text_cached(self.font_bold, dist_text, 30)
      rl.draw_text_ex(self.font_bold, dist_text,
                      rl.Vector2(panel_x + panel_w - 16 - ds.x, panel_y + 14), 30, 0,
                      rl.Color(255, 255, 255, ai))
    if c["xTurnCountDown"] > 0:
      cd_text = f"{c['xTurnCountDown']}s"
      cs = measure_text_cached(self.font_bold, cd_text, 20)
      rl.draw_text_ex(self.font_bold, cd_text,
                      rl.Vector2(panel_x + panel_w - 16 - cs.x, panel_y + 50), 20, 0,
                      rl.Color(255, 220, 100, ai))

    # --- badge row: road/SDI | desired speed | camera | traffic light | curve
    chip_x = panel_x + 16
    chip_y = panel_y + panel_h - 38
    v_ego_kph = ui_state.sm["carState"].vEgo * 3.6

    if c["szSdiDescr"]:
      chip_x = self._draw_chip(chip_x, chip_y, c["szSdiDescr"],
                               rl.Color(22, 160, 74, int(200 * a)), rl.Color(255, 255, 255, ai))
    elif c["szPosRoadName"]:
      cate_labels = {1: "高速", 2: "城快", 3: "国道", 4: "省道", 5: "县道", 6: "乡道"}
      chip_x = self._draw_chip(chip_x, chip_y, c["szPosRoadName"],
                               rl.Color(255, 255, 255, int(32 * a)), rl.Color(255, 255, 255, int(230 * a)),
                               tag=cate_labels.get(c["roadCate"], ""))

    if c["desiredSpeed"] > 0 and c["desiredSource"]:
      chip_x = self._draw_chip(chip_x, chip_y, f"{c['desiredSource'][:8]} {c['desiredSpeed']}",
                               rl.Color(255, 180, 50, int(220 * a)), rl.Color(16, 20, 24, ai))

    if c["xSpdLimit"] > 0 and c["xSpdDist"] > 0:
      over = v_ego_kph > c["xSpdLimit"]
      cam_text = f"\u25c9{c['xSpdLimit']} {self._format_distance(c['xSpdDist'])}"
      if c["xSpdCountDown"] > 0:
        cam_text += f" {c['xSpdCountDown']}s"
      chip_x = self._draw_chip(chip_x, chip_y, cam_text,
                               rl.Color(239, 68, 68, int(210 * a) if over else int(90 * a)),
                               rl.Color(255, 255, 255, ai))

    if c["trafficState"] > 0:
      light_colors = {1: rl.Color(255, 90, 90), 2: rl.Color(74, 222, 128), 3: rl.Color(52, 211, 153)}
      light_texts = {1: "红灯", 2: "绿灯", 3: "左转绿灯"}
      lc = light_colors.get(c["trafficState"], rl.Color(255, 214, 68))
      lt = light_texts.get(c["trafficState"], "信号灯")
      cd = c["trafficCountdown"] if c["trafficCountdown"] > 0 else c["leftSec"]
      chip_x = self._draw_chip(chip_x, chip_y, f"{lt} {cd}s" if cd > 0 else lt,
                               rl.Color(255, 255, 255, int(26 * a)), lc, dot=lc)

    if 0 < c["vTurnSpeed"] < 120:
      chip_x = self._draw_chip(chip_x, chip_y, f"弯道 {c['vTurnSpeed']}km/h",
                               rl.Color(255, 200, 50, int(46 * a)), rl.Color(255, 200, 50, ai))

  def _draw_chip(self, x: float, y: float, text: str, bg: rl.Color, fg: rl.Color,
                 tag: str = "", dot: rl.Color | None = None) -> float:
    """Draw one pill badge; returns the x coordinate for the next chip."""
    font_size = 20
    text = self._truncate_text(text, 240, font_size)
    ts = measure_text_cached(self.font_bold, text, font_size)
    w = ts.x + 24
    tag_bg_w = 0.0
    if tag:
      tag_bg_w = measure_text_cached(self.font_bold, tag, 16).x + 12
      w += tag_bg_w + 6
    if dot is not None:
      w += 16
    h = 30
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.5, 12, bg)
    tx = x + 12
    if dot is not None:
      rl.draw_circle_v(rl.Vector2(tx + 6, y + h / 2), 6, dot)
      tx += 16
    if tag:
      tag_s = measure_text_cached(self.font_bold, tag, 16)
      rl.draw_rectangle_rounded(rl.Rectangle(tx, y + (h - 20) / 2, tag_bg_w, 20), 0.3, 8,
                                rl.Color(255, 255, 255, 46))
      rl.draw_text_ex(self.font_bold, tag, rl.Vector2(tx + 6, y + (h - tag_s.y) / 2), 16, 0, fg)
      tx += tag_bg_w + 6
    rl.draw_text_ex(self.font_bold, text, rl.Vector2(tx, y + (h - ts.y) / 2), font_size, 0, fg)
    return x + w + 8

  def _format_distance(self, dist_meters: int) -> str:
    """Format distance string based on metric/imperial."""
    if ui_state.is_metric:
      if dist_meters < 1000:
        return f"{dist_meters} m"
      return f"{dist_meters / 1000:.1f} km"
    else:
      dist_ft = dist_meters * 3.28084
      if dist_ft < 1609:
        return f"{int(dist_ft)} ft"
      return f"{dist_meters / 1609.344:.1f} mi"

  def _truncate_text(self, text: str, max_width: float, font_size: int) -> str:
    """Truncate text to fit within max_width."""
    text_size = measure_text_cached(self.font_bold, text, font_size)
    if text_size.x <= max_width:
      return text

    truncated = text
    while len(truncated) > 3:
      truncated = truncated[:-1]
      text_size = measure_text_cached(self.font_bold, truncated + "...", font_size)
      if text_size.x <= max_width:
        return truncated + "..."

    return text[:3] + "..."
