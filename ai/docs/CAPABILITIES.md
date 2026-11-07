# op助手能做什么（用户速查）

> 在 Web 设置中可开关各工具；行驶中默认仅只读工具可用。

## 日常驾驶

- 读车辆状态、告警、路线事件
- 调参建议（openpilot Params / 各 fork 扩展前缀如 `dp_*`、`Sp*`、`Frog*`）
- 预设与回滚；**设置 → 平台 → 调参 A/B 对比**
- 停车后行程复盘、语音/文字简报

## 多社区 fork 与文档

- 安装后自动识别当前 fork（Dragonpilot / sunnypilot / FrogPilot 等），写入 `workspace/FORK_PROFILE.md`
- 对话中自动附带 fork/设备上下文；可问「当前分支推荐装哪个 release？」
- **社区 Wiki RAG**：从 GitHub、论坛（Discourse）、wiki.gg 拉取文档，回答 sunnypilot 设置项、分支说明等
- Web **设置 → 开发 → Fork 分析**：AI 全仓阅读（需 API）

详见 [FORK_AND_COMMUNITY.md](FORK_AND_COMMUNITY.md)。

## 无法开启 OP

- **一键健康检查**（`run_health_check`）与 Engage 分诊工作流
- Engage 分诊：SecOC、指纹、Panda、摄像头
- 丰田密钥：TSK 一条龙 / `tsk_diagnose_failure`
- C3 DOS / 双 Panda 刷机恢复

## 开发与 CI（C3）

- **安装 Runner**：提供 registration token → `install_github_runner`
- **管 CI**：配置 PAT → 查/取消/触发/等待 workflow
- **Prebuilt**：`prebuilt_branch_status` → `checkout_prebuilt_branch`
- **OTA 前**：`ota_preflight_checklist`
- **发 PR**：离路改代码 → `git_publish_pull_request` → PC 审阅（见 `ai/docs/GIT_PR.md`）
- **Web Bug PR**：`report_bug_and_publish_pr` → `mouxangithub/ai`（见 `ai/docs/PR_AUTOMATION.md`）
- **Actions 自动审阅/合并**：PR 带 `ai-auto-review`；低风险带 `ai-safe-merge`

## 云与备份

- Sunnylink 备份/恢复、`sunnylink_backup_watch`
- Konik 配对 vs Comma Connect（`konik-vs-comma` 技能）

## 新车适配

- 指纹、CAN、适配草稿、PR 描述生成

## 主动提醒（定时任务）

- 停车复盘、参数漂移、Runner/CI 健康、磁盘温度、CI 失败告警

## 插件（9 个）

`list_plugins` 查看：github-ci、git-github、branch-ota、tsk-secoc、sunnylink-cloud、device-extras 等。

## P2 增量能力

> P2 在 P0/P1 主线之上新增三项后端能力，Web 设置中默认关闭，通过平台工具或 HTTP 路由调用。

### WorkflowEngine（脚本式工作流）

- 位置：`ai/core/workflow/`
- 入口：`run_workflow` 平台工具 / `WorkflowEngine.run(definition, inputs)`
- 能力：
  - 声明式 YAML/JSON workflow definition
  - 变量作用域与步骤输出绑定：`${inputs.x}`、`${steps.step_id.output.field}`
  - 条件分支：`condition: "${steps.check.ok} == true"`
  - 循环：`for_each: "item in ${steps.list.output.items}"`
  - 并行分支：`parallel: [step_a, step_b]`
  - 子代理调用：`agent: {id, prompt, tools, max_rounds}`
  - 结构化错误码与 `cancel(run_id)` / `dispose(run_id)` 生命周期
  - 事件投影：`workflow/start`、`phase/start`、`phase/log`、`agent-start`、`agent-end`、`workflow/end`
- 调用示例：
  ```json
  {
    "definition": {
      "id": "route-summary",
      "steps": [
        {"id": "load", "kind": "tool", "inputs": {"tool": "list_routes", "limit": 5}},
        {"id": "summarize", "kind": "agent", "agent": {"prompt": " summarize routes", "max_rounds": 3}}
      ],
      "outputs": {"summary": "${steps.summarize.output.content}"}
    }
  }
  ```

### Skill 生命周期（scope / version / dispose）

- 位置：`ai/skill/`
- 新增字段：`scope`（global/session）、`version`（semver）、`capabilities`、`dependencies`、`source`
- HTTP 路由：
  - `POST /api/ai/skills/{id}/dispose`：调用 skill dispose hook 并移除
  - `GET /api/ai/skills/{id}/diagnose`：返回依赖满足情况、能力授权、来源可信度
  - `POST /api/ai/skills/diagnose-all`：批量诊断 + 冲突检测
  - `POST /api/ai/skills/session/register`：在当前会话注册 session scope skill
- 会话隔离：`SkillRegistry.for_session(session_id)` 返回 `SessionSkillRegistry` overlay，session skill 可覆盖同名全局 skill，不影响其他会话。

### MCP resources/read 与 prompts/get

- 位置：`ai/mcp/host.py`、`ai/server/handlers/phase2.py`
- 平台工具：`read_mcp_resource`、`get_mcp_prompt`（与 `call_mcp_tool`、`discover_mcp_tools` 风格一致）
- HTTP 路由：`POST /api/ai/mcp` 请求体 `{operation: "read_resource", server_id, uri}` 或 `{operation: "get_prompt", server_id, name, arguments}`
- 复用现有 `MCPStdioClient` stdio transport，按 session 加锁。

详细用户文档：[QUICKSTART.md](QUICKSTART.md)、[TROUBLESHOOTING.md](TROUBLESHOOTING.md)、[TUNING_GUIDE.md](TUNING_GUIDE.md)、[FAQ.md](FAQ.md)。

详细维护者文档：`ai/docs/PLUGIN_DEV.md`、`ai/docs/SKILL_AUTHORING.md`。
