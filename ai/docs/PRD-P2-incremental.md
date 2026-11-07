# AI OP 助手 P2 增量 PRD

> **版本**: v1.0  
> **日期**: 2026-09-12  
> **编写**: software-product-manager  
> **输入**:
> - `E:\sp\ai\docs\PRD-ai-op-assistant-v1.md`
> - `E:\sp\ai\docs\GAP-vs-dsh-latest.md`
> - `E:\sp\ai\docs\AUDIT-harness-alignment.md`
> - 关键源码：`ai/core/graph/*`、`ai/tools/domains/platform/workflows.py`、`workflow_custom.py`、`workflow_graph.py`、`ai/skill/models.py`、`registry.py`、`builtins.py`、`ai/mcp/host.py`、`ai/server/handlers/phase2.py`、`ai/tools/domains/platform/platform_extensions.py`

---

## 1. 概述

本 PRD 是 `PRD-ai-op-assistant-v1.md` 的 P2 增量文档，聚焦三项能力的增强：

1. **WorkflowEngine 脚本运行时语义**（当前只有图遍历 + prompt 注入）
2. **Skill scope/version/disposal 生命周期**（当前全局单例、无 dispose、无依赖诊断）
3. **MCP resources/read 与 prompts/get 支持**（当前只实现 list，未实现 read/get）

> 优先级声明：本次 PRD 中三项能力均为 **P2（Nice to Have）**，不阻塞 P0/P1 主线，但需在主线完成后按本 PRD 落地。

---

## 2. 能力一：WorkflowEngine 脚本运行时语义

### 2.1 当前状态

| 维度 | 当前实现 |
|------|----------|
| 图执行 | `ai/core/graph/executor.py` 支持 START/LLM/TOOL_CALL/TOOL_RESULT/OUTPUT/DECISION 节点的串行/分支执行 |
| Prompt 工作流 | `ai/tools/domains/platform/workflows.py` 用 `steps` + `prompt` 文本注入系统提示，依赖 LLM 自行按步骤调用工具 |
| 自定义图 | `ai/tools/domains/platform/workflow_graph.py` 用 JSON nodes/edges 保存并执行图工作流 |
| 缺失 | 无脚本级变量作用域、无 phase/log 事件、无条件表达式/循环、无并发分支、无子代理 `agent()` 调用、无结构化 WorkflowErrorCode、无 cancel/dispose |

### 2.2 目标范围

在 `ai/core/workflow/` 新增 **WorkflowEngine**，与现有 `ai/core/graph/` 和 `ai/tools/domains/platform/workflow_*.py** 并存，不替换现有能力。目标：

- 支持声明式/脚本式 workflow definition（YAML/JSON/Python-lite DSL）。
- 提供变量作用域、步骤/phase 生命周期、log 事件。
- 支持条件表达式、循环、并行/并发分支。
- 支持工具调用结果捕获与后续步骤引用。
- 支持子代理 `agent()` 调用。
- 结构化 `WorkflowErrorCode` 与 run-level cancel/dispose/grace timer。
- 完整事件投影：`workflow/start` / `phase/start` / `phase/log` / `agent-start` / `agent-end` / `workflow/end`。
- 能被现有 `AgentLoop` 调用。

### 2.3 用户故事

1. **作为开发者**，我想编写一个 workflow，在 5 个路线片段上并行调用 `analyze_route_summary`，再聚合结果生成调参报告，从而把原本需要手动多次对话的任务一次跑完。
2. **作为高级用户**，我想让 workflow 在 Panda 刷机失败时自动重试 3 次，超过则走"人工接管"分支并记录 fatal error，而不是直接崩溃。
3. **作为安全审核者**，我想看到某个 workflow run 的完整 phase 日志和每个工具调用的输入输出，便于事后审计。

### 2.4 验收标准（AC）

| ID | 验收标准 | 优先级 |
|----|----------|--------|
| WF-AC1 | `ai/core/workflow/` 目录存在 `engine.py`、`definition.py`、`context.py`、`errors.py`、`events.py` 五个核心模块 | P2 |
| WF-AC2 | `WorkflowEngine.run(definition, inputs)` 返回 `{ok, output, error, phases, logs}` | P2 |
| WF-AC3 | 支持步骤变量绑定：`steps[0].output.route_score` 可被 `steps[1].input.scores` 引用 | P2 |
| WF-AC4 | 支持条件表达式：`if: "${steps.check_vin.ok} == true"` | P2 |
| WF-AC5 | 支持循环：`for: item in ${steps.list_routes.result}` | P2 |
| WF-AC6 | 支持并行分支：`parallel: [step_a, step_b]`，超时统一由 grace timer 控制 | P2 |
| WF-AC7 | 支持子代理调用：`agent: {prompt: "...", tools: [...], max_rounds: 5}` | P2 |
| WF-AC8 | 事件投影：运行期间写入 `workflow/start`、`phase/start`、`phase/log`、`agent-start`、`agent-end`、`workflow/end` 到 session event log | P2 |
| WF-AC9 | 错误码：`WorkflowErrorCode` 包含 `INVALID_DEFINITION`、`TOOL_NOT_FOUND`、`TOOL_FAILED`、`AGENT_FAILED`、`TIMEOUT`、`CANCELLED`、`DISPOSED` | P2 |
| WF-AC10 | cancel/dispose：外部调用 `engine.cancel(run_id)` 后当前步骤完成即停止；`dispose(run_id)` 立即终止并清理 | P2 |
| WF-AC11 | AgentLoop 集成：`AgentLoop` 可通过 `workflow_id` 加载 WorkflowEngine definition 并在 step 边界查询一次图状态 | P2 |
| WF-AC12 | 不破坏现有 `workflows.py`、`workflow_custom.py`、`workflow_graph.py` 接口 | P2 |

### 2.5 不触碰范围

- 前端 workflow 可视化编辑器（纯后端能力）。
- 第三方 workflow 模板市场。
- 替换现有 prompt-based workflow 为强制脚本式 workflow。

---

## 3. 能力二：Skill scope/version/disposal 生命周期

### 3.1 当前状态

| 维度 | 当前实现 |
|------|----------|
| Skill 模型 | `ai/skill/models.py`：`Skill(id, name, description, policy, parameters, handler, metadata)` |
| 注册表 | `ai/skill/registry.py`：全局单例 `SkillRegistry`，基于 `base_dir/manifest.json` |
| 注册 | `register(skill, handler)` 直接写入全局 dict 并持久化 |
| 注销 | `unregister(skill_id)` 只从 dict 删除，无 dispose hook |
| 版本 | `metadata` 中可能存字符串 version，无语义化比较、无冲突检测 |
| 依赖 | 无 dependencies、capabilities、source 字段 |
| 内置技能 | `ai/skill/builtins.py` 注册 echo/get_time/workspace_summary 三个测试技能 |

### 3.2 目标范围

扩展 Skill 模型与 Registry，实现：

- `Skill` 增加 `scope`（global/session）、`capabilities`、`dependencies`、`source`、`version`（semantic version）。
- `SkillRegistry` 支持按 session 隔离子注册表（overlay on global）。
- 增加版本比较/冲突检测/依赖诊断。
- 增加 `dispose()` hook 与卸载前诊断。
- HTTP/工具接口暴露：dispose、version check、conflict diagnose、session scope registration。

### 3.3 用户故事

1. **作为多用户设备管理员**，我想为每个会话临时加载一套"试驾模式" skill，会话结束后自动 dispose，不影响其他会话。
2. **作为 skill 作者**，我想声明我的 skill 依赖 `vehicle-adaptation>=1.2.0` 和 `can_bus_access` capability，未满足时给出明确错误而不是运行时崩溃。
3. **作为平台维护者**，我想在升级 skill 前检查版本冲突和依赖兼容性，避免两个不同版本的同名 skill 同时生效。

### 3.4 验收标准（AC）

| ID | 验收标准 | 优先级 |
|----|----------|--------|
| SK-AC1 | `Skill` 模型新增字段：`scope: Literal["global", "session"]`、`capabilities: list[str]`、`dependencies: list[dict]`、`source: str`、`version: str`（semver） | P2 |
| SK-AC2 | `SkillRegistry` 新增 `for_session(session_id) -> SessionSkillRegistry`，返回 overlay 视图；session scope skill 不影响全局 | P2 |
| SK-AC3 | 增加 `SkillRegistry.dispose(skill_id)`，调用 skill.handler.dispose()（若存在），然后移除并持久化 | P2 |
| SK-AC4 | 增加 `SkillRegistry.diagnose(skill_id)`，返回版本、依赖满足情况、capability 是否授权、来源是否可信 | P2 |
| SK-AC5 | 增加 `SkillRegistry.check_conflicts()`，检测同名不同版本、循环依赖、缺失依赖 | P2 |
| SK-AC6 | 版本比较使用 semver：`1.2.0 < 1.10.0 < 2.0.0-alpha` | P2 |
| SK-AC7 | HTTP 路由：`POST /api/ai/skills/{id}/dispose`、`GET /api/ai/skills/{id}/diagnose`、`POST /api/ai/skills/diagnose-all`、`POST /api/ai/skills/session/register` | P2 |
| SK-AC8 | 工具接口：`dispose_skill`、`diagnose_skill`、`register_session_skill`、`check_skill_conflicts` | P2 |
| SK-AC9 | 内置 skill 升级到带 version/capabilities/dependencies 的完整示例 | P2 |
| SK-AC10 | session scope skill 在会话关闭/超时时自动 dispose | P2 |

### 3.5 不触碰范围

- 重写现有 `ai/skills/loader.py` 的文件技能加载流程（仅扩展字段）。
- 改变 skill 在 prompt 中的注入方式（只扩展元数据）。
- 引入第三方 skill 签名/证书机制（那是另一个 P2）。

---

## 4. 能力三：MCP resources/read 与 prompts/get 支持

### 4.1 当前状态

| 维度 | 当前实现 |
|------|----------|
| host | `ai/mcp/host.py`：实现 `MCPStdioClient`、`call_mcp_tool`、`discover_mcp_tools`、`discover_mcp_resources`、`discover_mcp_prompts` |
| 缺失 | `read_mcp_resource`、`get_mcp_prompt` 未实现 |
| HTTP | `server/handlers/phase2.py` 的 `api_platform_mcp` 只暴露 `discover_tools/discover_resources/discover_prompts` |
| 工具 | `tools/domains/platform/platform_extensions.py` 只注册 `call_mcp_tool`/`discover_mcp_tools`，无 resource/prompt 工具 |

### 4.2 目标范围

- 在 `ai/mcp/host.py` 新增 `read_mcp_resource` 和 `get_mcp_prompt`，复用 `MCPStdioClient.request`。
- 在 `server/handlers/phase2.py` 的 `api_platform_mcp` 增加对应 operation。
- 在 `tools/domains/platform/platform_extensions.py` 暴露对应平台工具与 schema。
- 补充 tests。

### 4.3 用户故事

1. **作为开发者**，我配置的 MCP server 提供了 `resource://docs/opendbc-latest`，我想让 AI 通过 `read_mcp_resource` 读取该文档作为上下文。
2. **作为用户**，我配置的 MCP server 提供了 prompt template "generate_car_port_draft"，我想让 AI 通过 `get_mcp_prompt` 获取该模板并填充变量。
3. **作为测试人员**，我想通过 pytest 验证 MCP resources/prompts 的读写路径，而不仅仅是 tools。

### 4.4 验收标准（AC）

| ID | 验收标准 | 优先级 |
|----|----------|--------|
| MCP-AC1 | `ai/mcp/host.py` 新增 `async def read_mcp_resource(params, server_id, uri, session_id)` | P2 |
| MCP-AC2 | `ai/mcp/host.py` 新增 `async def get_mcp_prompt(params, server_id, name, arguments, session_id)` | P2 |
| MCP-AC3 | `read_mcp_resource` 调用 `resources/read`，返回 `{ok, serverId, uri, contents}` | P2 |
| MCP-AC4 | `get_mcp_prompt` 调用 `prompts/get`，返回 `{ok, serverId, name, messages}` | P2 |
| MCP-AC5 | `server/handlers/phase2.py` 的 `api_platform_mcp` 增加 `op=read_resource` 和 `op=get_prompt` | P2 |
| MCP-AC6 | `tools/domains/platform/platform_extensions.py` 增加 `read_mcp_resource` 和 `get_mcp_prompt` 的工具 schema 与 handler | P2 |
| MCP-AC7 | `PLATFORM_TOOL_META` 和 `PLATFORM_SCHEMAS` 同步更新 | P2 |
| MCP-AC8 | 新增/补充 `ai/mcp/tests/` 中 resources/read 和 prompts/get 的单元测试 | P2 |
| MCP-AC9 | 复用现有 `MCPStdioClient.request` 和 session 锁，不引入新的 transport | P2 |

### 4.5 不触碰范围

- 第三方 MCP HTTP transport（保持 stdio）。
- MCP server 生命周期 persistent client/reconnect（已在 P1 规划）。
- 标准 ACP adapter（已在 P1 规划）。

---

## 5. 通用非功能需求

| ID | 需求 | 验收标准 |
|----|------|----------|
| NF-1 | 不影响 P0/P1 主线 | 新增代码通过独立模块引入，默认开关关闭，不破坏现有 `AgentLoop`、chat_handlers、session log |
| NF-2 | 离线可测 | WorkflowEngine 与 Skill lifecycle 的单元测试不依赖外部 API；MCP 测试使用 mock server 或已有 stub |
| NF-3 | 审计 | WorkflowEngine run、skill dispose、MCP resource/prompt 调用均写入 session audit event |
| NF-4 | 错误稳定码 | 新增错误均使用结构化 code，不返回裸 traceback 给前端 |
| NF-5 | 文档 | 每个新增工具/schema/HTTP 路由在本 PRD 落地后同步更新 `CAPABILITIES.md` 和 `PLUGIN_DEV.md` |

---

## 6. 依赖与接口关系

```text
ai/core/workflow/
  ├── engine.py          # WorkflowEngine 主入口
  ├── definition.py      # WorkflowDefinition 解析与校验
  ├── context.py         # RunContext / Scope / 变量引用
  ├── errors.py          # WorkflowErrorCode
  └── events.py          # workflow/start, phase/*, agent-start/end, workflow/end

ai/skill/
  ├── models.py          # Skill 字段扩展
  ├── registry.py        # 全局 + session overlay + dispose + diagnose
  └── builtins.py        # 升级内置 skill 示例

ai/mcp/host.py           # read_mcp_resource + get_mcp_prompt
ai/server/handlers/phase2.py  # MCP HTTP operation 扩展
ai/tools/domains/platform/platform_extensions.py  # 工具注册扩展
```

---

## 7. 待确认问题

1. **WorkflowEngine DSL 选择**：使用 YAML/JSON 声明式，还是 Python-lite DSL？建议先 YAML/JSON，便于前端将来可视化。
2. **Skill session scope 生命周期**：session scope skill 是随 HTTP session 销毁，还是随 AgentLoop session 关闭？建议随 AgentLoop session 关闭 dispose。
3. **MCP resource/prompt 的工具命名**：使用 `read_mcp_resource`/`get_mcp_prompt` 还是 `mcp_read_resource`/`mcp_get_prompt`？建议与现有 `call_mcp_tool` 风格一致：`read_mcp_resource`、`get_mcp_prompt`。
4. **WorkflowEngine 与现有图工作流的关系**：是否允许 workflow definition 内部嵌入 `graph` 步骤调用现有 `GraphExecutor`？建议允许，作为 migration 路径。
5. **Skill dispose 失败策略**：dispose hook 抛异常时是否阻止卸载？建议记录错误但仍移除，避免死锁。

---

## 8. 里程碑建议

| 阶段 | 周期 | 交付 |
|------|------|------|
| **P2-M1** | 1 周 | MCP resources/read + prompts/get 工具 + HTTP 路由 + tests |
| **P2-M2** | 1.5 周 | Skill scope/version/disposal 模型 + Registry + HTTP/工具接口 + tests |
| **P2-M3** | 2 周 | WorkflowEngine 核心 engine + definition/context/errors/events + AgentLoop 集成 + tests |
| **P2-M4** | 0.5 周 | 文档更新（CAPABILITIES.md / PLUGIN_DEV.md / 变更日志） |

---

## 9. 不触碰范围汇总

- 前端 workflow 可视化编辑器
- 第三方 MCP HTTP transport 与 persistent client/reconnect
- 标准 ACP adapter
- 重写现有 prompt-based workflow 为强制脚本式
- 第三方 skill 签名/证书机制
- 替换现有 `ai/skills/loader.py` 文件技能加载流程

---

*本文档为 P2 增量产品需求，需在 P0/P1 主线闭合后按里程碑实施。*
