# 遗留 dp_* 调优技能

适用于 Params 中仍存在 **`dp_*`** 扩展键的安装树。主调优路径见 **sp-tuning**；本节供对照与从旧 fork 迁移。

## 工具

- `list_tune_presets` / `apply_tune_preset` — dp_* 预设
- `fetch_dashy_settings` — Dashy `:5088`（若启用 `dp_dev_dashy`）
- `read_manager_log` — 优先 `dp_dev_last_log`，否则 `/data/log/latest.log`

## 横向 dp_lat_*

| Param | 说明 |
|-------|------|
| `dp_lat_alka` | 全速域 ALKA |
| `dp_lat_lca_speed` / `dp_lat_lca_auto_sec` | 变道辅助 |
| `dp_lat_road_edge_detection` | 路沿检测 |

## 纵向 dp_lon_*

`dp_lon_acm` / `dp_lon_aem` / `dp_lon_apm` / `dp_lon_ext_radar` — 配合 `LongitudinalPersonality`。

## 品牌

`dp_toyota_*`、`dp_honda_*`、`dp_vag_*` — 仅匹配 brand 时推荐。

## 与主路径对照

| 旧习惯 / dp_* | openpilot 等价 |
|---------------|----------------|
| `dp_lat_alka` | `Mads` + 转向设置 |
| `dp_dev_model_selected` | `ModelManager_ActiveBundle` |
| Dashy 调参 | `list_sp_settings` + 车机 UI |

用户在本车上请优先 **sp-tuning** 与 `list_sp_tune_presets`；无 `dp_*` 键时跳过本节。
