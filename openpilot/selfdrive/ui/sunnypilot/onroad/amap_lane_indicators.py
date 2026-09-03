#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import time
import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
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
    if not ui_state.amap_enabled:
      return

    sm = ui_state.sm
    if sm.recv_frame["carStateSP"] < ui_state.started_frame:
      return

    cs_sp = sm["carStateSP"]
    if not cs_sp.amapLineValid:
      return

    self._draw_side(
      rect,
      is_left=True,
      blocked=cs_sp.amapLeftLineBlocked,
      alpha=self._left_alpha_filter.x,
    )
    self._draw_side(
      rect,
      is_left=False,
      blocked=cs_sp.amapRightLineBlocked,
      alpha=self._right_alpha_filter.x,
    )

  def _draw_side(self, rect: rl.Rectangle, is_left: bool, blocked: bool, alpha: float) -> None:
    if alpha <= 0.01:
      return

    MARGIN_X = 12
    BAR_WIDTH = 8
    BAR_HEIGHT = 120
    BAR_Y = rect.y + rect.height * 0.55

    if is_left:
      x = rect.x + MARGIN_X
    else:
      x = rect.x + rect.width - MARGIN_X - BAR_WIDTH

    y = BAR_Y - BAR_HEIGHT / 2

    base_color = rl.Color(0xff, 0x66, 0x33, 0xff) if blocked else rl.Color(0x66, 0xff, 0x99, 0xff)
    color = rl.Color(base_color.r, base_color.g, base_color.b, int(255 * alpha))
    rl.draw_rectangle_rounded(
      rl.Rectangle(x, y, BAR_WIDTH, BAR_HEIGHT),
      0.5,
      8,
      color,
    )


class CarrotNavigationPanel:
  """HUD navigation panel showing carrotMan navigation data.

  Displays turn-by-turn navigation, speed limits, traffic state,
  road information, and ETA/destination data from carrotMan service.
  """

  def __init__(self):
    self.font_bold = gui_app.font(FontWeight.BOLD)
    self.font_demi = gui_app.font(FontWeight.SEMI_BOLD)
    self.font_norm = gui_app.font(FontWeight.NORMAL)

    # Turn icons
    self.turn_icons = {}
    self._load_turn_icons()

    # Panel settings from params
    self.params = ui_state.params
    self._panel_side = int(self.params.get("CarrotPanelSide") or b"0")
    self._panel_opacity = int(self.params.get("CarrotPanelOpacity") or b"100")

    # Cached navigation data
    self._cache = {
      "carrotManAlive": False,
      "activeCarrot": 0,
      "nRoadLimitSpeed": 0,
      "xSpdType": -1,
      "xSpdLimit": 0,
      "xSpdDist": 0,
      "xSpdCountDown": 0,
      "xTurnInfo": -1,
      "xDistToTurn": 0,
      "xTurnCountDown": 0,
      "atcType": "",
      "vTurnSpeed": 0,
      "szPosRoadName": "",
      "szTBTMainText": "",
      "szTBTMainTextNext": "",
      "szNearDirName": "",
      "desiredSpeed": 0,
      "desiredSource": "",
      "trafficState": 0,
      "trafficCountdown": 0,
      "leftSec": 0,
      "nGoPosDist": 0,
      "nGoPosTime": 0,
      "szGoalName": "",
      "szSdiDescr": "",
      "roadCate": 0,
    }

    # Fade filter for smooth appearance
    self._alpha_filter = FirstOrderFilter(0, 0.1, 1 / gui_app.target_fps)

  def _load_turn_icons(self) -> None:
    """Load turn-by-turn navigation icons."""
    icon_size = 128
    icon_dir = "../../sunnypilot/selfdrive/assets/img_"
    try:
      self.turn_icons[1] = gui_app.texture(icon_dir + "turn_l.png", icon_size, icon_size)
      self.turn_icons[2] = gui_app.texture(icon_dir + "turn_r.png", icon_size, icon_size)
      self.turn_icons[3] = gui_app.texture(icon_dir + "lane_change_l.png", icon_size, icon_size)
      self.turn_icons[4] = gui_app.texture(icon_dir + "lane_change_r.png", icon_size, icon_size)
      self.turn_icons[7] = gui_app.texture(icon_dir + "turn_u.png", icon_size, icon_size)
    except Exception:
      pass

  def update(self) -> None:
    """Update navigation data from carrotMan."""
    sm = ui_state.sm

    # Check if carrotMan is alive and updated
    carrot_alive = sm.alive("carrotMan")
    self._cache["carrotManAlive"] = carrot_alive

    if not carrot_alive or sm.recv_frame["carrotMan"] < ui_state.started_frame:
      self._alpha_filter.update(0.0)
      return

    # Read settings
    self._panel_side = int(self.params.get("CarrotPanelSide") or b"0")
    self._panel_opacity = int(self.params.get("CarrotPanelOpacity") or b"100")

    if not sm.updated["carrotMan"]:
      return

    try:
      cm = sm["carrotMan"]
      self._cache["activeCarrot"] = cm.activeCarrot
      self._cache["nRoadLimitSpeed"] = cm.nRoadLimitSpeed
      self._cache["xSpdType"] = cm.xSpdType
      self._cache["xSpdLimit"] = cm.xSpdLimit
      self._cache["xSpdDist"] = cm.xSpdDist
      self._cache["xSpdCountDown"] = cm.xSpdCountDown
      self._cache["xTurnInfo"] = cm.xTurnInfo
      self._cache["xDistToTurn"] = cm.xDistToTurn
      self._cache["xTurnCountDown"] = cm.xTurnCountDown
      self._cache["atcType"] = cm.atcType
      self._cache["vTurnSpeed"] = cm.vTurnSpeed
      self._cache["szPosRoadName"] = cm.szPosRoadName
      self._cache["szTBTMainText"] = cm.szTBTMainText
      self._cache["szTBTMainTextNext"] = cm.szTBTMainTextNext
      self._cache["szNearDirName"] = cm.szNearDirName
      self._cache["desiredSpeed"] = cm.desiredSpeed
      self._cache["desiredSource"] = cm.desiredSource
      self._cache["trafficState"] = cm.trafficState
      self._cache["trafficCountdown"] = cm.trafficCountdown
      self._cache["leftSec"] = cm.leftSec
      self._cache["nGoPosDist"] = cm.nGoPosDist
      self._cache["nGoPosTime"] = cm.nGoPosTime
      self._cache["szGoalName"] = cm.szGoalName
      self._cache["szSdiDescr"] = cm.szSdiDescr
      self._cache["roadCate"] = cm.roadCate
    except Exception:
      pass

    # Determine if panel should be visible
    c = self._cache
    has_dest = c["nGoPosDist"] > 0 and c["nGoPosTime"] > 0
    has_goal = bool(c["szGoalName"])
    has_turn = c["xTurnInfo"] > 0
    has_camera = c["xSpdLimit"] > 0 and c["xSpdDist"] > 0
    has_traffic = c["trafficState"] > 0
    has_road = bool(c["szPosRoadName"])
    has_sdi = bool(c["szSdiDescr"])
    has_tbt = bool(c["szTBTMainText"])

    should_show = has_dest or has_goal or has_turn or has_camera or has_traffic or has_road or has_sdi or has_tbt
    self._alpha_filter.update(1.0 if should_show else 0.0)

  @property
  def visible(self) -> bool:
    return self._alpha_filter.x > 0.01

  def render(self, rect: rl.Rectangle) -> None:
    """Render the navigation panel."""
    if not self.visible:
      return

    alpha = int(255 * self._alpha_filter.x)
    if alpha < 10:
      return

    c = self._cache
    if not c["carrotManAlive"]:
      return

    # Panel dimensions
    panel_w = 790
    panel_h = 240
    panel_x = rect.x - 11 if self._panel_side == 0 else rect.x + rect.width - panel_w + 11
    panel_y = rect.y + rect.height - panel_h - 120

    # Draw panel background
    bg_color = rl.Color(0, 105, 148, min(alpha, self._panel_opacity))
    border_color = rl.Color(255, 255, 255, int(alpha * 0.3))
    rl.draw_rectangle_rounded(
      rl.Rectangle(panel_x, panel_y - 60, panel_w, panel_h + 60),
      0.1,
      30,
      bg_color,
    )
    rl.draw_rectangle_rounded_lines_ex(
      rl.Rectangle(panel_x, panel_y - 60, panel_w, panel_h + 60),
      0.1,
      30,
      1,
      border_color,
    )

    # TBT Main Text (top)
    if c["szTBTMainText"]:
      tbt_text = c["szTBTMainText"]
      if c["szNearDirName"]:
        tbt_text += " -> " + c["szNearDirName"]
      tbt_text = self._truncate_text(tbt_text, panel_w - 40, 40)
      tbt_size = measure_text_cached(self.font_bold, tbt_text, 40)
      rl.draw_text_ex(
        self.font_bold,
        tbt_text,
        rl.Vector2(panel_x + 20, panel_y - 55 + (45 - tbt_size.y) / 2),
        40,
        0,
        rl.Color(255, 255, 255, alpha),
      )

    # Turn info (left side)
    if c["xTurnInfo"] > 0:
      self._render_turn_info(panel_x, panel_y, c, alpha)

    # Info section (right of turn icon)
    info_x = panel_x + 190
    info_y = panel_y + 15

    # ETA and destination
    if c["nGoPosDist"] > 0 and c["nGoPosTime"] > 0:
      self._render_eta_info(info_x, info_y, c, alpha)

    # Goal name only
    elif c["szGoalName"]:
      goal_text = "🏁 " + c["szGoalName"]
      goal_text = self._truncate_text(goal_text, panel_w - 210, 36)
      rl.draw_text_ex(
        self.font_demi,
        goal_text,
        rl.Vector2(info_x, info_y),
        36,
        0,
        rl.Color(180, 230, 255, alpha),
      )

    # SDI description or road name (bottom)
    bottom_y = panel_y + 190
    if c["szSdiDescr"]:
      self._render_sdi_info(info_x, bottom_y, c, alpha)
    elif c["szPosRoadName"]:
      self._render_road_info(info_x, bottom_y, c, alpha)

    # Speed limit and desired speed
    if c["nRoadLimitSpeed"] > 0 or (c["desiredSpeed"] > 0 and c["desiredSource"]):
      self._render_speed_info(info_x, panel_y + 140, c, alpha, rect)

    # Speed camera info
    if c["xSpdLimit"] > 0 and c["xSpdDist"] > 0:
      self._render_camera_info(info_x, bottom_y, c, alpha)

    # Traffic light info
    if c["trafficState"] > 0:
      cam_y = bottom_y + 80 if c["xSpdLimit"] > 0 and c["xSpdDist"] > 0 else bottom_y
      self._render_traffic_info(info_x, cam_y, c, alpha)

  def _render_turn_info(self, panel_x: int, panel_y: int, c: dict, alpha: int) -> None:
    """Render turn icon and distance."""
    icon_x = panel_x + 20
    icon_y = panel_y + 20
    icon_sz = 128

    # ATC type background
    if c["atcType"]:
      atc_green = rl.Color(0, 180, 0, 100 if "prepare" in c["atcType"] else 255)
      rl.draw_rectangle_rounded(
        rl.Rectangle(icon_x - 16, icon_y - 26, 160, 230),
        0.1,
        15,
        atc_green,
      )

    # Draw turn icon
    turn_type = c["xTurnInfo"]
    if turn_type in self.turn_icons:
      icon = self.turn_icons[turn_type]
      rl.draw_texture_ex(icon, rl.Vector2(icon_x, icon_y), 0.0, 1.0, rl.Color(255, 255, 255, alpha))
    else:
      # Fallback text for turn types without icons
      turn_label = "TG" if turn_type == 6 else ("目的地" if turn_type == 8 else f"减速:{turn_type}")
      turn_size = measure_text_cached(self.font_bold, turn_label, 35)
      rl.draw_text_ex(
        self.font_bold,
        turn_label,
        rl.Vector2(icon_x + icon_sz / 2 - turn_size.x / 2, icon_y + icon_sz / 2 - turn_size.y / 2),
        35,
        0,
        rl.Color(255, 255, 255, alpha),
      )

    # v-Turn speed (curve advisory)
    if 0 < c["vTurnSpeed"] < 120:
      vturn_text = f"{c['vTurnSpeed']}km/h"
      rl.draw_text_ex(
        self.font_bold,
        vturn_text,
        rl.Vector2(icon_x - 16 + (160 - measure_text_cached(self.font_bold, vturn_text, 34).x) / 2, icon_y + icon_sz + 4),
        34,
        0,
        rl.Color(255, 200, 50, alpha),
      )

    # Turn distance
    if c["xDistToTurn"] > 0:
      dist_text = self._format_distance(c["xDistToTurn"])
      dist_size = measure_text_cached(self.font_bold, dist_text, 40)
      rl.draw_text_ex(
        self.font_bold,
        dist_text,
        rl.Vector2(icon_x - 16 + (160 - dist_size.x) / 2, icon_y + icon_sz + 10),
        40,
        0,
        rl.Color(255, 255, 255, alpha),
      )

    # Turn countdown
    if c["xTurnCountDown"] > 0:
      countdown_text = f"{c['xTurnCountDown']}s"
      rl.draw_text_ex(
        self.font_bold,
        countdown_text,
        rl.Vector2(icon_x - 16 + (160 - measure_text_cached(self.font_bold, countdown_text, 30).x) / 2, icon_y + icon_sz + 55),
        30,
        0,
        rl.Color(255, 220, 100, alpha),
      )

  def _render_eta_info(self, info_x: int, info_y: int, c: dict, alpha: int) -> None:
    """Render ETA and destination info."""
    # ETA calculation
    remaining_minutes = c["nGoPosTime"] / 60
    now = time.localtime()
    eta_minutes = now.tm_min + int(remaining_minutes)
    eta_hour = (now.tm_hour + eta_minutes // 60) % 24
    eta_min = eta_minutes % 60

    if remaining_minutes >= 60:
      eta_str = f"ETA: {eta_minutes // 60}h{eta_minutes % 60:.0f}m({eta_hour:02d}:{eta_min:02d})"
    else:
      eta_str = f"ETA: {remaining_minutes:.0f}min({eta_hour:02d}:{eta_min:02d})"

    rl.draw_text_ex(
      self.font_bold,
      eta_str,
      rl.Vector2(info_x, info_y),
      50,
      0,
      rl.Color(255, 255, 255, alpha),
    )

    # Destination distance
    dest_dist = self._format_distance(c["nGoPosDist"])
    if c["szGoalName"]:
      dest_dist += " 🏁 " + c["szGoalName"]
    dest_dist = self._truncate_text(dest_dist, 580, 40)
    rl.draw_text_ex(
      self.font_bold,
      dest_dist,
      rl.Vector2(info_x, info_y + 55),
      40,
      0,
      rl.Color(255, 255, 255, alpha),
    )

  def _render_sdi_info(self, info_x: int, bottom_y: int, c: dict, alpha: int) -> None:
    """Render SDI description with green background."""
    sdi_text = c["szSdiDescr"]
    sdi_size = measure_text_cached(self.font_bold, sdi_text, 40)

    # Green background
    rl.draw_rectangle_rounded(
      rl.Rectangle(info_x - 10, bottom_y - 2, sdi_size.x + 20, sdi_size.y + 6),
      0.2,
      10,
      rl.Color(0, 180, 0, alpha),
    )

    rl.draw_text_ex(
      self.font_bold,
      sdi_text,
      rl.Vector2(info_x, bottom_y),
      40,
      0,
      rl.Color(255, 255, 255, alpha),
    )

  def _render_road_info(self, info_x: int, bottom_y: int, c: dict, alpha: int) -> None:
    """Render road name with category tag."""
    road_cate_labels = {1: "高速", 2: "城快", 3: "国道", 4: "省道", 5: "县道", 6: "乡道"}
    cate_label = road_cate_labels.get(c["roadCate"], "")

    x_offset = 0
    if cate_label:
      cate_size = measure_text_cached(self.font_bold, cate_label, 28)
      cate_w = cate_size.x + 16

      # Category tag background
      cate_bg = rl.Color(0, 130, 0, 200) if c["roadCate"] == 1 else (
        rl.Color(200, 130, 0, 200) if c["roadCate"] == 2 else rl.Color(100, 100, 100, 200)
      )
      rl.draw_rectangle_rounded(
        rl.Rectangle(info_x, bottom_y + 2, cate_w, 30),
        0.2,
        8,
        cate_bg,
      )
      rl.draw_text_ex(
        self.font_bold,
        cate_label,
        rl.Vector2(info_x + 8, bottom_y + 2 + (30 - cate_size.y) / 2),
        28,
        0,
        rl.Color(255, 255, 255, alpha),
      )
      x_offset = cate_w + 8

    # Road name
    road_name = self._truncate_text(c["szPosRoadName"], 580 - x_offset, 40)
    road_size = measure_text_cached(self.font_bold, road_name, 40)
    rl.draw_text_ex(
      self.font_bold,
      road_name,
      rl.Vector2(info_x + x_offset, bottom_y + (30 - road_size.y) / 2),
      40,
      0,
      rl.Color(255, 255, 255, alpha),
    )

  def _render_speed_info(self, info_x: int, rs_y: int, c: dict, alpha: int, rect: rl.Rectangle) -> None:
    """Render current road speed limit and desired speed."""
    has_road_limit = c["nRoadLimitSpeed"] > 0
    has_apply = c["desiredSpeed"] > 0 and c["desiredSource"]

    if has_road_limit:
      # Get current speed for overspeed check
      v_ego = ui_state.sm["carState"].vEgo
      speed_kph = v_ego * 3.6
      over_limit = speed_kph > c["nRoadLimitSpeed"] + 2

      limit_bg = rl.Color(255, 50, 50, 210) if over_limit else rl.Color(255, 255, 255, 210)
      limit_text_color = rl.Color(255, 255, 255, alpha) if over_limit else rl.Color(0, 0, 0, alpha)

      # LIMIT label
      rl.draw_text_ex(
        self.font_bold,
        "LIMIT",
        rl.Vector2(info_x, rs_y - 28),
        24,
        0,
        rl.Color(255, 255, 255, alpha),
      )

      # Speed box
      rl.draw_rectangle_rounded(
        rl.Rectangle(info_x, rs_y, 90, 42),
        0.2,
        12,
        limit_bg,
      )
      rl.draw_text_ex(
        self.font_bold,
        str(c["nRoadLimitSpeed"]),
        rl.Vector2(info_x + (90 - measure_text_cached(self.font_bold, str(c["nRoadLimitSpeed"]), 36).x) / 2, rs_y + 3),
        36,
        0,
        limit_text_color,
      )

    if has_apply:
      apply_x = info_x + 110 if has_road_limit else info_x
      src_text = self._truncate_text(c["desiredSource"], 120, 24)
      rl.draw_text_ex(
        self.font_bold,
        src_text,
        rl.Vector2(apply_x, rs_y - 28),
        24,
        0,
        rl.Color(255, 180, 50, alpha),
      )

      apply_bg = rl.Color(255, 180, 50, 210)
      rl.draw_rectangle_rounded(
        rl.Rectangle(apply_x, rs_y, 90, 42),
        0.2,
        12,
        apply_bg,
      )
      rl.draw_text_ex(
        self.font_bold,
        str(c["desiredSpeed"]),
        rl.Vector2(apply_x + (90 - measure_text_cached(self.font_bold, str(c["desiredSpeed"]), 36).x) / 2, rs_y + 3),
        36,
        0,
        rl.Color(255, 255, 255, alpha),
      )

  def _render_camera_info(self, info_x: int, cam_y: int, c: dict, alpha: int) -> None:
    """Render speed camera info."""
    circle_r = 35
    circle_cx = info_x + circle_r
    circle_cy = cam_y + circle_r

    # Get current speed for overspeed check
    v_ego = ui_state.sm["carState"].vEgo
    speed = v_ego * 3.6 if ui_state.is_metric else v_ego * 2.237
    overspeed = round(speed) > c["xSpdLimit"]

    circle_color = rl.Color(255, 50, 50, 255) if overspeed else rl.Color(255, 80, 80, 255)

    # Draw circle
    rl.draw_circle_lines_ex(circle_cx, circle_cy, circle_r, 4, circle_color)
    rl.draw_circle_v(rl.Vector2(circle_cx, circle_cy), circle_r, rl.Color(255, 255, 255, 200))

    # Speed limit number
    text_color = rl.Color(255, 50, 50, 255) if overspeed else rl.Color(0, 0, 0, alpha)
    rl.draw_text_ex(
      self.font_bold,
      str(c["xSpdLimit"]),
      rl.Vector2(circle_cx - circle_r + (circle_r * 2 - measure_text_cached(self.font_bold, str(c["xSpdLimit"]), 40).x) / 2,
                 circle_cy - circle_r + (circle_r * 2 - measure_text_cached(self.font_bold, str(c["xSpdLimit"]), 40).y) / 2),
      40,
      0,
      text_color,
    )

    # Camera distance
    cam_dist = self._format_distance(c["xSpdDist"])
    if c["xSpdCountDown"] > 0:
      cam_dist += f" {c['xSpdCountDown']}s"
    rl.draw_text_ex(
      self.font_bold,
      cam_dist,
      rl.Vector2(circle_cx + circle_r + 15, circle_cy - 20),
      36,
      0,
      rl.Color(255, 255, 255, alpha),
    )

    # Camera type
    type_labels = {2: "区间测速", 4: "区间测速", 22: "减速带", 100: "移动测速"}
    type_label = type_labels.get(c["xSpdType"], "")
    if type_label:
      rl.draw_text_ex(
        self.font_norm,
        type_label,
        rl.Vector2(circle_cx + circle_r + 15, circle_cy + 18),
        26,
        0,
        rl.Color(255, 200, 50, alpha),
      )

  def _render_traffic_info(self, info_x: int, tl_y: int, c: dict, alpha: int) -> None:
    """Render traffic light info."""
    light_colors = {1: rl.Color(255, 50, 50), 2: rl.Color(50, 255, 50), 3: rl.Color(50, 255, 100)}
    light_texts = {1: "红灯", 2: "绿灯", 3: "左转绿灯"}

    light_color = light_colors.get(c["trafficState"], rl.Color(200, 200, 50))
    light_text = light_texts.get(c["trafficState"], "信号灯")

    light_r = 14
    light_cx = info_x + light_r
    light_cy = tl_y + light_r

    # Draw light
    rl.draw_circle_lines_ex(light_cx, light_cy, light_r, 2, rl.Color(60, 60, 60, alpha))
    rl.draw_circle_v(rl.Vector2(light_cx, light_cy), light_r, light_color)

    rl.draw_text_ex(
      self.font_demi,
      light_text,
      rl.Vector2(light_cx + light_r + 10, tl_y),
      32,
      0,
      light_color,
    )

    # Countdown
    countdown = c["trafficCountdown"] if c["trafficCountdown"] > 0 else c["leftSec"]
    if countdown > 0:
      countdown_text = f"{countdown}s"
      rl.draw_text_ex(
        self.font_bold,
        countdown_text,
        rl.Vector2(light_cx + light_r + 10 + 140, tl_y),
        30,
        0,
        rl.Color(255, 255, 255, alpha),
      )

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
