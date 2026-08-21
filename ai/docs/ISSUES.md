# Issue 提交（GitHub / Gitee）

op助手可将 bug、功能建议等自动整理为 **Issue**（与 PR 发布互补）。

## Issue vs PR

| 场景 | 工具 |
|------|------|
| 已改代码，要合入 | `publish_changes` / `git_publish_pull_request` |
| 记录 bug / 建议，尚未改代码 | `report_issue` / `create_issue` |
| op助手 UI bug（AI 能直接修） | `report_bug_and_publish_pr` → PR |

## 模板

内置：`bug`、`feature`、`assistant`、`suggestion`、`tuning`、`adaptation`、`openpilot_pc`

GitHub 表单：`.github/ISSUE_TEMPLATE/`（`op_bug.yml`、`feature_request.yml`、`tuning_help.yml`、`vehicle_adaptation.yml`、`documentation.yml` 等）

仓库模板：优先读取 `.github/ISSUE_TEMPLATE/*.yml`

## 工具

| 工具 | 说明 |
|------|------|
| `discover_issue_templates` | 列出可用模板 |
| `create_issue` | 按模板创建 Issue |
| `report_issue` | 结构化 bug/feature/suggestion |

## 配置

**设置 → 开发 → 反馈提交**：

- 默认目标单元（assistant / openpilot）
- 默认模板
- 是否搜索重复 Issue

Token 与 **代码发布** 共用（GitHub PAT / Gitee 令牌）。

## API

- `GET /api/ai/issues` — 状态与内置模板
- `GET /api/ai/issues?view=templates&unit_id=assistant`
- `POST /api/ai/issues` — `operation`: `create` | `report` | `save_settings`

## 安全

- 离路 + `confirm=true` 或 Web 确认后创建
- 创建前搜索相似 open issues（可配置关闭）
- Token 不出现在 API 响应中
