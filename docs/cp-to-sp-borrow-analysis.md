# cp → sp 功能借鉴分析（2026-09-30）

> 只调研、未改码。本文件为决策输入，供分析后确定移植范围。
> 基准：cp = `E:/cp`（CarrotPilot，分支 carrot-wip）；sp = `E:/sp`（本 fork，分支 test）。

---

## 0. 结论速览

| # | 主题 | 结论 | 工作量 |
|---|---|---|---|
| 1 | HUD（native onroad） | **不做**。cp 1614 行 vs sp 180 行，sp 更简洁；尊重现有设计 | 0 |
| 2 | 大模型 / eGPU 全链路 | **不建议照搬**。sp 已有大/小模型双 runner + 模型下载管理；cp 的 big_model+jetlink 是 USB eGPU 专用管线，sp 无对应硬件支持层 | 评估后单独立项 |
| 3 | path/lanes/radar/标线 overlay | **部分可做**：`road_markings.py`（163 行，纯几何）可低风险移植；radar overlay 建议做；path/lanes 的「Carrot 专属绘制」**建议在 webui 简洁行车画面实现**而非 native | 中 |
| 4 | 调参项 186 项对齐 | **应做**。cp 186 项 → sp 已注册 154、**未注册 32**、已注册但无 UI 入口 84 | 中 |
| 5 | IMU 自动校准 | **已完整**。无重大缺口，仅建议补可观测性 | 小 |

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

## 4. 调参项 186 项对齐 — 应做

### 4.1 数据（精确对比结果）

```
cp carrot_settings.json:  186 项参数
sp params_keys.h 已注册:   154 项（cp∩sp）
sp 未注册:                  32 项  ← 需要补
sp 已注册但无 UI 入口:       84 项  ← 需要补 UI 暴露（当前 UI 只暴露 108）
```

### 4.2 未注册的 32 项（需先补 `params_keys.h` + 消费逻辑）

按类别分组：

| 类别 | 键 |
|---|---|
| 转向/力矩 | `CustomSteerMax`、`CustomSteerDeltaUp/Down/UpLC/DownLC`、`DisableMinSteerSpeed`、`MaxAngleFrames` |
| 纵向/巡航 | `AChangeCostStarting`、`CarrotCruiseDecel`、`CarrotCruiseAtcDecel`、`CruiseCoastingPercent`、`StoppingAccel`、`VEgoStopping`、`SpeedTFFactor` |
| 车道/变道 | `AdjustLaneOffset`、`LaneChangeBsd`、`CarrotTireTrajectory` |
| 视觉/雷达 | `CarrotVisionEnabled`、`EnableCornerRadar`、`RadarTrackFlip`、`DriverMonitoringEnabled/Mode` |
| 车辆/硬件 | `CanfdDebug`、`CanfdHDA2`、`HDPuse`、`HardwareC3xLite`、`HyundaiCameraSCC`、`IsLdwsCar` |
| 测试/杂项 | `CruiseButtonTest1/2/3`、`MaxTimeOffroadMin` |

⚠️ 关键判断：**这 32 项大多是 cp 特有的硬件/车型能力（CanfdHDA2、HyundaiCameraSCC、HDPuse、C3xLite）或测试项（CruiseButtonTest*）**。**不是每一项都该无脑补**——建议先逐项确认 sp 消费逻辑是否存在，只补「sp 确实会用」的键，纯 cp 硬件相关的可以跳过。

### 4.3 已注册但无 UI 入口的 84 项

已注册（params_keys.h 有）但 `carrot_tuning_items.py` 没暴露，**只差 UI 入口**，价值高、风险低：

重点子集（用户可感知）：
- 横向力矩：`LateralTorqueCustom/AccelFactor/Friction/KpV/KiV/Kf/Kd`、`LatMpcPathCost/MotionCost/AccelCost/JerkCost/SteeringRateCost/InputOffset`、`CustomSR`、`SteerRatioRate`、`SteerActuatorDelay`
- 纵向：`LongTuningKpV/KiV/Kf`、`LongActuatorDelay`、`CruiseMaxVals0-6`、`LeadAccelResponseTF1-4`
- 显示：`ShowTpms`、`ShowDateTime`、`ShowDeviceState`、`ShowRadarInfo`、`ShowLaneInfo`、`ShowPathEnd`、`ShowPathMode/Color*`、`ShowCustomBrightness`、`ShowModelView`
- 音/提醒：`MuteDoor`、`MuteSeatbelt`、`SoundLanguageSetting`、`HapticFeedbackWhenSpeedCamera`

### 4.4 推荐做法（「用 sunnypilot 统一控制」）

1. **补 UI 入口为主**：84 项已注册，在 `carrot_tuning_items.py` 对应分组补 `option_item_sp(...)` 行即可（参考现有 108 项写法，含 min/max/step 与翻译）
2. **32 项先审计后补**：只补 sp 有消费逻辑的（如 `StoppingAccel`、`LaneChangeBsd` 若有对应代码），纯 cp 硬件项不补
3. 补完后跑 `carrot_tuning_render_smoke.py` + `test_translations` 验证

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
