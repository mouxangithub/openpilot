# OP 助手可借鉴能力补充分析报告

> 来源：`E:\deepseek-harness`、`E:\learn-workbuddy`、WorkBuddy 桌面端能力
> 时间：2026-09-12
> 范围：识别可迁移/借鉴到 `E:\sp\ai` 子仓库与 `ai/web` 的能力 seam、模块、前端入口

---

## 一、deepseek-harness → ai/ 可迁移 seam

### P0 — 协议语义层，建议优先落地

| seam | dsh 实现位置 | ai/ 现状 | 建议落点 | 难度 | 收益 |
|---|---|---|---|---|---|
| **Session-level sandbox policy + runtime-context snapshot** | `packages/sandbox/sandbox-policy/src/index.ts` | 已有 `SandboxPolicyService` 读取 params 默认模式，缺 session override 和 system-prompt 注入 | `ai/sandbox/runtime.py` + `core/session/folds.py` + `core/agent/agent.py` | 中 | 让每轮请求都带当前 sandbox 上下文，模型明确知道能力边界 |
| **Permission presets（sandbox + approval bundle）** | `packages/interaction/permission-presets/src/index.ts` + `user-approval/src/index.ts` | 只有 capability policy，没有 `/permission` 命令和 ask/never approval policy | `ai/permissions/service.py` + `core/chat/commands.py` | 中高 | 用户可通过聊天命令切换权限预设，默认危险操作需批准 |
| **Event projection 统一框架** | `packages/session/session-projection/src/index.ts` | 只有 `fold_domain_events()` 函数，无通用 registry、schema、checkpoint | `core/session/projections.py`（新建） | 中 | 所有 session 状态都能从 event log 重建，为后续 fold 提供基础设施 |

### P1 — 生命周期与错误契约

| seam | dsh 实现位置 | ai/ 现状 | 建议落点 | 难度 |
|---|---|---|---|---|
| **Attachment store abstraction** | `packages/attachment/attachment/src/index.ts` | 已有 content-addressed upload，缺 image normalization 和 request-image variant | `ai/attachment/store.py` | 中 |
| **Command registry + slash command 生命周期** | `packages/interaction/commands/src/index.ts` | 只有聊天队列，无 `/command` 解析 | `core/chat/commands.py`（新建） | 中 |
| **Approval service** | `packages/interaction/user-approval/src/index.ts` | 有 HITL 但无标准 `approval/asked`+`decided` 事件 | `ai/permissions/approval.py`（新建） | 中高 |
| **Session persistence abstraction** | `packages/session/session-persistence/src/index.ts` | 已有 JSONL storage，缺抽象接口、write lease、fork 语义 | `core/session/storage.py` + `model.py` | 中高 |
| **Settings namespace seam** | `packages/settings/settings/src/index.ts` | 已有 `ConfigRegistry`，缺 base/user layer 和 `mutate(path ops)` | `ai/config/registry.py` | 中 |
| **Session event vocabulary & repair** | `packages/core/session/src/types.ts` + `repair.ts` | 事件类型较简化，repair 只补缺失 result | `core/session/model.py` + `repair.py` | 中 |

### P2 — 增强项

- **Workflow engine**：新建 `ai/core/workflow/`，实现最小 workflow DSL。
- **Skill scope/version/disposal**：增强 `ai/skills/loader.py`。
- **Remote spill backend**：抽象 `ai/tools/result_externalize.py`。
- **LSP diagnostics/rename**：扩展 `ai/tools/harness_tools.py`。
- **MCP resources/prompts**：扩展 `ai/mcp/host.py`。

---

## 二、learn-workbuddy → ai/ 可迁移模块

### P0 — 高价值且可立即融合

| 章节 | 核心机制 | 建议落点 | 与 ai/ 关系 |
|---|---|---|---|
| **s10_workspace_memory** | append-only evidence journal + conflict adjudication | `ai/core/wspace/store.py` + `workspace_enrich.py` | ai 已有 markdown 记忆，缺事务化 evidence log |
| **s11_user_memory** | preference dedupe/expiry/provenance | `ai/tools/domains/core/memory_store.py` | 可补 preference 生命周期 |
| **s12_cloud_memory** | RecallHit 统一召回契约 | `ai/services/rag/recall_engine.py`（新建） | ai 召回分散，缺统一命中对象 |
| **s14_context_compact** | durable retrieval evidence 不进入有损摘要 | `ai/core/session/compaction.py` + `pruner.py` | 关键补强，避免 RAG 证据被压缩掉 |
| **s15_prompt_assembly** | memory candidate 准入选择器 | `ai/common/prompt_budget.py` | 把 recall hits 转成 prompt 前做 scope/confidence/dedupe 筛选 |
| **s22_automation_scheduler** | RRULE + 自然语言创建任务 | `ai/tools/domains/platform/scheduler.py` | 替换/增强现有触发器集合 |
| **s23_audit_sandbox** | SHA-256 hash-chain + 命令安全分级 | `ai/permissions/policy.py` + `sandbox/shell_runner.py` | 叠加命令分级到现有 vehicle_guard |

### P1 — 第二阶段

- s04 permission hooks（ask 用户批准流程）
- s07 session management（ACP-like lifecycle）
- s08 model routing（cost tracking）
- s09 JSONL transcript replay
- s13 output externalization（retention lease）
- s16 skills system（SKILL.md frontmatter）
- s17 MCP connectors（trust workflow、deferred tools）
- s18 experts system（专家包缓存与 prompt 注入）

---

## 三、ai/web 与 WorkBuddy 桌面端差距

### ai/web 当前已有

聊天、设置 schema-driven UI、Platform/Harness 面板、终端、Canvas、Cabana、TSK、模型 hub、主题/i18n 基础、设备信任、同步 WebSocket。

### 明显缺失但后端已支持（可快速补齐）

| WorkBuddy 能力 | 车载 web 适用性 | 难度 | 推荐 UI 位置 |
|---|---|---|---|
| **文件管理器** | 高 | 中 | 新增 Files 抽屉 |
| **知识库文档管理** | 高 | 中 | Platform 设置 Knowledge 卡片 |
| **技能市场/已安装管理** | 高 | 中 | Platform 设置 Skills 卡片 |
| **MCP 配置** | 高 | 低 | Platform 设置 MCP 卡片增强 |
| **自动化/Scheduler 任务创建** | 高 | 低 | Settings scheduler-view 扩展 |
| **版本更新入口** | 高 | 低 | Settings About 卡片 |
| **通知中心** | 高 | 低 | 顶栏铃铛 |
| **代码编辑器/预览** | 高（PC）/ 中（车机只读） | 中 | 新增 Code 面板 |
| **发布/PR/Issue** | 中 | 中 | 新增 Publish 抽屉 |
| **Bundle 管理** | 中 | 低 | Platform 设置 Bundles 卡片 |
| **Logs/Diagnostics 实时查看** | 中 | 低 | 新增 Logs 抽屉 |
| **Wiki ingest 入口** | 高 | 低 | Knowledge 卡片 |
| **聊天导出/导入/归档** | 高 | 低 | 会话菜单 |

### 需要重构/优化的前端工程

- **SPA 路由**：当前 hash 变化靠全局变量，建议引入集中式路由。
- **状态管理**：模块间耦合严重，建议用轻量 store。
- **组件化**：模态框、卡片、表单抽象不足。
- **响应式**：移动端设置侧边栏、Cabana/Terminal 小屏适配。
- **错误处理/离线回退**：统一 `web-api.js` 错误提示。
- **i18n 完整化**：大量中文硬编码需提取 key。

### 安全敏感功能必须沿用现有机制

参数写入、设备刷写/重启、代码写入必须复用后端 `system.safety` 的驾驶状态判断和 `write_pending` 确认流程，web UI 默认只读，停车+管理员模式才允许写入。

---

## 四、综合落地建议

### 近期（1-2 周）

1. **补齐 web 入口**：文件管理、知识库、技能市场、版本更新、通知中心。
2. **P0 seam 落地**：event projection 框架 → session sandbox policy → permission presets。

### 中期（2-4 周）

3. **learn-workbuddy 融合**：durable retrieval evidence（s14）、memory candidate selector（s15）、RRULE scheduler（s22）、命令分级审计（s23）。
4. **ai/web 重构**：SPA 路由、组件化、响应式、i18n。

### 远期

5. **P1/P2 seam**：approval service、session persistence 抽象、workflow engine、MCP resources/prompts。
