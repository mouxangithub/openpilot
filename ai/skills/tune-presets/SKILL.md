# 调优预设

用 `list_tune_presets` 列出 ID，静止时 `apply_tune_preset`（需用户确认）。

| preset_id | 说明 | 风险 |
|-----------|------|------|
| `comfort_follow` | ACM + 纵向舒适 | 需 OP 纵向 |
| `standard_follow` | 关闭 ACM/AEM/APM | 安全回退 |
| `sport_follow` | AEM+APM + 激进人格 | 跟车更近 |
| `alka_enable` / `alka_disable` | ALKA 开关 | 品牌需支持 |
| `lca_basic` | LCA 20mph | 无自动变道 |
| `ui_rainbow_on` | 彩虹路径 | 仅 UI |

写前：`snapshot_tune_state` + `diff_params` 展示变更。
