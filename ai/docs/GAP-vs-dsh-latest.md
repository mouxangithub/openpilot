# GAP: E:\sp\ai vs E:\deepseek-harness 最新差距清单

- 日期：2026-09-04
- 基准：`E:\deepseek-harness`（TypeScript/Cordis 插件化 harness）
- 被对比：`E:\sp\ai`（OP 助手 Python 子模块）
- 来源：AUDIT-harness-alignment.md（含增量复核）+ 最新一轮独立探索代理对比（15 项差距）
- 用途：指导下一阶段对齐工作，每项完成后更新状态标注

> 状态标注：`[已闭合]` / `[部分闭合]` / `[未开始]` / `[外部阻断]`

## 一、状态校正（相对审计增量复核章节）

- **U7 MCP persistent stdio client：已闭合**（审计增量章节写作时未含）。`mcp/host.py` 已实现 per-(server, session) 持久客户端、initialize/initialized 握手、45s 超时、EOF/异常清理、配置指纹淘汰、`close_mcp_sessions_for_session` 批量关闭（接入 Agent `_run_post_chat`）。71/71 测试通过（`ai/mcp/tests/test_host_lifecycle.py` 4 项 + harness 套件）。
- **Sandbox 三入口统一：已闭合**。`h_run_shell`/`h_run_shell_command`/`_h_run_python_code` 均走 `run_shell_via_sandbox`/`run_python_via_sandbox`，session_id/cwd 透传。

## 二、剩余差距（按可落地优先级排序）

### P0 — 协议语义（可本地完成）

| # | 差距 | dsh 基准 | ai 现状 | 状态 |
|---|------|----------|---------|------|
| G1 | **Spill waterfall + content-block 语义**（= U3，任务 #46） | `packages/spill/spill-policy/src/index.ts:190-231`：`await next()` waterfall、只处理 accepted plain-text、跳过 nested PTC 的 model-facing arm、dispatch-log arm、UTF-8 head/tail retention、预留 notice 字节 | Model-facing arm（`ff3d04d`）+ dispatch-log arm（`3129923`）：`loop.py` 的 TOOL_RESULT 日志副本经 `bound_dispatch_log_copy`（kind="dispatch"）独立收敛——read 族/nested 的模型面结果保持完整而日志副本缩为 preview+locator，与 dsh `tools/ptc-dispatch-log` 语义对齐；spill ref 记录 kind；QA_PASS=YES（12 套件 89 项，spill 双写/双臂产物互不冲突、surface 校验合法、异常路径无阻断） | `[闭合]`（ai 无 PTC nested dispatch 生产者，arm 以 read 族/大结果日志副本为实际覆盖面） |
| G2 | **Goal/Plan/Todo event projection**（= U6） | `packages/goal/goal/src/domain.ts:13-114`：`goal/change` snapshot/tombstone 事件 + replay fold + scoped emit；plan/todo 同为 tool/domain event 投影 | **已闭合**：Commit `b9c115d`（mutation → domain event + replay fold + ContextVar 透传）+ `17ace86`（resume fold-first 重建，legacy 启发式仅作 fallback）；测试 14/14 + 全量回归 | `[已闭合]` |
| G3 | **Compaction（会话压缩与 tool 结果修剪）** | dsh 有 compaction 语义：长会话上下文压缩、旧 tool 结果裁剪，保证 token 预算 | Commit `9e7529c`：`core/session/tokens.py` 启发式 token meter（ASCII~4/CJK~1.6 chars-per-token）；`compaction.py` budget 门控（`ai_compaction_max_tokens` 默认 32768，超 budget×threshold_ratio 才触发，=0 只手动）+ retain_ratio 保留最近 tool 结果 + LLM 摘要优先/确定性 digest 兜底 + shadow-priced prune 带 token 价格；修复旧版 max_tokens=0 恒触发与非连续 REPLACE 必挂 surface 校验两处 bug；QA_PASS=YES（budget 门控/retain/摘要回退/pre-step 无回归逐项命中） | `[闭合]`（meter 为启发式估计；真实 provider usage 校准为后续） |

### P1 — 生命周期与错误契约（可本地完成）

| # | 差距 | dsh 基准 | ai 现状 | 状态 |
|---|------|----------|---------|------|
| G4 | **Agent 门面公开迭代接口**（= U13 的一部分） | public `wakeDriver()/whenIdle()` 生命周期驱动 | Commit `070dfc9`：AgentLoop 新增公开 `run_until_idle(is_cancelled=...)`（外部取消在排队轮间抛 ChatCancelled）与 `when_idle(timeout=...)`；门面 `run_with_loop` 已改用公开 seam，不再调用私有 `_run()`；静态守卫测试 + 7/7 行为测试 | `[已闭合]` |
| G5 | **LSP structured error taxonomy + 取消 + 结果上限**（= U5） | `packages/lsp/*`：provider/extension 路由、60s tool budget、结果上限、`NO_PROVIDER/WORKSPACE_OUTSIDE/INVALID_RESPONSE` 错误码、取消升级终止进程 | `tools/harness_tools.py` LSP 四操作 + `LspError` 结构化错误码 + 60s 超时 + 结果上限 + workspace containment + 取消停止 server（commit `f715db1`） | `[已闭合]`（真实 provider 端到端受环境限制） |
| G6 | **Scheduler（agent 级 cron/at/every 工具）** | dsh 有 agent 级定时任务工具（at/cron/every） | 双实现并存：`schedule/store.py`+`runtime.py`（durable reminder → mailbox，commit `6122a3d`）与 `tools/domains/agent_scheduler.py`+`scheduler_cron.py`（at/cron/every/list/cancel 工具 + `/api/ai/agent-schedule` 路由，纯 Python cron 解析，零新依赖） | `[已闭合]`（两套定位互补：store=提醒投递，agent_scheduler=动作调度） |
| G7 | **Subagent capability matrix + 父子 lineage**（= U9 剩余） | provider capability 声明、parentSession/delegationDepth/origin 持久化、depth/tool/outputSchema 能力拒绝 | Commit `10980e6`：`subagent/capabilities.py`（agentOptions/outputSchema/depthLimit/toolFilter/persona 五旗 + `validate_request`/`validate_depth` fail-loud 拒绝，深度上限对注入 runner 也生效）；runner 发 `subagent/start`/`subagent/end` lineage 事件（runId/provider/depth 配对）；pool/harness handler 透传 session_log | `[闭合]` |
| G8 | **Profile patch composition**（= U12 剩余） | `packages/boot/app-boot/src/profile.ts`：ordered `dsh.profile.bundles`、`dsh.bundle.patch`、`cordis.patch.yml` 原子合成 | Commit `03e3060`：`bundle/profile.py`——profile 目录（`profile.json` manifest + 用户 `cordis.patch.json` 层），有序 bundle 层→用户层→launcher 层合成（include 追加/逐键合并、exclude 剪除），未知/重复 bundle 与畸形 patch 均 fail-loud；patch 文件用 JSON（设备无 yaml 依赖） | `[闭合]`（HTTP 暴露为后续产品接线） |
| G9 | **U1 剩余细节**：完整 header 字段、ignorable event、全部 surface 细节核对 | `packages/core/session/src/types.ts:29-94,211-423` | 基础 strict event/surface 已落地（#34） | `[部分闭合]` |
| G10 | **U2 剩余细节**：完整 transcript/surface 语义、resume 后 loop 生命周期 | `packages/core/session/src/repair.ts` | repair closers 已落地（#33） | `[部分闭合]` |
| G11 | **U4 剩余**：SandboxPolicy session cwd/mode、可回放 runtime-context、host fallback 收敛 | `packages/sandbox/sandbox-policy/src/index.ts:1-130` | 三入口统一已闭合；session policy 缺 | `[部分闭合]` |
| G12 | **U13 剩余**：集中 config schema、依赖清单、启动诊断、边界错误稳定 code | 基准 Cordis inject/Schemastery Config | `config/registry.py` + `validator.py` + `config/schemas/*.json`（conversation/evolution/vehicle_safety/data_backup/dev_diagnostics/agent_scheduler 6 域）+ `core/diagnostics.py` 启动诊断 + `server/handlers/config_schema_handlers.py`（`GET /api/ai/config/schema`、`GET /api/ai/config/diagnose`、`PATCH /api/ai/config` 校验+revision）+ `core/errors.py` 稳定错误码；`aid.py` 启动时调用诊断 | `[已闭合]`（逐域迁移旧 key 为后续工作） |

### P1 — 外部阻断（不可本地完成）

| # | 差距 | 阻断原因 |
|---|------|----------|
| G13 | MCP HTTP transport + bounded reconnect | 需真实第三方 MCP server 验证（U7 剩余） |
| G14 | 标准 ACP SDK adapter（Content-Length framing、permission/progress/cancel、resume repair） | 需标准 ACP SDK 依赖与对端联调（U8） |

### P2 — 增强（可本地完成但优先级低）

- G15 WorkflowEngine 脚本运行时语义（U10）
- G16 Skill scope/version/disposal 生命周期（U11 剩余）
- G17 远程 spill backend、LSP diagnostics/rename、MCP resources/prompts、workflow 可视化/模板市场

### 探索代理识别的其余差距（合并归类）

- Scheduler → G6；LSP taxonomy → G5；MCP HTTP/reconnect → G13；Compaction → G3；Agent facade → G4。
- 其余 10 项（attachment admission 严格化、PTC nested dispatch 等）均归入 G9/G1/P2 细节。

## 三、本轮推进计划

1. **G1 Spill waterfall**（engineer-general）→ #46
2. **G2 Goal/Plan/Todo event projection**（engineer-retry）
3. **G5 LSP error taxonomy + 取消 + 结果上限**（engineer-fix）
4. 完成后依次：G4 Agent 门面、G3 Compaction、G6 Scheduler
5. 每项完成 → 独立 QA 复核（qa-final）

## 四、边界说明（不得对外虚报）

- 本机无 scons、无 `cereal/gen/`、无 `libparams_c.so` → 不能构建完整 openpilot，只能针对 `ai/` 子模块用 pytest 验证。
- G13/G14 需外部环境，本地只能做代码层准备，不能声称"验证通过"。
- 严格协议/生命周期/恢复语义仍未全闭合前，不得声称"与 deepseek-harness 全语义对齐"。
