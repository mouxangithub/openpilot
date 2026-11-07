# ai/ 子模块架构优化建议报告

> **分析对象**: `E:\sp\ai` 子模块（约 764 个 .py 文件）  
> **版本**: v1.0  
> **日期**: 2026-09-12  
> **编写**: software-architect  
> **说明**: 本报告基于现有 PRD、架构设计文档、历史任务记录及代码片段进行静态分析，未执行全量代码扫描。具体优化实施前建议结合 IDE/AST 做精准依赖分析。

---

## 执行摘要

ai/ 子模块经过多年/多人迭代，已出现明显的**分层模糊、重复抽象、注册入口分散**问题。最紧迫的三项优化是：

1. **统一工具注册层**：将 `harness_tools.py`、`agent_tools.py`、`platform_extensions.py` 中的多入口合并为单一 `ToolRegistry`。
2. **合并 skills/ 与 skill/**：文件型 Skill 包与动态 Skill 注册表应共享同一模型和生命周期。
3. **统一 session/event 持久化**：`core/session/storage.py` 与 `core/session/log.py`（SessionLog）应收敛到同一事件协议。

以下按问题类型逐条给出优化建议。

---

## 1. 重复抽象或职责重叠

### 1.1 `ai/skills/` 与 `ai/skill/` 应合并或明确分层

**问题描述**
- `ai/skills/` 是文件型 Skill 包加载器（loader/registry.json/snapshot/disclosure/unified），面向静态 Skill 目录。
- `ai/skill/` 是动态 Skill 注册表（models/registry/builtins/diagnostics/conflicts/session_registry/semver），面向运行时 Skill 对象。
- 两者都定义了 Skill 概念，但数据模型不同、注册入口不同、生命周期不同，容易造成开发者混淆。

**涉及文件**
- `ai/skills/loader.py`
- `ai/skills/registry.json`
- `ai/skills/snapshot.py`
- `ai/skills/disclosure.py`
- `ai/skills/unified.py`
- `ai/skill/models.py`
- `ai/skill/registry.py`
- `ai/skill/builtins.py`
- `ai/skill/session_registry.py`

**建议方案**
- **长期目标**：合并为 `ai/skills/` 单一层级，`ai/skill/` 作为兼容 shim 保留 1-2 个版本后废弃。
- **短期方案**：
  1. 统一 `SkillManifest` 模型，将文件型 Skill 的 metadata 映射到 `ai/skill/models.py` 的字段。
  2. `ai/skills/loader.py` 只负责从磁盘读取并返回 `SkillManifest` 列表，不再维护独立 registry。
  3. `ai/skill/registry.py` 成为唯一运行时注册表，接收来自文件加载器、内置、MCP 的 Skill。
  4. `ai/skills/unified.py` 改名为 `ai/skills/loader.py`，原 `loader.py` 内容迁移。

**优先级**: 高

**风险**
- 文件型 Skill 的历史字段可能无法完全映射到新模型，需要兼容层。
- 合并期间测试覆盖不足会导致 Skill 工具丢失。

---

### 1.2 `core/session/storage.py` 与 `core/session/log.py`（SessionLog）功能重叠

**问题描述**
- `core/session/storage.py` 负责 JSONL transcript 的 append/read/repair（事件协议层）。
- `core/session/log.py` 的 `SessionLog` 也提供 `append(EventType, payload)` 和持久化，但事件模型不同。
- 同一 session 可能同时被两个组件写不同格式的日志，导致 resume 时数据不一致。

**涉及文件**
- `ai/core/session/storage.py`
- `ai/core/session/log.py`
- `ai/core/session/repair.py`
- `ai/core/session/manager.py`

**建议方案**
- 将 `SessionLog` 作为 `SessionStorage` 的薄包装或子类：
  - `SessionStorage` 提供底层 JSONL append/read/fsync。
  - `SessionLog` 仅提供类型化 API（如 `log.append_turn_start(...)`），内部调用 `SessionStorage.append_event()`。
- 统一事件类型枚举，移除 `log.py` 中独立的 `EventType`。

**优先级**: 高

**风险**
- 历史 `SessionLog` 文件格式与 `SessionStorage` 不兼容，需要 migration 或双写过渡期。
- 测试用例（如 `test_harness_enable.py` 中的 `repair_session_log`）需要同步更新。

---

### 1.3 `permissions/` 与 `sandbox/` 职责边界模糊

**问题描述**
- `permissions/` 包含 policy/service/presets/approval/hitl/capability/vehicle_guard。
- `sandbox/` 包含 runtime/policy。
- 两者都涉及"是否允许执行"，但 `permissions/` 偏 capability/HITL，`sandbox/` 偏进程/文件系统隔离。代码中可能出现交叉调用。

**涉及文件**
- `ai/permissions/policy.py`
- `ai/permissions/service.py`
- `ai/permissions/presets.py`
- `ai/sandbox/runtime.py`
- `ai/sandbox/policy.py`

**建议方案**
- 明确分层：
  - `permissions/` = **授权决策**（who can do what）。
  - `sandbox/` = **执行隔离**（how to run safely）。
- 将 `sandbox/policy.py` 中关于 capability 判断的逻辑迁移到 `permissions/service.py`。
- `sandbox/runtime.py` 只负责进程/文件系统层面的隔离实现，不直接做 capability 判断。

**优先级**: 中

**风险**
- 当前代码可能大量依赖 `sandbox.policy` 的 capability 判断，迁移需逐步进行。

---

## 2. 循环依赖风险

### 2.1 `tools/agent_tools.py` 与 `skill/registry.py`、`mcp/host.py` 的互相导入

**问题描述**
- `agent_tools.py` 在 `build_tool_schemas()` 中导入 `ai.skill.registry` 和 `ai.tools.harness_tools`。
- `harness_tools.py` 又可能导入 `agent_tools.py` 中的工具函数（如 `_h_lsp`、`_h_mcp_discover`）。
- MCP handler 注册也在 `agent_tools.py` 中完成，形成"工具注册中心 → 扩展 → 工具注册中心"的循环。

**涉及文件**
- `ai/tools/agent_tools.py`
- `ai/tools/harness_tools.py`
- `ai/skill/registry.py`
- `ai/mcp/host.py`

**建议方案**
- 引入**工具注册器接口** `ai/tools/tool_registry.py`（**注：原稿写作 `ai/tools/registry.py`，实际落点为 `tool_registry.py`；`registry.py` 保留为兼容 facade，勿改为类**）：
  - 定义 `ToolRegistry` 类，提供 `register(name, handler, spec, capability)`。
  - `agent_tools.py` 在模块加载时创建全局 `ToolRegistry` 实例（经 `registry_from_agent_tools()` 桥接）。
  - `harness_tools.py`、`skill/registry.py`、`mcp/host.py` 在初始化时向该实例注册，而不是互相 import。
- 将工具 schema 构建延迟到首次调用时（lazy build），打破模块级循环。

**优先级**: 高

**风险**
- 重构后需确保所有工具的注册顺序不变，否则会导致工具缺失。
- 延迟构建可能影响启动时工具列表的可用性，需要缓存机制。

---

### 2.2 `core/agent/agent.py` 与 `core/chat/runner.py` 的紧耦合

**问题描述**
- `Agent` 依赖 `runner.py` 构造参数。
- `runner.py` 又依赖 `Agent.run()` 返回值做生命周期管理。
- 本地 dev 的 `op_routes.py` 试图复用 `Agent`，但需要复制大量 `runner.py` 的构造逻辑。

**涉及文件**
- `ai/core/agent/agent.py`
- `ai/core/chat/runner.py`
- `ai/server/op_routes.py`

**建议方案**
- 提取 `ai/core/agent/factory.py`：
  - 提供 `create_agent(session_id, agent_id, body, config, *, provider=None)`。
  - 工厂函数统一处理 `Params`、`StateReader`、`ToolPipeline`、`OfflineProvider` 等默认依赖。
- `runner.py` 和 `op_routes.py` 都调用工厂函数。
- `Agent` 类本身只保留运行逻辑，移除对 `runner.py` 的隐式依赖。

**优先级**: 高

**风险**
- 工厂函数的默认参数需要与现有 `runner.py` 完全一致，否则会影响生产 chat 行为。

---

## 3. 配置/Schema 分散

### 3.1 配置模型分散在多个文件

**问题描述**
- `ai/core/config/schema.py` 定义 `AIOPConfig`（6 域配置）。
- `ai/common/evolution_config.py` 可能包含 evolution 相关配置。
- `ai/common/params.py` 可能包含与 `openpilot.common.params` 桥接的配置。
- 多处存在对 `Params().get(...)` 的直接调用，配置来源不透明。

**涉及文件**
- `ai/core/config/schema.py`
- `ai/core/config/diagnose.py`
- `ai/common/evolution_config.py`
- `ai/common/params.py`
- 各模块中直接使用 `Params().get(...)` 的文件

**建议方案**
- 建立单一配置源：
  - `AIOPConfig` 作为运行时配置对象。
  - 所有模块通过 `AIOPConfig` 获取配置，不直接调用 `Params()`。
  - `Params()` 仅在配置加载阶段使用一次。
- 将 `evolution_config.py` 中的配置项迁移到 `AIOPConfig` 的 `evolution` 域。
- 提供配置诊断 API（已实现于 `server/op_routes.py:api_config_diagnose`），扩展为自动检测未通过 `AIOPConfig` 读取的参数。

**优先级**: 中

**风险**
- `Params()` 调用点众多，全面替换工作量大，建议分阶段进行。

---

### 3.2 工具 Schema 分散在多文件

**问题描述**
- `ai/tools/schemas.py`：标准工具 schema。
- `ai/tools/domains/platform/platform_extensions.py`：平台扩展工具 schema。
- `ai/tools/harness_tools.py`：harness 工具 schema。
- `ai/tools/vehicle/schemas.py`：车辆工具 schema。
- `ai/tools/agent_tools.py` 负责汇总，但逻辑复杂且容易遗漏。

**涉及文件**
- `ai/tools/schemas.py`
- `ai/tools/domains/platform/platform_extensions.py`
- `ai/tools/harness_tools.py`
- `ai/tools/vehicle/schemas.py`
- `ai/tools/agent_tools.py`

**建议方案**
- 每个 domain 只声明自己负责的 schema 和 handler：
  - `ai/tools/vehicle/__init__.py` 提供 `register_vehicle_tools(registry)`。
  - `ai/tools/domains/platform/__init__.py` 提供 `register_platform_tools(registry)`。
  - `ai/tools/harness_tools.py` 提供 `register_harness_tools(registry)`。
- `agent_tools.py` 简化为 orchestrator（`ToolRegistry` 取自 `ai/tools/tool_registry.py`）：
  ```python
  registry = ToolRegistry()
  register_vehicle_tools(registry)
  register_platform_tools(registry)
  register_harness_tools(registry)
  register_skill_tools(registry)
  register_mcp_tools(registry)
  return registry
  ```

**优先级**: 高

**风险**
- 需要统一 handler 签名（部分 handler 是 sync，部分是 async，部分需要 `params`/`get_state_reader`）。
- 建议通过 adapter 统一 handler 接口。

---

## 4. 工具注册方式不统一

### 4.1 多处注册入口

**问题描述**
- `ai/tools/agent_tools.py:make_handlers()` 汇总所有 handler。
- `ai/tools/harness_tools.py:register_harness_handlers()` 注册 harness handler。
- `ai/tools/domains/platform/platform_extensions.py` 注册平台扩展 handler。
- `ai/skill/registry.py` 注册 skill handler。
- `ai/mcp/host.py` 动态发现 MCP handler。
- 各入口的参数签名不一致，导致本地 dev 和生产的工具集可能不同。

**涉及文件**
- `ai/tools/agent_tools.py`
- `ai/tools/harness_tools.py`
- `ai/tools/domains/platform/platform_extensions.py`
- `ai/skill/registry.py`
- `ai/mcp/host.py`

**建议方案**
- 引入 `ai/tools/tool_registry.py` 作为统一注册表（**落点说明见 2.1 节；`registry.py` 保留 facade**）：
  ```python
  class ToolRegistry:
      def register(self, name: str, handler: Callable, spec: dict, capability: dict | None = None) -> None: ...
      def get_handler(self, name: str) -> Callable | None: ...
      def get_schema(self, name: str) -> dict | None: ...
      def list_tools(self) -> list[dict]: ...
      def handlers(self) -> dict[str, Callable]: ...
      def to_handlers_dict(self) -> dict[str, Callable]: ...
      def filter_by_capability(self, *, group=None, driving=None, enabled_only=False, ...) -> list[str]: ...
  ```
- 所有扩展通过 `register_tools(registry)` 函数注册。
- `Agent` 内部 `ToolPipeline` 直接使用 `ToolRegistry`。

**优先级**: 高

**风险**
- 需要改动 `ToolPipeline` 的初始化方式，可能影响现有测试。

---

## 5. Session/Event 存储格式不一致

### 5.1 `SessionStorage` vs `SessionLog`

已在 1.2 中描述，此处补充风险：
- `repair_session_log()` 在 `test_harness_enable.py` 中测试，但生产 resume 可能走 `SessionStorage.repair()`，两者修复逻辑不一致会导致 resume 行为差异。
- 建议统一修复逻辑，将 `repair_session_log()` 实现委托给 `SessionStorage.repair_interrupted()`。

**优先级**: 高

---

## 6. 前端与后端接口不一致或重复路由

### 6.1 `server/routes.py` 与 `server/op_routes.py` 重复

**问题描述**
- `server/routes.py` 是生产路由，可能包含 `/api/chat`、`/api/chat/completions`。
- `server/op_routes.py` 是本地 dev 路由，也包含 `/api/chat`、`/api/chat/completions`、`/api/chat/jobs`。
- 两者逻辑重复，本地 dev 与生产行为容易分叉。

**涉及文件**
- `ai/server/routes.py`
- `ai/server/op_routes.py`
- `ai/server/app_factory.py`（如果存在）

**建议方案**
- 提取共享 handler 到 `ai/server/handlers/chat.py`：
  - `create_chat_job(request)`
  - `run_chat(request)`
  - `chat_completions(request)`
- `routes.py` 和 `op_routes.py` 只负责路由绑定，handler 逻辑共享。
- `op_routes.py` 可以额外提供本地 dev 专用的 bootstrap/providers/status 等路由。

**优先级**: 高

**风险**
- 生产路由可能有认证/中间件依赖，共享 handler 时需确保本地 dev 也能安全调用。

---

### 6.2 前端 Web 路由与后端 API 能力不匹配

**问题描述**
- 前端（`ai/web/static/`）可能缺少对 harness 工具、capability 面板、workflow 状态等能力的消费界面。
- 后端已具备的能力（如 `/api/ai/config/diagnose`、`/api/audit/verify`）前端未调用。

**涉及文件**
- `ai/web/static/js/*.js`
- `ai/web/index.html`
- `ai/server/routes.py`

**建议方案**
- 建立 API 能力清单 `CAPABILITIES.md`，前后端共同维护。
- 前端按能力清单逐步实现对应面板，避免后端能力闲置。
- P2 若启动 React/Electron 重构，可借此机会统一前后端接口契约。

**优先级**: 中

**风险**
- 前端重构工作量大，建议先补齐 Vanilla JS 面板，再规划重构。

---

## 7. 其他可优化点

### 7.1 `evolution/` 与 `core/agent/` 的边界

**问题描述**
- `ai/evolution/gepa_engine.py`、`skill_source.py` 涉及技能进化和代码生成，与 `core/agent/` 的 AgentLoop 可能有重叠。
- 建议明确：`evolution/` 负责技能/工作流的生成与优化，`core/agent/` 负责运行时执行。

**涉及文件**
- `ai/evolution/gepa_engine.py`
- `ai/evolution/skill_source.py`
- `ai/core/agent/loop.py`

**建议方案**
- `evolution/` 只输出 `WorkflowDefinition` 或 `SkillManifest`，不直接调用 AgentLoop。
- AgentLoop 通过标准接口消费 evolution 产物。

**优先级**: 低

---

### 7.2 `core/workflow/` 与现有 `core/graph/`、`tools/domains/platform/workflow_*.py` 并存

**问题描述**
- P2 新增 `core/workflow/` 后，将出现三种 workflow 运行时：
  1. `core/graph/executor.py` 的图执行
  2. `tools/domains/platform/workflows.py` 的 prompt-based workflow
  3. `core/workflow/` 的脚本式 WorkflowEngine
- 三者并存会增加维护成本。

**涉及文件**
- `ai/core/graph/executor.py`
- `ai/tools/domains/platform/workflows.py`
- `ai/tools/domains/platform/workflow_graph.py`
- `ai/tools/domains/platform/workflow_custom.py`
- `ai/core/workflow/engine.py`

**建议方案**
- 长期：统一为 `core/workflow/`，将图执行作为 workflow 的一种 step（`kind: graph`）。
- 短期：保持并存，但统一通过 `WorkflowEngine` 暴露接口，旧实现作为 adapter 接入。

**优先级**: 中

**风险**
- 统一过程需要兼容现有 workflow 定义格式。

---

## 8. 优化路线图建议

| 阶段 | 优化项 | 优先级 | 预计收益 |
|------|--------|--------|----------|
| **M1** | 统一 `ToolRegistry`，合并工具注册入口 | 高 | 消除循环依赖，统一本地/生产工具集 |
| **M1** | 提取 `AgentFactory`，统一本地/生产 Agent 构造 | 高 | 消除 `op_routes.py` 与 `runner.py` 的重复逻辑 |
| **M2** | 合并 `skills/` 与 `skill/` | 高 | 消除 Skill 概念双轨制 |
| **M2** | 统一 `SessionStorage` 与 `SessionLog` | 高 | 消除 resume/repair 行为不一致 |
| **M3** | 共享 chat handler，合并 `routes.py` 与 `op_routes.py` | 高 | 消除生产/本地 dev 路由分叉 |
| **M3** | 清理 `permissions/` 与 `sandbox/` 边界 | 中 | 明确授权与隔离职责 |
| **M4** | 统一配置源 `AIOPConfig` | 中 | 提升配置可维护性 |
| **M4** | 统一 workflow 运行时 | 中 | 降低 workflow 相关维护成本 |
| **M5** | 前端能力清单对齐 + 面板补齐 | 中 | 提升后端能力利用率 |
| **M6** | 明确 `evolution/` 与 `core/agent/` 边界 | 低 | 长期架构清晰 |

---

## 9. 风险总览

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 重构导致工具丢失 | 高 | 新增全量工具注册回归测试 |
| `SessionLog` 格式迁移失败 | 高 | 双写过渡期 + 修复逻辑统一 |
| `routes.py` 与 `op_routes.py` 合并引入认证问题 | 中 | 共享 handler 时保留各自的中间件 |
| Skill 合并导致文件型 Skill 不可用 | 中 | 文件型 loader 保持兼容，仅将运行时注册委托 |
| 配置统一工作量大 | 中 | 分阶段替换 `Params()` 调用点 |

---

*本报告为静态架构分析结论，具体实施前建议用 AST/依赖图工具做精准影响面评估。*
