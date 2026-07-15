# PC 开发环境技能

> 仅在 **PC dev**（非 comma 车机 C3/C3X/C4）时，`pc_launch_*` 工具会出现在 op 助手工具列表中。  
> 先调用 `get_host_environment` 确认 `host_kind: pc_dev` 与 `pc_tools` 库存；`hardware_profile` 含 PC 上经 `panda_tici` 探测的 MCU（F4/H7）及 manager/pandad 状态。车机显示 C3/C3X/C4。设备对照见 `ai/docs/COMMA_DEVICES.md`。

## 适用主机

- Ubuntu 24.04（上游推荐开发环境）
- macOS / WSL（部分二进制需 scons 构建）

## 工具对照

| PC 命令 | op 助手工具 |
|---------|-------------|
| `tools/plotjuggler/juggle.py <route>` | `pc_launch_plotjuggler` |
| `tools/jotpluggler/jotpluggler <route>` | `pc_launch_jotpluggler`（需 `scons -u`） |
| `tools/replay/replay <route>` | `pc_launch_replay`（需 `scons -u`） |
| `tools/cabana/cabana <route>` | `pc_launch_cabana`（需 `scons -u`） |
| `tools/lib/auth.py` | `pc_auth_login_hint` + `comma_auth_status` |
| `tools/sim/run_bridge.py` | `pc_launch_sim_bridge`（默认关闭，勿接真车） |

### ZMQ 流式联调（PC replay → 可视化）

| 场景 | op 助手工具 |
|------|-------------|
| 一键：replay 发 ZMQ + 开可视化 | `pc_launch_replay_viz_stream`（`viz=plotjuggler` 或 `jotpluggler`） |
| 分步：只开 replay 发布 | `pc_launch_replay_stream` |
| 分步：只开 PlotJuggler 订阅 | `pc_launch_plotjuggler_stream` → GUI 里 Cereal Subscriber → Start |
| 分步：只开 JotPluggler 流 | `pc_launch_jotpluggler_stream` |

等价命令：`ZMQ=1 tools/replay/replay <route>` + `ZMQ=1 tools/plotjuggler/juggle.py --stream`

### can_replay（不接 op 助手）

`tools/replay/can_replay.py` 需要 **Panda Jungle USB 硬件** + 接在 Jungle 上的 comma 设备/Panda；**不需要真车上路**，但没有硬件时脚本只会空等设备，无法当「纯读日志」工具用。看 CAN 内容请用 `extract_can_ids_from_route` / Web Cabana。

车机 comma 设备上请用：**Web Cabana**、`route_time_series`、`plotjuggler_data_summary`（无 GUI）。

## op 助手 + TSK（PC 本地）

与车机同一进程，默认端口 **5090**（非 manager 拉起）：

```bash
cd openpilot && source .venv/bin/activate
python3 -m ai.aid
```

| 入口 | URL |
|------|-----|
| op 助手 | `http://127.0.0.1:5090/` |
| TSK SecOC | `http://127.0.0.1:5090/?settings=secoc` |

PC 上 TSK 为 `dry_run`（无真实 panda）；可测页面、`/api/tsk/*` 与助手工具 `get_tsk_manager_status` 等。详见 `ai/docs/TSK_AND_AID.md`。

| 需求 | 工具 |
|------|------|
| TSK 流水线状态 | `get_tsk_manager_status` |
| offroad 查找安装密钥 | `tsk_find_and_install_key(confirm=true)` |
| 一键 UDS 提取 | `tsk_extract_key(confirm=true)` |
| 手动安装密钥 | `tsk_install_secoc_key(key=…, confirm=true)` |
| 清除提取缓存 | `tsk_clear_cache(confirm=true)` |
| 卸载密钥 | `tsk_uninstall_key(confirm=true)` |

## 数据抓取（AI 可读）

GUI 工具本身不回传数据；op 助手在 **启动时自动快照** 路线上下文，并可用专用工具复查：

| 需求 | 工具 |
|------|------|
| 不启动 GUI，只要路线参数/信号 | `pc_capture_route_context` |
| 启动 PlotJuggler/Replay/Cabana 后拿启动参数 + 数据 | `pc_launch_*` 返回 `session_id` + `data_snapshot` |
| 查历史启动、进程是否还在 | `pc_list_tool_sessions` |
| 按 session 重读快照或刷新 | `pc_get_tool_session(session_id, refresh_data=true)` |

`data_snapshot` 典型字段：

- `car_params` — 路线 qlog 里的 carParams（平台、指纹、FW 样本）
- `topics` — 日志里出现的 cereal topic 列表
- `signal_summary` — PlotJuggler 风格关键信号统计
- `juggle_context` — 推断的 platform / DBC（与 juggle.py 一致）
- `route_summary` / `video_info` — 段目录、qlog、摄像头

## 典型流程

1. `get_host_environment` — 看 `routes_dir`、`pc_tools.replay.launchable` 等  
2. **Git 分支**：`git_status` → `git_list_branches` → `git_stash(confirm=true)`（如有改动）→ `git_checkout` → `git_fetch` / `git_pull` → `git_commit`  
3. **同步代码到车机前**：`pc_devsync_status(device_ip="192.168.x.x")` — 只读体检（rsync/git/ssh、SSH 是否通）；`ready` 为 true 后再 `pc_devsync_run(confirm=true)` 或终端跑 `suggested_command`  
4. `list_drive_routes` / `pc_capture_route_context` — 先拿结构化数据  
5. `pc_launch_plotjuggler` — 后台开 GUI，同时返回 `session_id` 与 `data_snapshot`  
6. 用户看完图后问「刚才那条路线的纵向怎么样？」→ `pc_get_tool_session(session_id)`  
7. 适配/调参：`car_porting_*`、`long_maneuver_report`、桌面 Cabana 编辑 DBC  

## 构建提示

```bash
cd openpilot && tools/op.sh setup && source .venv/bin/activate && scons -u
cd tools/plotjuggler && ./juggle.py --install
```

## 禁止

- 车机上调用 `pc_launch_*`（会被环境检测拒绝）  
- 真车连接时运行 `pc_launch_sim_bridge` / joystick  
- AI 代写 `opendbc/` 生产路径（仍走 `save_adaptation_draft`）
