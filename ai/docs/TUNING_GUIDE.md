# 调参指南（维护者与车主）

车主向简明版见 Wiki [Tuning-for-Owners](wiki/Tuning-for-Owners.md)。

## 原则

1. **先感受后参数** — 用自然语言描述问题  
2. **最小改动** — 每次 1–3 项，试开再迭代  
3. **先快照** — `snapshot_tune_state` / 调参护照自动记录  
4. **须确认** — Web 确认卡或终端 `y`；禁止行驶中写入  

## 工作流

| 工作流 ID | 用途 |
|-----------|------|
| `tune_session` | 标准调优会话 |
| `post_tune_validation` | 改参后量化验证 |
| `compare_routes_tune` | 改前改后路线对比 |

Web：`/调手感` 或首屏向导。CLI：`op tune`。

## 工具（AI 内部）

- `snapshot_tune_state` / `restore_tune_snapshot`  
- `diff_params` + consumer_lexicon 通俗展示  
- `list_tune_passport` — 历史记录  

## 技能

启用 `sp-tuning` 等相关技能（Onboarding 可选「调优」）。

## 相关文档

- [CAPABILITIES.md](CAPABILITIES.md)  
- [VEHICLE_ADAPTATION_GUIDE.md](VEHICLE_ADAPTATION_GUIDE.md)（适配与调参边界）
