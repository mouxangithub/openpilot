# 系统设置与参数

## 真相来源（优先级）

1. **`list_sp_settings`** — 当前品牌可见项 + 当前值（来自 `params_catalog.json` + UI 自动发现）
2. **`get_params_catalog`** — 写入等级 tier
3. **车机 Settings UI** — 本安装树 `selfdrive/ui` 与扩展设置布局
4. **Dashy** — 若本机启用；`fetch_dashy_settings` 作补充

## 专用工具（不必死记 Param）

| 领域 | 读 | 写（静止+confirm） |
|------|-----|-------------------|
| 车型平台 | `get_car_platform_bundle`, `list_car_platforms` | `select_car_platform` |
| NN 模型 | `get_model_manager_status`, `list_model_bundles` | `select_model_bundle`, `refresh_model_list` |
| MADS | `get_mads_settings` | `set_mads_settings` 或 `write_params` |
| MADS 横向/LKAS 排查 | `diagnose_mads_lateral` | —（只读；见 mads-lateral-troubleshoot 技能） |
| OSM 地图 | `get_osm_status`, `list_osm_regions` | `select_osm_region`, `trigger_osm_download` |
| 通用调参 | `read_params`, `snapshot_tune_state` | `write_params`, `apply_sp_tune_preset` |

## ai_* 配置

`ai_provider`、`ai_model` 等走 **`/data/ai/config.json`**（或 PC `~/.comma/ai/config.json`），**不在** `params_keys.h` 编译。

## 日志

`read_manager_log`：先 `dp_dev_last_log`（遗留路径），再 `/data/log/latest.log`（车机默认）。

## 与 Carrot/CP 迁移

见 **carrot-legacy** 技能；写入本机 **openpilot Params**，不要写 CP 专有键。
