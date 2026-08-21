# GitHub Runner 与 C3 prebuilt CI

适用于 **comma three** 自建 Actions Runner：编译 `master-c3` → 发布 `master-c3-prebuilt`，以及 GUI / Param 启停 Runner。

> 事实来源：`ai/docs/GITHUB_RUNNER.md`、`release/ci/README.md`

## 何时触发

- GitHub Actions **build** 作业一直 **Pending**（等待 `tici` runner）
- 用户问「怎么开 Runner」「prebuilt 怎么编译」「GUI Runner 开关没用」
- 车机需要 `prebuilt` 快速启动
- `EnableGithubRunner` / 开发者高级控制相关

## 核心概念（勿混淆）

| 对象 | 说明 |
|------|------|
| `EnableGithubRunner` | UI/manager **允许**启停 Runner，不是安装开关 |
| `github_runner_start` | manager 子进程，跑 `github_runner.sh start` |
| `{base}/runner/.service` | **真实** systemd 单元名（fork 仓库名会体现在此） |
| `/data/openpilot` | 车机 **live** 代码树；CI 编译用 `{base}/builds`，勿 wipe |
| `tici` 标签 | workflow `runs-on` 要求；注册 Runner 时须带上 |

## 推荐工具顺序

### A. 已安装 — 排查不工作

1. `github_runner_status` — Param 门控、服务名、systemd、目录
2. `github_runner_recovery_hint` — 下一步建议
3. `get_device_settings` — 确认 `ShowAdvancedControls`、`EnableGithubRunner`
4. `list_managed_processes` — 是否有 `github_runner_start`
5. `grep_log` — `github_runner|actions.runner|EnableGithubRunner`
6. 电压/网络：`GithubRunnerSufficientVoltage`、`NetworkMetered`（见 status 输出）
7. 仍失败 → 对照 `ai/docs/GITHUB_RUNNER.md` 重装或 `--restore`

### B. 未安装 — 用户发来 registration token 安装（首选）

用户从 GitHub 复制 **registration token**（Settings → Actions → Runners → New self-hosted runner）并粘贴到对话：

1. `github_runner_status` — 确认当前未安装或需 `--restore`
2. `install_github_runner(token=<用户粘贴的token>, confirm=true)` — **直接执行** `release/ci/install_github_runner.sh`（离路、root、约 5–10 分钟）
3. 若 UI 需二次确认：先 `confirm=false` 或走 `pending_id`，用户点确认后再 `confirm=true`
4. 安装返回里的 `status_after_install` / 再调 `github_runner_status` — 看 `installed`、`systemd`、标签 `tici`
5. 提示打开 `EnableGithubRunner`（`set_device_settings`）让 manager 接单

**注意**：registration token ≠ PAT。PAT 用于 `set_github_actions_pat` 查/取消 workflow。

已有 `.credentials` 仅换 token：`install_github_runner(restore=true, token=..., confirm=true)`

### C. prebuilt 发布与车机更新

1. PC：推 `master-c3` 或手动 Run workflow `build.yaml`
2. 等 `build`（C3）+ `publish`（云端）完成
3. 车机：`git fetch && git reset --hard origin/master-c3-prebuilt`
4. `test -f /data/openpilot/prebuilt` 或 `get_build_info`

## GUI 启停条件（全部满足才 start）

- 离路
- `EnableGithubRunner=true`
- `NetworkMetered≠true`
- `GithubRunnerSufficientVoltage=true`（车载 >9V；桌面 USB 可能不满足）

**非 release 分支**才显示 Runner 开关（`developer.py`）。

## 常见坑

1. **服务名不一致** — fork 注册为 `actions.runner.<org>-<repo>.<host>`；旧脚本写死 `sunnypilot` → 已改为读 `.service`
2. **`--start-at-boot`** — 开机自启与 GUI 并行；只要 GUI 控制则 `systemctl disable`
3. **桌面调试** — 电压门控导致 Runner 不启，属预期
4. **Pending ≠ 车机问题** — 也可能是 GitHub 无 runner、标签不对、runner 离线

## SSH 速查

```bash
cat /data/github/runner/.service
systemctl status "$(cat /data/github/runner/.service)"
cat /data/openpilot/release/ci/install_github_runner.sh | head
```

### E. Prebuilt 发布闭环（workflow: prebuilt_release）

1. `check_github_runner_health` → `github_runner_status`
2. `trigger_github_workflow(confirm=true)` 或 PC push `master-c3`
3. `wait_github_workflow(ref=master-c3)` — 完成可收到通知
4. `prebuilt_branch_status` → `checkout_prebuilt_branch(confirm=true)`
5. `ota_preflight_checklist` → 重启

### D. GitHub Actions 远程管理（需 PAT）

1. `github_actions_auth_status` — 是否已配置 PAT
2. 未配置 → `set_github_actions_pat(token=..., confirm=true)`（scopes: repo + actions）
3. `list_github_workflow_runs` — 最近运行；`status=in_progress` 看正在执行的
4. `get_github_workflow_run(run_id=...)` — jobs、runner 名、标签
5. `list_github_runners` — GitHub 侧 online/busy
6. 取消卡死编译 → `cancel_github_workflow_run(run_id=..., confirm=true)`
7. 仅停本地服务（不卸载）→ `stop_github_runner_service(confirm=true)`

`github_runner_status` 在 PAT 有效时会附带 `github_api` 摘要（进行中 run、busy runner）。

## 相关技能

- `pc-dev-environment` — workflow 触发、git、devsync
- `network-diagnostics` — 同步代码、SSH
- `diagnostics` — 进程/日志
- `sp-display-device` — `EnableGithubRunner` 等开发者 Param
