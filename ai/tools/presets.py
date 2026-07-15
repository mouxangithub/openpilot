"""Dragonpilot tune presets — stationary apply only."""

from __future__ import annotations

from typing import Any

# Preset id -> param writes (string values for Params.put compatibility)
TUNE_PRESETS: dict[str, dict[str, Any]] = {
  "comfort_follow": {
    "name": "舒适跟车",
    "description": "ACM 滑行 + 纵向人格舒适",
    "params": {"dp_lon_acm": "1", "LongitudinalPersonality": "2"},
  },
  "standard_follow": {
    "name": "标准跟车",
    "description": "关闭 ACM/AEM/APM，纵向人格标准",
    "params": {
      "dp_lon_acm": "0",
      "dp_lon_aem": "0",
      "dp_lon_apm": "0",
      "LongitudinalPersonality": "1",
    },
  },
  "sport_follow": {
    "name": "激进跟车",
    "description": "AEM+APM 开启，纵向人格激进",
    "params": {
      "dp_lon_aem": "1",
      "dp_lon_apm": "1",
      "LongitudinalPersonality": "0",
    },
  },
  "alka_enable": {
    "name": "开启 ALKA",
    "description": "全速域横向车道保持",
    "params": {"dp_lat_alka": "1"},
  },
  "alka_disable": {
    "name": "关闭 ALKA",
    "params": {"dp_lat_alka": "0"},
  },
  "lca_basic": {
    "name": "变道辅助 20mph",
    "description": "LCA 20mph，无自动变道",
    "params": {"dp_lat_lca_speed": "20", "dp_lat_lca_auto_sec": "0"},
  },
  "ui_rainbow_on": {
    "name": "彩虹路径",
    "params": {"dp_ui_rainbow": "1"},
  },
  "toyota_comfort": {
    "name": "丰田舒适",
    "description": "ACM + 舒适纵向 + 路沿",
    "params": {"dp_lon_acm": "1", "LongitudinalPersonality": "2", "dp_lat_road_edge_detection": "1"},
  },
  "toyota_alka_lca": {
    "name": "丰田 ALKA + 变道",
    "description": "全速域横向 + LCA 20mph",
    "params": {"dp_lat_alka": "1", "dp_lat_lca_speed": "20", "dp_lat_lca_auto_sec": "0"},
  },
  "vag_eps_safe": {
    "name": "VAG 防 EPS 锁止",
    "description": "低速避免 EPS lockout",
    "params": {"dp_vag_avoid_eps_lockout": "1"},
  },
  "honda_standard": {
    "name": "本田标准横向",
    "description": "关闭 ALKA，标准纵向",
    "params": {"dp_lat_alka": "0", "LongitudinalPersonality": "1"},
  },
  "rollback_last_tune": {
    "name": "恢复上次调优快照",
    "description": "从最近一次自动/手动快照恢复 dp_*",
    "params": {},
    "rollback": True,
  },
}


def list_presets() -> list[dict[str, Any]]:
  return [
    {
      "id": pid,
      "name": p.get("name", pid),
      "description": p.get("description", ""),
      "params": list(p["params"].keys()) if not p.get("rollback") else ["_restore_snapshot"],
      "rollback": bool(p.get("rollback")),
    }
    for pid, p in TUNE_PRESETS.items()
  ]


def get_preset(preset_id: str) -> dict[str, Any] | None:
  return TUNE_PRESETS.get(preset_id)
