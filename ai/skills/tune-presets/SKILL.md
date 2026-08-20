# 调优预设与回滚

本机可并行使用两套预设 API（按 Params 中实际存在的键选择）：

| 系列 | 列出 | 应用 |
|------|------|------|
| `sp_*` | `list_sp_tune_presets` | `apply_sp_tune_preset` |
| `dp_*` 遗留 | `list_tune_presets` | `apply_tune_preset` |

## 快照

- `save_tune_snapshot` / `restore_tune_snapshot` / `list_tune_snapshots`  
- 预设 `sp_rollback_last_tune` / `rollback_last_tune` 均恢复最近快照  

## 审计

`list_audit_trail`、`list_tune_passport` 查看历史写入。

详见 **sp-tune-presets** 与 **dp-tune-presets** 技能。
