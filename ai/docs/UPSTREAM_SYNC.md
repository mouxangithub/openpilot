# 上游同步（sunnypilot → master-c3-new）

从 **sunnypilot** 上游拉取 `master`，在 **`master-c3-new`** 分支上合并（以 `master-c3` 为只读基底），推送后开 **Draft PR**。你在车机自测通过后，**手动**合并 PR 到 `master-c3`。

**CI 绝不会** push 或 merge 到 `master-c3`；带 `upstream-sync` 标签的 PR **禁止** `ai-safe-merge` 自动合并。

## 仓库与顺序

| 顺序 | Fork | 上游 | 输出分支 |
|------|------|------|----------|
| 1 | `mouxangithub/opendbc` | `sunnypilot/opendbc:master` | `master-c3-new` |
| 2 | `mouxangithub/panda` | `sunnypilot/panda:master` | `master-c3-new` |
| 3 | `mouxangithub/openpilot` | `sunnypilot/sunnypilot:master` | `master-c3-new` |

依赖链：**opendbc → panda → openpilot**（`repository_dispatch`）。

## 流程

```
sunnypilot/master
       │
       ▼ 以 master-c3 为基底，仅在 master-c3-new 上合并
  master-c3-new  ──push──►  fork（供你自测）
       │
       ▼ 开 Draft PR → master-c3（upstream-sync，不自动 merge）
  OpenCode 审阅 → 你测车 → 手动合并 master-c3
```

1. **合并**：`upstream_sync_merge.sh` fetch upstream 并 merge。
2. **冲突**：`opencode run` CLI 在当前分支解冲突（**不会**创建 `opencode/dispatch-*` 分支）；随后 workflow commit 并 push `master-c3-new`。
3. **测试**：各仓跑 `test.sh`（openpilot 仅布局快检）。
4. **推送**：`git push origin master-c3-new --force-with-lease`。
5. **PR**：开 **Draft** PR（`master-c3-new` → `master-c3`），打 `ai-auto-review`、`upstream-sync`。
6. **下游**：opendbc 成功 → dispatch panda → dispatch openpilot；openpilot 用 `upstream_sync_submodules.sh` 把子模块指到 `master-c3-new` tip。

## 触发方式

| 仓库 | 定时 | 手动 | 被触发 |
|------|------|------|--------|
| opendbc | 每周一 02:00 UTC | `workflow_dispatch` | — |
| panda | — | `workflow_dispatch` | opendbc dispatch |
| openpilot | — | `workflow_dispatch` | panda dispatch |

仅跑 openpilot 时：先确保 opendbc/panda 的 `master-c3-new` 已更新，再手动触发 openpilot 并勾选「更新子模块」。若子仓尚无 `master-c3-new`，openpilot 脚本会 **回退** 到 `master-c3` 并打 warning，不中断 workflow。

## GitHub 配置

在三仓 **Settings → Secrets and variables → Actions** 配置：

| 类型 | 名称 | 说明 |
|------|------|------|
| Secret | `OPENCODE_API_KEY` | 解冲突 + PR 审阅 |
| Secret | `SYNC_PAT` | 跨仓 `repository_dispatch`、推分支（需 `repo` 权限） |
| Variable | `OPENCODE_MODEL` | 如 `opencode/deepseek-v4-flash` |

标签（若无则创建）：`upstream-sync`、`ai-auto-review`。

## C3 适配要点（冲突时 OpenCode 须保留）

### openpilot

- `release/ci`、tici prebuilt、`sunnypilot/*` C3 层、统一或拆分 pandad（以本 fork 为准）
- 子模块：`mouxangithub/opendbc`、`mouxangithub/panda` @ `master-c3` / `master-c3-new`

### opendbc

- `opendbc/sunnypilot/**`
- `opendbc/safety/**`；若改 `can.h`，需同步 **openpilot 侧**固件树 CAN hash pin（`panda/` 和/或 `panda_tici/`，见目标 fork）

### panda

- `board/stm32f4/**`、`boards/dos.h`（DOS / 内置 F4）
- opendbc 依赖指向 `mouxangithub/opendbc@master-c3`

## 本地自测

```bash
# 子仓
git fetch origin master-c3-new && git checkout master-c3-new

# openpilot（含子模块）
git fetch origin master-c3-new
git checkout master-c3-new
git submodule update --init --recursive
```

通过后合并对应 PR 到 `master-c3`。需要 C3 prebuilt 时在 openpilot PR 打 `prebuilt` 标签。

## 工作流文件

| 仓库 | 工作流 | 脚本 |
|------|--------|------|
| opendbc | `.github/workflows/upstream-sync.yml` | `.github/scripts/upstream_sync_*.sh` |
| panda | 同上 | 同上 |
| openpilot | 同上 | + `upstream_sync_submodules.sh` |

PR 审阅见 [PR_AUTOMATION.md](./PR_AUTOMATION.md)（`opencode-pr.yml`）。
