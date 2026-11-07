# PR 自动化（双仓库）

op助手在车机/本地改代码后发布 PR，GitHub Actions 自动审阅；低风险变更可带 `ai-safe-merge` 自动 squash 合并。

## 仓库目标

| `repo_target` | GitHub 仓库 | 默认 base | 说明 |
|---------------|-------------|-----------|------|
| `openpilot` | `mouxangithub/openpilot` | `master-c3` | 车机 fork；路径门控更严 |
| `assistant` / `ai` | `mouxangithub/ai` | `main` | op助手 Web / 独立 ai 仓 |

配置项（`/data/ai/config.json`）：

- `ai_github_actions_pat` — GitHub PAT（repo 权限）
- `ai_assistant_repo_path` — 独立 ai 仓本地路径（可选）
- `ai_assistant_repo_url` / `ai_openpilot_repo_url`
- `ai_assistant_default_branch` / `ai_openpilot_default_branch`

## 工具

| 工具 | 用途 |
|------|------|
| `git_publish_pull_request` | 提交 → 推送 → 开 PR → 打标签 |
| `report_bug_and_publish_pr` | 结构化 Bug 报告 → PR（默认 assistant 仓） |
| `auto_review_pull_request` | 设备侧摘要审阅（可选合并） |
| `merge_github_pull_request` | 合并（需 `ai-safe-merge` + 路径/分支门控） |

## 标签

| 标签 | 含义 |
|------|------|
| `ai-auto-review` | 触发 Actions 审阅 |
| `ai-safe-merge` | 允许自动 squash（仍须 CI 绿 + 路径白名单） |
| `ai-auto-fix` | 预留：Actions 尝试自动修复 |

## openpilot 自动合并门控

- head 分支必须以 `ai/` 开头
- 仅允许改动：`ai/`、`docs/`、`.github/`
- 禁止：`selfdrive/`、`panda/`、`opendbc/safety/`、`opendbc/car/`、`cereal/`、`common/params_keys.h`
- 总 diff ≤ 500 行

## assistant (ai) 仓

- head：`ai/`、`fix/`、`web/`
- 路径限制更宽松；diff ≤ 1000 行
- UI/docs/typo 类 Bug 默认可打 `ai-safe-merge`

## GitHub Actions（混合架构）

| 工作流 | 职责 |
|--------|------|
| `opencode-pr.yml` | **OpenCode** AI 审阅 + 评论 `/oc` `/opencode` 改代码 |
| `ai-pr-automation.yml` | **仅**规则门控 squash 合并（`ai-safe-merge`） |

文档：[OpenCode GitHub 集成](https://opencode.ai/docs/zh-cn/github/)

### 1. OpenCode 审阅（`opencode-pr.yml`）

- PR 带 `ai-auto-review`（创建时自动打标）→ OpenCode Agent 发审查评论
- PR/Issue/行内评论写 `/oc` 或 `/opencode` → 按需修复、改 PR

**GitHub 配置**（Settings → Secrets and variables → Actions）：

| 类型 | 名称 | 说明 |
|------|------|------|
| **Secret** | `OPENCODE_API_KEY` | [OpenCode Zen](https://opencode.ai) 控制台 API Key |
| **Variable** | `OPENCODE_MODEL` | 如 `opencode/deepseek-v4-flash`（默认即此） |

与车机 op助手 `opencode-zen` + `deepseek-v4-flash` 对齐；**PR 审阅只读 GitHub 配置，不读车机 config.json**。

可选：安装 [OpenCode GitHub App](https://github.com/apps/opencode-agent) 或仓库内 `opencode github install`。

### 2. 安全自动合并（`ai-pr-automation.yml`）

- 仅当 PR 有 `ai-safe-merge` 且通过路径/分支/CI 门控时 squash 合并
- 脚本：`.github/scripts/ai_pr_safe_merge.py`（无 LLM，纯规则）
- OpenCode **不会**自动 merge 到 `master-c3`

### 标签触发

| 标签 | 触发 |
|------|------|
| `ai-auto-review` | OpenCode 审阅 |
| `ai-safe-merge` | 规则自动 squash |
| `ai-auto-fix` | 预留；可用 `/oc fix this` 代替 |

## Bug 报告流程（op助手 Web）

```
report_bug_and_publish_pr(
  repo_target="assistant",
  title="...",
  repro_steps="...",
  expected="...",
  actual="...",
  severity="ui",
  confirm=false
)
# 用户确认 → confirm=true
```

PR 创建后：OpenCode 自动审阅；带 `ai-safe-merge` 时规则工作流可自动合并。

## PC 上手动让 OpenCode 改 PR

在 PR 评论或代码行评论中：

```
/oc 把这里的错误处理补上
/opencode fix this
```

参见 [OpenCode GitHub 文档](https://opencode.ai/docs/zh-cn/github/)。

## 技能

- `git-pr-workflow` — 通用 PR 流程
- `ai-web-bugfix` — Web Bug → PR

参见 `ai/docs/GIT_PR.md`、`ai/docs/GITHUB_RUNNER.md`。
