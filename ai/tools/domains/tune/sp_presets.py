"""openpilot tune presets — stationary apply only."""

from __future__ import annotations

from typing import Any

SP_TUNE_PRESETS: dict[str, dict[str, Any]] = {
  "sp_comfort_lon": {
    "name": "SP 舒适纵向",
    "description": "LongitudinalPersonality 舒适 + DEC 关闭",
    "params": {"LongitudinalPersonality": "2", "DynamicExperimentalControl": "0"},
  },
  "sp_standard_lon": {
    "name": "SP 标准纵向",
    "description": "标准人格 + 地图/视觉 SCC 关闭",
    "params": {
      "LongitudinalPersonality": "1",
      "SmartCruiseControlMap": "0",
      "SmartCruiseControlVision": "0",
    },
  },
  "sp_scc_map_vision": {
    "name": "SP 智能巡航",
    "description": "开启地图与视觉 Smart Cruise",
    "params": {"SmartCruiseControlMap": "1", "SmartCruiseControlVision": "1"},
  },
  "sp_mads_full": {
    "name": "SP MADS 全开",
    "description": "MADS + 主巡航联动 + UEM",
    "params": {
      "Mads": "1",
      "MadsMainCruiseAllowed": "1",
      "MadsUnifiedEngagementMode": "1",
      "MadsSteeringMode": "0",
    },
  },
  "sp_mads_brake_pause": {
    "name": "SP MADS 刹车暂停横向",
    "description": "踩刹车时暂停 ALC",
    "params": {"Mads": "1", "MadsSteeringMode": "1"},
  },
  "sp_lagd_on": {
    "name": "SP 在线学习转向延迟",
    "description": "Lagd 开启（默认 SP 体验）",
    "params": {"LagdToggle": "1"},
  },
  "sp_lagd_fixed_delay": {
    "name": "SP 固定转向延迟",
    "description": "关闭 Lagd，软件延迟 0.2s",
    "params": {"LagdToggle": "0", "LagdToggleDelay": "0.2"},
  },
  "sp_lane_turn_on": {
    "name": "SP 低速打灯弯道",
    "description": "LaneTurnDesire 低速打灯规划转弯",
    "params": {"LaneTurnDesire": "1", "LaneTurnValue": "19.0"},
  },
  "sp_torque_live": {
    "name": "SP 在线扭矩学习",
    "description": "LiveTorque + 关闭自定义覆盖",
    "params": {"LiveTorqueParamsToggle": "1", "CustomTorqueParams": "0"},
  },
  "sp_toyota_sng": {
    "name": "SP 丰田停走",
    "description": "Toyota SNG hack",
    "params": {"ToyotaStopAndGoHack": "1"},
    "brands": ["toyota", "lexus"],
  },
  "sp_toyota_stock_lon": {
    "name": "SP 丰田原厂纵向",
    "params": {"ToyotaEnforceStockLongitudinal": "1"},
    "brands": ["toyota", "lexus"],
  },
  "sp_subaru_sng": {
    "name": "SP 斯巴鲁停走",
    "params": {"SubaruStopAndGo": "1"},
    "brands": ["subaru"],
  },
  "sp_hyundai_lon_tune": {
    "name": "SP 现代纵向调优",
    "params": {"HyundaiLongitudinalTuning": "1"},
    "brands": ["hyundai", "kia", "genesis"],
  },
  "sp_speed_limit_assist": {
    "name": "SP 限速辅助",
    "description": "开启地图限速模式与标准策略",
    "params": {"SpeedLimitMode": "1", "SpeedLimitPolicy": "0", "SpeedLimitOffsetType": "0"},
  },
  "sp_speed_limit_offset_5": {
    "name": "SP 限速 +5",
    "params": {"SpeedLimitMode": "1", "SpeedLimitOffsetType": "1", "SpeedLimitValueOffset": "5"},
  },
  "sp_nn_lateral": {
    "name": "SP NN 横向",
    "params": {"NeuralNetworkLateralControl": "1"},
  },
  "sp_model_tune_reset": {
    "name": "SP 模型调参默认",
    "description": "CameraOffset 0 / PlanplusControl 1.0",
    "params": {"CameraOffset": "0.0", "PlanplusControl": "1.0"},
  },
  "sp_lane_change_fast": {
    "name": "SP 快速变道",
    "params": {"AutoLaneChangeTimer": "0", "AutoLaneChangeBsmDelay": "0"},
  },
  "sp_lane_change_cautious": {
    "name": "SP 谨慎变道",
    "params": {"AutoLaneChangeTimer": "2", "AutoLaneChangeBsmDelay": "2"},
  },
  "sp_visuals_minimal": {
    "name": "SP 极简 HUD",
    "params": {
      "RainbowMode": "0", "ChevronInfo": "0", "DevUIInfo": "0",
      "StandstillTimer": "0", "RoadNameToggle": "0",
    },
  },
  "sp_visuals_rainbow": {
    "name": "SP 彩虹路径",
    "params": {"RainbowMode": "1", "ChevronInfo": "1"},
  },
  "sp_acc_custom": {
    "name": "SP 自定义 ACC 步进",
    "params": {
      "CustomAccIncrementsEnabled": "1",
      "CustomAccShortPressIncrement": "1",
      "CustomAccLongPressIncrement": "5",
    },
  },
  "sp_dec_on": {
    "name": "SP DEC 开启",
    "params": {"DynamicExperimentalControl": "1"},
  },
  "sp_quiet_device": {
    "name": "SP 安静模式",
    "params": {"QuietMode": "1"},
  },
  "sp_rollback_last_tune": {
    "name": "恢复上次 SP/DP 调优快照",
    "description": "从 tune_snapshot_store 恢复",
    "params": {},
    "rollback": True,
  },
}


def list_sp_presets(brand: str = "") -> list[dict[str, Any]]:
  brand_l = brand.lower()
  out: list[dict[str, Any]] = []
  for pid, p in SP_TUNE_PRESETS.items():
    brands = p.get("brands")
    if brands and brand_l and brand_l not in [b.lower() for b in brands]:
      continue
    out.append({
      "id": pid,
      "stack": "openpilot",
      "name": p.get("name", pid),
      "description": p.get("description", ""),
      "params": list(p["params"].keys()) if not p.get("rollback") else ["_restore_snapshot"],
      "rollback": bool(p.get("rollback")),
      "brands": brands,
    })
  return out


def get_sp_preset(preset_id: str) -> dict[str, Any] | None:
  return SP_TUNE_PRESETS.get(preset_id)
