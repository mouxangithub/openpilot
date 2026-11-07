# P1/P2 全量回归测试计划

> **作者**：严过关（QA 工程师）
> **版本**：v1.0（2026-09）
> **范围**：覆盖 P0 已验收基线、P1 独立 seam 与 P2 扩展面
> **基线仓库**：`E:\sp\ai`
> **设计依据**：`docs/system_design_p1p2.md`（T01-T05 任务列表与验收标准）

---

## 1. 测试目标

1. 验证 P0 基线（projection、sandbox、permission preset/approval、evidence、memory selector、command classifier、scheduler rrule、op_routes fallback）在 P1/P2 代码接入后不被破坏。
2. 验证 P1 新增/增强模块（attachment、chat commands、result_externalize、skills loader、session replay、MCP trust、session cost/manager、AgentLoop、ToolPipeline、bundle/profile、ACP、workflow graph、LSP handlers、config schema）满足 T01-T04 验收标准。
3. 验证 P2 扩展面（远程 spill backend、LSP 诊断、MCP resources/prompts、workflow 可视化、前端设置面板）具备可测试 seam，并在依赖缺失时优雅降级。
4. 保证 `ai/tests/bootstrap_pc.py` 可在无 openpilot/cereal 环境下完成核心回归。

---

## 2. 测试范围

### 2.1 纳入范围（In Scope）

| 层级 | 模块/文件 | 对应任务 | 重点验证项 |
|------|-----------|----------|------------|
| 基础设施 | `ai/config/registry.py`, `validator.py`, `schemas/*.json` | T01 | 新增命名空间加载；字段类型/枚举/min/max/secret/restart 校验；错误码稳定 |
| 启动诊断 | `ai/core/diagnostics.py` | T01 | P1/P2 模块 import 检查；致命错误不阻塞启动但记录 cloudlog |
| Server 路由 | `ai/server/routes/__init__.py`, `server/op_routes.py`, `server/app_factory.py` | T01/T02/T05 | 生产路由与本地 fallback 共存；关键 fallback 路由 200 |
| Agent facade | `ai/core/agent/agent.py`, `loop.py` | T02 | 默认启用 `AgentLoop`；`run_until_idle` 公共 seam；取消/排队边界 |
| 工具流水线 | `ai/core/tools/pipeline.py`, `tools/harness_tools.py`, `tools/agent_tools.py`, `core/tools/guard.py`, `core/tools/sandbox_hooks.py` | T02/T03 | spill post-waterfall、guard hooks、并发工具调用、session_ctx 传递 |
| Spill | `ai/tools/result_externalize.py` | T03 | 阈值决策、`toolresult://` 指针、read/grep 豁免、lease 生命周期 |
| 会话恢复 | `ai/core/session/log.py`, `repair.py`, `folds.py`, `server/handlers/sessions_handlers.py` | T03 | 损坏日志加载、repair closure、resume/repair 路由响应结构、domain state 重建 |
| Sandbox | `ai/sandbox/policy.py`, `ai/core/tools/sandbox_hooks.py`, `ai/tools/fs_tools.py` | T03 | 模式求交、越权路径、超时、取消结构化错误 |
| Bundle/Profile | `ai/bundle/{manifest,loader,store,profile_compose,profile,packer}.py`, `server/handlers/bundle_handlers.py`, `server/handlers/profile_handlers.py` | T04 | 原子安装与回滚、profile compose 冲突诊断、`GET /api/ai/profile/current` |
| ACP | `ai/acp/{protocol,loader}.py`, `ai/cli/acp_server.py` | T04 | `--smoke` 端到端；package 加载；JSON-RPC 帧协议 |
| MCP | `ai/mcp/{host,trust,resources}.py`, `tools/harness_tools.py` | T04/P2 | trust fingerprint、授权后工具可见、未授权不可见、health/resources |
| Workflow graph | `ai/tools/domains/platform/workflow_graph.py`, `ai/core/graph/executor.py` | T04 | graph 执行、`advance_graph_workflow` 步进、`requires_tools` 预检失败 |
| LSP | `ai/lsp/{server_manager,client,index,diagnostics}.py`, `server/handlers/lsp_handlers.py` | P2/T05 | 服务器生命周期、definition/references/hover、索引、诊断聚合 |
| 前端 | `ai/web/static/**` | T05 | 设置页配置卡片、会话列表 interrupted/repair 状态、spill 提示、MCP/LSP 面板 |
| 现有回归 | `ai/tests/test_harness_enable.py`, `test_agent_facade.py`, `test_subagent_capabilities.py`, `test_profile_composition.py`, `test_spill_waterfall.py` 等 | P0-P1 | 持续通过 |

### 2.2 暂不纳入/降级处理（Out of Scope / Deferred）

- 真实 MCP server stdio 长稳压测：使用 mock JSON-RPC transport 或 `--smoke` 模式验证。
- 远程 spill backend（S3/数据库）：仅验证 `SpillBackend` 接口与本地实现；远程 backend 作为后续插件测试。
- 前端跨浏览器 UI 自动化：以单元测试 + 路由契约测试为主，手工验收关键面板。
- 车辆控车相关操作：不在 P1/P2 范围内，沿用 P0 安全硬限制测试。

---

## 3. 测试策略

### 3.1 分层策略

| 层次 | 方法 | 工具 | 目标 |
|------|------|------|------|
| 单元测试 | 隔离函数/方法；mock 外部依赖 | `unittest`, `pytest`, `unittest.mock` | 核心算法、状态机、schema 校验、spill 决策 |
| 集成测试 | 多组件串联；临时目录/内存数据库 | `aiohttp.test_utils.AioHTTPTestCase`, `tempfile` | 路由 handler、bundle 安装、session resume/repair、LSP 生命周期 |
| 契约测试 | 验证请求/响应结构 | 静态断言 + handler 单元测试 | API 响应字段稳定（如 `{ok, error?, error_code?}`） |
| 端到端冒烟 | 启动服务并调用关键端点 | `python -m ai.cli.acp_server --smoke` | ACP stdio 基本会话流程 |
| 回归测试 | 复用并扩展现有 P0 测试 | `pytest ai/tests/test_*.py` | P0 基线不被破坏 |

### 3.2 Mock/Stub 原则

- `openpilot.common.params` / `swaglog`：通过 `ai.tests.bootstrap_pc` 与 `ai.dev.run_pc._install_openpilot_mocks()` 打桩。
- LLM provider：注入 `OfflineProvider` 或 `AsyncMock` 的 `stream_fn`。
- MCP server：用 `AsyncMock` 替换 `MCPStdioClient.request`，返回标准 `tools/list`、`tools/call` 响应。
- LSP server：用 mock subprocess + `LspClient` 或 fake JSON-RPC reader/writer。
- Bundle 存储：使用临时目录作为 `BundleStore.store_dir`。

### 3.3 环境策略

- **PC 本地**：`cd /e/sp && PYTHONPATH="E:\sp\ai" python -m pytest ai/tests/test_p1p2_regression.py -q`
- **CI/无 openpilot**：`python -m pytest ai/tests/test_p1p2_regression.py -q`（依赖 `bootstrap_pc`）
- **有 openpilot 设备**：运行全量 `ai/tests/test_*.py` + `ai/core/tests/test_*.py` + `ai/bundle/tests/test_*.py`

---

## 4. 用例清单

### 4.1 T01 — 项目基础设施与配置 schema

| ID | 用例名称 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|----|----------|----------|------|----------|--------|
| T01-01 | ConfigRegistry 加载全部新增命名空间 | schema 文件存在 | `ConfigRegistry().namespaces()` | 包含 sandbox/spill/mcp/bundle/workflow/lsp/subagent | P0 |
| T01-02 | `get_schema(namespace)` 返回字段结构 | registry 已加载 | 调用 `get_schema('spill')` | 返回 revision、fields、默认值、secret/restart 标记 | P0 |
| T01-03 | validate_payload 识别未知字段 | 已知 schema | 传入未注册字段 | 返回 `ERR_CONFIG_INVALID` 与字段名 | P0 |
| T01-04 | validate_payload 校验枚举/范围/secret/restart | 已知 schema | 传入越界数值、非法枚举、非布尔 | 分别返回类型/枚举/边界错误 | P0 |
| T01-05 | 启动诊断覆盖 P1/P2 import | 运行环境 | `run_startup_diagnostics()` | `ai.core.agent.agent`、`ai.tools.result_externalize`、`ai.bundle.profile_compose`、`ai.lsp.server_manager` 等 import 检查通过 | P0 |
| T01-06 | 致命 import 失败不阻塞启动 | 临时移除某非核心模块 | 调用诊断 | `ok=False` 但函数不抛异常；cloudlog 记录 | P1 |
| T01-07 | `/api/ai/config/schema` 按 namespace 返回 | 服务启动 | GET `/api/ai/config/schema?namespace=workflow` | `ok=True`, `data.namespace == 'workflow'` | P0 |
| T01-08 | `/api/ai/config/diagnose` 返回诊断结果 | 服务启动 | GET `/api/ai/config/diagnose` | `ok` 与 `data.checks` 列表 | P0 |
| T01-09 | `/api/ai/config/schema` 缺失 namespace 404 | 服务启动 | GET `?namespace=not_exist` | `ok=False`, `error_code=ERR_NOT_FOUND`, status=404 | P1 |

### 4.2 T02 — AgentLoop 默认启用与工具流水线

| ID | 用例名称 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|----|----------|----------|------|----------|--------|
| T02-01 | Agent 默认走 run_with_loop | 新 Agent 实例 | `ai_use_agent_loop` 默认 True | 不调用旧私有 `loop._run()`，源码静态检查通过 | P0 |
| T02-02 | `AgentLoop.run_until_idle` 单 turn 完成 | mock `stream_fn` 返回 idle | 调用 `run_until_idle()` | 返回 `{ok: True, agentId}` | P0 |
| T02-03 | run_until_idle 排空排队 followup | 注入 mid-turn 用户消息 | 调用 `run_until_idle()` | `state.inbox.has_pending == False` | P0 |
| T02-04 | 外部取消抛出 ChatCancelled | 注入取消回调 | 调用 `run_until_idle(is_cancelled=lambda: True)` | 抛出 `ChatCancelled` | P0 |
| T02-05 | harness_tool_schemas 包含 P1 工具 | — | 调用 `harness_tool_schemas()` | 包含 goal_create/plan_generate/todo_write/lsp/run_python_code/workflow_advance/mcp_discover | P0 |
| T02-06 | ToolPipeline 安装 spill 与 guard hooks | Agent 初始化 | 检查 pipeline hooks 长度 | spill post-waterfall 与 guard 已注册 | P1 |
| T02-07 | 工具调用至少触发一次事件 | mock provider 返回 tool_call | AgentLoop 运行 | SessionLog 中出现 TOOL_CALL/TOOL_RESULT | P1 |

### 4.3 T03 — 会话恢复、Spill 与 Sandbox

| ID | 用例名称 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|----|----------|----------|------|----------|--------|
| T03-01 | SessionLog 加载损坏日志 | 构造缺少 closure 的 JSONL | `SessionLog(..., load_persisted=True)` | 成功加载，事件可遍历 | P0 |
| T03-02 | repair 生成确定性 closure | 缺少 TOOL_RESULT/STEP_END/TURN_END | `repair_session_log(log)` | 仅补充缺失事件，不臆造模型结果；重复调用幂等 | P0 |
| T03-03 | `/api/ai/sessions/{id}/resume` 响应结构 | persisted log 存在 | POST resume | 返回 `{ok, replayedEvents, reconstructed:{goal,plan,todo}, interrupted, repaired}` | P0 |
| T03-04 | `/api/ai/sessions/{id}/repair` 修复并返回 | persisted log 存在 | POST repair | 返回 `{ok, repaired}`，repaired 为事件列表 | P0 |
| T03-05 | fold_domain_events 重建 goal/plan/todo | 注入 GOAL_CHANGE/PLAN_CHANGE/TODO_CHANGE | 调用 fold | 返回最新 snapshot；tombstone 置 null | P0 |
| T03-06 | spill 大文本生成 toolresult:// | 文本超过阈值 | `spill_text_if_needed()` | 返回指针 + 预览，文件保存完整内容 | P0 |
| T03-07 | read/grep 工具不 spill | 调用 read_file 返回超大文本 | pipeline execute | 结果未 externalized | P0 |
| T03-08 | 失败结果不 spill | handler 返回 `ok=False` | pipeline execute | 原错误返回，无 externalized 标记 | P0 |
| T03-09 | sandbox 越权路径拒绝 | policy 为 read-only | 请求写系统路径 | 返回结构化错误并含 policy 摘要 | P1 |
| T03-10 | shell/python 超时/取消 | 注入长时间命令 | 取消或超时 | 返回 `ERR_TIMEOUT`/`cancelled`，不泄漏绝对路径 | P1 |

### 4.4 T04 — ACP/MCP/Bundle/Workflow

| ID | 用例名称 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|----|----------|----------|------|----------|--------|
| T04-01 | ACP server smoke | 可运行 `python -m ai.cli.acp_server --smoke` | 执行 smoke | initialize/tools/list/session/create/shutdown 通过 | P0 |
| T04-02 | ACP package 加载 | 提供有效 ACP 目录 | `acp.loader.load_directory()` | 返回 AcpPackage，元数据完整 | P1 |
| T04-03 | 已授权 MCP 工具可见 | server 已信任并启用 | `register_mcp_handlers()` | 工具以 `mcp__<server>__<tool>` 注册 | P0 |
| T04-04 | 未授权 MCP 工具不可见 | server 未信任 | `register_mcp_handlers()` | 对应工具不在 handlers 中 | P0 |
| T04-05 | MCP trust fingerprint 稳定 | 固定 server config | `fingerprint_server_config()` | 相同配置 digest 相同；改动 args/env 后 digest 变 | P1 |
| T04-06 | Bundle 原子安装 | store 中存在 bundle zip | `store.install_bundle(..., clean=True)` | 成功安装；失败回滚，目标目录无残留 | P0 |
| T04-07 | Bundle 安装 capability 冲突 | 两个 bundle 声明同名 capability | 安装第二个 | 抛出 BundleInstallError 并说明冲突 | P1 |
| T04-08 | ProfileComposer compose 冲突诊断 | 两个 bundle 对同 key 设不同值 | `compose()` | 返回冲突消息列表，冲突含 `ERR_PROFILE_CONFLICT` | P0 |
| T04-09 | Profile preview 返回有序 layers | 提供 bundle 列表 | `preview()` | layers 顺序 = bundles → profile | P1 |
| T04-10 | `GET /api/ai/profile/current` | 服务启动 | 调用接口 | 返回 sandbox/spill/mcp/agentLoop 当前生效值 | P0 |
| T04-11 | Workflow graph 执行 | 保存 graph | `execute_graph_workflow()` | 返回 `GraphResult(ok=True)` | P1 |
| T04-12 | Workflow advance 步进 | graph 存在 | `advance_graph_workflow(id, 'step')` | 当前 node 前进，状态持久化 | P1 |
| T04-13 | Workflow requires_tools 预检失败 | node 声明未注册 tool | 执行 graph | 提前失败并返回替代路径/错误 | P1 |

### 4.5 T05/P2 — 前端可观测性与扩展面板

| ID | 用例名称 | 前置条件 | 步骤 | 预期结果 | 优先级 |
|----|----------|----------|------|----------|--------|
| T05-01 | 设置页配置卡片存在 | 前端构建/静态资源 | GET `/static/js/settings/*.js` | 文件存在且导出 registry/render/save 模块 | P1 |
| T05-02 | 会话列表展示 interrupted/repair | 构造 repair 所需日志 | GET `/api/ai/sessions` | compact 列表含 `repairRequired`/`interrupted` 标记 | P1 |
| T05-03 | 工具结果 spill UI 提示 | spill 后结果 | 前端渲染 | 显示 "Full output saved" 类提示，不泄露完整路径 | P2 |
| T05-04 | MCP panel 基础路由 | 服务启动 | GET `/api/ai/mcp/servers`（fallback 或真实） | 返回 `{ok, items:[]}` 或真实列表 | P2 |
| T05-05 | LSP panel 基础路由 | 服务启动 | GET `/api/ai/lsp/servers` | 返回 `{ok, servers:[]}` | P2 |
| T05-06 | workflow editor 保存 graph | 提供 graph JSON | POST `/api/ai/workflows`（如存在）或本地 save_graphs | 保存后可重新加载 | P2 |

---

## 5. 环境依赖

### 5.1 必需

- Python 3.13（与仓库一致）
- `PYTHONPATH=E:\sp\ai` 或等效路径
- 现有依赖：`aiohttp>=3.9`、`pytest`
- 运行 PC 测试前导入 `ai.tests.bootstrap_pc`

### 5.2 可选

- `openpilot-common`：在真实车机/有 openpilot 源码环境使用；PC 测试通过 mock 跳过。
- `croniter`：若扩展 scheduler 完整 cron 语义。
- `aiosqlite` / `boto3`：远程 spill backend 插件测试（P2 后续）。
- `mcp` SDK：可选，当前使用轻量 stdio JSON-RPC。

### 5.3 测试数据

- 临时 bundle zip（通过 `BundleStore.save_bundle` 创建）
- 临时 session JSONL（通过 `SessionLog` + `tempfile` 创建）
- mock ACP 目录（含 `acp.json` 与占位 payload）

---

## 6. 阻塞/外部依赖项

| 依赖 | 影响范围 | 状态 | 缓解措施 |
|------|----------|------|----------|
| `ai/server/handlers/workflow_handlers.py` | T04 workflow HTTP CRUD + T05 可视化保存 | 当前不存在 | 先测 `workflow_graph.py` 直接 API；workflow handler 落地后补充集成用例 |
| `ai/server/handlers/mcp_handlers.py` | T04 MCP health/resources、T05 MCP panel | 当前不存在 | 使用 `op_routes.api_fallback` 验证 `{ok, items:[]}`；handler 落地后补充真实用例 |
| `ai/lsp/diagnostics.py` | P2 LSP 诊断聚合 | 当前不存在 | 先测 `lsp/client.py` + `server_manager.py` 基础生命周期；诊断模块落地后补充 |
| 远程 spill backend 实现 | P2 远程 spill | PRD 列 P2，尚未实现 | 接口已定义，本地 backend 为默认；远程 backend 作为插件后续测试 |
| 前端构建链 | T05 UI 自动化 | 无构建链，原生 JS | 以路由/静态文件存在性 + 契约测试代替完整 E2E |
| MCP server 真实进程 | T04 MCP stdio | 依赖外部二进制 | 使用 mock transport 或示例 `everything` server 做冒烟 |

---

## 7. 执行计划

1. **Round 1**：运行现有 P0/P1 回归 + 新增 `test_p1p2_regression.py`；记录失败并路由。
2. **Round 2**：修复测试或等待工程师修复源码后重新运行；仍失败的作为 Known Issues 记录。
3. **每日/每次 PR**：`python -m pytest ai/tests/test_p1p2_regression.py ai/tests/test_harness_enable.py ai/tests/test_agent_facade.py -q`
4. **里程碑回归**：`python -m pytest ai/tests ai/core/tests ai/bundle/tests -q`

---

## 8. 成功标准

- `test_p1p2_regression.py` 全部通过。
- 现有 P0/P1 回归测试（`test_harness_enable.py`、`test_agent_facade.py`、`test_subagent_capabilities.py`、`test_profile_composition.py`、`test_spill_waterfall.py`）继续通过。
- T01-T04 中所有 P0 优先级用例通过；P1/P2 用例失败数 ≤ 2 且均为已知外部依赖项。
- 无新增阻塞性生产代码缺陷未路由。
