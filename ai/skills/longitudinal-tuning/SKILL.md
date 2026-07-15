# 纵向调优

## 上游

- `LongitudinalPersonality`：0 激进 / 1 标准 / 2 舒适
- `ExperimentalMode`：部分车型实验纵向
- `openpilotLongitudinalControl` 必须为 true 才改 `dp_lon_*`

## Dragonpilot

| Param | 作用 |
|-------|------|
| `dp_lon_acm` | 自适应滑行 |
| `dp_lon_aem` | 加速响应 |
| `dp_lon_apm` | 减速响应 |
| `dp_lon_ext_radar` | 外部雷达 |

预设：`comfort_follow`、`sport_follow`。写前 `diff_params`。

## Maneuver 路试（封闭场地）

1. `maneuver_mode_status` — 只读，不代开 Param  
2. 按 `tools/longitudinal_maneuvers/README.md` 采集路线  
3. `long_maneuver_report` — 路线 HTML 报告 + 文字摘要  
4. `mpc_longitudinal_tuning_report` — MPC 仿真场景 HTML（无需路线）  
5. PC 全量曲线：`pc_launch_jotpluggler` 或 `tools/plotjuggler/juggle.py <route> --layout layouts/tuning.xml`  
6. PC 流式：`pc_launch_replay_viz_stream`

CP 用户口述 `TFollowGap*`、`CruiseMaxVals*` 等：先 `search_knowledge_base` 或启用 **carrot-legacy**；映射到上表与 `list_tune_presets`。
