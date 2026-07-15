# Engage 失败 / 无法开启 openpilot 分诊

当用户说「点不了 OP」「无法 engage」「一直 dashcam」「未识别车辆」时，**按顺序**分诊，不要跳步。

## 第一步：读现状

同时调用（行驶中也可）：

- `get_vehicle_state`
- `read_onroad_events`
- `read_params`：`CarParams`, `CarParamsCache`, `Version`, `IsOnroad`（按需）

可选：`trip_review` 生成结构化报告。

## 决策树

```
有 startupNoSecOcKey？
  └─ 是 → SecOC 分支（启用 secoc-toyota 技能话术）
         调用 `get_tsk_manager_status` + `lookup_secoc_tier`
         按 install_options 选路径：RAV4 Prime/Sienna → `tsk_extract_key`；
         用户已有 key → 引导 `/?settings=secoc` 手动安装或 `tsk_install_secoc_key`；
         否则 CAN→DF→`tsk_find_and_install_key`，或 `tsk_run_pipeline(confirm=true)`
         黑屏：`tsk_restart_pandad` 仅终止本机 pandad（C3→pandad_tici，C3X/C4→pandad）
         禁止在聊天中粘贴完整密钥

有 carUnrecognized / startupNoCar？
  └─ 是 → 指纹/适配分支（vehicle-adaptation）
         1. 读 fingerprint、brand（read_params / get_vehicle_state）
         2. 指纹是否正确：五类 CAN 是否齐全（车速/转角/制动/油门/档位）→ analyze_can_id_pattern
         3. CAN 连接：harness、panda
         4. DBC：list_dbcs；先查是否 🔴 SecOC（密钥优先于 DBC）
         5. 非 SecOC：vehicle-adaptation 全流程 + Cabana 抓 CAN

有 startupNoControl / dashcamMode / startupMaster？
  └─ 是 → 区分：
         - dashcamMode：可能正常或未选车型
         - startupNoControl：车型在表但无横向/纵向控制权限
         - 读 CarParams.openpilotLongitudinalControl、指纹是否在 CARS.md
         - `search_knowledge_base`：`builtin_op_cars_support`（ACC 列 openpilot / available / Stock / dashcam）

有 steerUnavailable / steerTempUnavailable / invalidLkasSetting？
  └─ 是 → 横向/LKAS 分支
         - 本田：LOW_SPEED_LOCKOUT、STEER_STATUS（vehicle-adaptation 锁止节）
         - VAG：`dp_vag_avoid_eps_lockout`
         - 丰田：先排除 SecOC，再查 PCM lockout、TSS 设置

有 camera / calibration / modeld 相关事件？
  └─ 是 → `grep_log` + `read_manager_log`，建议检查摄像头遮挡、校准、温度

否则
  └─ `grep_log` 最近错误 + `snapshot_tune_state` + 询问用户具体操作步骤
```

## 常见事件 → 动作

| 事件名 | 优先动作 |
|--------|----------|
| `startupNoSecOcKey` | optskug 文档 + Dashy SecOCKey（用户自填） |
| `carUnrecognized` | 指纹适配；SecOC 车先密钥 |
| `startupNoControl` | 查 CARS.md 支持级别、stock lon、实验模式 |
| `dashcamMode` | 确认是否预期；查 CP.secOc / 指纹 |
| `steerUnavailable` | 品牌锁止 / SecOC / 扭矩 |
| `invalidLkasSetting` | 车内 LKAS 开关 |
| `commIssue` / `deviceFalling` | harness、panda、USB 线 |

## 硬件快速检查（引导用户）

- Comma 设备灯态、过热
- Harness 型号是否匹配（丰田 SecOC 常用 Harness A）
- OBD-C 线是否为官方/USB3.1
- `run_shell`：`ip_addr`（仅静止）看网络可选

## 写操作边界

- 分诊阶段**只读**；调参建议用 `diff_params` 预览。
- `write_params` / 预设仅静止 + 用户确认。
- 永不建议公开道路首次测试转向。

## 相关技能

- `secoc-toyota` — SecOC 专章
- `vehicle-adaptation` — DBC/指纹草稿
- `onroad-events` — 事件严重级别
- `dp-brand-*` — 品牌调优项
