# op助手 (ai) 架构说明

> 迁移状态与脚本见 [ARCHITECTURE_TARGETS.md](./ARCHITECTURE_TARGETS.md)。

## 概览

`ai/` 是 openpilot 树内的 LLM 助手子模块：Web UI、工具调用、RAG、会话同步、车辆诊断。兼容各社区 fork，按当前安装树自动发现参数与 UI。

```
浏览器 (Vanilla JS + 模块化拆分)
    │  HTTP / WebSocket
    ▼
aid.py ──► server/app_factory.create_app()
    │
    ├── server/           路由、handler、终端 WS
    ├── core/             聊天、同步、LLM、工作区（无 HTTP）
    ├── services/         Cabana · TSK · Panda · RAG
    ├── tools/domains/    按领域分包的 LLM 工具实现
    ├── agents/           多 Agent 编排
    ├── skills/           Markdown 技能与 RAG 种子
    └── web/static/       前端资源
```

**根目录约定**：仅保留 `aid.py` 与 `__init__.py` 作为 Python 入口；业务代码全部在子包内。`tools/*.py` 保留一行垫片 `from ai.tools.domains.<domain>.<module> import *` 以兼容旧 import 路径。

## 分层职责

| 层 | 路径 | 职责 |
|----|------|------|
| 入口 | `aid.py` | 解析参数、初始化 TSK、启动 aiohttp |
| 传输 | `server/` | `app_factory`、`handlers/*`、`routes/`、`terminal.py` |
| 内核 | `core/llm/` | `client`、`model_accounts`、`model_router`、`embedding`、`usage` |
| 内核 | `core/chat/` | `runner`、`jobs`、`compaction`、`command_queue`、`sanitize` |
| 内核 | `core/sync/` | `hub`（`/api/ai/sync/ws`）、`protocol`、`device_trust` |
| 内核 | `core/wspace/` | `store`、`persona`（用户数据在 `ai/workspace/`） |
| 内核 | `core/runtime/` | `heartbeat`、`evolution_pipeline`、`sidecar_hub` |
| 服务 | `services/cabana/` | `car_params`、`dbc`、`live`、`replay`、`handlers`、`routes` |
| 服务 | `services/tsk/` | SecOC HTTP API（`routes.py`） |
| 服务 | `services/panda/` | Panda 刷机 API |
| 服务 | `services/rag/` | `builtin_loader`（`data/rag/builtin/` JSON） |
| 基础设施 | `infra/` | `timezone`、`auth`、`version`、硬件门面 |
| 工具 | `tools/` | `registry.py`、`executor.py`、`agent_tools.py` |
| 工具域 | `tools/domains/*/` | 物理分包，见下表 |
| 集成 | `fork/`、`integration/` | fork 检测、Wiki ingest、社区注册 |

### tools/domains 分包

| 域 | 典型模块 |
|----|----------|
| `core` | `diagnostics_tools`、`rag_store`、`rag_seed`、`memory_store`、`wiki_rag` |
| `tune` | `sp_settings`、`dp_settings`、`tune_write_pipeline`、`route_scoring_tools` |
| `vehicle` | `adaptation`、`car_porting_tools`、`fingerprint_lib` |
| `can` | CAN 相关只读工具 |
| `secoc` | `tsk_tools`、`secoc_lookup` |
| `devops` | `git_tools`、`github_api_client`、`pc_dev_tools`、`ota_tools` |
| `cloud` | `comma_cloud_tools`、`sunnylink_tools` |
| `media` | `route_tools`、`route_media_tools`、`plotjuggler_tools` |
| `platform` | `session_store`、`scheduler_actions`、`publish_tools`、`consumer_tools` |

域索引与 Agent 映射：`tools/domains/__init__.py`（`DOMAIN_MODULES`、`AGENT_DOMAINS`）。

## server/handlers 拆分

| 模块 | 职责 |
|------|------|
| `_api_common.py` | 共享依赖；`__all__` 导出 `_json_response` 等别名 |
| `chat_handlers.py` | `/api/ai/chat`、jobs、shell |
| `config_handlers.py` | config、models、providers、skills |
| `sessions_handlers.py` | 会话 CRUD |
| `memory_handlers.py` | 设备记忆 |
| `rag_handlers.py` | 知识库 |
| `scheduler_handlers.py` | 定时任务 |
| `tools_handlers.py` | 工具元数据 |
| `fork_handlers.py` | fork 分析/同步 |
| `publish_handlers.py` | 发布 PR |
| `dev_handlers.py` | 开发面板、缓存 |
| `misc_handlers.py` | 通知、workflows、package |
| `phase2.py` | workspace、MCP、平台扩展 |
| `api.py` | 聚合 re-export |

路由注册：`server/routes/__init__.py` + `server/routes/agents.py`。

## 多 Agent 编排

```
用户消息 / 斜杠命令 / workflow
        │
        ▼
  agents/router.py  ──► agent_id + workflow
        │
        ├── filter_tools_for_agent()
        ├── agent_system_prompt()
        └── office.py（工位状态）
        ▼
  core/chat/runner.py  （工具循环）
        ▼
  SSE: agent_handoff | tool_call | agent_done | …
```

多域编排：`agents/orchestrator.py`（顺序委派 + synthesis）。  
API：`GET/POST /api/ai/agents`。内置专员：`op`、`triage`、`tune`、`route`、`adapt`、`secoc`、`devops`、`cloud`、`pc`。

## 前端模块

| 路径 | 职责 |
|------|------|
| `web/static/js/ai.js` | 主应用（聊天、设置、WS、配置） |
| `web/static/js/app/globals.js` | `App` 命名空间 |
| `web/static/js/app/dom.js` | `$` / `$$` / `els`、启动页 |
| `web/static/js/app/registry.js` | 子模块注册 |
| `web/static/js/chat/model-tag.js` | 消息模型标签 |
| `web/static/js/sessions.js` | SessionStore（内存，服务端权威） |
| `web/static/js/session-sync.js` | WS 合并与冲突策略 |
| `web/static/js/web-sync-ws.js` | `/api/ai/sync/ws` 客户端 |
| `web/static/js/web-chat-jobs.js` | 多会话 job 轮询 |
| `web/static/js/cabana-panel.js` | Cabana 面板 |
| `web/static/js/tsk-panel.js` | SecOC 设置侧栏 |

### 会话同步（Gateway 模式）

1. **服务端权威** — Params `ai_web_sessions` + `stateVersion`
2. **WebSocket** — `core/sync/hub.py`：`/api/ai/sync/ws`
3. **客户端** — `SessionStore` 内存；hello 全量 + 实时 `sessions` / `chat_event`

详见 [SESSION_SYNC.md](./SESSION_SYNC.md)。

## 启动流程（app_factory）

1. 注册 AI / Cabana / Panda / TSK / Sync / Terminal 路由
2. 静态文件 `web/static/`
3. 后台：`scheduler_loop`、`status_watch_loop`
4. 延迟任务：RAG 种子、Wiki ingest、向量 reindex

## 开发与验证

```bash
# PC 预览
py -3 ai/dev/run_pc.py --port 5090

# 架构 import 检查
py -3 ai/scripts/verify_architecture.py

# 单元测试（PC mock）
py -3 ai/tests/run_tests_pc.py
```

## 参考

- [OPENCLAW_LEARNINGS.md](./OPENCLAW_LEARNINGS.md) — 会话同步设计来源
- [TSK_AND_AID.md](./TSK_AND_AID.md) — SecOC 与 aid 合并
- [OpenClaw](https://github.com/openclaw/openclaw)
