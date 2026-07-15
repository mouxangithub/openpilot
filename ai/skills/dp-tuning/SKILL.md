# Dragonpilot 调优技能

本 fork 的调优项定义在 `dragonpilot/settings/`，运行时通过 **Params** 读写。

## 调优前必做

1. `get_vehicle_state` → 记录 brand、carFingerprint、vEgo、enabled、openpilotLongitudinalControl（从 CarParams 或状态）。
2. `read_params` 读取目标 key 的**当前值**。
3. 确认 `LongitudinalPersonality`、是否 `ExperimentalMode`。
4. **车辆静止**后再建议写入（行驶中仅解读）。

用户引用 **OpenPilotCP / Carrot** 参数名时：先 `search_knowledge_base`，或启用 **carrot-legacy** 技能；勿写入 CP 专有 Param。

## 横向 Lateral

| Param | 类型 | 说明 |
|-------|------|------|
| `dp_lat_alka` | bool | 全速域 ALKA：巡航断开仍可车道保持（多品牌） |
| `dp_lat_offset_cm` | int | 车道中心偏移（厘米），左负右正 |
| `dp_lat_lca_speed` | int | 变道辅助速度阈值 mph，**0=关闭** |
| `dp_lat_lca_auto_sec` | float | 打灯后自动变道延迟秒，0=关；依赖 lca_speed>0 |
| `dp_lat_road_edge_detection` | bool | 路沿检测 |

**ALKA 调优建议**：先确认用户想要「踩刹车也不断横向」；本田/丰田需确认车型在 brands 列表内。

## 纵向 Longitudinal

| Param | 说明 | 前置 |
|-------|------|------|
| `dp_lon_acm` | 自适应滑行，减少不必要的制动 | 需 OP 纵向 |
| `dp_lon_aem` | 加速响应人格 | 需 OP 纵向 |
| `dp_lon_apm` | 减速响应人格 | 需 OP 纵向 |
| `dp_lon_ext_radar` | 外部雷达数据融合 | 车型相关 |

配合上游 `LongitudinalPersonality`（0 激进 / 1 标准 / 2 舒适）一起解读。

## 品牌特调

| Param | 品牌 |
|-------|------|
| `dp_toyota_stock_lon` | 丰田原厂纵向 |
| `dp_toyota_tss1_sng` | TSS1 停走 |
| `dp_toyota_door_auto_lock_unlock` | 门自动锁 |
| `dp_honda_nidec_stock_long` | 本田 Nidec 纵向 |
| `dp_vag_a0_sng` | VAG 停走 |
| `dp_vag_avoid_eps_lockout` | 避免 EPS 锁止 |

仅当 `brand` 匹配时推荐修改。

## UI / 设备

| Param | 说明 |
|-------|------|
| `dp_ui_display_mode` | HUD 布局 |
| `dp_ui_hide_hud_speed_kph` | 超过该速度隐藏 HUD 元素 |
| `dp_ui_lead` | 前车信息强度 |
| `dp_ui_rainbow` | 彩虹规划路径 |
| `dp_dev_model_selected` | 当前驾驶模型名 |
| `dp_dev_model_list` | 可选模型 JSON（只读） |

改模型后通常需 reengage 或重启 ui。

## 上游 Openpilot 开关（dashy 镜像）

常用：`OpenpilotEnabledToggle`, `ExperimentalMode`, `DisengageOnAccelerator`, `IsLdwEnabled`, `AlwaysOnDM`, `LongitudinalPersonality`, `DistractionDetectionLevel`, `IsMetric`.

## 推荐对话流程

1. 用户描述手感问题 → 映射到 1–3 个 Param  
2. 读当前值 + 解释含义  
3. 给出建议值与风险  
4. 静止 + 用户确认 → 写入（`write_params` 实现后）  
5. 写后 `read_params` 验证，提示路试

完整分级见 `ai/skills/params_catalog.json`。
