# Carrot / OpenPilotCP → Dragonpilot 迁移

> **默认关闭。** 面向从 **CarrotPilot (CP)** 迁到本 fork 的用户；日常 Dragonpilot 用户无需开启。

## 规则

1. `search_knowledge_base`（关键词：CP 参数名、横向、纵向、迁移）  
2. `list_dp_settings` + `read_params` 核对本车可调项  
3. **禁止** 写入 CP 专有 Param（`LateralTorqueKpV`、`LatMpcPathCost`、`TFollowGap3` 等）  
4. 写 `dp_*` 前：`snapshot_tune_state` + `diff_params`，车辆静止

## 核心对照

| CP / 社区说法 | Dragonpilot | 技能 |
|---------------|-------------|------|
| MADS / 全速域横向 | `dp_lat_alka` | alka-troubleshooting |
| 滑行 / ACM | `dp_lon_acm` | longitudinal-tuning |
| 加减速人格 | `dp_lon_aem`, `dp_lon_apm` | longitudinal-tuning |
| 变道 LCA | `dp_lat_lca_speed`, `dp_lat_lca_auto_sec` | dp-tuning |
| 车道偏移 | `dp_lat_offset_cm` | dp-tuning |
| 路沿 | `dp_lat_road_edge_detection` | dp-tuning |
| 外部雷达 | `dp_lon_ext_radar` | dp-tuning |
| 彩虹路径 | `dp_ui_rainbow`, `dp_ui_display_mode` | dragonpilot-dashy |
| Carrot 面板 | Dashy + `dp_*` | `fetch_dashy_settings` |
| 实验模式 | `ExperimentalMode` | read_params |
| 驾驶个性 | `LongitudinalPersonality` | longitudinal-tuning |
| 模型 | `dp_dev_model_selected` | model-selection |
| 品牌特调 | `dp_toyota_*`, `dp_honda_*`, `dp_vag_*` | dp-brand-* |

## 横向（CP 多数无同名）

| CP | DP |
|----|-----|
| SteerActuatorDelay, LatSmoothSec, LateralTorque*, LatMpc* | 无；用 list_dp_settings / dp-brand-* |
| AdjustLaneOffset, PathOffset | `dp_lat_offset_cm` |
| UseLaneLineSpeed | 结合 `dp_lat_alka` |
| LaneChange* | `dp_lat_lca_*` |

## 纵向

| CP | DP |
|----|-----|
| TFollowGap*, CruiseMaxVals*, LongTuning* | Personality + `list_tune_presets` |
| CruiseEcoControl | `dp_lon_acm` |
| MyDrivingMode | `dp_lon_aem`/`apm` |

## UI

| CP ShowPath* | `dp_ui_*` + Dashy |

## 车辆适配

指纹 / CarState / CarController 流程与上游 openpilot 相同 → **vehicle-adaptation** 技能；仅 Param 命名不同。

## 工作流

1. 分清：适配 / 横向 / 纵向 / UI  
2. `search_knowledge_base` + 上表  
3. `list_dp_settings`  
4. 写入：preset 或 `write_params`（静止+确认）  
5. 告知用户：「本车为 Dragonpilot，CP 项 X 对应 dp_Y」

主技能：`dp-tuning`、`dragonpilot-dashy`、`longitudinal-tuning`。
