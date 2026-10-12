# cp → sp 功能借鉴分析（2026-09-30，2026-10-12 复核）

> 只调研、未改码。本文件为决策输入，供分析后确定移植范围。
> 基准：cp = `E:/cp`（CarrotPilot，分支 carrot-wip）；sp = `E:/sp`（本 fork，分支 test）。
>
> **2026-10-12 复核**：§4 与 §7.1 的数字已用当前仓库状态重算（原数字来自 09-30，已失效）。
> 复核报告与逐项 grep 记录见 `artifacts/cp_sp_overall_gap_2026-10-12.md`。
> 总体结论更新为：**文件/端口层已基本追平，唯一真·未移植大项只剩 `cluster/`（产品决策）。**

---

## 0. 结论速览

| # | 主题 | 结论 | 工作量 |
|---|---|---|---|
| 1 | HUD（native onroad） | **不做**。cp 1614 行 vs sp 146+347 行，sp 更简洁；尊重现有设计 | 0 |
| 2 | 大模型 / eGPU 全链路 | **不建议照搬**。sp 已有大/小模型双 runner + 模型下载管理；cp 的 big_model+jetlink 是 USB eGPU 专用管线，sp 无对应硬件支持层 | 评估后单独立项 |
| 3 | path/lanes/radar/标线 overlay | **部分可做**：`road_markings.py`（163 行，纯几何）可低风险移植；radar overlay 建议做；path/lanes 的「Carrot 专属绘制」**建议在 webui 简洁行车画面实现**而非 native | 中 |
| 4 | 调参项对齐 | **数量已反超**（sp 340 vs cp 184）。cp 独有 **30 项**（2026-10-12 重算，原 32）：4 项 sp 已引用应补键、4 项保持退役、26 项跳过（消费者模块不在 sp）。**无 UI 入口 48 项且 0 死旋钮**（原报 84） | 小 |
| 5 | IMU 自动校准 | **已完整**。无重大缺口，仅建议补可观测性 | 小 |
| 6 | `radar/` + `radar_motion/` | **已移植**（2026-10-12 更正）。整包在 sp 且被 `radard_dpath`/`carrot_functions`/radar tools 引用。注意 cp 自己的 radar 树也是离线工具链，**两侧均未接行车 radard**，属对等 | 0 |
| 7 | `realtime/` | **已移植**（2026-10-12 更正）。`compact_state`(+C++/pyx) 接入 7000；raw 传输改装为 `server/services/raw_*.py` + `camera_relay.py` | 0 |
| 8 | `cluster/` | **产品决策：不做**。36 py / 33,142 行独立外接屏 App，需 C3X 副屏硬件 | — |

---

## 1. HUD（native）— 结论：不做

用户明确「sunnypilot 的 UI 比较简洁简单，cp 的太乱了」。

代码证据：
- cp `selfdrive/ui/onroad/hud_renderer.py` = **1614 行**：Carrot 车速面板、信号灯、TPMS、设备状态、日期时间、跟车档、驾驶模式、速度限制、eGPU 徽章
- sp `selfdrive/ui/sunnypilot/onroad/hud_renderer.py` = **146 行** + `speed_limit.py`（347 行，独立限速渲染）

sp 已把「限速」等核心信息拆成独立组件（`speed_limit.py`、`speed_renderer.py`、`chevron_metrics.py`），体系更干净。**维持现状，不移植 cp 的 HUD。**

---

## 2. 大模型 / eGPU 全链路 — 结论：不建议照搬

**sp 现状（已具备）**：
- `selfdrive/modeld/models/`：`driving_supercombo.onnx`（小）+ `big_driving_supercombo.onnx`（大）+ dmonitoring —— 大/小模型**都已在仓内**
- `sunnypilot/modeld_v2/`：大模型编译/消息管线（`compile_modeld.py`、`fill_model_msg.py`、`meta_20hz.py`）
- `sunnypilot/models/`：`manager.py` + `fetcher.py` + `runners/` —— 模型下载/切换/状态上报，`ModelManager_DownloadRef` 进度镜像
- eGPU 面板：`/api/egpu/model` 已实现（读 `deviceState.chestnutPresent` + `chestnutState`）

**cp 特有管线**：`big_model.py`（manifest 下载 + 校验）、`precompiled_*`（预编译 runner/worker）、`jetlink/`（USB gadget 主机 + Jetlink 客户端）、`system/hardware/usbgpu.py`（USB GPU 探测）。

**关键差异**：cp 的整条链路围绕 **USB 外接 eGPU（Jetlink）** 构建，需要对应硬件与内核支持。sp 没有 `usbgpu.py` 硬件抽象、没有 `jetlinkd` 进程，且 eGPU 功能已通过 `deviceState/chestnutState` 上报（面板工作正常）。

**建议**：
- **不移植 jetlink/usbgpu/precompiled 管线**（无硬件、收益未知）
- **可选小项**：`big_model.py` 的 manifest 校验思路（sha256 + 大小限制 + 断点下载）可借鉴进 sp 自己的 `models/fetcher.py`，但 sp fetcher 已有下载管理，**大概率不缺**
- 结论：**这条先不动**，除非后续确定要支持 USB eGPU 硬件

---

## 3. path / lanes / radar / 道路标线 overlay — 部分可做

### 3.1 现状

**cp**（`selfdrive/ui/onroad/model_renderer.py`，1300+ 行）：
- `_draw_carrot_overlays(sm)`：path / lanes / blindspot / radar 四层，带 `timing` 诊断
- 私有绘制工具：三角化、四边填充、多边形描边、文本盒（约 200 行纯算法）
- `road_markings.py`（**163 行，纯 numpy 几何**）：`lane_dash_segments`（车道虚线分段）、`project_lane_segments`（批量投影）

**sp**：
- native：`sunnypilot/onroad/rainbow_path.py`（79 行，彩虹渐变）、`blind_spot_indicators.py`（52 行，图标式盲点）、`model_renderer.py`（32 行）—— 已有盲点图标 + 彩虹路径，但**无车道虚线、无 radar overlay、无 Carrot 风格 path 多边形**
- webui：`model_webgl.js`（635 行，WebGL2：lanes / path ribbon / leads + 彩虹）、`road_lite.js`（2081 行，`drawLaneLines`）、`onroad.js`（413 行）—— **webui 已具备 lane/path 基础渲染**

### 3.2 推荐方案（按「简洁」原则取舍）

| 项 | 是否做 | 落点 | 理由 |
|---|---|---|---|
| `road_markings.py` 车道虚线几何 | ✅ 做 | **webui `model_webgl.js`** 移植投影逻辑 | 163 行纯数学，零依赖，视觉提升明显，webui 已有 canvas 管线 |
| radar overlay（雷达目标点/占用） | ⚠️ 评估 | webui | sp 用 stock radard；需确认 `radarState` 字段可经 `raw_multiplex` 拿到 |
| Carrot 风格 path 多边形（渐变填充） | ⚠️ 部分 | webui | webui 已有 rainbowPath 基础，加「路径终点/模式着色」开关即可，**不做 cp 全套** |
| blindspot overlay | ❌ 不做 | — | sp 已有图标式盲点（native + 大概率 webui），足够 |
| 车道线虚线（native） | ❌ 不做 | — | native 保持简洁，webui 简洁行车画面才是落点 |

**核心思路**：用户要「简洁」，cp 的 overlay 全部集中在 native 会污染现有简洁 HUD；而 **webui 的 `road_lite.js` / `model_webgl.js` 本来就是「简洁行车画面」的载体**，把车道虚线和雷达信息加在这里性价比最高。

---

## 4. 调参项对齐 — 数字已于 2026-10-12 重算

> ⚠️ **本节数据在 2026-10-12 全面重算**。原数字（cp 186 / sp 已注册 154 / 未注册 32 /
> 无 UI 入口 84）取自 2026-09-30，此后 sp 的目录已扩到 340 项，多个数字已失效。
> 重算方法见本报告末尾的「复核方法」，可复现。

### 4.1 数据（2026-10-12 实测）

```
cp carrot_settings.json:        184 项参数
sp carrot_settings_sp.json:     340 项参数         ← 已远超 cp
sp params_keys.h 中 carrot 参数: 239 项
cp 有而 sp 无（未注册）:          30 项  ← 见 4.2
native UI 暴露:                  108 项
UI 总可达（native + webui 面板）:  297 项
carrot 参数但无 UI 入口:           48 项  ← 见 4.3（原报告 84 项）
其中属于「用户可调却无入口」:        0 项  ← 其余 48 项是运行时/状态参数，本就不该有旋钮
```

关键变化：**参数数量已经反超**（340 vs 184）。差距从「数量不足」变成了「少数 cp 专属键」。

### 4.2 未注册的 30 项 —— 已逐项分类，不必全补

| 类别 | 键 | 判定 |
|---|---|---|
| **A. sp 内已有引用**（键未注册但代码在别处读） | `CanfdHDA2`、`HyundaiCameraSCC`、`DriverMonitoringEnabled`、`DriverMonitoringMode` | 出现在 `carrot/server/features/intro/presets.py`（引导预置）与 `server/services/params.py`（备份排除 / 在线校验）。**建议补注册**，否则 `Params.get` 无默认值 |
| **B. 已明确退役** | `AChangeCostStarting`、`SpeedTFFactor`、`StoppingAccel`、（`DynamicTFollow`） | cp 自身也已删除；sp 有 `TestRetiredParamsStayRetired`（`tests/test_carrot_man.py:1866`）断言其**不得回归**。`AChangeCostStarting`/`SpeedTFFactor` 被 sp 自己的 `LongitudinalMpcTuningAChangeCost` / `EnableSpeedTF` 取代，`StoppingAccel` 并入 `LongitudinalMpcTuningStopDistance`。**保持退役** |
| **C. cp 专属硬件 / 车型 / 测试项** | `CanfdDebug`、`CruiseButtonTest1/2/3`、`CustomSteerDelta{Up,Down,UpLC,DownLC}`、`CustomSteerMax`、`HyundaiCanfdClusterDirectTx`、`IsLdwsCar`、`HardwareC3xLite`、`MaxAngleFrames`、`MaxTimeOffroadMin`、`CarrotTireTrajectory`、`HDPuse`、`VEgoStopping` | sp 内无读取方，消费逻辑位于 cp 的 opendbc 接入层（本 fork 未携带）。**跳过** |
| **D. 有真实消费方，但消费者在 sp 不存在的模块** | `AdjustLaneOffset`、`LaneChangeBsd`、`CruiseCoastingPercent`、`CarrotCruiseDecel`、`CarrotCruiseAtcDecel`、`DisableMinSteerSpeed` | 见 4.2.1 —— 这 6 项不是「通用调参」，但**移植成本等于移植整个消费模块**，故同样跳过 |

原判断「大多是 cp 特有硬件/车型能力或测试项」**基本正确**。30 项里只有 A 类 4 项值得补键，
B 类保持退役，C/D 类共 26 项跳过。

#### 4.2.1 D 类 6 项：消费者全部落在 sp 没有的模块

最初怀疑这 6 项是「通用调参」，实测**每一项在 cp 都有真实消费方，但消费者都在 sp 不存在的文件里**：

| 参数 | cp 的消费者 | sp 对应模块 | 判定 |
|---|---|---|---|
| `AdjustLaneOffset` | `selfdrive/controls/lib/lane_planner_2.py:161` → `self.adjustLaneOffset` | **`lane_planner_2.py` 不存在**（sp 无 cp 横向栈） | 跳过。注：sp 的等价物是 `PathOffset`（已注册、已接 UI），语义为「车道偏移左右修正」，与此参数重叠 |
| `LaneChangeBsd` | `selfdrive/controls/lib/desire_helper.py:77` → `self.laneChangeBsd` | `desire_helper.py` **存在**，但无 `laneChangeBsd` 字段；sp 该文件走 `AutoLaneChangeController`（另一套设计） | 跳过。sp 的 BSD 逻辑在 `carrot` 侧（`DisableBlindSpot`/`DynamicBlindRange` 等已注册） |
| `CruiseCoastingPercent` | `longitudinal_planner.py:128` → `coasting_percent(...)` | sp 的 `longitudinal_planner.py` **无 coasting 分支**，只有 stock 的 `get_coast_accel`（物理滑行，非滑行的巡航百分比） | 跳过。属功能缺失而非参数缺失；要做得先移植该滑行策略 |
| `CarrotCruiseDecel` | `opendbc/car/hyundai/carcontroller.py:860` | **韩系车型专属**（sp `TOYOTA_WILDLANDER_PHEV` 无关） | 跳过 |
| `CarrotCruiseAtcDecel` | `opendbc/car/hyundai/carcontroller.py:861` | 同上，韩系专属 | 跳过 |
| `DisableMinSteerSpeed` | `opendbc/car/interfaces.py:376` | sp 的 `interfaces.py` 无此分支 | 跳过。属 ATC/转向低速逻辑，随 opendbc 层一起 |

**结论：确认 6 项全部跳过**——没有一项是「补个键就能用」的通用调参。这一节的判断与
原 §4.2 的「先审计后补」一致，但理由更精确：不是「cp 硬件专属」，而是**消费者模块不在 sp**。

逐项 grep 记录见 `artifacts/cp_sp_overall_gap_2026-10-12.md` §3。

### 4.3 无 UI 入口的 48 项 —— 0 项是坏旋钮

原报告称 84 项「只差 UI 入口，价值高、风险低」，**这个判断需要修正**。实测 48 项里：

- **绝大多数是运行时/状态参数**，本就不应该有用户旋钮：`CarrotNaviAppStatus`、`CarrotVisionActive`、
  `EnableRadarTracksResult`、`CarrotException`、`CarrotNavFeaturesSeeded`、
  `CarrotStopDistanceMigrated` / `CarrotUdpPortMigrated`（一次性迁移标记）、`RecordFrontLock`、
  `CarrotManUdpPort`、`CarrotSourceTimeoutMs` 等。
- **看起来像用户可调、实际已另有入口**：`LongitudinalMpcTuning*`（11 项）有专门的设置页
  `selfdrive/ui/sunnypilot/layouts/settings/cruise_sub_layouts/longitudinal_mpc_tuning.py`，
  只是参数审计脚本此前不认 `_read_tuning_float()` 间接读取而误报（2026-10-12 已修复该脚本）。
- 真正「用户可调但无专页」的残余候选很少：`AutoRoadSpeedAdjust`、`AutoSpeedUptoRoadSpeedLimit`、
  `JLeadFactor3`、`LeadForecast`、`LaneChangeSmoothing`、`PaddleMode`、`SoftHoldOnCancel`、
  `UseLaneLineSpeed`、`TrafficLightNavCautionOnly`。这些是否要补入口是**产品取舍**，不是缺陷。

**结论：不存在「死旋钮」。** 参数审计（`carrot/tests/audit_param_consistency.py`）当前
PASSED，84 条「无读取方」全部落在已声明未移植族内，0 条待调查。

### 4.4 推荐做法

1. **A 类 4 项补注册**（`params_keys.h` 加键，默认值与 cp 对齐），其余 26 项不动。
2. 无 UI 入口的 48 项**不做批量补**——原「84 项只差 UI」的前提已不成立。
3. 若要给 4.3 末尾的残余候选补入口，逐个人工判断，并同步 `sp_param_labels.py` 与各 `.po`。
4. 任何参数改动后跑：`audit_param_consistency.py` + `carrot_tuning_render_smoke.py` + `test_translations`。

---

## 5. IMU 自动校准 — 已完整，无重大缺口

### 5.1 现状盘点（代码证据）

| 环节 | 实现 | 状态 |
|---|---|---|
| 算法 | `locationd/imu_calibrationd.py`：静态相位（重力/陀螺零偏 → pitch/roll）+ 动态相位（陀螺积分 vs 相机里程计 → yaw），完整状态机 `CalibrationState`（7 态） | ✅ |
| 门控 | `process_config.py:110-113`：`imu_calibration_enabled`/`disabled` 二选一（`ImuCalibrationEnabled`） | ✅ |
| 持久化 | `ImuCalibrationMatrix`（3×3 float32, 36 字节）+ `ImuCalibrationStatus`（JSON） | ✅ |
| 消息 | cereal `ImuCalibrationSP`（`custom.capnp:811`） | ✅ |
| 消费 | `locationd/helpers.py`（`calib_from_device` 装配，含 det 校验）；`locationd.py` 读 `ImuCalibrationMatrix` | ✅ |
| UI | native big UI + mici UI 双份校准页（实时角度预览、进度、重置）；webui `panels.js` 有 `imu_calibration` 分支 + `ensureImuCalibrationBlock` | ✅ |
| 测试 | `locationd/test/test_imu_calibrationd.py` = 425 行 **22 个用例**（静态旋转各轴、斜坡拒绝、动态中断续接、超时、矩阵往返、大 yaw 跳变拒绝、reset） | ✅ |
| 错误处理 | 8 类 `CalibrationError`（斜坡过陡/非静止/相机里程计不可靠/超时等） | ✅ |

### 5.2 建议补全（小，可选）

1. **可观测性**：校准期间在 webui 设置页显示实时 `yaw_std` / `valid_ratio`（native 已有，webui 分支较浅）——低成本
2. **文档**：`imu_calibrationd.py` 模块 docstring 已很完整，可在 `docs/` 补一页「何时需要 / 流程」给用户
3. 阈值是否需要可调：当前阈值硬编码（`STATIC_MAX_SLOPE_ANGLE` 等），不建议参数化（安全底线，保持固定）

**结论：功能层面已开发完整，无需返工。**

---

## 6. 建议的执行顺序（待确认后开工）

1. **P0**：调参项 UI 补全（84 项已注册项 → 分组暴露）——纯 UI，风险低，收益明确
2. **P0**：`road_markings.py` 车道虚线 → webui `model_webgl.js`——163 行纯几何，视觉提升大
3. **P1**：未注册 32 项审计 → 只补有消费逻辑的键
4. **P2**：radar overlay（webui）评估
5. **P2**：IMU 校准 webui 可观测性小增强
6. **不做**：native HUD 移植、jetlink/usbgpu 大模型管线、blindspot 重做

---

*查证时间：2026-09-30；所有结论均有文件路径级代码证据。*

---

## 7. 复核与更新（2026-10-11 首版 / **2026-10-12 更正**）

> ⚠️ **2026-10-11 的首版本节判断有误**：当时用的是「sp 101 文件」的旧快照，得出
> 「cp 独有 850」并据此认为多个子系统未移植。实际 sp `carrot/` 当时已有 297 文件，
> 相关子系统**早已移植并接入**。下表为 2026-10-12 用当前仓库重做的结论。

对 `E:/cp/openpilot/selfdrive/carrot` 与 `E:/sp/openpilot/sunnypilot/carrot` 做文件级 diff
（只计 `*.py` / `*.pyx` / `*.json` / `*.md`）：

```
cp 331 文件 | sp 297 文件 | cp 独有 115
```

**cp 独有 115 项的去向：**

| cp 独有 | 数量 | 状态 |
|---|---:|---|
| `tests/`（cp 自有 pytest 套件） | 51 | 不移植；sp 有自己的 `unittest` 套件 |
| `cluster/` | 40 | **产品决策：不做**（见 §8） |
| `realtime/` raw 传输 | 6 | **已移植**（改装进 `server/services/raw_*.py` + `camera_relay.py`） |
| `server/` 片段 | 5 | 4 个是测试；`features/egpu_model.py` 有意不取 |
| `bluetooth/tests/` | 2 | 有意不移植（见 `carrot/README.md`） |
| `xiaoge/README.md` | 1 | 文档，可选 |
| 根级启动器 / 工具 | 11 | 全部已处置，见下 |

**根级 11 项逐项判定：**

| 文件 | 行数 | 判定 |
|---|---:|---|
| `cruise_gap.py` | 15 | **已移植** → `sunnypilot/selfdrive/car/cruise_helpers.py`（3 helper 同名同义，有测试） |
| `driving_mode.py` | 108 | **已移植** → 并入 `carrot/carrot_functions.py` |
| `radar_lead_simulator.py`、`radar_lead_validation_review.py`、`radar_lead_video_review.py`、`validate_radar_lead_model.py` | 15 each | 都是 15 行 shim，`raise SystemExit(main())` 指向 `radar/tools/`（**该工具链已移植**，commit `adfa4d806`）。不拷 shim 不丢行为 |
| `cluster_run.py`、`cluster_autorun.py`、`cluster_replay_usb.py` | — | 属 `cluster/`，不做 |
| `cweb_push.py` | 310 | 有意不移植（XOR 混淆的第三方 phone-home，隐私红线） |

**结论：除 `cluster/` 外，文件层没有遗漏。**

### 7.1 ~~`radar_motion/` 是唯一尚未决策的大项~~ → **已移植，见下**

原判断（sp 只取了 `lane_change_gap.py` 1 个文件、cut-in 全无）**已失效**。实测：

- `openpilot/sunnypilot/carrot/radar_motion/` = **14 文件 / 12,158 行**（cp 为 11,493 行，
  sp 还多出 `cutin_alert.py`、`cutin_helpers.py`），含 `controller.py`（`DPathRadarController`）、
  `trajectory_cutin` / `trajectory_cutout`、`occupancy_v2` / `occupancy_v3`、`predictor`、
  `primary`、`lead_selection`、`lead_dynamics`、`timing`、`coordinates`、`native`，以及
  `_motion_native.pyx` + `SConscript`（Cython 加速也在）。
- 被 `radar/radard_dpath.py`、`carrot_functions.py`、`radar/tools/radar_validation_replay.py`
  等引用——**已接入**，不是死代码。
- `radar/` 整树（15,839 行）同样在 sp：`radard_dpath`、`radarcan`、`can_batch`、`lateral`、
  `route_replay/`、`tools/`。

**唯一需要注意的定性事实**：cp 自己的 `radar/` 树**也是离线工具链，没有接进行车 `radard`**
（两个仓库里 `carrot/radar/` 之外都没有导入 `radard_dpath`）。所以这不是 sp 的差距，
而是一个仍然开放的产品问题：**要不要把行车雷达路径切换成 `DPathRadarController`**。

### 7.2 `realtime/` —— 同样已移植

- `compact_state`（`compact_state.py` + `compact_state_native.cc/.h` + `compact_state_pyx.pyx`）
  逐字移植，并已接入 7000 的 `/ws/compact_state` 与 dashcam replay。
- cp 的 raw 传输（`raw_protocol.py` / `raw_runner.py` / `raw_services.py` / `transports/`）
  **未按文件拷贝，而是并入** `server/services/`：`raw_protocol.py`、`raw_services.py`、
  `raw_relay.py`、`camera_relay.py`（合计 949 行）。原因：本 fork 里唯一消费者是 7000 面板，
  cluster 不移植，没有第二个消费者需要那个独立包。`/ws/raw_multiplex`、`/ws/raw/{service}`、
  `/ws/compact_state` 均已实现。

### 7.3 仍然成立：不要碰的三样

1. `cweb_push.py` —— 第三方 phone-home，隐私红线（见 §3 与 `carrot/README.md`）
2. `recovery/server.py` + `terminal.py` + `support_terminal` —— 6999 无鉴权 PTY shell
   （sp 已移植但**默认关闭**，且第三方目的地清空）
3. cp 的 `kmap/` —— 韩国 Kakao 地图、作者个人 key、默认首尔；sp 已用 `web/map/` 自研替代

---

## 8. `cluster/` —— 记录为产品决策：不移植（2026-10-12）

cp 的 `cluster/` 是 **36 个 py / 33,142 行**的完整独立应用：C3X 手柄 + USB 外接屏 +
H.264 管线 + 场景渲染器 + 回放工具 + `main.py`。它与驾驶链解耦，需要外接副屏硬件才有意义。

sp 现有的 `cluster_view/`（5 文件 / 1,151 行 = `cluster_config` / `cluster_display` /
`cluster_overlay` / `cluster_overlay_renderer`）是同一套 HUD 的**轻量子集**，方向一致。

**决策：不移植，除非确定要支持 C3X 外接副屏硬件。**

---

## 9. 复核方法（可复现）

```bash
# 文件层差集（cp 相对 sp）
cd E:/cp/openpilot/selfdrive/carrot && \
  find . \( -name '*.py' -o -name '*.pyx' -o -name '*.json' -o -name '*.md' \) | sed 's|^\./||' | sort > /tmp/cp.txt
cd E:/sp/openpilot/sunnypilot/carrot && \
  find . \( -name '*.py' -o -name '*.pyx' -o -name '*.json' -o -name '*.md' \) | sed 's|^\./||' | sort > /tmp/sp.txt
comm -23 /tmp/cp.txt /tmp/sp.txt          # 115 项

# 参数差集
python -c "import json;a={i['name'] for i in json.load(open('openpilot/sunnypilot/carrot_settings.json'))['params']};\
b={i['name'] for i in json.load(open('openpilot/sunnypilot/carrot_settings_sp.json'))['params']};print(len(a),len(b),sorted(a-b))"

# 参数一致性审计（UI 覆盖 / 无读取方 / 默认值三表对齐）
python openpilot/sunnypilot/carrot/tests/audit_param_consistency.py
```

⚠️ 审计脚本会遍历整仓，**Windows 上直接跑会卡住**；用 `importlib` 加载后 monkeypatch
`os.walk` 跳过 `webui/` 与 `tinygrad_repo/` 即可（2026-10-12 起脚本内部已做单次索引，
2.7 秒可完成）。

**风险**：中低。唯一要小心的是它消费的是「dPath 历史」这类输入，接错输入会得到
「看起来合理但语义不对」的输出 —— 接的时候要对着 cp 的 `radard_dpath.py` 调用点核对字段含义，
而不是照搬参数。

### 7.2 既有结论复核（未变）

第 1–5 节的结论（HUD 不做 / eGPU 管线不照搬 / overlay 部分做且落 webui / 调参项应补 UI 入口 /
IMU 已完整）本次复核**仍然成立**，无新增反证。第 4 节的 32 项未注册键审计仍待执行。

### 7.3 不要碰的三样（复述，因为它们是「盲抄必错」的典型）

1. **`cweb_push.py`** —— 每 5 s 把设备 IP POST 到第三方中继（URL 以 XOR 混淆内嵌）。产品/隐私决策，不是移植任务。
2. **`recovery/server.py` + `features/terminal.py` + `support_terminal`** —— 7000/6999 上**无鉴权**的远程 shell；cp 与 sp 的 server 都没有 auth。补它等于开一个「同网段任意设备可在控车计算机上执行命令」的口子。
3. **`realtime/compact_state`（C++/Cython）** —— 字节打包 HUD 协议，sp 无对应 cereal 消息，猜一个会给出解码成错误数字的流。
