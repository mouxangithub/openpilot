# Harness 架构对齐审计

- 基准：`E:\deepseek-harness`（当前源码）
- 被审计：`E:\sp\ai`（当前源码）
- 范围：Agent/Session/Tools/Sandbox/Subagent/Skill/Todo/Plan/Goal/LSP/Attachment/Spill/ACP/MCP/Bundle/Workflow/配置/依赖/运行流程。
- 结论：P0 业务工具已接通，但“P0-P2 与 deepseek-harness 语义完全对齐”**不成立**；仍有 4 项 P0 级协议/恢复差距、5 项 P1 级架构差距，另有若干 P2 能力缺失。

## 1. 已闭合项（以功能接通为准）

| 领域 | ai 当前实现（路径:行） | 基准对应 | 结论 |
|---|---|---|---|
| AgentLoop | `core/agent/agent.py:716-721` 默认进入 `run_with_loop`，保留显式旧路径 | `packages/core/agent-loop/src/agent.ts:70-545` | P0 主流程已接通；但运行模型不同，见未闭合 U1 |
| 工具注册 | `tools/agent_tools.py:1792-1794` 调用 harness + MCP 注册；`tools/harness_tools.py:489-512` | `packages/*/tool-*` + `core/tools` | goal/plan/todo/subagent/LSP/Python/workflow/MCP 可见可调 |
| 附件注入 | `core/chat/runner.py:120-148` 解析 `body.attachments` 与 `attachment://` 并追加 system block | `packages/attachment/*` | P0 接线闭合；基准更严格的 admission/image wire 约束仍缺 |
| Spill | `core/agent/agent.py:129-146` pipeline post hook；`tools/result_externalize.py:48-110` | `packages/spill/spill-policy/src/index.ts:110-231` | 大结果盘片化闭合；waterfall 组合与 UTF-8 cap 语义不完全一致（U3） |
| Sandbox 基本接线 | `core/tools/sandbox_hooks.py:17-57`，`agent_tools.py:1602-1608` | `packages/sandbox/sandbox-policy/src/index.ts:1-130` | shell/python 有 runner、超时/输出/禁词；基准 session policy 未对齐（U4） |
| LSP 四操作 | `tools/harness_tools.py:339-375`；`lsp/client.py:228-259` | `packages/lsp/tool-lsp` | 四操作和 1-based 转换已存在；缺 provider/capability 严格校验（U5） |
| MCP 基本桥接 | `tools/harness_tools.py:442-482`，`mcp/host.py:99-149` | `packages/mcp/mcp-client/src/index.ts:1-188` | enabled server 可发现/调用；仅 stdio 一次性 RPC，无长连/reconnect/HTTP（U7） |
| ACP 基本入口 | `cli/acp_server.py:39-187` | `packages/acp/acp/src/*` | 独立 stdio 可 smoke；不是标准 ACP SDK/帧协议（U8） |
| Workflow 图基础 | `tools/domains/platform/workflow_graph.py:1-80` | `packages/workflow/workflow/src/index.ts:31-187` | 图加载/推进可用；不是 WorkflowEngine 脚本运行时（U10） |

## 2. 未闭合项（按优先级）

### P0-阻断级

**U1 Session 事件/Surface 不是基准协议（P0，最高）。**
- `E:\sp\ai\core\session\log.py:19-31,133-153,214-239,309-354`：事件 envelope 仅 `type/seq/time/data/surfaceOp/sourceEventSeqs`；surface 仅 APPEND/简化 REPLACE，缺 `SESSION_FORMAT_VERSION`、SessionHeader（cwd、parentSession、seedLength、origin、delegationDepth、agentPreset）、`ignorable`、严格 surface eligibility/provenance/replacement 校验。
- 基准：`E:\deepseek-harness\packages\core\session\src\types.ts:29-94,211-423`、`surface.ts:184-395`。要求 message-producing event 强制 surface marker、seq 连续、replace 必须引用 shadowed seq、tool-result replace 只能改 content。
- 建议：为 JSONL 增加版本 header；将 surface fold 独立为严格 `fold_surface`，加载/append 时拒绝非法 event；保留现有日志用兼容导入器，不静默吞未知 required event。

**U2 Resume/Repair 只报告 orphan，不合成可继续 transcript（P0）。**
- `server/handlers/sessions_handlers.py:74-123` 仅扫描 `tool/call - tool/result` 差集，返回 `interrupted`，`repaired=[]`；`tools/domains/platform/transcript_store.py:101-138` 只拼 SSE delta。
- 基准：`E:\deepseek-harness\packages\core\session\src\repair.ts:13-133` 的 `interruptedTurnClosers` 对未完成 call 合成错误 `tool/result`（区分 `TOOL_NOT_STARTED`/`TOOL_OUTCOME_UNKNOWN`），再补 `step/end`、`turn/end(reason=interrupted)`，保留原始 evidence。
- 建议：实现确定性 `interrupted_turn_closers`；resume 先 repair/append closers，再创建 loop；side effect 工具结果文案必须要求先核验外部状态，不自动重试。`recover_partial` 不应作为唯一恢复源。

**U3 Spill post-hook 不是 waterfall 语义（P0）。**
- `core/agent/agent.py:129-146` 直接 `externalize_if_needed(result)`；工具 registry 无 `(exec,result,next)` 链；失败只靠同步文件写回退。
- 基准：`E:\deepseek-harness\packages\spill\spill-policy\src\index.ts:190-231` 先 `await next()`，只对 accepted plain-text 内容处理；跳过 nested PTC 的 model-facing arm，另有 dispatch-log arm；预留 notice 字节确保替换结果仍不超 cap。
- 建议：扩展 `ToolPipeline` post hook 为 waterfall（兼容现有简单 hook）；结果模型区分 value/content/block；对纯文本 block 做 UTF-8 head/tail retention；为 `tool/code-dispatch`（若实现 PTC）单独限日志副本。

**U4 Sandbox 缺 session-scoped policy 和可回放上下文（P0）。**
- `core/tools/sandbox_hooks.py:17-57` 仅读 `ai_sandbox_shell` 全局开关；`sandbox/runtime.py:13-31` 有 mode 类型但未持久化/解析；runner cwd 使用 `workspace_path` 全局目录。
- 基准：`E:\deepseek-harness\packages\sandbox\sandbox-policy\src\index.ts:1-130`：deployment 默认 read-only、session cwd 边界、session mode override 事件/Projection、每次 capability call resolve，policy 进入 runtime-context 供 replay。
- 建议：新增 `SandboxPolicyService` 等价 Python seam；以 session cwd 为 containment root；把 mode/cwd 写入 `request/context`；默认 read-only，workspace-write 需 profile/显式批准；删除“sandbox 异常自动回退宿主”或至少只在显式兼容开关下允许并审计。

### P1-高优先级

**U5 LSP seam 只实现调用，不实现 provider 生命周期语义。**
- `tools/harness_tools.py:339-375` 要求先 HTTP 启动 server；缺失时返回字符串错误；`lsp/server_manager.py:17-123` 以 workspace 单一 client 管理，配置无能力/扩展名冲突校验。
- 基准包 `packages/lsp/lsp-stdio`、`tool-lsp` 将 provider/extension 路由注册进 DI，调用有结果上限、取消和 structured LspError。
- 建议：从 session cwd 推导 workspaceRoot；provider 按 language/extension 路由；加入 60s tool budget、结果上限、`NO_PROVIDER/WORKSPACE_OUTSIDE/INVALID_RESPONSE` 错误码；调用取消时升级终止进程。

**U6 Goal/Plan/Todo 是独立 JSON 快照，不是 session event projection。**
- `goal/store.py:31-141,158-332`、`plan/store.py:16-191`、`todo/store.py:15-112` 直接读写状态文件；工具结果虽写进 `SessionLog`，状态变更本身不可由 session replay 重建。
- 基准 goal：`packages/goal/goal/src/domain.ts:13-114` 以 `goal/change` 完整 snapshot/tombstone 事件 + replay fold + goal/changed scoped emit；plan/todo 亦通过 tool/domain event 投影。
- 建议：保持 JSON store 作为当前兼容读模型，新增 session 事件写入；resume 以事件 fold 为准，快照只作索引/缓存；所有状态迁移用稳定错误码（如 GOAL_STALE_REVISION、GOAL_INVALID_TRANSITION）。

**U7 MCP 缺连接生命周期和 transport 能力。**
- `mcp/host.py:73-96` 每次调用 spawn 一次并 `communicate`；`tools/harness_tools.py:442-482` 读取 server 工具名缓存，工具 schema 不从 `tools/list` 载入；无 reconnect、断连隔离、60s per-call、serverName 合法性/作用域保留。
- 基准：`packages/mcp/mcp-client/src/index.ts:47-188` 支持 stdio + streamable-http、namespace `mcp__server__tool`、工具注册 generation、reconnect、scope disposal、startup failure policy。
- 建议：将 `ai/mcp/host.py` 改为 app/session 生命周期 client；保存完整 schema；namespace 改为 `mcp__<server>__<tool>`（兼容旧名映射）；allowlist + server scope；支持 HTTP transport 与 bounded reconnect。

**U8 ACP 不是 ACP wire/SDK 对齐。**
- `cli/acp_server.py:27-37,121-147` 采用裸 newline JSON（每行一个 JSON-RPC），且 `session/resume` `:73-78` 只设置 id，不加载/repair session；缺标准 `session/request_permission`、tool progress/cancel 语义。
- 基准 `packages/acp/acp/src/codec.ts:14-33` 对标准 ACP StopReason 映射，实际入口依赖 `@agentclientprotocol/sdk`，支持标准 session 生命周期。
- 建议：以标准 ACP SDK/协议帧实现 adapter；至少引入 Content-Length framing、版本协商、structured stopReason 映射、resume 真正调用 session repair；stdout 仅协议、stderr 日志保留。

**U9 Subagent 仅单一 in-process pool，缺 provider/capability 安全边界。**
- `subagent/pool.py:15-188` 只有固定并发池；`harness_tools.py:255-267` `params=None, tools=None`，不会继承父 session cwd/权限，结果回主会话缺稳定 child event lineage。
- 基准 `packages/subagent/subagent-acp/src/index.ts:1-207` 及 `subagent-*` providers：provider capability 声明、ACP 子进程隔离、parent cwd 继承、permission policy、depth/tool/outputSchema 能力拒绝。
- 建议：定义 `SubagentProvider` 接口及 capability matrix；至少实现 in-process + ACP provider；持久化 parentSession/delegationDepth/origin；工具执行使用子 session 的 policy，不传 `None`。

### P1/P2

**U10 Workflow 语义不等价。** `workflow_graph.py:49-80` 使用 JSON 图和 `advance_graph_workflow`，而基准 `packages/workflow/workflow/src/index.ts:31-187` 是脚本引擎/WorkflowEngine Service，含 phase/log/agent-start/end、fatal error taxonomy、run cancellation/disposal。建议先明确产品是否需要脚本兼容；若需要，新增 `WorkflowEngine` seam，图仅作一个 provider。

**U11 Skill 仅 handler 动态注册，不具备基准 package/loader 生命周期。** `tools/agent_tools.py:1786-1803` 直接把 registry skill 映射 lambda；基准有 `skill/skill`、`tool-skill`、文件技能包、badge/catalog 与 scope disposal。建议新增 skill manifest/version/capability、session scope、卸载与冲突诊断。

**U12 Bundle/Profile 语义不等价。** `bundle/manifest.py:33-76` + `bundle/loader.py:20-113` 是 zip+bundle.json+ACP 包安装；基准 `packages/boot/app-boot/src/profile.ts:5-21,49-118,791-860` 是 profile 目录、ordered `dsh.profile.bundles`、bundle `dsh.bundle.patch`、用户 `cordis.patch.yml`、原子 patch 合成和模块 fallback。建议把当前 bundle 作为 artifact/import 层，新增 profile manifest、patch layers、原子校验/回滚，避免声称已完成 P1 bundle/profile。

**U13 配置/依赖模型未对齐。** 基准根 `package.json` + 各包 manifest 通过 `inject`/Schemastery Config 声明依赖，启动时 loader 拒绝缺失依赖、冲突、坏配置；E:
sp
aI 主要依靠 Params（`ai/common/storage.py`）和函数级 try/except 静默回退。建议为 harness 能力引入集中 config schema、依赖清单、启动诊断；边界错误保留稳定 code，禁止核心初始化异常被无声吞掉。

## 3. 运行流程对比

**基准流程**：profile/bundle compose → Cordis Context/Service 注入 → SessionStore prepare/restore + strict surface fold → ReactLoopAgent `send/followup/steer/inject` durable inbox → pre-step system-prompt assemble → request waterfall/adapter prepare → stream chunks → BlockAssembler → tool pipeline（pre/guard/body/post waterfall）→ tool result event/projection → turn/step closures → `whenIdle`/disposal。

**E:\sp\ai 流程**：aiohttp route → `_prepare_chat_run` 组装 tools → `Agent` 构造 `SessionLog` + ToolPipeline → runner 组 system/messages → AgentLoop 通过内部 `state.inbox` 驱动 → stream chunks → 简化 tool execute/post → SSE + transcript_store JSONL；goal/plan/todo、附件、MCP、sandbox 主要是外围接线。

核心风险：E:\sp\ai 的 `AgentLoop` 仍直接调用私有 `loop._run()`（`core/agent/agent.py:671`附近），而基准通过 public `wakeDriver()/whenIdle()` 生命周期驱动；这可能造成取消/后续消息唤醒、并发 session、dispose 边界不一致。建议增加 public `run_once()/when_idle()` seam，禁止门面调用私有 loop 方法。

## 4. P0-P2 完成声明核对

| 声称 | 真实判断 |
|---|---|
| P0-1 AgentLoop 默认接通 | **基本成立**，但 session surface/inbox/repair 语义未完全对齐 |
| P0-2 goal/plan/todo/subagent 模型工具 | **工具发现/调用成立**；状态未事件溯源、subagent provider/capability 缺失 |
| P0-3 附件注入 | **基本成立**；基准 admission/image content block/权限与 token provenance 更严格 |
| P0-4 spill post-execute | **基本成立**；非 waterfall，缺 dispatch-log、content block/UTF-8 cap 语义 |
| P0-5 sandbox shell/python | **部分成立**；无 session policy/回放上下文，异常可回退宿主有越权风险 |
| P0-6 LSP 工具 | **部分成立**；四 action 可调用，但 provider 路由/取消/structured errors 不完整 |
| P0-7 resume/repair | **不成立（关键）**；当前只返回 orphan 列表，未合成可继续 transcript |
| P0-8 MCP 桥接 | **部分成立**；发现/调用可用，缺连接生命周期、完整 schema、reconnect/HTTP |
| P1-1 ACP stdio | **部分成立**；入口存在，wire/session resume/标准 ACP 不对齐 |
| P1-2 bundle/profile | **不成立**；bundle archive ≠ profile patch composition |
| P1-3 workflow_graph | **部分成立**；图推进可用，不等价 WorkflowEngine 脚本/事件语义 |
| P2 增强项 | **未实现/非目标**：多 provider subagent 调度、远程 spill、LSP rename/diagnostics、workflow 可视化/模板市场、MCP resources/prompts 等 |

## 5. 修复优先顺序

1. **P0-A**：Session strict event/surface + repair closers（U1/U2），这是 resume、ACP、回放的共同地基。
2. **P0-B**：SandboxPolicy session scope + remove/contain host fallback（U4），避免工具越权。
3. **P0-C**：ToolPipeline post waterfall + spill content-block semantics（U3）。
4. **P0-D**：Goal/plan/todo event projection + subagent parent lineage/capabilities（U6/U9）。
5. **P1-A**：标准 ACP adapter + MCP persistent client/reconnect（U8/U7）。
6. **P1-B**：LSP provider registry/strict errors（U5）。
7. **P1-C**：Profile/bundle patch composition，workflow engine compatibility（U12/U10）。
8. **P2**：skill lifecycle、远程 spill、provider/adapter 扩展、diagnostics/visual workflow。

## 最终结论

`E:\sp\ai` 已完成“Python 侧 P0 工具接线”而非“deepseek-harness 全语义移植”。AgentLoop、工具 schema、附件、spill、sandbox、LSP、MCP、ACP、workflow 均有可执行入口，但 Session 事件溯源/repair、SandboxPolicy、Tool post waterfall、Goal/Plan/Todo projection、Subagent provider、标准 ACP、MCP 生命周期、Bundle/Profile composition 仍未对齐。故建议对外状态标记为：**P0 功能入口已接通；P0 协议与恢复语义部分未闭合；P1 仅有实验性入口；P2 未实现**。

## 6. 2026-09-04 增量复核（基于本轮后续实现）

本文件前述结论形成于本轮代码继续演进之前，以下是对后续实现的校正，不删除原始审计证据：

### 已由后续实现闭合或明显改善

| 原编号 | 后续实现 | 当前判断 |
|---|---|---|
| U7 部分 | `mcp/host.py` 基础桥接已保持；本轮未新增生命周期 | 仍部分闭合 |
| U9 部分 | `subagent/providers.py` provider registry、`SubagentTask.provider`、`subagent_start_many`、`subagent_report` 已实现 | provider 抽象/并行/汇报闭合；ACP provider、capability matrix、父子 lineage 仍缺 |
| U11 部分 | `skills/unified.py` 合并 file/dynamic catalog，动态优先、按 id 去重 | catalog 合并闭合；scope/version/disposal 仍缺 |
| U12 部分 | `BundleManifest.capabilities()`、`BundleLoader.install()` 原子回滚、能力冲突预检 | bundle 安装安全性改善；profile patch composition 仍缺 |
| P2 部分 | `spill/sqlite_store.py` 跨实例持久化；`subagent_start_many` 并行 fan-out | 本地 durable spill 与并行子代理闭合；远程 spill 等仍缺 |

### 仍未闭合的关键项（不得对外声称“全语义对齐”）

1. **U1 Session strict event/surface（P0）**：基础能力已落地（格式版本、SessionHeader、seq 连续性、surface eligibility、REPLACE provenance 与 target 校验均有实现和测试）；仍需继续核对与 dsh 的完整 header 字段、ignorable event 与全部 surface 细节。
2. **U2 Resume/Repair（P0）**：基础 repair 已落地：确定性生成 `TOOL_NOT_STARTED`/`TOOL_OUTCOME_UNKNOWN` closers、`step/end`、`turn/end(interrupted)`，并具备幂等 append 与测试；仍需继续核对完整 dsh transcript/surface 语义及 resume 后 loop 生命周期。
3. **U3 Spill waterfall（P0）**：仍是简单 post hook，未实现 accepted plain-text/content-block、UTF-8 cap、dispatch-log 等 dsh 语义；SQLite 只解决持久化 backend。
4. **U4 SandboxPolicy（P0）**：仍缺 session-scoped cwd/mode policy、可回放 runtime-context；宿主 fallback 风险需继续收敛。
5. **U5 LSP lifecycle（P1）**：仍缺 provider/extension 路由、结果上限、取消终止与完整 structured error taxonomy。
6. **U6 Goal/Plan/Todo event projection（P1）**：状态变更仍主要由 JSON 快照维护，session replay 不能完全重建。
7. **U7 MCP lifecycle（P1）**：仍缺持久 client、reconnect、HTTP transport、完整 tools/list schema 与 namespace scope。
8. **U8 ACP wire/SDK（P1）**：仍是裸 newline JSON-RPC，缺标准 SDK framing、permission/progress/cancel、真正 resume repair。
9. **U10 WorkflowEngine（P1/P2）**：当前 workflow graph 可推进，但不是脚本引擎/phase/log/cancel/disposal 语义。
10. **U12 Profile composition（P1）**：当前 bundle 能力校验与原子安装不等于 profile ordered bundle/patch layer 合成。
11. **U13 Config/dependency model（P1/P2）**：仍缺集中 schema、依赖冲突拒绝与核心初始化异常的严格处理。
12. **P2 剩余**：远程 spill、ACP/Codex/dsh 外部 provider、LSP diagnostics/rename、MCP resources/prompts、workflow 可视化/模板市场、skill scope lifecycle。

### 复核结论

本轮交付准确表述为：**OP 助手已形成可运行的 Python 侧 Harness 能力层，核心工具入口、SSE job 流、Agent Registry、Subagent provider registry、统一 Skill catalog、Bundle 原子安装、SQLite spill、WebUI 状态侧栏已落地；但与 deepseek-harness 的严格协议/生命周期/恢复语义仍有 P0–P1 未闭合项。**
