# 新车适配

从零或半支持状态适配 **openpilot** 新车：指纹、DBC、CarState/CarController 草稿、PC 验证、合入主线。

> **完整方法论**：`ai/docs/VEHICLE_ADAPTATION_GUIDE.md`（必读）。**SecOC 车**先走技能 **`secoc-toyota`**，再谈 DBC。

## 先分类（避免白做工）

1. `get_vehicle_state` + `read_params` — 当前认车与指纹
2. `compare_fingerprint` — 与已知平台对比
3. `lookup_secoc_tier` — 丰田/雷克萨斯是否 SecOC（是则先 TSK）
4. `search_knowledge_base` — 社区是否已有该平台

| 类型 | 特征 | 路径 |
|------|------|------|
| 已支持 | CARS 表有、仅手感差 | `sp-tuning` / 品牌技能 |
| 无 SecOC，缺指纹 | 能 dashcam，指纹不对 | 本文「标准流程」 |
| SecOC | 日志 SECOC / 无控车 | **`secoc-toyota`** 先行 |
| 完全未知 | 无 DBC | 指纹 → CAN 采集 → 草稿 → 路试 |

## 标准流程（无 SecOC 或密钥已装）

### 1. 发现与草稿（车机 / Web）

1. `list_car_platforms` / `get_car_platform_bundle` — 对照相近平台
2. `list_dbcs` / `read_dbc_file` / `read_dbc_platform_map` — 读 opendbc
3. `extract_can_ids_from_route` / `search_local_routes_for_can` — 从路线找 CAN 模式
4. `analyze_can_id_pattern` / `suggest_signals_for_adaptation` — 辅助猜信号
5. `get_adaptation_template` → `save_adaptation_draft` — 保存草稿到 `adaptation_drafts/`
6. `list_adaptation_projects` / `export_adaptation_bundle` — 导出给 PC

### 2. PC 验证（`pc-dev-environment`）

1. `get_host_environment` — 确认 PC 工具链
2. `pc_devsync_run` — 同步 fork 与草稿
3. `car_porting_auto_fingerprint` / `car_porting_fingerprint_to_draft`
4. `car_porting_test_interfaces` / `car_porting_test_route` — pytest 接口
5. `car_porting_steering_accuracy` — 横向精度（封闭场地）
6. `pc_launch_cabana` / `live_can_capture` — 对照 CAN
7. `run_pytest` / `run_scons_build` — 回归构建

### 3. 合入与跟踪

1. `generate_adaptation_pr_draft` — PR 描述草稿
2. `git_commit`（PC）— 人 review 后提交
3. `search_car_segments` / `car_porting_search_segments_by_can` — 找社区片段

## Cabana / 路线辅助

- `cabana_analyze` / `cabana_explain_signal` — 有 DBC 时解释信号
- `route_can_stats` / `search_route_messages` — 路线级 CAN 统计
- `analyze_route_summary` / `route_event_timeline` — 路试复盘

## 安全与边界

- 首次控车必须在 **封闭场地、低速**；AI 输出仅为草稿
- **不向 Panda 注入 CAN**（无 `can_replay` 真跑工具）
- Lite C3：`get_sp_device_hw` 确认无 DMS/功放预期

## 相关技能

- `secoc-toyota` — 丰田 SecOC 密钥
- `engage-troubleshooting` — 无法开启 OP
- `pc-dev-environment` — Replay / Cabana / devsync
- `car-platform` — 手动选 CarPlatformBundle
