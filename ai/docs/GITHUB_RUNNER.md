# GitHub Actions 自建 Runner（C3 prebuilt）

适用于 **comma three (C3 / `tici`)** 上运行 GitHub Actions，为 fork 编译并发布 **`*-prebuilt`** 分支。op助手技能：**`github-runner`**。

> 用户向手册（仓库根目录）：`release/ci/README.md`  
> 控制脚本：`release/ci/install_github_runner.sh`、`system/manager/github_runner.sh`

## 架构

```
push master-c3 ──► prepare_strategy ──► build (C3 Runner, label: tici)
                                              │
                                              ▼
                                         prebuilt.tar.gz
                                              │
publish ◄─────────────────────────────────────┘
    │
    ▼
master-c3-prebuilt 分支（车机 checkout 后含 prebuilt 文件，快速启动）
```

| 组件 | 路径 / 名称 |
|------|-------------|
| Runner 用户 | `github-runner` |
| 数据根目录 | `/data/github`（或 `/data/media/0/github`） |
| Runner 目录 | `{base}/runner` |
| 编译工作区 | `{base}/builds`（**不要**用 `/data/openpilot` 作 BUILD_DIR） |
| CI 绑定 openpilot | `{base}/openpilot` → mount bind 到 `/data/openpilot`（仅 Runner 作业内） |
| systemd 服务名 | `{runner}/.service`（如 `actions.runner.mouxangithub-openpilot.comma-xxxxx`） |
| Workflow | `.github/workflows/build.yaml` |
| 默认仓库 | `https://github.com/mouxangithub/openpilot` |

## GUI 启停（车机）

**设置 → 开发者 → 显示高级控制项 → GitHub Runner Service**

| Param | 作用 |
|-------|------|
| `ShowAdvancedControls` | 显示高级项（含 Runner 开关） |
| `EnableGithubRunner` | 允许 manager 启停 Runner |
| `NetworkMetered` | `true` 时 **禁止** 启 Runner |
| `GithubRunnerSufficientVoltage` | 电压 > 9V 时为 `true`（`hardwared` 写入；桌面 USB 常 < 9V） |

manager 条件（`system/manager/process_config.py` → `use_github_runner`）：

- **离路**（未 onroad）
- `EnableGithubRunner=true`
- `NetworkMetered=false`
- `GithubRunnerSufficientVoltage=true`（或未知时不挡）

满足时启动 `system/manager/github_runner.sh start`，循环 `systemctl start <service>`；进程退出时 `systemctl stop`。

**服务名解析**（`github_runner.sh`）：优先读 `{runner}/.service`，否则回退 `actions.runner.sunnypilot.$(hostname)`。fork 注册到自有仓库时 **必须** 读 `.service`，否则 GUI 无法控制。

## 安装（一次性）

### 方式 A：op助手对话（推荐）

1. GitHub → **Settings → Actions → Runners → New self-hosted runner**
2. 复制 **Registration token**（约 1 小时有效，**不是** PAT）
3. 车机 **离路**，对 op助手说，例如：

> 帮我安装 GitHub Runner，token 是 `AXXXXXXXXX...`

4. AI 调用 `install_github_runner(token=..., confirm=true)`，内部执行 `release/ci/install_github_runner.sh`
5. 安装完成后 `github_runner_status` 应显示 `installed`；GitHub 页 runner **Idle**，标签含 **`tici`**
6. 打开 **GitHub Runner Service**（`EnableGithubRunner=1`）让 manager 启停接单

### 方式 B：SSH 手动

```bash
cd /data/openpilot
git pull
sudo ./release/ci/install_github_runner.sh \
  --token <TOKEN> \
  --repo https://github.com/mouxangithub/openpilot
```

可选：

- `--start-at-boot` — systemd 开机自启（与 GUI 并行；若只要 GUI 控制则不要加，或事后 `systemctl disable`）
- `--restore` — 已有 `.credentials` + `.service` 时恢复

一键脚本（含 `ai` 子模块）：`release/ci/deploy_c3_runner.sh <TOKEN>`

## 卸载

```bash
sudo ./release/ci/uninstall_github_runner.sh
```

## GitHub 仓库配置

| 项 | 说明 |
|----|------|
| `DEPLOY_STRATEGY` | Actions Variable，见 `.github/DEPLOY_STRATEGY.example.json` |
| Workflow permissions | Read and write（推送 `*-prebuilt`） |
| Environments | 按策略创建 `c3-dev` / `feature-branch` 等 |

## 车机使用 prebuilt 分支

```bash
cd /data/openpilot
git fetch origin master-c3-prebuilt
git reset --hard origin/master-c3-prebuilt
git submodule update --init --recursive
test -f prebuilt && echo OK
sudo reboot
```

## 故障排查

| 现象 | 处理 |
|------|------|
| Actions `build` 一直 Pending | Runner 未注册/离线；`github_runner_status` |
| GUI 开关无效 | 对比 `cat /data/github/runner/.service` 与 `github_runner.sh` 使用的服务名 |
| 桌面供电 Runner 不启 | 电压 < 9V → `GithubRunnerSufficientVoltage=false` |
| checkout /tmp 满 | 临时目录使用 `/data/github/tmp`（runner 可写） |
| clone GitHub 失败（`RPC failed` / `early EOF`） | 默认已走镜像；可覆盖 Variable `GITHUB_MIRROR_PREFIXES` |
| 车机 `/data/openpilot` 被清空 | workflow BUILD_DIR 必须是 `/data/github/...`，非 live 目录 |
| 编译失败 | `/data/github/logs`、Actions 日志、`grep_log actions.runner` |

## op助手工具

| 工具 | 用途 |
|------|------|
| `github_runner_status` | 路径、Param 门控、systemd 状态；若已配置 PAT 则附带 API 摘要 |
| `github_runner_recovery_hint` | 推荐排查顺序 |
| `install_github_runner` | 预览/执行安装脚本（`confirm=true` + registration token） |
| `get_device_settings` / `set_device_settings` | 读写 `EnableGithubRunner` |
| `github_actions_auth_status` | PAT 是否已配置、是否有效（**不返回 token**） |
| `set_github_actions_pat` | 保存/清除 `ai_github_actions_pat`（`confirm=true`；空 token 表示清除） |
| `list_github_workflow_runs` | 列出 workflow 运行（默认 `build.yaml`） |
| `get_github_workflow_run` | 单次 run 详情 + jobs |
| `cancel_github_workflow_run` | 取消 run（`confirm=true`） |
| `list_github_runners` | GitHub 侧 runner 在线/忙碌 + 本地安装摘要 |
| `stop_github_runner_service` | 本地 `systemctl stop`（不卸载） |
| `trigger_github_workflow` | 手动触发 `build.yaml`（`confirm=true`） |
| `rerun_github_workflow` | 重跑失败 run |
| `wait_github_workflow` | 轮询至完成（可推送通知） |
| `check_github_runner_health` | 本地 + GitHub 健康摘要 |
| `prebuilt_branch_status` | 对比 dev / prebuilt 分支 |
| `checkout_prebuilt_branch` | 切换 `*-prebuilt` 并验证 `prebuilt` 文件 |
| `ota_preflight_checklist` | OTA 或换分支前预检 |

### GitHub PAT 配置（一次性）

用于在车机上通过 op助手 **查看/取消** Actions、**创建/审阅 Pull Request**，无需开浏览器：

1. GitHub → **Settings → Developer settings → Personal access tokens**
2. 创建 **classic** 或 **fine-grained** token，权限至少：
   - `repo`（读仓库；**发 PR / 合并** 也需此权限）
   - `actions`（读 workflow；取消 run 需 write）
3. 车机离路，对 op助手说「配置 GitHub PAT」或调用：
   - `set_github_actions_pat(token=<PAT>, confirm=true)`
4. 验证：`github_actions_auth_status`

发 PR 流程见 **`ai/docs/GIT_PR.md`**（`git_publish_pull_request`）。

Token 存入 **`/data/ai/config.json`** 的 **`ai_github_actions_pat`**（与 `ai_api_key` 相同存储方式；不会出现在日志/工具返回值中）。

若设备上曾配置过旧版 `GithubActionsPat` Param，首次读取时会自动迁移到 `config.json` 并删除旧 Param。

**注意**：registration token（安装 Runner 用）与 PAT **不是同一种** token。

## 国内网络加速（clone GitHub）

C3 在国内拉 GitHub 常出现 `RPC failed; curl 92 HTTP/2 stream ...` 或 `fatal: early EOF`。`build.yaml` 已默认启用 **GitHub 镜像加速**（方式 B），**无需在 C3 上配代理**。

默认镜像（按顺序尝试，失败后回退直连 GitHub）：

1. `https://ghfast.top/` + 原 URL
2. `https://ghp.ci/` + 原 URL
3. 直连 `https://github.com/...`

### 自定义镜像（可选）

仅在默认镜像不好用时，到 **Settings → Variables → Actions** 覆盖：

| 变量 | 示例值 | 说明 |
|------|--------|------|
| `GITHUB_MIRROR_PREFIXES` | `https://ghfast.top/,https://ghp.ci/` | 逗号分隔前缀 |
| `GITHUB_CLONE_FALLBACK_URLS` | `https://gitee.com/mouxangithub/openpilot.git` | 完整备用仓库 URL |

设为空字符串 `GITHUB_MIRROR_PREFIXES` 可禁用镜像、仅直连（不推荐国内环境）。

辅助脚本：`/data/github/ci/git_resilient_clone.sh`（安装 Runner 时自动部署）。

## 相关技能

- `github-runner` — Runner 与 prebuilt CI 主技能
- `git-pr-workflow` — 本地改代码 → 提交 PR（见 `GIT_PR.md`）
- `pc-dev-environment` — PC 侧触发 workflow、devsync
- `network-diagnostics` — 网络与代码同步
- `diagnostics` — 进程与日志
- `sp-display-device` — 开发者 Param 总览
