# openpilot 调优预设（sp_*）

静止 + `confirm=true` 应用。

## 工具

- `list_sp_tune_presets` — 列出 `sp_*` 预设 ID  
- `apply_sp_tune_preset` — 应用（自动快照可选）  
- `sp_rollback_last_tune` — 从 `tune_snapshot_store` 恢复  

## 常用 ID

| preset_id | 用途 |
|-----------|------|
| `sp_comfort_lon` | 舒适纵向人格 |
| `sp_scc_map_vision` | 地图+视觉 SCC |
| `sp_mads_full` | MADS 全开 |
| `sp_lagd_on` / `sp_lagd_fixed_delay` | Lagd 开关 |
| `sp_toyota_sng` | 丰田停走（brand 过滤） |

遗留 `dp_*` 预设见 **dp-tune-presets** / `list_tune_presets`。
