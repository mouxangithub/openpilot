# Git LFS：拉取与推送策略（fork）

本 fork 使用 sunnypilot 公共 LFS 仓拉取大文件（模型、音效等），**不向 LFS 远端上传**。op助手 在 `git_push` / `git_publish_pull_request` 时**默认**设置 `GIT_LFS_SKIP_PUSH=1`。

## 策略摘要

| 操作 | 行为 |
|------|------|
| **clone / pull** | 从 `.lfsconfig` 的 GitLab `sunnypilot-new-lfs` 拉取 LFS 对象 |
| **push 普通 Git** | 推到你的 GitHub fork（如 `mouxangithub/openpilot`） |
| **push LFS 对象** | **跳过**（无写权限 / 不上传自改大文件） |
| **自改 UI 资源** | `OpFont-*.otf`、`training/*.png` 等在 `.gitattributes` 中**排除 LFS**，走普通 Git |

## 推送前检查（AI / 人工）

```bash
# 预览是否会尝试上传 LFS（应为 0 个对象）
git lfs push --dry-run origin HEAD

# 查看待推送提交是否含 LFS 指针改动
git log -1 --stat
```

若 `dry-run` 显示有待上传对象，且你**不打算**上传 LFS：

- **推荐**：`git push`（op助手 已自动 `GIT_LFS_SKIP_PUSH=1`）
- **一次性（CMD）**：`set GIT_LFS_SKIP_PUSH=1` 后 `git push`
- **一次性（PowerShell）**：`$env:GIT_LFS_SKIP_PUSH=1; git push`
- **本仓持久**：`git config --local lfs.allowincompletepush true`

若要**恢复**向 LFS 上传（极少需要）：`GIT_LFS_SKIP_PUSH=0 git push`

## 常见失败

| 现象 | 原因 | 处理 |
|------|------|------|
| `Unprocessable entity` / LFS upload 失败 | push 尝试上传到 GitLab LFS 且无写权限 | 设 `GIT_LFS_SKIP_PUSH=1` 再 push |
| CI `git lfs pull` 失败 | Actions 托管机访问不了内网 LFS | 用 self-hosted runner 或确保可访问 `.lfsconfig` 的 url |
| 本地缺大文件 | 未 `git lfs pull` | `git lfs pull`（拉取，非推送） |

## op助手 工具

| 工具 | LFS 行为 |
|------|----------|
| `git_push` | 自动 `GIT_LFS_SKIP_PUSH=1` |
| `git_publish_pull_request` / `publish_changes` | 经 `git_push_at`，同上 |
| `git_pull` | **不**设置 skip；正常拉取 |

## 相关文件

- 仓库根 `.lfsconfig` — LFS 拉取 URL
- 仓库根 `.gitattributes` — LFS 跟踪规则与 fork 例外
- 技能：`git-lfs-fork`、`git-pr-workflow`
- 文档：`ai/docs/GIT_PR.md`
