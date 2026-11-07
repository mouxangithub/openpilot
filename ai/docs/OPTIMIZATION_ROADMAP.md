# AI OP 助手优化与学习路线图

> 综合三份调研报告：
> - dsh-explorer: deepseek-harness 可学习点
> - software-architect: ai/ 架构优化建议
> - software-engineer: 工具集成优化建议
>
> 生成时间：2026-09-18
> 范围：仅分析与建议，未修改代码

## 1. 执行摘要

ai/ 子模块已完成 P0-P2 增量能力建设，当前处于功能快速扩张后的收敛期。最紧迫的优化集中在四类问题：

1. **统一注册与返回契约**：工具 handler 注册风格不统一、TOOL_META 缺失、返回格式不一致。
2. **统一核心抽象**：skills/skill 双轨、session 持久化双轨、Agent/Chat handler 重复。
3. **补齐 deepseek-harness 关键语义**：Workflow fatal/dispose、MCP 命名空间/reconnect、Skill rank/scope/cache、Local spill 安全模式、Session adoptability。
4. **工具可组合性**：WorkflowEngine 与全量工具链桥接、health_check 诊断到修复闭环、CI/session-summary 高阶工作流。

本报告将建议按 P0/P1/P2 分级，并给出可落地的实施路线图。

---

## 2. deepseek-harness 可学习点（按 P0/P1/P2）

> 说明：当前环境无法直接读取 `E:\deepseek-harness`，以下结论基于历史已读源码记录，无法二次验证。

### 2.1 P0 — 高优先级

| # | 能力 | dsh 参考 | ai 现状 | 学习价值 | 建议落点 | 难度/风险 |
|---|------|---------|---------|---------|---------|----------|
| D-P0.1 | Workflow fatal/non-fatal 错误 + `dispose()` 稳定性 | `packages/workflow/workflow/src/index.ts` | 已实现 WorkflowEngine 核心，但需确认 `fatal` 标志与组合子错误映射 | 高 | `ai/core/workflow/engine.py` | 中：错误语义影响调试 |
| D-P0.2 | MCP `serverName` 命名空间隔离 + reconnect 监督 | `packages/mcp/mcp-client/src/index.ts` | 已实现 resources/prompts/tools，但命名空间与重连待对齐 | 高 | `ai/mcp/*.py` | 低：已有实现 |
| D-P0.3 | Skill rank/scope 合并 + 缓存失效事件 | `packages/skill/skill/src/index.ts` | 已实现 scope/version/disposal，rank/cache 事件待补齐 | 高 | `ai/skills/*.py`, `ai/agents/registry.py` | 中：与现有加载顺序冲突 |
| D-P0.4 | Local spill 安全模式（0700/0600、防 symlink、cleanup） | `packages/spill/spill-local/src/index.ts` | 已实现 remote spill backend，local backend 安全加固可借鉴 | 高 | `ai/tools/result_externalize.py`, `ai/server/routes/*.py` | 低：本地安全加固 |
| D-P0.5 | Session header adoptability 检查 | `packages/bundle/headless/src/index.ts` | 已实现 session fork/pause/dispose，adoptability 检查待补齐 | 高 | `ai/core/session/manager.py`, `ai/server/routes/agents.py` | 中：与恢复逻辑耦合 |

### 2.2 P1 — 中优先级

| # | 能力 | dsh 参考 | ai 现状 | 学习价值 | 建议落点 |
|---|------|---------|---------|---------|---------|
| D-P1.1 | Workflow 事件 vocabulary | `packages/workflow/workflow/src/index.ts` | 事件命名待对齐 | 中 | `ai/core/workflow/events.py`, `ai/server/handlers/consumer.py` |
| D-P1.2 | MCP resources cursor 分页 + templates | `packages/mcp/mcp-resources/src/index.ts` | resources/list 已实现，cursor/templates 待补齐 | 中 | `ai/mcp/*.py` |
| D-P1.3 | Skill provider 模型 + invocation policy | `packages/skill/skill/src/index.ts` | 无显式 provider/policy 抽象 | 中 | `ai/skills/*.py` |
| D-P1.4 | Bundle 声明式 profile 组合 | `packages/bundle/base/src/index.ts` | 已扩展 bundle/profile，声明式合成待增强 | 中 | `ai/config/schema.py`, `ai/server/routes/agents.py` |
| D-P1.5 | LSP provider 注册原子性 + 冲突检查 | `packages/lsp/lsp/src/index.ts` | ai 已超前支持 diagnostics/rename，可对表注册原子性 | 中 | `ai/tools/lsp*.py` |

### 2.3 P2 — 增强/研究方向

| # | 能力 | 说明 |
|---|------|------|
| D-P2.1 | Workflow phases meta 与可视化 | 为 workflow 提供进度条/阶段元数据 |
| D-P2.2 | MCP streamable-http transport | 支持浏览器/远程 MCP server |
| D-P2.3 | Agent lineage/fork/join/cancel 深层语义 | 明确 parentSession/origin/delegationDepth |
| D-P2.4 | Terminal/shell 沙箱与审计 | dsh 目录不可访问，需恢复访问后再对表 |
| D-P2.5 | Credentials/secret 管理 | 基础安全能力，dsh 目录不可访问 |
| D-P2.6 | Automations 触发器与错误恢复 | dsh 目录不可访问 |
| D-P2.7 | Storage/blob 外部化与 retention | dsh 目录不可访问 |
| D-P2.8 | Context/realm 隔离 | dsh 目录不可访问 |
| D-P2.9 | Webhook/event bus | dsh 目录不可访问 |
| D-P2.10 | Harness 测试框架与 fixture | dsh 目录不可访问 |

> 重要提示：dsh 原生 LSP 不支持 diagnostics/rename，ai/ 已超前实现，不要回退；dsh skill 无显式 version 字段，ai/ 应保持自己的 version 设计。

---

## 3. ai/ 架构优化建议（按 P0/P1/P2）

### 3.1 P0 — 高优先级

| # | 问题 | 涉及文件 | 建议方案 | 风险 |
|---|------|---------|---------|------|
| A-P0.1 | 工具注册入口分散 | `ai/tools/agent_tools.py`, `harness_tools.py`, `platform_extensions.py`, `skill/registry.py`, `mcp/host.py` | 引入 `ai/tools/tool_registry.py`，所有扩展通过 `register_tools(registry)` 注册（**实际落点见下方说明**） | 工具丢失风险，需全量回归 |

> **A-P0.1 落点说明（已实现）**：`ToolRegistry` 类的实际落点为 **`ai/tools/tool_registry.py`**。
> `ai/tools/registry.py` 保留为**兼容 facade**（`from ai.tools.registry import build_tool_schemas` 等模块级函数导入方式不变，勿改为类）。
> 桥接函数 `registry_from_agent_tools()` 位于 `tool_registry.py`，将 `agent_tools.build_tool_schemas()` / `TOOL_META` / `make_handlers()` 汇总为一个 `ToolRegistry`；`tool_registry.py` 本身零 openpilot 依赖（纯标准库），可用 `ToolRegistry.from_parts()` 依赖注入。配套测试：`ai/tests/test_tool_registry.py`。
| A-P0.2 | 双 Skill 系统 | `ai/skills/*.py`, `ai/skill/*.py` | 文件型 loader 只返回 `SkillManifest`，`ai/skill/registry.py` 成为唯一运行时注册表 | 需保持文件型 Skill 兼容 |
| A-P0.3 | Session 持久化双轨 | `core/session/storage.py`, `core/session/log.py`, `core/session/repair.py` | `SessionLog` 作为 `SessionStorage` 的类型化包装，统一修复逻辑 | 格式迁移需双写过渡期 |
| A-P0.4 | Agent/Chat handler 重复 | `core/agent/agent.py`, `core/chat/runner.py`, `server/op_routes.py`, `server/app_factory.py` | 新增 `ai/core/agent/factory.py`，统一本地/生产 Agent 构造 | 中间件差异需保留 |
| A-P0.5 | Chat 路由重复 | `server/routes.py`, `server/op_routes.py` | 提取 `server/handlers/chat.py`，两路由文件只负责绑定 | 认证中间件差异 |

### 3.2 P1 — 中优先级

| # | 问题 | 涉及文件 | 建议方案 |
|---|------|---------|---------|
| A-P1.1 | permissions/ 与 sandbox/ 边界模糊 | `permissions/*.py`, `sandbox/*.py` | permissions = 授权决策；sandbox = 执行隔离 |
| A-P1.2 | 配置源分散 | `core/config/schema.py`, `common/evolution_config.py`, `common/params.py` | 所有模块通过 `AIOPConfig` 读取，Params() 仅在加载阶段使用 |
| A-P1.3 | workflow 运行时未统一 | `core/graph/executor.py`, `tools/domains/platform/workflow_*.py`, `core/workflow/*.py` | 长期统一为 `core/workflow/`，短期旧实现作为 adapter |
| A-P1.4 | 前后端能力不对齐 | `web/static/js/*.js`, `server/routes.py` | 建立 `CAPABILITIES.md` 能力清单，补齐前端面板 |
| A-P1.5 | evolution/ 边界模糊 | `evolution/*.py`, `core/agent/loop.py` | evolution 只输出定义，AgentLoop 负责执行 |

### 3.3 P2 — 低优先级

| # | 问题 | 建议方案 |
|---|------|---------|
| A-P2.1 | 模块目录深度不一致 | 统一 `ai/tools/domains/{domain}/` 布局 |
| A-P2.2 | 测试框架不统一 | 统一使用 `OpenpilotTestCase` 子类，补充 `conftest.py` 风格 fixture |

---

## 4. 工具集成优化建议（按 P0/P1/P2）

### 4.1 P0 — 高优先级

| # | 问题 | 涉及文件 | 建议方案 | 依赖 |
|---|------|---------|---------|------|
| T-P0.1 | handler 注册风格不统一 | `extensions.py`, `platform_extensions.py`, `sp_tool_extensions.py`, `harness_tools.py`, `agent_tools.py` | 统一为返回 dict 风格；`register_harness_handlers` 改为 `make_harness_handlers` | 无 |
| T-P0.2 | make_platform_handlers 缺少 stationary_check/needs_confirm | `platform_extensions.py`, `extensions.py`, `agent_tools.py` | 扩展签名，对 backup/sessions_send/run_workflow 等写操作增加 confirm | T30 stationary/confirm 语义 |
| T-P0.3 | harness 工具未进入 TOOL_META | `agent_tools.py`, `harness_tools.py`, `toolsets.py` | 在 `harness_tools.py` 定义 `HARNESS_TOOL_META` 常量，合并进 TOOL_META | T-P0.1 |
| T-P0.4 | health_check/device_health/panda_status 返回格式不统一 | `health_check_tools.py`, `device_health_tools.py`, `core/errors.py` | 全部改为 `{ok, data, message/error}` 标准结构 | 前端/WorkflowEngine 适配 |
| T-P0.5 | WorkflowEngine 与真实 handler 桥接性能低 | `core/workflow/engine.py`, `platform_extensions.py`, `agent_tools.py` | 创建稳定的 `WorkflowToolAdapter` 类，避免每次重建 handlers | T-P0.1, T-P0.7 |

### 4.2 P1 — 中优先级

| # | 问题 | 涉及文件 | 建议方案 | 依赖 |
|---|------|---------|---------|------|
| T-P1.1 | 双调度器重叠 | `schedule/store.py`, `schedule/runtime.py`, `agent_scheduler.py`, `platform/scheduler.py`, `harness_tools.py` | 统一至 `platform/scheduler.py` 作为唯一持久化后端 | T30 scheduler 生命周期 |
| T-P1.2 | 双记忆系统重叠 | `memory_store.py`, `daily_memory.py`, `platform_extensions.py` | 定义统一 MemoryBackend 抽象，`sessions_send` 双写或新增统一接口 | T35 Web 面板 |
| T-P1.3 | health_check 诊断到 action 未链式触发 | `health_check_tools.py`, `sp_tool_extensions.py`, `core/workflow/engine.py` | 返回可执行 action 列表；新增 `run_remediation_workflow(scope)` 由 WorkflowEngine 编排 | T-P0.4, T-P0.5 |
| T-P1.4 | 审计覆盖不均 | `executor.py`, `extensions.py`, `platform_extensions.py`, `sp_tool_extensions.py`, `audit_store.py` | 所有写操作 handler 显式审计；建立 `@audited` 装饰器 | T-P0.2 |
| T-P1.5 | schedule/memory 适合暴露为 platform tool 但未暴露 | `platform_extensions.py`, `platform/scheduler.py`, `memory_store.py` | 将 scheduler list/upsert/remove、memory append/delete/read 加入 PLATFORM_TOOL_META | T-P0.3, T-P1.2 |
| T-P1.6 | 长耗时工具缺少协作取消 | `harness_tools.py`, `executor.py`, `core/workflow/engine.py` | 子进程/LSP 请求接受 `asyncio.Event` 取消信号 | T31 测试 hang 排查 |
| T-P1.7 | WorkflowEngine 无法直接调度 platform/sp/extension 工具 | `core/workflow/engine.py`, `agent_tools.py`, `extensions.py`, `sp_tool_extensions.py` | WorkflowToolAdapter 暴露全量 handlers，StepKind.TOOL 支持任意已注册工具 | T-P0.5 |

### 4.3 P2 — 低优先级

| # | 问题 | 涉及文件 | 建议方案 |
|---|------|---------|---------|
| T-P2.1 | harness 工具缺少 Web UI label | `tool_ui_meta.py`, `harness_tools.py` | 补充 label/description/category |
| T-P2.2 | MCP 动态工具缺少 stable meta | `mcp/host.py`, `harness_tools.py`, `agent_tools.py` | MCP host 提供 `get_tool_meta`；注册时同步写入运行时 meta |
| T-P2.3 | panda 工具分散 | `sp_tool_extensions.py`, `extensions.py`, `device_health_tools.py`, `health_check_tools.py` | 迁移到单一 `panda_tools.py` |
| T-P2.4 | session summary / CI workflow 缺失 | `platform_extensions.py`, `memory_store.py`, `daily_memory.py`, `extensions.py` | 新增 `finish_session(session_id)` 和 `run_ci_workflow(...)` 高阶工具 |
| T-P2.5 | 错误码细分不足 | `core/errors.py`, `sp_tool_extensions.py`, `platform_extensions.py` | 扩展 `ERR_STATIONARY_REQUIRED`、`ERR_DEPENDENCY_UNAVAILABLE` 等 |
| T-P2.6 | run_workflow 桥接返回未使用 ok_result | `platform_extensions.py`, `core/workflow/engine.py`, `core/errors.py` | WorkflowError 增加 `to_err_code()`，结果统一映射到 ok_result/tool_error |

---

## 5. 综合实施路线图

建议按以下里程碑推进，每步都伴随全量回归测试。

### M1: 统一工具注册契约（P0 基础）
- A-P0.1 统一 ToolRegistry
- T-P0.1 handler 注册风格统一
- T-P0.3 harness 工具补 TOOL_META
- T-P0.2 make_platform_handlers 增加 stationary_check/needs_confirm

### M2: 统一核心抽象（P0 骨架）
- A-P0.2 合并 skills/ 与 skill/
- A-P0.3 统一 Session 持久化
- D-P0.5 Session header adoptability 检查
- A-P0.4 提取 AgentFactory
- A-P0.5 共享 chat handler

### M3: WorkflowEngine 生产就绪（P0 能力）
- T-P0.4 统一返回格式
- T-P0.5 WorkflowToolAdapter 稳定桥接
- T-P1.7 WorkflowEngine 调度全量工具
- D-P0.1 Workflow fatal/dispose 稳定性
- D-P1.1 Workflow 事件 vocabulary

### M4: MCP / Spill / Skill 强化（P0/P1）
- D-P0.2 MCP 命名空间隔离 + reconnect
- D-P0.4 Local spill 安全模式
- D-P0.3 Skill rank/scope/cache 失效事件
- D-P1.2 MCP resources cursor/templates
- D-P1.3 Skill provider/invocation policy

### M5: 高阶工作流与诊断闭环（P1）
- T-P1.1 双调度器合并
- T-P1.2 双记忆系统统一
- T-P1.3 health_check 可执行 action 链
- T-P1.5 schedule/memory 暴露为 platform tool
- T-P1.4 审计覆盖补齐

### M6: 配置/边界/体验打磨（P1/P2）
- A-P1.1 理清 permissions/sandbox 边界
- A-P1.2 统一配置源
- A-P1.3 统一 workflow 运行时
- A-P1.4 前后端能力对齐
- T-P1.6 长耗时工具协作取消
- T-P2.1~T-P2.6 UI label、MCP meta、panda 收敛、CI workflow、错误码细分

### M7: 深度对表 dsh 增强方向（P2，需恢复目录访问）
- D-P2.4~D-P2.10 terminal/shell、credentials、automations、storage、context、webhook、harness 测试框架

---

## 6. 风险与前提

1. **dsh 目录不可访问**：P2 方向性建议无法在当前环境二次验证，需恢复 `E:\deepseek-harness` 访问后再做深度对表。
2. **工具注册重构风险**：统一 ToolRegistry 时可能导致工具丢失或本地/生产工具集不一致，需全量回归 `test_harness_enable.py`、`test_p1p2_regression.py`、`test_p2_integration.py`。
3. **Session 格式迁移风险**：统一 Session 持久化时建议双写过渡期，避免旧 transcript 无法 resume。
4. **权限/安全敏感**：stationary_check、confirm、审计、spill 权限 均涉及车载安全，修改后需重点验证车辆行驶中写保护。
5. **不要回退已有能力**：LSP diagnostics/rename、Skill version 字段等 ai/ 已超前实现的能力应保留。

---

## 7. 建议下一步

1. 确认是否恢复 `E:\deepseek-harness` 目录访问，以便对 P2 方向做文件级验证。
2. 从 M1 开始实施：先统一工具注册契约，风险最低且为后续所有工作流/面板/审计打好基础。
3. 在实施 M2 前，先产出 `ai/skill/` 与 `ai/skills/` 合并的详细设计文档，避免破坏文件型 Skill 兼容。
4. 每项 M 实施后，运行 P0-P2 全量测试 + 本地 dev 服务 smoke test。
