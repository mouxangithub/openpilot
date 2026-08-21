# OpenClaw 借鉴笔记（op助手）— 更新版

参考：[OpenClaw](https://github.com/openclaw/openclaw) · [Architecture](https://docs.openclaw.ai/concepts/architecture)

## 已落地（完整）

| 能力 | 实现 |
|------|------|
| WS hello 快照、stateVersion、幂等、lane | `sync_hub`, `session_store`, `chat_jobs` |
| 多专员编排（并行） | `agents/orchestrator.py` — `asyncio.gather` |
| 模型 failover | `model_router.py` + **设置 → 备用模型** UI |
| Plugin hooks | `hooks/registry.py` + `hooks/builtin.py` |
| 会话 compaction + `/compact` | `session_compaction.py` + 斜杠命令 |
| **上下文设置** | 设置 → 模型 → 上下文与压缩（轮次/token 阈值） |
| **Issue 提交** | `issue_tools.py` + 开发页「反馈提交」+ `ai/docs/ISSUES.md` |
| **Toolsets** | `tools/toolsets.py` — driving_readonly / offroad_full / secoc / devops / pc_replay |
| **Session 工具 + FTS** | `tools/session_index.py`, `tools/platform_extensions.py` |
| **MCP stdio 桥** | `mcp/host.py` + `/api/ai/mcp` |
| **技能自学习** | `tools/skill_learning.py` + `/api/ai/learned-skills` |
| **Hermes 进化闭环** | 完整 5 步：轨迹→LLM反思→Pareto→批准；见 `ai/docs/HERMES_EVOLUTION.md` |
| **Progressive Disclosure** | `skills/disclosure.py` + `load_skill` 工具 |
| **对话后进化管线** | `evolution_pipeline.py` — 工作区/技能/工具描述 |
| **USER.md / MEMORY.md / 每日日志** | `workspace/USER.md`、`MEMORY.md`、`memory/YYYY-MM-DD.md` 注入 prompt |
| **Memory protocol 技能** | `skills/memory-protocol/SKILL.md` 固定加载 + 强制工具写入 |
| **Memory nudge** | `core/chat/runner.py` system 提示 |
| **Heartbeat LLM 巡检** | `heartbeat.py` — 读 HEARTBEAT.md + LLM 判断，无事静默 |
| **Cron NL + chat_notify** | `tools/scheduler.py` `parse_nl_task_spec` + `chat_notify` 动作 |
| 斜杠命令补全 | `/compact` `/agent` `/verbose` `/trace` `/usage` `/memory` `/workspace` `/office` 等 |
| Web 平台面板 | 设置 → **平台** — 工作区/MCP/技能/搜索/调试开关 |
| SOUL/AGENTS/TOOLS 人设 | `workspace/*.md` + REST API |

## 刻意不做

| OpenClaw 能力 | 说明 |
|---------------|------|
| Exec Approval（危险操作人工确认） | 用户明确排除 |
| 多通道 Ingress（WhatsApp/Telegram 等 50+） | 聚焦车载 Web |
| Subagents 递归 | 扁平专员编排已够用 |

## 平台 API

| 端点 | 用途 |
|------|------|
| `GET/POST /api/ai/workspace` | SOUL/USER/MEMORY/HEARTBEAT 编辑 |
| `GET /api/ai/sessions/search?q=` | FTS 跨会话搜索 |
| `GET/POST /api/ai/mcp` | MCP 服务配置 |
| `GET/POST /api/ai/learned-skills` | 已学技能列表与批准 |
| `GET /api/ai/toolsets` | 工具集说明 |
| `POST /api/ai/scheduler` `{nl: "每天9点…"}` | 自然语言定时任务 |

## 验证清单

1. 设置 → 平台：编辑 USER.md 保存后，新对话 system 含用户画像
2. `/compact` 触发会话摘要写入 memory notes
3. 多域问题触发 orchestrator 并行专员 + OP 汇总
4. Scheduler `chat_notify` / NL 添加任务可推送通知
5. MCP server 配置后 `discover_mcp_tools` / `call_mcp_tool` 可用
6. `/verbose` `/trace` 切换后 job body 带标志，SSE 有 trace 事件
