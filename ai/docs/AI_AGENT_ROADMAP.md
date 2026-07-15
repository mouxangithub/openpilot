# op助手 AI Agent 能力路线图

> **维护者参考文档**（非用户手册）。用户安装与使用请阅 [docs/README.md](README.md)、[INSTALL.md](INSTALL.md)、[OVERVIEW.md](OVERVIEW.md)。  
> 更新：2026-07-15  
> 参考：上游 openpilot 车辆适配方法论、社区调优实践、各 fork 的 `settings/ITEMS`

---

## 0. 内化能力概览

op助手将社区公开的**适配与调优方法**写入技能与内置知识库，供 AI 检索执行，而非在界面或技能名中挂作者/外链。

| 能力域 | 技能 / RAG | 要点 |
|--------|------------|------|
| 车辆适配 | `vehicle-adaptation` + `builtin_vehicle_adaptation_guide` | 指纹五类 CAN、CarState/CarController 草稿、封闭场地验证 |
| CP 迁移 | `carrot-legacy` + `builtin_cp_*_mapping` | CP Param → `dp_*` / Dashy，禁止写 CP 专有项 |
| 调优 | `dp-tuning`, `longitudinal-tuning`, `dp-brand-*` | `list_dp_settings`, 预设, `diff_params` |
| Engage 分诊 | `engage-troubleshooting` + `builtin_engage_triage` | SecOC → 指纹 → dashcam → LKAS |
| 官方文档摘要 | `builtin_op_*`（`comma_docs_rag.py`） | CARS 表解读、集成/限制/安全、日志、car port、fork 合规 |

OpenPilotCP 在中文社区通常指 **Carrot2 / ajouatom 系 fork** 的调优方案，核心能力包括：

| Carrot/OpenPilotCP 常见能力 | 本 fork 对应 |
|------------------------------|-------------|
| 全速域横向（ALKA / MADS 类） | `dp_lat_alka` |
| 自适应滑行 ACM | `dp_lon_acm` |
| 加速/减速人格 AEM/APM | `dp_lon_aem`, `dp_lon_apm` |
| 变道辅助 LCA | `dp_lat_lca_speed`, `dp_lat_lca_auto_sec` |
| 横向偏移 | `dp_lat_offset_cm` |
| 路沿检测 | `dp_lat_road_edge_detection` |
| 外部雷达融合 | `dp_lon_ext_radar` |
| 品牌特调（丰田/本田/VAG） | `dp_toyota_*`, `dp_honda_*`, `dp_vag_*` |
| 模型选择 | `dp_dev_model_selected`, `dp_dev_model_list` |
| UI 显示模式 / 彩虹路径 | `dp_ui_*` |
| 上游 openpilot 开关 | `OpenpilotEnabledToggle`, `ExperimentalMode`, `LongitudinalPersonality` 等 |

技能文件 `ai/skills/dp-tuning/`、`dragonpilot-dashy/`、`carrot-legacy/`（CP 用户可选）、`vehicle-adaptation/` 已整理。内置知识库 `rag_seed` 含 CP→DP 横向/纵向/UI/适配摘要。

---

## 0.1 适配与调优落地（已完成）

- **P0** 内置 RAG：`builtin_vehicle_adaptation_guide`（标准适配纲要）+ CP 调优对照文档  
- **P1** `vehicle-adaptation` 技能（指纹→接口→参数→路试）；`carrot-legacy` 为 CP 参数迁移  
- **P2** `registry.json` v5 对齐 `requires_tools`  
- **P3** shell 白名单 `list_adaptation_drafts`、`grep_log_errors`；诊断技能含 PC↔车机命令对照

---

## 附录：外部参考（开发文档）

维护者查阅用，**不出现在**技能名、RAG 标题或 AI 面向用户的文案中。

| 主题 | 链接 |
|------|------|
| 社区车辆适配博文 | https://yuluoqc.xyz/2025/11/19/1054.html |
| OpenPilotCP 玩法仓库（master 分支，仓库名末尾 `-`） | https://github.com/yuluoqingcheng/OpenPilotCP_Yuluoqc_advanced_gameplay- |

---

## 1. 设计原则

### 1.1 安全分层（与 `ai/system/safety.py` 一致）

> **2026-07 更新**：默认 `ai_admin_mode=1` 开放模式。`reboot_device`/`shutdown_device` 在静止时可用；仅永久禁止直接控车。

| 层级 | 含义 | 开放模式 (admin=1) |
|------|------|---------------------|
| **L0 只读** | 读状态、路线、CAN、知识库 | ✅ 行驶中可用 |
| **L1 配置写** | 改 Param、Git 写、调参 | ✅ 行驶中可用（建议停车） |
| **L2 服务控制** | 重启 ui/manager、shell | ✅ 行驶中可用 |
| **L3 永久禁止** | 直接控车（转向/制动/油门） | ❌ |

**判定行驶中**：`enabled` / `vEgo > 0.1` / `started && ignition`（`dp_dev_go_off_road` 可强制视为 offroad）。

### 1.2 工具双开关模型（Web 设置 → `toolPrefs`）

每个工具两个维度：

1. **enabled** — 用户是否允许 AI 使用该工具  
2. **allow_while_driving** — 仅对 **L0 只读** 工具有意义；关闭则行驶中隐藏该工具

| 工具 | enabled 默认 | 行驶中 | 说明 |
|------|-------------|--------|------|
| `get_vehicle_state` | on | ✅ | 车辆 cereal 快照 |
| `read_params` | on | ✅ | 读 Param；**开放模式完整可读**（默认 `ai_admin_mode=1`） |
| `list_dp_settings` | on | ✅ | Dragonpilot 可调项 + 当前值 |
| `get_params_catalog` | on | ✅ | Param 安全分级 |
| `list_tune_presets` / `apply_tune_preset` | 读 on / 写 off | 写仅静止 | 预设调优 |
| `write_params` | on | ✅ | 开放模式可写（仅禁直接控车 Param）；legacy 需白名单 + 静止 |
| `cabana_*` | on | ✅ | CAN 分析 |
| `update_agent_memory` | on | ✅ | 跨会话记忆 |
| `manage_scheduled_task` | off | ✅ | 定时任务 CRUD |
| `run_shell` / `restart_*` | shell on | ❌ | safety 强制静止 |

### 1.3 Param 写权限分级（`ai/skills/params_catalog.json`）

| 等级 | AI 行为 |
|------|---------|
| `read_always` | 可读 |
| `write_offroad_ui` | 静止可写（UI/显示类） |
| `write_offroad_tune` | 静止可写（驾驶手感，需二次确认） |
| `write_offroad_dev` | 静止可写（开发者项，默认关闭工具） |
| `write_forbidden` | AI 永不可写 |
| `read_redacted` | 开放模式不脱敏；legacy 模式返回 `[redacted]` |

---

## 2. 当前能力 vs 缺口

### 已实现 ✅（2026-07-14 全量扩展）

- **~110+ LLM tools**（含 Git push、OTA、批量路线评分、pytest/scons、SSH 只读、Comma 云路线、视觉抽帧、PJ 布局、语义记忆等）
- **31 Skills**（registry v14；`requires_tools` 运行时过滤；含 `dp-brand-tesla`）
- **统一写参管道** `tune_write_pipeline`（快照 + 护照 + 回归；`write_params` / `confirm_pending` / `apply_tune_preset`）
- **调参护照 Web 面板** + `GET /api/ai/tune_passport`
- **多模型路由** `ai_model_fast` / `ai_model_deep` / `ai_model_routing`（`model_router.py`）；聊天输入区 **自动 / 快 / 深** 切换（`modelProfile`）
- **定时任务**：`daily_at` 触发 + 默认种子（停车复盘、参数漂移、Git fetch）
- **开机**：`sync_knowledge_from_docs` + RAG 自动 reindex
- **Web 开发面板**（设置 → 开发：hostEnvironment、PC 会话、报告/导出）
- **tools/ 覆盖矩阵**（车机可调用 vs PC 指引）见下表

| `tools/` 目录 | op 助手工具 | 备注 |
|---------------|-------------|------|
| `lib/logreader` + `log_time_series` | `read_qlog_segment`, `route_time_series`, `plotjuggler_data_summary` | 时序/片段 |
| `lib/route`, `framereader` | `analyze_route_summary`, `route_video_info`, `route_fetch_frame` | 增强摘要 + 抽帧 |
| `clip/run.py`, `lib/extract_audio.py` | `route_export_clip`, `route_extract_audio` | 导出至 `ai/data/exports/` |
| `ublox/` 日志 | `route_ublox_summary` | GPS 模块摘要 |
| `lib/comma_car_segments`, `auth`, `bootlog` | `search_car_segments`, `comma_auth_status`, `read_bootlog`, `car_porting_search_segments_by_can` | 需网络 |
| `cabana/dbc/generate_dbc_json` | `read_dbc_platform_map` + `read_dbc_file` | 平台→DBC |
| `car_porting/*` | `car_porting_*` 全套（含 `test_interfaces`, `steering_accuracy`） | 静止跑 pytest |
| `longitudinal_maneuvers`, `lateral_maneuvers` | `long_maneuver_report`, `lat_maneuver_report`, `maneuver_mode_status`, `maneuversd_status` | 只读 Param |
| `plotjuggler/juggle.py` | `plotjuggler_data_summary`, `list_plotjuggler_layouts` + `pc_launch_plotjuggler` | 不启 GUI |
| `jotpluggler/` | `list_jotpluggler_layouts` + `pc_launch_jotpluggler` + stream | 需 scons |
| `longitudinal_maneuvers/mpc_longitudinal_tuning_report.py` | `mpc_longitudinal_tuning_report` | 仿真 HTML |
| `replay/`, `sim/`, `camerastream/` | `pc_launch_replay*` / `pc_launch_replay_ui` / `pc_launch_camerastream` | **pc_only** |
| `replay/can_replay.py` | `route_can_stats`（只读分析） | **不向 Panda 注 CAN** |
| 路线分析 | `compare_route_signals`, `batch_route_summary`, `search_route_messages` | 多路线/消息检索 |
| `webcam/` | `get_webcam_dev_setup` | PC 开发指引 |
| `devsync/` | `get_devsync_hint`, `pc_devsync_status` | 指引 + 同步前只读体检 |
| CI 片段 | `openpilotci_segment_url` | 构建测试链接 |
| `cereal/` 实时 | `live_cereal_summary` | 进程/消息摘要 |
| 构建/进程 | `get_build_info`, `list_managed_processes` | git + managerState |
| `cabana/`（桌面 Qt） | Web Cabana + `pc_launch_cabana`（PC） | `get_host_environment` 自适应 |
| PC 数据回传 | `pc_capture_route_context` / `pc_get_tool_session` | 启动 GUI 时自动 `data_snapshot` |
| **故意不接** | `joystick/`, `can_replay` 真跑 | 控车 / 向 Panda 注 CAN |

**工作流**：`compare_routes_tune`、`batch_route_review`（Web 快捷卡片）

### 已实现 ✅（2026-07-09 全量增强）

- **27 个 LLM tools**（诊断、Dashy、RAG、路线、写确认等）
- **18 个 Skills**（含品牌条件加载、Web 开关 `ai_skills_enabled`）
- 记忆自动注入对话（**无独立 Web 记忆面板**）
- 通知中心（顶栏铃铛 + `ai_notifications.json` 队列）
- 写操作预览 + `pending_id` + Web 确认弹窗
- 工具双开关（enabled + 行驶中）
- 调优快捷卡片（ALKA / 纵向 / events / dp_settings）
- params_catalog 与 `dragonpilot/settings` 自动合并
- 轻量 RAG（`ai_rag_documents` 关键词检索）
- 定时任务触发器：interval / on_offroad / on_ignition / on_wifi
- 可选 LAN PIN（`ai_web_pin`）
- 会话同步车机（`ai_web_sessions`）

### 后续可选

| 任务 | 说明 |
|------|------|
| C3/C3X/C4 实机全量回归 | 新工具链、Cabana 回放/视频车机验证 |

### 已实现（2026-07-09 增强）

- 适配：`compare_fingerprint`、`suggest_signals_for_adaptation`、`get_adaptation_template`、`extract_can_ids_from_route`
- Cabana 弹窗：实时 CAN、离线回放、uPlot 曲线、`qcamera.ts` 视频同步、一键送入聊天
- 混合 RAG 检索 + settings/技能 digest + 启动自动 reindex
- 调优：`save_tune_snapshot` / `restore_tune_snapshot` / `rollback_last_tune` 预设；写参前自动快照
- 工作流模板（engage / 适配 / CP 迁移 / 调优 / 复盘）+ Web 快捷卡片
- 定时任务：`trip_review_offroad`、`reindex_rag_wifi`、`check_critical_events`
- SecOC：`lookup_secoc_tier`；路线：`suggest_tune_from_route`
- 适配包下载 `GET /api/ai/adaptation/{id}/bundle?download=1`

---

## 3. 可 AI 控制的操作清单（本 fork）

### 3.1 行驶中可读（建议默认开启）

- 车辆状态：`vEgo`, `enabled`, events, `carFingerprint`  
- 大部分 `dp_*` 与 openpilot toggles 的**当前值**  
- CAN 实时/回放（Cabana）  
- 系统负载：`uptime`, `free`, `df`（若开放 shell）  
- `dp_dev_last_log` 最近错误  

### 3.2 静止才可写（需 `write_params` + 用户开关）

- 全部 `dp_lat_*` / `dp_lon_*` / `dp_ui_*`（调优）  
- `LongitudinalPersonality`, `ExperimentalMode`, `IsLdwEnabled` 等  
- `dp_dev_model_selected` 模型切换  
- `ai_*` 自身配置  

### 3.3 建议 AI 永不可写

- `SecOCKey`, `GithubSshKeys`, `SshEnabled`, `AdbEnabled`  
- `AlphaLongitudinalEnabled`, `JoystickDebugMode`, `LongitudinalManeuverMode`  
- `OpenpilotEnabledToggle`（可由 AI **建议**，用户确认后写）  
- 任何直接控车接口（不存在 tool）  

### 3.4 不可控 / 硬禁止

- 方向盘/制动/油门执行器（无 tool，永久禁止）  
- `JoystickDebugMode`、`LongitudinalManeuverMode` 等直接控车 Param  

> **2026-07 更新**：`reboot_device` / `shutdown_device` 在静止 offroad 时可用；`git_push`、`ota_status`、`run_pytest` 等开发工具已实现，行驶中仍拦截写操作。

---

## 4. 实施状态

```
✅ Phase 1  调优工具 + Skills + params 策略
✅ Phase 2  记忆 Param 注入（无 Web 面板）
✅ Phase 3  定时任务 + 后台循环
⏸ Phase 4  外部 CP 仓库公开后补文档（可选）
```

---

## 5. 给 AI 的使用说明（摘要）

调优对话推荐流程：

1. **规划模式**：读状态 + 读相关 `dp_*` → 解释现状 → 给出步骤  
2. 用户确认后切 **执行模式**（车辆静止）  
3. 写 Param 前再次确认车型与 `openpilotLongitudinalControl` 等前置条件  
4. 写后 `read_params` 验证 → 提示重启 ui 或 reengage  

详细技能见 `ai/skills/*/SKILL.md`。
