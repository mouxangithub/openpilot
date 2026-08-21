"""Exact design tokens from openpilot/sunnypilot raylib UI (BIG 2160×1080)."""

from __future__ import annotations

DESIGN = {
  "width": 2160,
  "height": 1080,
  "sidebar_width": 500,
  "onroad_sidebar_width": 300,
  "panel_margin": 50,
  "close_btn_size": 160,
  "close_icon_size": 70,
  "nav_btn_height": 110,
  "nav_icon_size": 70,
  "list_row_height": 170,
  "toggle_width": 210,
  "toggle_height": 120,
  "border_size": 30,
  "border_roundness": 0.12,
  "panel_radius": 30,
  "list_font_size": 40,
  "nav_font_size": 55,
  "hud_speed_size": 176,
  "hud_unit_size": 66,
  "set_speed_size": 90,
  "alert_min_height": 271,
}

COLORS = {
  "sidebar": "#000000",
  "panel": "#292929",
  "panel_op": "#0a0a0a",
  "close_btn": "#292929",
  "close_btn_pressed": "#3b3b3b",
  "on_bg": "#1C65BA",
  "off_bg": "#393939",
  "button_primary": "#465BEA",
  "item_text": "#ffffff",
  "item_desc": "#808080",
  "text_selected": "#ffffff",
  "line_separator": "#3a3a3a",
  "disengaged": "#122839",
  "engaged": "#167f40",
  "override": "#89928d",
  "lat_only": "#00c8c8",
  "long_only": "#961ca8",
  "alert_normal": "#151515f1",
  "alert_user": "#da6f25",
  "alert_critical": "#c92231",
  "hud_engaged": "#80d8a6",
  "hud_disengaged": "#919b95",
  "metric_border": "rgba(255,255,255,0.33)",
  "temp_warn": "#daca25",
  "temp_danger": "#c92231",
}

PANEL_ICONS: dict[str, str] = {
  "device": "sunnypilot/selfdrive/assets/offroad/icon_home.png",
  "network": "icons/network.png",
  "sunnylink": "icons/wifi_strength_full.png",
  "toggles": "sunnypilot/selfdrive/assets/offroad/icon_toggle.png",
  "software": "sunnypilot/selfdrive/assets/offroad/icon_software.png",
  "models": "sunnypilot/selfdrive/assets/offroad/icon_models.png",
  "steering": "sunnypilot/selfdrive/assets/offroad/icon_lateral.png",
  "cruise": "icons/speed_limit.png",
  "visuals": "sunnypilot/selfdrive/assets/offroad/icon_visuals.png",
  "display": "sunnypilot/selfdrive/assets/offroad/icon_display.png",
  "storage": "selfdrive/assets/icons/metric.png",
  "osm": "sunnypilot/selfdrive/assets/offroad/icon_map.png",
  "trips": "sunnypilot/selfdrive/assets/offroad/icon_trips.png",
  "vehicle": "sunnypilot/selfdrive/assets/offroad/icon_vehicle.png",
  "firehose": "sunnypilot/selfdrive/assets/offroad/icon_firehose.png",
  "developer": "icons/shell.png",
}

FONT_FILES = {
  "regular": "selfdrive/assets/fonts/Inter-Regular.ttf",
  "medium": "selfdrive/assets/fonts/Inter-Medium.ttf",
  "semibold": "selfdrive/assets/fonts/Inter-SemiBold.ttf",
  "bold": "selfdrive/assets/fonts/Inter-Bold.ttf",
  "op_medium": "selfdrive/assets/fonts/OpFont-Medium.otf",
  "audiowide": "selfdrive/assets/fonts/Audiowide-Regular.ttf",
}

def tokens_payload() -> dict:
  return {"design": DESIGN, "colors": COLORS, "panel_icons": PANEL_ICONS, "fonts": FONT_FILES}
