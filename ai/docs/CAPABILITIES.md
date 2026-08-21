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

详细用户文档：[QUICKSTART.md](QUICKSTART.md)、[TROUBLESHOOTING.md](TROUBLESHOOTING.md)、[TUNING_GUIDE.md](TUNING_GUIDE.md)、[FAQ.md](FAQ.md)。

详细维护者文档：`ai/docs/PLUGIN_DEV.md`、`ai/docs/SKILL_AUTHORING.md`。
