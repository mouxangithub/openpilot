# WorkBuddy 对齐笔记

参考 [learn-workbuddy](https://github.com/adongwanai/learn-workbuddy) 24 章路线图。

## 已实现（完整 Harness）

| 章节 | 能力 | 实现 |
|------|------|------|
| s03 | Agent Loop + 工具 | `core/chat/runner.py` |
| s04 | 权限 Hook | `hooks/permissions.py` |
| s06 | Sidecar 子进程 | `core/runtime/sidecar_process.py` + `sidecar_hub.py` |
| s08 | 模型路由 + 档位 | `model_router.py` + `model_tier.py` |
| s09 | JSONL Transcript + 恢复 UI | `transcript_store.py` + `transcript-recovery.js` |
| s12 | Profile 同步 manifest | `profile_sync.py` + 设置→平台 |
| s13 | 大输出外部化 | `result_externalize.py` |
| s14-s15 | Prompt 预算 | `prompt_budget.py` |
| s16-s18 | Experts 管理 UI | `workbuddy-panel.js` + `/api/ai/agents` |
| s19-s20 | 交付物 / File Cards | `artifact-store.js` + `artifact-panel.js` |
| s20 | Canvas 持久化 | `canvas/store.py` → `workspace/artifacts/*.jsonl` |
| s22 | 自动化黑板 + Workflow 编辑器 | scheduler board + `workflow-editor.js` |
| s23 | 审计 hash chain + SQLite | `audit_store.py` + `harness_db.py` |
| — | 聊天 Sidecar / 编排任务板 | `chat-sidecar.js` + `orchestration-blackboard.js` |
| — | 用量 SQL 汇总 | `GET /api/ai/usage/summary` |

## API 一览

| 端点 | 说明 |
|------|------|
| `GET/POST /api/ai/harness/config` | Harness 开关与模型档位 |
| `GET /api/ai/audit` | 审计链（支持 `?tool=&since=` SQL 查询） |
| `GET /api/ai/usage/summary` | SQLite 用量聚合 |
| `GET/POST /api/ai/profile/sync` | Profile manifest 导出/合并 |
| `GET/PUT /api/ai/workflows/custom` | 自定义工作流 |
| `GET /api/ai/transcript` | 会话 JSONL |
| `GET /api/ai/transcript/recover` | 崩溃恢复 |
| `GET /api/ai/sidecar/status` | Sidecar 子进程状态 |

## 测试

```bash
py -3 -m pytest ai/tests/test_harness.py -q
```

## 启动

```bash
py -3 ai/dev/run_pc.py --port 5090
```

硬刷新 `Ctrl+Shift+R`（静态资源 `?v=20260819d`）。

## 可选深化

- 高危工具完全迁入 Sidecar 子进程执行（当前子进程负责事件落盘）
- Konik/Sunnylink 自动云端 Profile 推送（当前为 manifest 手动导入导出）
- 可视化 Workflow 节点图（当前为步骤列表编辑器）
