# Git 提交与 Pull Request

让 op助手在**离路**时把本地改动变成 GitHub Pull Request，你在 PC 上拉取、审阅、合并即可。

> **多仓 / Gitee / Fork 发布**：见 [PUBLISH.md](./PUBLISH.md)。**Issue 反馈**：见 [ISSUES.md](./ISSUES.md)。

## 前置条件

1. **Git 凭据**：设备或 PC 上 `git push` 能成功（SSH key 或 credential helper）。
2. **GitHub PAT**（`ai_github_actions_pat`）：与 Runner registration token **不同**，需 classic/fine-grained PAT，权限至少：
   - `repo`（含 pull requests 读写）
   - 若还要管 CI：`actions:read`（已有 workflow 工具）
3. 配置：`set_github_actions_pat(token=..., confirm=true)`（写入 `config.json`）

## Git LFS（fork 推送）

本 fork **从 GitLab 拉 LFS、不向 LFS 上传**。`git_push` / `git_publish_pull_request` 自动设置 `GIT_LFS_SKIP_PUSH=1`。

详见 [GIT_LFS.md](./GIT_LFS.md)；技能 `git-lfs-fork`。推送前建议：`git lfs push --dry-run origin HEAD`（应为 0 对象）。

## 核心工具

| 工具 | 作用 |
|------|------|
| `git_publish_pull_request` | 一键：建 `ai/*` 分支 → commit → push → 开 PR |
| `list_github_pull_requests` | 列出 open/closed PR |
| `get_github_pull_request` | PR 详情 + 变更文件列表 |
| `review_github_pull_request` | 发表评论 / Approve / Request changes |
| `merge_github_pull_request` | 合并 PR（默认 squash） |
| `auto_review_pull_request` | 自动摘要 diff 并发审阅评论 |

写操作均需 **离路** + `confirm=true`（或 Web UI 待确认）。

## 典型流程（车机改代码 → PC 审核）

```
用户：帮我把刚才的改动发个 PR
AI：
  1. git_status / git_diff
  2. git_publish_pull_request(title=..., confirm=false)  → 预览
  3. 用户确认后 confirm=true
  4. 返回 pull_request_url
```

在 PC 上：

```bash
git fetch origin
git checkout ai/your-branch
# 审阅后 GitHub 网页合并，或让 AI 调用 merge_github_pull_request
```

## 安全门控

- 在 `master-c3` 等保护分支上有未提交改动时，会自动 `git checkout -b ai/...`，**不会**直接在保护分支上提交。
- `merge_github_pull_request` 合并到 `master-c3` 时，**仅允许** head 分支以 `ai/` 开头。
- 默认**不**自动合并；`auto_review_pull_request(merge_if_clean=true)` 仍需 `confirm=true` 且 PR 可合并。

## 工作流

- `publish_pr`：发布 PR 一条龙
- `pr_review_merge`：审阅 + 可选合并

技能：`git-pr-workflow`（`ai/skills/git-pr-workflow/SKILL.md`）

## GitHub Actions 自动审阅（可选）

仓库可添加 `.github/workflows/ai-pr-review.yml`：在 PR 打标签 `ai-auto-review` 时触发 CI，与 op助手工具互补（车机发 PR，云端/PC 自动审阅）。

## 与现有 Git 工具的关系

- `git_commit` / `git_push`：分步手动
- `generate_adaptation_pr_draft`：仅生成 Markdown，不 push
- `git_publish_pull_request`：上述能力的组合 + GitHub API 建 PR
