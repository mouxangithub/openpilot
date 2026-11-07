# Harness 能力启用增量 PRD

- **版本**：v1.0（2026-09）
- **范围**：仅接通已移植/已实现但尚未进入默认运行链路的 harness 能力；不修改本 PRD 之外的车辆控制能力。
- **依据**：`ai/goal`、`plan`、`todo`、`subagent`、`lsp`、`attachment`、`spill`、`sandbox`、`acp`、`bundle`、`core/agent`、`mcp`、`tools/workflows.py` 现有代码及 deepseek-harness Agent Notes（session、LSP、spill、生命周期、执行环境等）。

## 1. 目标与成功指标

### 1.1 目标
1. 让 AgentLoop 默认可执行完整的规划—工具调用—复盘闭环。
2. 将 goal/plan/todo/subagent、LSP 等模型工具统一注入 LLM，并保持参数校验、超时、取消和安全边界。
3. 将附件、MCP、spill、sandbox 纳入同一会话上下文与工具执行流水线。
4. 提供可恢复、可诊断、可发布的 session、ACP stdio、bundle/profile 与 workflow_graph 路由。

### 1.2 成功指标
- 默认新会话可完成一次 goal→plan→todo→执行→goal 推进，且事件可回放。
- 已启用工具的 schema、调用、结果、错误在 Web/CLI/ACP 三种入口一致。
- session resume/repair 在进程重启、尾部损坏、缺失事件时可恢复或给出结构化错误。
- shell/python 仅在 sandbox 策略允许时执行；越权路径、超时、取消均被拒绝并审计。

## 2. 用户故事

- 作为车主/开发者，我可以用自然语言提出目标，系统自动生成并维护计划与待办，完成后自动推进或请求澄清。
- 作为用户，我可以上传日志、图片或文档，模型能引用附件内容而非只看到文件名。
- 作为开发者，我可以让模型用 LSP 精确跳转定义、引用、实现和 hover。
- 作为管理员，我可以选择 bundle/profile、MCP 工具和 workflow_graph，并通过 ACP stdio 接入 IDE/外部客户端。
- 作为用户，我可以在会话中断后 resume；若日志不完整，系统能 repair 并说明修复范围。
- 作为安全审计者，我可以看到 sandbox、MCP、subagent、spill 的调用、权限、耗时和结果摘要。

## 3. 需求与优先级

### 3.1 P0（必须本增量交付）

#### P0-1 AgentLoop 默认接通
- 应用默认创建并运行 `core/agent` AgentLoop；配置缺失时使用安全默认 profile。
- 每轮统一执行：读取会话状态→选择 workflow/goal→LLM→工具→post-execute→事件持久化→继续/结束。
- 支持 AbortSignal、超时、取消、最大轮次和结构化错误；禁止无限自循环。

**验收**：新会话无需隐藏开关即可触发至少一个模型工具；成功、工具错误、取消、超时均写入可回放事件；旧聊天入口不回退到旁路执行器。

#### P0-2 goal/plan/todo/subagent 模型工具
- 注入 goal 创建/读取/更新/完成、plan 生成/更新、todo 增删改查/完成、subagent 启动/查询/取消/释放工具。
- 所有 ID、状态迁移、owner/scope、并发和生命周期遵循现有模型与 store；subagent 结果回传主会话并可审计。
- 系统提示词说明何时规划、何时委派、何时自动推进；工具不可直接突破安全策略。

**验收**：LLM 可发现并调用上述工具；非法状态迁移被拒绝；subagent 崩溃/取消不影响主会话；goal 完成后自动标记关联 plan/todo，未完成项保留。

#### P0-3 附件注入 LLM
- attachment store/extract/context 在 LLM 请求前生成受限上下文块，包含附件 ID、类型、摘要/文本、来源和截断信息。
- 按会话与权限隔离；遵守字节、字符、数量和 token 预算；不可解析内容以可见错误提示，不阻塞纯文本对话。

**验收**：上传文本、图片/二进制（可提取时）后，下一次 LLM 请求能引用附件；超限有截断标记；跨 session 不可读取；事件记录注入版本与哈希。

#### P0-4 spill post-execute
- 默认接入 spill policy 的 `tools/post-execute` waterfall；对超大纯文本结果保存完整内容并返回预览、定位符、检索提示。
- spill 失败、无 owner、非文本结果必须原样回退，不将成功调用改为错误；跳过 `read` 防止循环。

**验收**：配置阈值后大结果产生 spill 文件/引用且可用既有 read/grep 检索；小结果、非文本、read 结果不变；重启清理与权限策略生效。

#### P0-5 sandbox 接入 shell/python
- shell_runner/python_runner 通过 sandbox runtime 执行；统一 cwd、环境变量、超时、资源限制、stdout/stderr 上限、取消和审计。
- 默认最小权限；工作区 containment、网络/写权限由 profile 明确声明；拒绝直接宿主执行和 shell 拼接注入。

**验收**：允许的 shell/python 在 sandbox 中成功运行；越权路径、禁网、超时、取消均被拦截；输出超限按 spill/预览策略处理；审计含命令摘要、sandbox profile 与退出原因。

#### P0-6 LSP 模型工具
- 注入单一 `lsp` 工具，支持 `goToDefinition`、`findReferences`、`goToImplementation`、`hover`；坐标对模型为 1-based UTF-16。
- 从 session cwd 得到 workspaceRoot；提供方注册/扩展名路由、结果上限、60 秒工具预算、取消和结构化错误沿用现有 seam。

**验收**：四种操作 schema 与结果可见；workspace 缺失、工作区外路径、冲突提供方、畸形响应均有确定错误；结果按 `path:line:character` 渲染并截断标记。

#### P0-7 session resume/repair
- resume 从持久化事件重建 goal、计划、todo、工具状态、附件引用、spill 引用和 token 计量。
- repair 仅执行确定性修复：截断损坏尾记录、补齐可推导索引/快照、标记未完成调用为 interrupted；不得臆造模型结果。

**验收**：进程重启后 resume 可继续；损坏日志 repair 后可读且报告修复项；不可修复冲突返回结构化错误并保留原始证据；重复恢复不产生重复副作用。

#### P0-8 MCP 工具桥接
- 将已连接 MCP server 的工具发现、schema、调用、取消、超时和结果转换桥接到 `ctx.tools`；保留 server/tool 来源和权限。
- 默认 deny 未授权 server；名称冲突命名空间化；MCP 返回的资源/非文本块按 content block 处理并接入 spill。

**验收**：授权 MCP 工具可被 LLM 发现和调用；断连、超时、非法 schema、冲突均可诊断；调用事件含 server、tool、耗时和错误分类；未授权工具不可见。

### 3.2 P1（本增量交付，允许分批上线）

#### P1-1 ACP stdio server
- 提供 JSON-RPC/stdio 入口，复用 AgentLoop、session、工具注册和事件协议；支持 initialize、session create/resume、prompt、tool progress、cancel、shutdown。
- stdout 仅输出协议帧，日志走 stderr；支持无密钥确定性 smoke test。

**验收**：标准客户端可建立会话、发送 prompt、接收增量事件和取消；畸形帧不会导致进程崩溃；stderr 不污染协议；退出完成清理。

#### P1-2 bundle/profile
- bundle 描述可加载插件、工具、MCP、sandbox、模型和 UI 能力；profile 负责默认值、权限、资源上限和环境选择。
- 加载前校验 manifest、版本、依赖和能力冲突；失败原子回滚；展示当前生效 profile。

**验收**：可加载最小/开发/只读 profile；缺依赖或冲突不产生半加载状态；profile 变更写入 session 元数据；敏感配置不进入模型上下文。

#### P1-3 workflow_graph 路由
- 将 `tools/workflows.py` 与 goal/plan/todo 状态映射为可持久化 workflow graph；节点支持条件、重试上限、人工确认、并行/串行和补偿。
- AgentLoop 每轮按图路由，不允许模型绕过节点权限；失败节点可暂停、重试或转人工。

**验收**：预置工作流可从入口运行并持久化节点状态；条件分支、重试、暂停/恢复可回放；节点工具不满足 requires_tools 时提前失败并给出替代路径。

### 3.3 P2（后续增强）

- 多 subagent 并行协作、成本/配额调度和跨 provider 路由。
- 远程/数据库 spill backend 与 ACP 远程环境适配。
- LSP 诊断、符号、重命名、代码操作（需独立写入预览和权限模型）。
- workflow graph 可视化编辑器、模板市场、版本迁移工具。
- 附件 OCR/多模态深度解析、增量索引与引用级溯源。
- MCP 资源订阅、提示模板、server 健康面板。

## 4. UI 影响

- Web 聊天：增加目标/计划/待办侧栏或折叠卡片、subagent 状态、工具进度、取消/恢复入口。
- 会话列表：显示 interrupted、repair required、最后 workflow 节点、附件和 spill 数量；提供 Resume/Repair，并在修复前展示预览。
- 设置→开发：增加 AgentLoop、profile/bundle、MCP server、sandbox 权限与 LSP provider 配置；高风险权限显式确认。
- 工具结果：显示截断/ spill 提示、来源 server、LSP 位置卡片；不泄露内部密钥、完整环境变量或宿主路径（按 profile 脱敏）。
- ACP/CLI 无图形界面时提供等价文本状态、错误码和进度事件。

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| AgentLoop 自循环、成本失控 | 最大轮次/预算/截止时间，状态机门禁，逐轮事件与告警 |
| shell/python 或 MCP 越权 | sandbox 最小权限、工作区 containment、server allowlist、审计与人工确认 |
| 附件 prompt 注入或敏感数据泄露 | 明确不可信内容边界、权限隔离、大小/token 限制、敏感字段脱敏 |
| session repair 臆造状态 | 仅确定性修复，保留原日志，repair report 可审阅 |
| spill 路径泄露/磁盘耗尽 | 0600 文件、会话隔离、启动清理、配额与失败回退 |
| LSP 进程卡死/不兼容 | 有界生命周期、取消后终止升级、能力校验、结果限制 |
| bundle/profile 依赖冲突 | manifest 原子校验和回滚、版本锁定、启动 smoke test |
| ACP/MCP 协议不兼容 | 协议版本协商、结构化错误、固定 JSONL/stdio 回归测试 |

## 6. 非目标（Out of Scope）

- 任何直接控制车辆转向、制动、油门的工具或绕过现有安全分层。
- 自动未经用户确认修改车辆关键参数、密钥、SSH/ADB 或安全策略。
- 新增 LLM provider、重写已有 stores、替换事件溯源格式（仅做兼容接线）。
- 构建通用 IDE、语言服务器安装器或 MCP server 市场；LSP 仍只提供四种只读操作。
- 以 spill 替代资源采集上限，或新增专用 artifact_read/artifact_search 工具。
- 跨设备同步私有附件、spill 原文或敏感 session 内容（除非另有安全设计）。
- 本 PRD 不要求修改 deepseek-harness 上游代码，仅要求在 `ai` 中完成接线与验收测试。
