# openpilot 调优技能

本机调优项在 **Settings** UI 与 **Params** 中；AI 通过 `list_sp_settings` / `write_params` 操作。

遗留 **`dp_*`** 扩展参数见 **dp-tuning** 技能（仅当 Params 中存在对应键）；**不要与主路径混用**。

## 调优前必做

1. `get_vehicle_state` → brand、fingerprint、vEgo、enabled
2. `list_sp_settings` 或 `read_params` 读当前值
3. **车辆静止**后再写入

## 横向 Lateral

| Param | 说明 |
|-------|------|
| `Mads` / `MadsSteeringMode` | MADS 与踩刹车时横向行为（见 mads-settings 技能） |
| `LagdToggle` / `LagdToggleDelay` | 在线学习转向延迟 vs 固定延迟 |
| `LaneTurnDesire` / `LaneTurnValue` | 低速打灯弯道规划 |
| `BlinkerPauseLateralControl` | 打灯暂停横向 |
| `LiveTorqueParamsToggle` / `CustomTorqueParams` | 扭矩学习与自定义 |
| `NeuralNetworkLateralControl` | NN 横向控制 |

工具：`get_mads_settings`、`set_mads_settings`、`get_torque_settings`、`set_torque_settings`、`get_speed_limit_settings`、`get_model_tune_settings`、`list_model_bundles`（模型页 Lagd 相关）

`list_sp_settings` 现已使用 **合并 catalog**（静态 + UI 文案 + params_keys.h），与 `get_params_catalog` 一致。

## 纵向 Longitudinal

| Param | 说明 |
|-------|------|
| `LongitudinalPersonality` | 0 激进 / 1 标准 / 2 舒适 |
| `DynamicExperimentalControl` | DEC 动态实验纵向 |
| `SmartCruiseControlMap` / `SmartCruiseControlVision` | 地图/视觉智能巡航 |
| `SpeedLimitMode` / `SpeedLimitPolicy` | 限速辅助 |

## 车型与模型

| 概念 | 工具 | Param |
|------|------|-------|
| **车型平台** | `list_car_platforms`, `select_car_platform` | `CarPlatformBundle` |
| **驾驶 NN 模型** | `list_model_bundles`, `select_model_bundle` | `ModelManager_*` |

注意：`select_driving_model` 历史命名指 **车型**，不是神经网络模型。

## 地图 OSM

`get_osm_status` → `list_osm_regions` → `select_osm_region` → `trigger_osm_download`（offroad + WiFi）

## 预设

- 主路径：`list_sp_tune_presets` + `apply_sp_tune_preset`
- 遗留 `dp_*`：`list_tune_presets` + `apply_tune_preset`（键存在时）

## 推荐流程

1. 用户描述问题 → 映射 1–3 个 Param  
2. `diff_params` 预览  
3. 静止确认 → `write_params` 或预设  
4. 路试 → `compare_tune_ab` / `score_tune_session`

完整分级见 `ai/skills/params_catalog.json`；UI 自动发现见 `catalog_builder.py`。
