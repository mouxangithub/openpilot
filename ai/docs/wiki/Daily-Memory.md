# Daily Memory（每日记忆）

> Wiki 说明页。实际文件在设备 `workspace/memory/`（**每轮对话会自动注入给 AI**，无需 Web UI 浏览）。

Hermes / OpenClaw 风格：**一天一页**，像 Wiki 子页面。

## 文件结构

```
workspace/memory/
├── INDEX.md           # 自动索引（最近 14 天 + 最近一条摘要）
├── 2026-07-28.md      # 今日日志
├── 2026-07-27.md
└── ...
```

## AI 如何读

1. **每轮 system prompt** 注入 `INDEX.md` + 近 7 天页面摘要（今日优先完整）
2. 需要某天全文时调用工具 `read_daily_memory`（含 index + 文件列表）
3. 长期稳定事实应沉淀到上级 `MEMORY.md`，日记只保留「那天发生了什么」

## AI 如何写

- 对话中：`append_daily_memory`（memory-protocol 强制）
- 对话后：自动提炼（`ai_evolution_auto_memory`）
- `/compact` 压缩时也会写入当日页

## 与 MEMORY.md 区别

| | Daily `memory/YYYY-MM-DD.md` | `MEMORY.md` |
|--|------------------------------|-------------|
| 粒度 | 按天、流水账 | 跨月精选 |
| 类比 | Hermes 每日 Wiki 页 | 长期知识库 |
| 读者 | 主要是 AI 自己续写上下文 | AI + 用户偶尔编辑 |

## 保留

默认保留 30 天（`prune_old_daily_files`），可在平台备份中一并导出。
