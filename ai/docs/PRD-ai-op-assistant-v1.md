# AI OP 助手增强版产品需求文档（PRD）v1.0

> **项目**: AI OP 助手增强版  
> **版本**: v1.0  
> **日期**: 2026-09-12  
> **编写**: software-product-manager  
> **输入文档**:
> - `E:\sp\ai\docs\GAP-vs-dsh-latest.md`（ai 子仓库 vs deepseek-harness 差距分析）
> - `E:\learn-workbuddy\learn-workbuddy-技术总结报告.md`（learn-workbuddy 技术总结）
> - `E:\sp\ai\docs\PRODUCT.md`、`ARCHITECTURE.md`、`AI_AGENT_ROADMAP.md`、`AUDIT-harness-alignment.md`、`VEHICLE_ADAPTATION_GUIDE.md`、`CAPABILITIES.md`、`ARCH-harness-enable-incremental.md`

---

## 1. 项目信息

| 字段 | 内容 |
|------|------|
| **产品名称** | ai_op_assistant_enhanced |
| **编程语言 / 框架** | Python 3.13 + aiohttp + Vanilla JS 前端；参考 learn-workbuddy 的 Vite + React + MUI + Tailwind CSS 建议用于后续 WebUI 重构 |
| **语言** | 中文 |
| **原始需求复述** | 基于 learn-workbuddy 的 harness 安全/审计/扩展设计，结合 deepseek-harness 协议语义差距，制定 AI OP 助手增强版 PRD，指导后续 P0/P1 能力落地与车机安全对齐 |

---

## 2. 产品定义

### 2.1 Product Goals

1. **统一 Harness 语义对齐**：在保留 OP 助手车机垂直能力的前提下，补齐与 deepseek-harness 的 P0 协议/恢复/沙盒语义差距，使会话可恢复、事件可审计、工具调用可治理。
2. **车辆场景下的安全增强**：从"全局沙盒开关"升级为"分级 capability + human-in-the-loop + 审计链"，在提升 commaai/openpilot 操作效率的同时守住车机安全底线。
3. **可扩展的垂直助手体验**：通过 Skill/Expert/MCP 三层扩展模型，让普通车主用自然语言完成调优、适配、排障，开发者能安全地接入新工具与新车型能力。

### 2.2 目标用户

| 用户角色 | 特征 | 核心诉求 |
|----------|------|----------|
| **日常车主** | 不懂编程、不懂汽修 | 用自然语言调手感、复盘行程、获取告警解释 |
| **新车适配者** | 愿意投入数天到数周做车型适配 | 指纹采集、CAN 分析、适配草稿生成、PR 描述 |
| **排障用户** | 遇到 engage 失败、突然退出、参数漂移 | 一键健康检查、分诊向导、参数回滚 |
| **开发者/CI 维护者** | 维护 fork、GitHub Runner、prebuilt | 安全的 shell/python 沙盒、自动化任务、PR 自动化 |
| **安全/合规审核者** | 关注车辆数据与操作审计 | 完整审计链、分级授权、可回放的操作上下文 |

### 2.3 核心用户故事

1. **作为日常车主**，我想对 AI 说"变道激进一点"，让助手在停车后生成可回滚的调参 diff 并经我确认后写入，从而避免记参数名和手动改设置。
2. **作为新车适配者**，我想让助手读取我的 CAN 日志、对照已有 DBC、生成 CarState/CarController 草稿到 `adaptation_drafts/`，以便我在 PC 上人工 review 后再提 PR。
3. **作为排障用户**，我想点击"开不起来"向导，助手自动执行 Panda → SecOC → 指纹 → dashcam → LKAS 分诊链，并告诉我哪一步失败及下一步怎么做。
4. **作为开发者**，我想通过 MCP 接入一个自研的 SecOC 诊断 server，并在 Web 设置里一键 trust + 授权该 server 的特定工具，而不必改主代码。
5. **作为安全审核者**，我想查看某次固件刷写操作的完整审计链：谁授权、什么 capability、哪个设备句柄、固件哈希、结果状态，且日志不可篡改。

---

## 3. 技术规范

### 3.1 功能需求池

#### P0 — Must Have（产品上线前必须完成）

| ID | 需求 | 验收标准 | 参考来源 |
|----|------|----------|----------|
| F0-1 | **Session 严格事件协议与版本头** | JSONL 增加 `SESSION_FORMAT_VERSION`、SessionHeader（cwd/parentSession/seedLength/origin/delegationDepth/agentPreset）、`ignorable` 标记；surface 操作严格校验 APPEND/REPLACE provenance；seq 连续、replace 必须引用 shadowed seq、tool-result replace 只能改 content | GAP G9, AUDIT U1 |
| F0-2 | **Resume/Repair 可继续 transcript** | 实现确定性 `interrupted_turn_closers`：对未完成 call 合成 `TOOL_NOT_STARTED`/`TOOL_OUTCOME_UNKNOWN`、补 `step/end`、`turn/end(reason=interrupted)`；resume 幂等、side-effect 工具结果不自动重试 | GAP G10, AUDIT U2 |
| F0-3 | **ToolPipeline post-execute spill waterfall** | 先 `await next()`，仅处理 accepted plain-text；跳过 nested PTC 的 model-facing arm；实现 dispatch-log arm（日志副本缩为 preview+locator）；UTF-8 head/tail retention；预留 notice 字节 | GAP G1, AUDIT U3 |
| F0-4 | **SandboxPolicy session-scoped policy** | 新增 `SandboxPolicyService`；session cwd 为 containment root；mode/cwd 写入 `request/context`；默认 read-only；`workspace-write` 需 profile/显式批准；宿主 fallback 仅在显式兼容开关下允许并审计 | GAP G11, AUDIT U4 |
| F0-5 | **车辆 capability 分级授权** | 定义 `usb_device_access`/`can_bus_access`/`vehicle_flash`/`vehicle_log_read`/`dbc_parse` 等 capability；运行时权限 = Harness 基础权限 ∩ Skill manifest ∩ capability grant | learn-workbuddy 第 8 章 |
| F0-6 | **高后果动作 human-in-the-loop** | 固件刷写、控制报文发送、系统关键参数写入必须弹窗确认；模型不能替用户点击"允许"；确认 UI 在隔离安全上下文显示 | AI_AGENT_ROADMAP 安全分层 |
| F0-7 | **哈希链审计落盘** | 每次工具调用、capability 使用、固件刷写写入 SHA256 hash-chain；包含 `prev_hash`、chain tip anchor；支持本地 `verify` 命令 | learn-workbuddy s23 |
| F0-8 | **AgentLoop 默认接通** | `Agent.run()` 默认进入 `run_with_loop()`；参数 `ai_use_agent_loop` 默认 True；保留旧路径兜底 | ARCH-harness-enable D1 |
| F0-9 | **Harness 模型工具统一注册** | 新增 `tools/harness_tools.py`，导出 `harness_tool_schemas()` 与 `register_harness_handlers()`；在 `make_handlers` 与 `chat_handlers` 双向接入 | ARCH-harness-enable D2 |
| F0-10 | **附件注入 LLM** | `core/chat/runner.build_chat_messages` 支持 `body.attachments` 与 `attachment://id`；mime 白名单、每附件字符上限、跨 session 隔离 | ARCH-harness-enable D3 |

#### P1 — Should Have（上线后 1-2 个迭代补齐）

| ID | 需求 | 验收标准 | 参考来源 |
|----|------|----------|----------|
| F1-1 | **LSP provider 生命周期语义** | provider/extension 按 language/extension 路由；60s tool budget；结果上限；`NO_PROVIDER/WORKSPACE_OUTSIDE/INVALID_RESPONSE` 错误码；取消升级终止进程 | GAP G5, AUDIT U5 |
| F1-2 | **Goal/Plan/Todo event projection** | 状态变更写入 session event；resume 以事件 fold 为准；快照只作索引/缓存；稳定错误码（GOAL_STALE_REVISION 等） | GAP G2, AUDIT U6 |
| F1-3 | **MCP persistent client + bounded reconnect** | per-(server, session) 持久客户端；initialize/initialized 握手；45s 超时；EOF/异常清理；配置指纹淘汰；namespace `mcp__<server>__<tool>` | GAP G13, AUDIT U7 |
| F1-4 | **标准 ACP SDK adapter** | Content-Length framing、版本协商、structured stopReason、`session/request_permission`、tool progress/cancel、真正 resume repair | GAP G14, AUDIT U8 |
| F1-5 | **Subagent provider capability matrix + lineage** | provider capability 声明、ACP 子进程隔离、parent cwd 继承、depth/tool/outputSchema 能力拒绝；持久化 parentSession/delegationDepth/origin | GAP G7, AUDIT U9 |
| F1-6 | **集中 config schema + 启动诊断** | 6 域 JSON schema（conversation/evolution/vehicle_safety/data_backup/dev_diagnostics/agent_scheduler）；`GET /api/ai/config/diagnose`；边界错误稳定 code；aid 启动时调用诊断 | GAP G12, AUDIT U13 |
| F1-7 | **Bundle/Profile patch composition** | profile 目录 + ordered bundles + 用户 patch 层；原子合成、include/exclude、未知/重复 bundle fail-loud | GAP G8, AUDIT U12 |
| F1-8 | **WorkflowEngine 脚本运行时语义** | phase/log/agent-start/end、fatal error taxonomy、run cancellation/disposal；图仅作为 provider 之一 | GAP G15, AUDIT U10 |
| F1-9 | **Skill scope/version/disposal 生命周期** | skill manifest/version/capability、session scope、卸载与冲突诊断 | GAP G16, AUDIT U11 |

#### P2 — Nice to Have（后续产品增强）

| ID | 需求 | 验收标准 | 参考来源 |
|----|------|----------|----------|
| F2-1 | **远程 spill backend** | 工具结果/会话摘要可写入远程对象存储；多设备共享 | GAP G17 |
| F2-2 | **LSP diagnostics/rename** | 除四操作外支持 diagnostics、rename | GAP G17 |
| F2-3 | **MCP resources/prompts** | 支持 MCP resources/list、resources/read、prompts | GAP G17 |
| F2-4 | **Workflow 可视化/模板市场** | Web 端 workflow 编辑器、社区模板 | GAP G17 |
| F2-5 | **Embedding-based 记忆召回** | 当前 lexical + recency 引入 embedding/BM25/LTR | learn-workbuddy 改进点 |
| F2-6 | **前端 UI 重构为 React/Electron** | 将 Vanilla JS 前端迁移到 Vite + React + MUI + Tailwind CSS | learn-workbuddy 技术栈 |

### 3.2 非功能需求

#### 性能

| ID | 需求 | 验收标准 |
|----|------|----------|
| NF-P1 | 上下文预算可控 | `ai_compaction_max_tokens` 默认 32768；超阈值触发 compaction；保留最近 tool 结果 + LLM 摘要/确定性 digest 兜底 |
| NF-P2 | 大工具结果外部化 | 超过 `ai_externalize_threshold` 写入磁盘，prompt 中只保留 preview + locator |
| NF-P3 | 工具 schema 按需加载 | MCP/Skill 工具走延迟加载（ToolSearch + DeferExecuteTool），避免一次性塞入 400+ schema |
| NF-P4 | AgentLoop 取消响应 | 外部取消在排队轮间抛 ChatCancelled；取消后已执行 side-effect 工具结果不自动重试 |

#### 安全

| ID | 需求 | 验收标准 |
|----|------|----------|
| NF-S1 | 默认拒绝（fail-closed） | 未知工具、未匹配权限规则、无法解析的命令默认拒绝 |
| NF-S2 | 工作区路径逃逸防护 | 解析真实路径，拒绝 `..` 穿越、绝对外部路径、符号链接逃出 workspace/session cwd |
| NF-S3 | 环境变量最小化 | 子进程仅保留 `PATH`、语言区域、临时目录变量；`HOME`/`PWD` 指向 workspace；API key/SSH_AUTH_SOCK 不传入 |
| NF-S4 | 车辆操作分级 | L0 只读、L1 配置写、L2 服务控制、L3 永久禁止直接控车；行驶中 `enabled`/`vEgo>0.1` 限制写操作 |
| NF-S5 | 审计不可抵赖 | hash chain + head anchor；固件/控制类操作记录 capability、设备句柄、固件哈希；审计锚点可配置远端/WORM 存储 |
| NF-S6 | Prompt injection 防御 | 工具结果和文件内容默认不可信；高后果动作必须人类审批 |

#### 车机约束

| ID | 需求 | 验收标准 |
|----|------|----------|
| NF-C1 | 离线可跑 | 核心诊断、参数读取、本地 RAG 不依赖云端 API；无 key 模式可运行基础 harness |
| NF-C2 | 低资源友好 | 车机 C3/C3X/C4 内存/CPU 受限；避免大模型全量加载；优先使用 lite/default 模型路由 |
| NF-C3 | 网络受限 | 云端 embedding/RAG 仅在 WiFi 下触发；MCP HTTP 支持 bounded reconnect 与超时 |
| NF-C4 | 温度/电源安全 | 高负载任务（视频导出、模型 benchmark）默认排队到停车/充电状态 |
| NF-C5 | 封闭场地验证 | 首次控车测试向导强制提示"封闭场地、低速"；AI 生成 DBC/CarState 需人 review 后合入 |

---

## 4. 参考 learn-workbuddy 可借鉴模块清单

| learn-workbuddy 模块 | 可借鉴点 | 迁移/适配到 OP 助手 |
|----------------------|----------|---------------------|
| `mini_workbuddy/agent.py` | `call_id` 分配、事件落盘再返回 | `core/chat/runner` 已具备，强化 event_id/session_id 注入 |
| `s04_permission_hooks/code.py` | `PermissionPolicy` / `GovernedToolRunner` / `ALLOW/ASK/DENY` 三级 | 替换为 capability + tiered authorization 模型 |
| `mini_workbuddy/tools.py` | 命令黑名单、工作区路径守卫、子进程环境过滤 | 升级为 `SandboxPolicyService` + session cwd containment |
| `s09_jsonl_transcript/code.py` | `O_APPEND` + `fsync` + partial tail 忽略 | 已部分实现；补齐 strict event/surface header |
| `s10_workspace_memory` ~ `s12_cloud_memory` | 三层记忆所有权、source_event_id 溯源 | 已具备 memory store；对齐 event projection |
| `s13_output_externalization/code.py` | head + tail + `[full at: path]` 指针 | 已部分实现；升级为 spill waterfall |
| `s14_context_compact/code.py` | L1~L4 四层压缩管线 | 已部分实现；接入真实 provider usage 校准 |
| `s15_prompt_assembly/code.py` | 分段 prompt 装配顺序 | 已部分实现；对齐附件/connector/skill 注入位置 |
| `s16_skills_system/code.py` | SKILL.md frontmatter、权限声明、按需加载 | 已具备 skill catalog；补齐 scope/version/disposal |
| `s17_mcp_connectors/code.py` | connector trust、Skill grant 交集、延迟加载 | 已部分实现；补齐 persistent client/reconnect/HTTP |
| `s18_experts_system/code.py` | expert pack 整包加载 | 新车适配/品牌特调 expert pack |
| `s22_automation_scheduler/code.py` | RRULE 定时任务、软删除 | 已部分实现；对齐 cron/every/list/cancel 工具 |
| `s23_audit_sandbox/code.py` | SHA256 hash chain + `audit.head` anchor | 车辆场景扩展 capability/设备/固件字段 |
| `mini_workbuddy/audit.py` | 并发追加、崩溃恢复、截断检测 | 接入 OP 会话运行时 |

---

## 5. 与 deepseek-harness 需对齐的关键 seam

| Seam | 当前 ai 状态 | dsh 基准 | 对齐目标 |
|------|--------------|----------|----------|
| **Session event/surface** | 简化 envelope + APPEND/REPLACE | strict header、ignorable、eligibility/provenance | F0-1 |
| **Resume/Repair** | 仅返回 orphan 列表 | interruptedTurnClosers 合成可继续 transcript | F0-2 |
| **Spill waterfall** | 简单 post hook | `await next()`、content-block 语义、dispatch-log arm | F0-3 |
| **SandboxPolicy** | 全局开关 + workspace 目录 | session-scoped cwd/mode、可回放 runtime-context | F0-4 |
| **LSP lifecycle** | 四操作可调用 | provider/extension 路由、结果上限、取消终止 | F1-1 |
| **Goal/Plan/Todo projection** | JSON 快照为主 | session event + replay fold | F1-2 |
| **MCP client lifecycle** | 每次调用 spawn | persistent stdio、HTTP transport、reconnect、schema 缓存 | F1-3 |
| **ACP wire** | 裸 newline JSON-RPC | Content-Length framing、标准 SDK、permission/progress/cancel | F1-4 |
| **Subagent provider** | in-process pool | capability matrix、ACP provider、parent lineage | F1-5 |
| **Bundle/Profile** | zip+bundle.json | ordered bundle patch composition | F1-7 |
| **WorkflowEngine** | JSON 图推进 | 脚本引擎/phase/log/cancel/disposal | F1-8 |
| **Config/Dependency model** | Params + try/except | 集中 schema、依赖清单、启动诊断 | F1-6 |

---

## 6. UI 设计草案

### 6.1 核心页面/组件

1. **聊天主界面**
   - 模型切换（自动/快/深）
   - 斜杠指令快捷入口：`/调手感`、`/适配新车`、`/开不起来`、`/复盘`
   - 待确认操作卡片（参数 diff、固件刷写、DTC 清除）
   - 工具调用展开/折叠（显示 tool_call_id、状态、审计链链接）

2. **车辆安全面板**
   - capability 授权列表（USB/CAN/Flash/Log/Dbc）
   - 当前行驶状态（enabled/vEgo/ignition）
   - 高风险操作历史 + 审计 verify 按钮

3. **设置 → AI 治理**
   - `ai_use_agent_loop` 开关
   - `ai_sandbox_shell` / `ai_sandbox_mode`（read-only/workspace-write/danger-full-access）
   - MCP server trust/grant 管理
   - Skill enabled + 行驶中可用开关

4. **适配与诊断向导**
   - 四步向导：指纹 → CAN/DBC → 适配草稿 → 封闭场地验证
   - Engage 分诊树状结果
   - Cabana 面板集成（实时/回放/一键送入聊天）

### 6.2 交互流程示例：调手感

```text
用户："变道激进一点"
  ↓
AI：解析意图 → 列出建议调整的 dp_lat_* 参数及当前值
  ↓
生成人类可读 diff 卡片（旧值 → 新值、影响说明、回滚方式）
  ↓
用户点击"确认"（停车状态）
  ↓
调用 write_params → 记录快照 → 写入参数 → 写入 hash-chain 审计
  ↓
返回"已调整，可在 设置 → 调参护照 查看/回滚"
```

---

## 7. 待确认问题

1. **Capability 授权粒度**：`vehicle_flash` 是否需进一步拆分为 `panda_flash`/`ecu_flash`/`firmware_update`？还是作为一个粗粒度 capability？
2. **Human-in-the-loop 触发条件**：除固件刷写、控制报文外，是否将"批量参数写入 > N 项"也纳入强制确认？N 取多少？
3. **审计锚点存储**：车机环境通常无稳定的远端 WORM 存储，是否先采用本地 head anchor + 用户可选 sunnylink 云端锚点？
4. **MCP 工具可见性**：默认是"未配置 server 不注册"还是"注册但 DENY"？前者隐藏工具，后者可见但不可调用。
5. **AgentLoop 默认开启节奏**：是否先灰度到 `op chat` / Web，再扩展到定时任务/自动化？
6. **前端技术栈**：当前 Vanilla JS 前端是否在本次 PRD 周期内启动向 Vite+React 迁移？还是仅作为 P2？
7. **与 commaai 官方安全策略冲突点**：openpilot 官方对某些参数/接口有严格限制， capability 列表需法务/安全团队 review。

---

## 8. 优先级与里程碑建议

| 阶段 | 周期 | 交付 |
|------|------|------|
| **M1** | 2 周 | F0-1/F0-2/F0-8（Session 协议 + AgentLoop 默认） |
| **M2** | 2 周 | F0-3/F0-4/F0-5/F0-6/F0-7（Spill + SandboxPolicy + 车辆 capability + HITL + 审计） |
| **M3** | 2 周 | F0-9/F0-10 + F1-1/F1-6（Harness 工具注册 + 附件 + LSP + 配置诊断） |
| **M4** | 3 周 | F1-2/F1-3/F1-4/F1-5/F1-7/F1-8/F1-9（事件投影 + MCP + ACP + Subagent + Bundle/Profile + WorkflowEngine + Skill 生命周期） |
| **M5** | 持续 | F2 增强项 + 前端重构 + 实机全量回归 |

---

## 9. 关键术语表

| 术语 | 说明 |
|------|------|
| **deepseek-harness (dsh)** | TypeScript/Cordis 插件化 harness 基准 |
| **learn-workbuddy** | 桌面 Agent 工程教学蓝图，提供权限/审计/记忆/扩展机制参考 |
| **OP 助手 / ai** | openpilot 树内的 Python LLM 助手子模块 |
| **capability** | 车辆/系统级能力授权单元，如 `can_bus_access` |
| **HITL** | Human-in-the-loop，人类在关键环节确认 |
| **hash-chain** | SHA256 链接式审计日志，含 head anchor 防截断 |
| **surface** | 会话事件中对模型可见的消息面操作 |
| **spill** | 大工具结果外部化/会话摘要机制 |
| **MCP** | Model Context Protocol，外部工具标准协议 |
| **ACP** | Agent Client Protocol，标准客户端协议 |

---

*本文档为产品需求输入，具体技术实现方案需由 software-architect 与 software-engineer 进一步细化设计。*
