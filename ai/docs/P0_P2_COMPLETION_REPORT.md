# AI OP 助手 P0–P2 落地完成度报告

> 生成时间：2026-09-18
> 范围：E:\sp\ai 子仓库
> 统计：M1–M6 共产生 15+ 个 commit，新增/修改约 30 个文件，新增测试 10+ 个

## 1. 执行摘要

本轮在 `ai/` 子仓库持续推进 P0–P2 路线图落地。已完成 M1–M6 中大部分高优先级项，核心能力包括：统一工具注册契约、统一 session/memory/scheduler 抽象、WorkflowEngine 生产就绪、MCP/Skill/Spill 强化、health_check 诊断闭环、平台工具审计覆盖、错误码标准化等。

剩余差距集中在：长耗时工具协作取消、 harness/MCP Web UI meta、Panda 工具收敛、CI/session-summary 高阶工作流、以及全量测试套件稳定性。

## 2. 里程碑完成情况

### M1: 统一工具注册契约（已完成）
- 统一 handler 返回 dict 风格
- 引入 `tool_error` / `ok_result` 标准返回结构
- harness 工具补入 TOOL_META
- 相关文件：`ai/tools/agent_tools.py`, `ai/tools/harness_tools.py`, `ai/core/errors.py`, `ai/tools/toolsets.py`

### M2: 统一核心抽象（部分完成，由 m2-engineer 继续）
- A-P0.3 统一 Session 持久化：`ai/core/session/repair.py` 增强，统一 resume 路径（commit c5f08d5）
- A-P0.1 工具注册入口分散：通过 `platform_extensions.py` 统一 platform tool surface
- A-P0.2 双 Skill 系统 / A-P0.4 AgentFactory / A-P0.5 Chat 路由重复：仍在推进中，见 m2-engineer 任务

### M3: WorkflowEngine 生产就绪（已完成）
- D-P0.1 Workflow fatal/non-fatal 错误（commit 84057d5）
- T-P0.5 稳定 WorkflowToolAdapter，避免每次重建 handlers（commit 2f20dec）
- T-P1.7 WorkflowEngine 可调度全量工具
- 相关文件：`ai/core/workflow/engine.py`, `ai/core/workflow/errors.py`, `ai/core/workflow/tool_adapter.py`, `ai/tools/domains/platform/platform_extensions.py`

### M4: MCP/Spill/Skill 强化（已完成）
- D-P0.4 Local spill 安全模式：0700 权限、防 symlink、cleanup（commit 9237516）
- D-P0.3 Skill rank ordering + invocation policy + skills/change 事件（commit 93e5059）
- D-P1.2 MCP resource templates + cursor 分页（commit 532919a）
- D-P0.2 MCP stdio client supervised reconnect + backoff（commit 97736c4）
- 相关文件：`ai/mcp/host.py`, `ai/skill/registry.py`, `ai/skill/models.py`, `ai/tools/result_externalize.py`

### M5: 高阶工作流与诊断闭环（已完成）
- T-P0.4 health_check 标准返回契约
- T-P1.3 health_check executable remediation actions（commit b9b3d8e）
- T-P1.2 统一 MemoryBackend + append_unified_memory（commit）
- T-P1.1 双调度器合并（legacy + RRULE）+ 暴露为 platform tool
- T-P1.5 schedule/memory 暴露为 platform tool
- T-P1.4 自动审计覆盖包装器
- 相关文件：`ai/common/memory_backend.py`, `ai/tools/domains/platform/scheduler.py`, `ai/tools/domains/platform/platform_extensions.py`, `ai/tools/domains/platform/audit_cover.py`, `ai/tools/domains/platform/health_check_tools.py`

### M6: 配置/边界/体验打磨（部分完成）
- T-P2.5 错误码细分：`ERR_STATIONARY_REQUIRED`, `ERR_DEPENDENCY_UNAVAILABLE`
- T-P2.6 run_workflow 桥接使用 `ok_result` / `tool_error`
- T02 AgentLoop default enable in dev routes（任务 39 已完成）
- 剩余：T-P1.6 长耗时工具协作取消、T-P2.1 harness Web UI label、T-P2.2 MCP stable meta、T-P2.3 Panda 收敛、T-P2.4 CI/session-summary 高阶工具

## 3. 新增测试覆盖

| 测试文件 | 覆盖项 |
|----------|--------|
| `ai/tests/test_scheduler_unified.py` | 统一调度器 RRULE/legacy 创建、取消、非法 rrule |
| `ai/tests/test_audit_cover.py` | platform tool 自动审计、脱敏、只读工具跳过 |
| `ai/tests/test_error_codes.py` | 新错误码存在性与 stationary 检查映射 |
| `ai/tests/test_memory_backend.py` | 双记忆 backend fan-out |
| `ai/tests/test_health_check_contract.py` | health_check executable actions 与 data 契约 |
| `ai/tests/test_mcp_discovery.py` | MCP resource templates + cursor 分页 |
| `ai/tests/test_mcp_reconnect.py` | MCP stdio client reconnect/backoff |
| `ai/tests/test_skill_registry_ext.py` | skill rank/invocation policy/change events |

最近子集测试结果：28 passed / 1 warning，无 hang。

## 4. 剩余差距清单（按优先级）

### P1 — 建议近期补齐
1. **T-P1.6 长耗时工具协作取消**
   - 位置：`ai/tools/harness_tools.py`, `ai/core/workflow/engine.py`, `ai/tools/executor.py`
   - 问题：子进程/LSP/网络请求无法响应 WorkflowEngine 取消信号
   - 方案：给耗时工具增加 `cancellation_event: asyncio.Event` 参数，循环内定期检查

2. **A-P0.4 AgentFactory + A-P0.5 共享 chat handler**
   - 位置：`ai/core/agent/factory.py`, `ai/server/handlers/chat.py`
   - 负责人：m2-engineer
   - 问题：生产路由与本地 dev 路由分别构造 Agent/Loop，重复且易不一致

3. **A-P0.2 双 Skill 系统收敛**
   - 位置：`ai/skills/` vs `ai/skill/`
   - 问题：文件型 loader 与运行时 registry 并存
   - 方案：`ai/skills/loader.py` 只返回 `SkillManifest`，`ai/skill/registry.py` 成为唯一运行时注册表

### P2 — 体验与完整性
4. **T-P2.1 harness 工具缺少 Web UI label**
   - 位置：`ai/tools/harness_tools.py`, `ai/tools/domains/platform/tool_ui_meta.py`
   - 方案：为每个 harness tool 补充 label/description/category

5. **T-P2.2 MCP 动态工具缺少 stable meta**
   - 位置：`ai/mcp/host.py`, `ai/tools/agent_tools.py`
   - 方案：MCP host 提供 `get_tool_meta()`，注册时同步写入运行时 meta

6. **T-P2.3 Panda 工具分散**
   - 位置：`ai/tools/sp_tool_extensions.py`, `ai/tools/extensions.py`, `ai/tools/domains/platform/device_health_tools.py`
   - 方案：迁移到单一 `panda_tools.py`

7. **T-P2.4 session summary / CI workflow 缺失**
   - 位置：`ai/tools/domains/platform/platform_extensions.py`
   - 方案：新增 `finish_session(session_id)` 与 `run_ci_workflow(...)` 高阶工具

### 工程化
8. **任务 31：全量测试套件 hang 排查**
   - 当前已验证近期新增测试无 hang
   - 建议：在 CI 中对 `ai/tests/` 全量运行，对超过 60s 的测试用 `--durations=0` 识别耗时大户

9. **任务 32：汇总 P0–P2 完成度与差距清单文档**
   - 本文档即任务 32 产出

## 5. 最近提交记录

```text
b9b3d8e M5: health_check standard contract + executable remediation actions (T-P0.4, T-P1.3)
97736c4 M4: MCP stdio client supervised reconnect + backoff (D-P0.2)
532919a M4: MCP resource templates + cursor pagination (D-P1.2)
93e5059 M4: skill rank ordering + invocation policy + skills/change events (D-P0.3, D-P1.3)
9237516 M3: harden local spill storage permissions and symlink handling
84057d5 M3: add fatal/non-fatal flag to WorkflowError (D-P0.1)
2f20dec M3: stable WorkflowToolAdapter with cached handlers + cancellation (T-P0.5)
c5f08d5 M2: unified session resume path (A-P0.3)
```

## 6. 下一步建议

1. 等待 m2-engineer 完成 M2 剩余项（AgentFactory、共享 chat handler、skill 双轨收敛）。
2. 由 software-engineer-2-2 或 QA 对全量测试套件进行 hang/超时排查。
3. 优先实现 T-P1.6 协作取消，这对 WorkflowEngine 在生产环境稳定运行至关重要。
4. 将剩余 T-P2.x 体验项拆分为独立小 PR，降低 review 成本。
