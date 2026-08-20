# GitHub Actions 预编译（prebuilt）指南

本仓库使用 **sunnypilot prebuilt action**（`.github/workflows/sunnypilot-build-prebuilt.yaml`）在 **comma three (C3)** 上交叉编译，并把带 `prebuilt` 标记的代码推到 `*-prebuilt` 分支。车机安装该分支后可跳过本地 scons，开机更快。

仓库：`https://github.com/mouxangithub/openpilot`

## 架构概览

```
push master-c3  ──►  prepare_strategy  ──►  build (C3 自建 Runner)
                              │                    │
                              │                    ▼
                              │              prebuilt.tar.gz
                              ▼                    │
                         publish ◄─────────────────┘
                              │
                              ▼
                    推送到 master-c3-prebuilt 分支
```

| 阶段 | 运行环境 | 说明 |
|------|----------|------|
| `prepare_strategy` | GitHub 云端 | 根据 `DEPLOY_STRATEGY` 决定输出分支名 |
| `build` | **自建 Runner**（标签 `tici`） | 在 C3 上 scons 全量编译 |
| `publish` | GitHub 云端 | 打包并 force-push 到 `*-prebuilt` 分支 |

> **重要**：`build` 作业必须在带 `tici` 标签的自建 Runner 上运行（真机 C3/C3X）。没有自建 Runner 时 workflow 会一直排队。

## 一次性配置（GitHub 网页）

### 1. 注册自建 Runner（在 C3 上）

1. 打开 [Actions → Runners → New self-hosted runner](https://github.com/mouxangithub/openpilot/settings/actions/runners/new)
2. 复制 **Registration token**（有效期约 1 小时）
3. SSH 进 C3，执行：

```bash
cd /data/openpilot
git pull   # 确保有最新 install_github_runner.sh
sudo ./release/ci/install_github_runner.sh --token <你的token> --repo https://github.com/mouxangithub/openpilot
```

4. 回到 GitHub → Runners，确认出现 **Idle** 状态且带 `tici` 标签

可选：`--start-at-boot` 开机自启；`--restore` 仅恢复已有配置。

### 2. 配置仓库变量 `DEPLOY_STRATEGY`

[Settings → Secrets and variables → Actions → Variables](https://github.com/mouxangithub/openpilot/settings/variables/actions)

新建变量 **`DEPLOY_STRATEGY`**，值为 `.github/DEPLOY_STRATEGY.example.json` 的内容（单行 JSON 亦可）。

未配置时，推 `master-c3` 会回退为：输出分支 **`master-c3-prebuilt`**，环境名 **`feature-branch`**。

### 3. 配置 Environment（可选）

若 `DEPLOY_STRATEGY` 里写了 `"environment": "c3-dev"`，需在  
[Settings → Environments](https://github.com/mouxangithub/openpilot/settings/environments) 创建同名环境（如 `c3-dev`、`feature-branch`）。  
不配置审批规则即可直接发布。

### 4. Workflow 权限

[Settings → Actions → General → Workflow permissions](https://github.com/mouxangithub/openpilot/settings/actions)  
选择 **Read and write permissions**，允许 workflow 推送 `*-prebuilt` 分支。

### 5. 国内网络加速（已内置，一般无需配置）

`build.yaml` 默认通过 **GitHub 镜像**（`ghfast.top` → `ghp.ci` → 直连）拉代码，C3 上**不用配代理**。

若默认镜像不稳定，可在 **Settings → Variables → Actions** 覆盖 `GITHUB_MIRROR_PREFIXES`。详见 `ai/docs/GITHUB_RUNNER.md`。

## 如何使用

### 方式 A：推代码自动打包

向 **`master-c3`** 推送 commit 后自动触发（已配置在 workflow `on.push.branches`）。

### 方式 B：手动触发

1. [Actions → sunnypilot prebuilt action → Run workflow](https://github.com/mouxangithub/openpilot/actions/workflows/sunnypilot-build-prebuilt.yaml)
2. **branch**：要编译的分支（默认 `master-c3`）
3. **wait_for_tests**：是否在编译前等待 `tests.yaml` 通过

### 方式 C：PR 打标签

对外部 PR 打上 **`prebuilt`** 标签可触发一次编译（`pull_request_target`）。

## 车机安装 prebuilt 分支

```bash
cd /data/openpilot
git fetch origin master-c3-prebuilt
git checkout -B master-c3-prebuilt origin/master-c3-prebuilt
# 或 reset 到该分支
git reset --hard origin/master-c3-prebuilt
git submodule update --init --recursive
sudo reboot
```

确认存在 `prebuilt` 文件即表示已带预编译产物：

```bash
test -f /data/openpilot/prebuilt && echo OK
```

## 其它 Workflow

| 文件 | 用途 | 本 fork 是否启用 |
|------|------|------------------|
| `tests.yaml` | PR/推送 CI 测试 | ✅ 含 `master-c3` |
| `sunnypilot-build-prebuilt.yaml` | C3 预编译发布 | ✅ 主流程 |
| `prebuilt.yaml` / `release.yaml` | 上游 sunnypilot 官方 Docker 定时构建 | ❌ 仅 `sunnypilot/sunnypilot` |
| `sunnypilot-master-dev-prep.yaml` | master → master-dev 合并 | 可选，需额外 secrets |

## 故障排查

| 现象 | 处理 |
|------|------|
| `build` 一直 Pending | C3 未注册 Runner 或 Runner 离线 |
| `publish` 权限失败 | 检查 Workflow permissions 与 `contents: write` |
| Environment 等待审批 | 在 Environments 关闭 required reviewers |
| 编译失败 | SSH 上 C3 看 Runner 日志：`/data/github/logs` 或 Actions 网页日志 |
| **检出仓库秒失败、无日志** | Runner 服务曾把**空的** `/data/github/openpilot` bind 到 `/data/openpilot`，导致 CI 内看不到本地仓库。修复：去掉 systemd `ExecStart` 里的 `mount --bind ...` 并 `systemctl restart` runner；见 `install_github_runner.sh` |
| 检出很慢（约 1 分钟） | 正常：`git worktree` 需展开约 4500 个文件；勿用网络 clone |
| 子模块缺失 | workflow 已 `submodules: recursive`；本地确认 `.gitmodules` 正确 |

## 相关脚本

- `release/ci/install_github_runner.sh` — 在 C3 安装 GitHub Actions Runner
- `release/ci/uninstall_github_runner.sh` — 卸载 Runner
- `release/ci/deploy_c3_runner.sh` — 一键部署（含 `ai` 子模块）
- `system/manager/github_runner.sh` — manager 按 Param 启停 systemd 服务（读 `runner/.service`）
- `release/ci/publish.sh` — 将编译产物推到 `*-prebuilt` 分支
- `release/ci/docker_build_sp.sh` — 上游 Docker 构建（本 fork 默认不用）

## op助手（AI）

车机 op助手 技能 **`github-runner`**、文档 **`ai/docs/GITHUB_RUNNER.md`**、工具 `github_runner_status` / `github_runner_recovery_hint` / `install_github_runner`。
