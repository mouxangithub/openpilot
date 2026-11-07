# 遗留 dp_* 调优预设

## 工具

- `list_tune_presets` — comfort_follow、alka_enable、vag_eps_safe 等  
- `apply_tune_preset` — 应用 dp_* 预设  
- `rollback_last_tune` — 恢复快照  

主路径预设见 **sp-tune-presets** / `list_sp_tune_presets`。

## 注意

本机 **可能无** `dp_*` params_keys；预设仅在 Params 中存在对应键时有效。失败时用 `diff_params` 检查。
