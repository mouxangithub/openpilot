# op助手 Web Bug → Pull Request

用户在 Web/UI 反馈 Bug 时，结构化收集信息并发布 PR 到 `mouxangithub/ai`（或 openpilot）。

> 详见 `ai/docs/PR_AUTOMATION.md`

## 何时触发

- 用户说「这个界面有 bug」「帮我提个 issue/PR」
- Web 端反馈表单提交后由 AI 跟进
- 小改动（文案、样式、docs）适合 `severity=ui|docs|typo`

## 流程

```
report_bug_and_publish_pr(
  repo_target="assistant",
  title="fix(web): ...",
  repro_steps="1. 打开 ... 2. 点击 ...",
  expected="应显示 ...",
  actual="实际 ...",
  severity="ui",
  confirm=false
)
```

用户确认后 `confirm=true`。工具会：

1. 附加环境信息与近期 audit trail
2. 在 assistant 仓 commit/push（`ai/*` 或 `fix/*` 分支）
3. 创建 PR 并打 `ai-auto-review`（UI 类可加 `ai-safe-merge`）
4. GitHub Actions 自动审阅；符合条件则 squash 合并

PC 上可在 PR 评论 `/oc ...` 让 OpenCode 继续改代码（见 `ai/docs/PR_AUTOMATION.md`）。

## 参数

| 参数 | 说明 |
|------|------|
| `repo_target` | 默认 `assistant`；openpilot 内 ai 改动用 `openpilot` |
| `severity` | `ui` / `docs` / `typo` / `web` / `logic` / `crash` |
| `request_auto_fix` | 打 `ai-auto-fix` 标签（预留 Actions 自动修复） |
| `attach_audit` | 附最近工具审计记录 |

## 注意

- **离路**才能执行写操作
- 需配置 `ai_github_actions_pat` 与 git push 凭据
- `logic` / `crash` 类默认**不**自动合并，需 PC 人工审阅
- 独立 ai 仓路径：`ai_assistant_repo_path` 或环境变量 `AI_ASSISTANT_REPO_PATH`

## 相关工具

- `git_publish_pull_request` — 非 Bug 场景的通用 PR
- `get_github_pull_request` — 查 PR 状态
- `auto_review_pull_request` — 设备侧补审
