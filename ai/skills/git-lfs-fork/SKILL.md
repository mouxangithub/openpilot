# Git LFS 推送策略（fork）

用户在本 fork **推送代码**、发 PR、或问「push 失败 / LFS / Unprocessable entity」时启用。

> 完整说明：`ai/docs/GIT_LFS.md`

## 策略（必须遵守）

1. **拉取**：`git lfs pull` 从 `.lfsconfig`（GitLab sunnypilot-new-lfs）拉大文件 — **正常执行**
2. **推送**：**不向 LFS 上传** — 使用 `GIT_LFS_SKIP_PUSH=1`
3. **自改 UI 字体/训练图**：已在 `.gitattributes` 排除 LFS，走普通 Git

## op助手 行为

- `git_push`、`git_publish_pull_request`、`publish_changes` **已自动** `GIT_LFS_SKIP_PUSH=1`
- 用户手动 shell push 时，提醒设置环境变量或 `lfs.allowincompletepush true`

## 推送前（AI 应做）

```
git_status → git_diff
git lfs push --dry-run origin HEAD   # 应为 0 个上传对象
git_push / git_publish_pull_request(confirm=true)
```

## 用户手动命令

**CMD**

```cmd
set GIT_LFS_SKIP_PUSH=1
git push origin master-c3
```

**PowerShell**

```powershell
$env:GIT_LFS_SKIP_PUSH=1
git push origin master-c3
```

**持久（本仓）**

```bash
git config --local lfs.allowincompletepush true
```

## 常见错误

| 错误 | 处理 |
|------|------|
| LFS upload `Unprocessable entity` | `GIT_LFS_SKIP_PUSH=1` 后重试 push |
| push 含新 LFS 指针 | 改为普通 Git 或不要提交大文件到 LFS 跟踪路径 |
| CI `git lfs pull` 失败 | 检查 runner 能否访问 `.lfsconfig` URL |

## 禁止

- 未经用户明确要求，不要设 `GIT_LFS_SKIP_PUSH=0` 上传 LFS
- 不要把密钥写进 `.lfsconfig` pushurl 来「绕过」权限

## 相关

- 技能 `git-pr-workflow`
- 文档 `ai/docs/GIT_PR.md`
