# op助手 目标架构（2026-08）

本文件描述 `ai/` 包的分层与迁移状态。**根目录仅保留 `aid.py` 与 `__init__.py`。**

## 分层

```
aid.py                 # 唯一进程入口
server/                # HTTP/WS 传输层
core/                  # 平台内核（无 HTTP）
  llm/                 # client, model_accounts, model_router, embedding, usage
  chat/                # runner, jobs, compaction, command_queue, sanitize
  sync/                # hub, protocol, device_trust
  workspace/           # store, persona
  runtime/             # heartbeat, evolution_pipeline, sidecar_hub
services/              # 垂直业务能力
  cabana/              # CAN 面板（car_params, dbc, live, replay, handlers, ai_explain）
  tsk/                 # SecOC API
  panda/               # Panda 刷机路由
  rag/                 # builtin_loader
infra/                 # auth, config, safety, paths, hardware, timezone, version
integration/           # fork 等外部集成
tools/                 # LLM 工具
  registry.py          # 元数据门面
  executor.py          # 执行与审计
  agent_tools.py       # schema/handler 聚合
  domains/             # 物理分包（core/tune/vehicle/can/secoc/devops/cloud/media/platform）
data/rag/builtin/      # 静态内置知识 JSON（可选，由 export 脚本生成）
web/static/js/
  app/                 # globals, dom, registry
  chat/                # model-tag 等
```

## 依赖规则

1. `server` → `services` / `core` → `infra`
2. `core` 不 import `server`
3. `tools` 通过 `services.cabana.qlog_finder` / `services.cabana.app` 访问 Cabana
4. 禁止从 `ai` 根 import 业务模块（无垫片）

## 迁移脚本

| 脚本 | 用途 |
|------|------|
| `scripts/arch_migrate.py` | 初始 core/services 归位 |
| `scripts/rewrite_imports.py` | 全库 import 规范化 |
| `scripts/split_cabana_app.py` | Cabana app 物理拆分 |
| `scripts/migrate_tools_domains.py` | tools → domains/* |
| `scripts/export_rag_builtin.py` | RAG 静态文档导出 JSON |
| `scripts/fix_domain_packages.py` | 合并 domains 同名包冲突 |
| `scripts/rewrite_domain_imports.py` | domains 内部 import 规范化 |
| `scripts/verify_architecture.py` | import 门禁（PC 自动 mock） |

## 状态

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0–P2 | core/ + API 拆分 | ✅ |
| P3 | cabana 拆分为 10+ 子模块 | ✅ |
| P4 | tools domains 全量物理迁移 + 根路径垫片 | ✅ |
| P5 | 前端 app/dom.js、chat/model-tag | ✅ |
| P6 | 根目录清理、import 规范化、RAG data 目录 | ✅ |
| P7 | 文档与 PC 验证脚本对齐新架构 | ✅ |

## 后续（可选）

- `ai.js` 继续拆为 ES modules + esbuild 打包
- `data/rag/builtin/` 全量 JSON 化（在车机环境跑 export 脚本）
- `tools/agent_tools.py` 按 domain 拆 schema 注册
