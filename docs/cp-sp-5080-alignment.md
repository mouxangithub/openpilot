# cp → sp 功能缺口 与 7000 ↔ 5080 互补分析

> 2026-10-11。基于 E:/cp（c4702e42 前后，9 月以来 631 个提交）与 E:/sp 当前 test 分支的逐目录对比，
> 以及 webui（5080）前端 panels.js/components.js 的逆向。本文是路线图，不是实施记录。

## 一、cp → sp：还没抄过来的能力

### A 类：真实功能缺口（建议移植）

| 能力 | cp 实现 | sp 现状 | 移植难度 | 价值 |
|---|---|---|---|---|
| **雷达 CAN 注入（radarcan）** | `carrot/radar/radarcan.py` 独立进程：CAN 驱动的雷达预处理 → 发布 `liveTracks`，让原厂雷达/SCC 看见运动检测前车 | **无**。`EnableRadarTracks` 参数 + UI 开关在（目录/车机页都有），但 plannerd 不消费、无 radarcan 进程 → **死开关** | 中：单文件进程 + plannerd 接 `radar_track_mode`（cp plannerd.py:44 附近 12 行）+ manager 进程 | 高：丰田/现代原厂雷达融合，配合 carrot_serv 的运动检测是 cp 纵向的核心竞争力 |
| **radard_dpath（雷达规划路径）** | `carrot/radar/radard_dpath.py` 替代 radard 的 DPath 路径，消费 radar_motion.controller/lead_selection/occupancy_v2/v3/native 全套 | radar_motion 只有 lane_change_gap | 大：整套 lead_dynamics/lead_selection/occupancy + Cython native + SConscript | 中高：与 radarcan 配套；单独移植无意义，跟 radarcan 一起做 |
| **信号灯辅助（signal_assist）** | `signal_assist.py`（红绿灯观测/停止辅助，**仅观测不控车**）+ `signalcolord` 进程（modeld.signal_color_shadow）+ signal_display + 近期大量实车验证提交 | 无 | 中：cp 自己标注 experimental、opt-in | 中：绿灯放行/红灯确认与 visuals 的 GreenLightAlert 呼应；cp 仍在活跃迭代，建议等它收敛 |
| **carrot_cluster（独立仪表进程）** | `cluster_autorun` → cluster_live：独立进程 + H264 管线 + GLES dmabuf + gamepad，ClusterHud 开启时跑 | sp 是 **UI 进程内 overlay**（cluster_view 渲染库 + cluster_overlay_smoke），无独立进程 | 两种架构不可直接平移 | 低：sp 的 overlay 方案已工作且少一个进程；除非要 cp 的 H264 外接屏能力，不建议抄 |
| **cweb_push** | carrot 推送通道 | 无 | 低 | 低：国内用不上 cp 的推送 |
| **kmap（韩国 Kakao 地图）** | carrot/kmap | 无（carrot_map.js 也是死代码） | - | **不适用**：国内应走 Amap/navipilot/OSM |

### B 类：sp 已用不同架构覆盖（不必抄）

| cp 方案 | sp 方案 | 结论 |
|---|---|---|
| `jetlinkd` 独立守护 | `models_manager` + `modeld_tinygrad` + jetlink_adapter（依赖倒置，v0.8.5 pin） | sp 架构更完整，保留 |
| `navd`（上游导航） | `mapd` + `mapd_manager`（OSM）+ navipilot 7714 | 双导航栈共存，保留 |
| `cluster` 独立进程 | UI 内 overlay（cluster_view） | 保留 sp 方案 |
| `beep`/`micd`/`soundd` | `beepd`/`micd`/`soundd`（AudioProcess，正则漏计） | 已对齐 |
| egpu_model | egpu.py（读 chestnut/jetlink 而非 cp 的 big_model 管线） | sp 版正确（匹配本 fork 硬件栈） |
| server/features 差集 | 仅 egpu_model.py 一项 | **7000 服务端与 cp 已完全对齐**（含本轮 Camera/params_extra/credentials/preferences/opui_proxy 的 additions） |

### C 类：cp 在活跃演进、值得持续盯的

- **信号灯辅助**（9 月以来十几个实车验证提交，红绿灯观测→停止辅助假设）
- **Hyundai CAN-FD**（aReq 置零试验）、**RAV4 转向激活**
- **radar 验证工具链**（radar_web_export / replay 工具，配合 radarcan 移植一起抄）

## 一·五、实施结果（2026-10-11 全部落地，设备实测）

| 项 | 状态 | 证据 |
|---|---|---|
| 7000 接入 OSM/蓝牙/行程/IMU | ✅ 已实现 | 四页走 /api/opui；蓝牙成为侧栏能力分区；web 构建 + settings 测试 242 通过 |
| radarcan（CAN→liveTracks） | ✅ 已实现 | `carrot/radar/radarcan.py` + can_batch/lateral + cereal `liveTracks @153` + `RadarData.radarTrackFlipped @4`；设备实测 `EnableRadarTracks=1` 时 radard 关、radard_dpath+radarcan 开（分进程验证），`new_message('liveTracks')` 可用 |
| radar_motion 全套 + radard_dpath | ✅ 已实现 | 15 文件 11.6k 行整包移植（零外部依赖），`_motion_native.so` 设备编译成功、BACKEND=cython；radard_dpath 消费 liveTracks 产出 radarState（planner 侧零改动） |
| signal_assist 信号灯观测 | ✅ 已实现（库层） | 5 模块 + 4 测试 + tools/signal_analysis 移植；设备 104 passed；daemon 由 cp 同款文件系统 opt-in 门控（默认关）。**未接 sp planner**：cp 的挂钩需要不同的 CarrotPlanner 签名，且上游仍在重验证 |
| EnableRadarTracks 死开关 | ✅ 已点亮 | 参数+UI 原本就在；现在有真实消费者 |

### 与 cp 的差异（有意保留）

- radard 只在 `EnableRadarTracks` 开启时才换成 radard_dpath；cp 是无条件替换。sp 默认路径零变化。
- signal 不接 planner/cluster（cp 的集成点形状不同）；planner 集成测试以明确原因 skip。

## 二、与当前项目的结合方式

1. **radarcan 优先**：它是 cp 纵向能力的地基，且 sp 已有死开关（EnableRadarTracks）。路线：
   声明 `EnableRadarTracksResult` → 移植 radarcan.py + can_batch/lateral → plannerd 接
   radar_track_mode → manager 加进程（only_onroad）→ 设备 scons 无需（纯 Python）→ 丰田
   WILDLANDER_PHEV 实车验证 liveTracks。
2. **radar_motion 全套 + radard_dpath** 作为第二阶段（依赖 radarcan 先行）。
3. **signal_assist 观望**：等 cp 收敛后整包移植，先不接车控。
4. **持续跟踪**：给 cp 建立月度 diff 例行（本文件 §一.三 更新）。

## 三、7000 ↔ 5080：取长补短

### 各自独有（已核实）

| 7000（cp 面板） | 5080（webui，镜像车机 UI） |
|---|---|
| 驾驶页：WebRTC 视觉流 + mini HUD + AR 叠层 + carrot navi ws 地图流 | **模型管理**（双槽位+树形弹窗，已搬）、**车辆选择**（平台树，已搬） |
| 设置档案/热门值/intro 预设（一套目录驱动） | **OSM 管理**（regions/select/progress/size/delete）、**行程统计**（trips）、**蓝牙配对**（bluetooth/{operation}）、**IMU 校准**（calibration/{action}）、**开发者**（分支切换/备份）、亮度/告警音/agnos 系统更新 |
| 工具：dashcam/screenrecord/camera/终端/日志/支持终端 | 实时状态 hub（ws_rpc/state_hub）、model overlay/projection（模型输出可视化）、WebRTC 健康检查 |
| typed 参数写路径（ParamWriteError 语义）+ xiaoge 代理 | 面板 schema（panels/{id}）+ design tokens + i18n |

### 结合现状与路线

**已做**：`/api/opui/*` 透传 → 模型管理、车辆选择已用 5080 实现；5001 视觉链与 5080 的 webrtc_api 各自独立。

**已完成**：模型管理、车辆选择（前一轮）；**OSM 管理、蓝牙配对、行程统计、IMU 校准（本轮）**。

**下一步（按性价比排序）**：
1. **OSM 管理页**（regions 树 + 下载进度 + 删除）— 纯前端，API 已通代理；替换掉 OSM 分区的只读参数行。
2. **蓝牙配对页** — bluetooth/{operation}；修正"蓝牙无能力"的旧结论。
3. **行程统计页** — trips API（local/cloud 数据源已在本 fork 参数里）。
4. **IMU 校准动作页** — calibration/{action}，替换 IMU 分区的只读行（Status/Matrix 只读保留）。
5. **反向取长**：5080 的驾驶页目前没有 cp 的 AR 叠层/HUD/导航地图流——可在 5080 侧 iframe 或
   代理 7000 的 `/` 驾驶页（或直接给 5080 加个指向 7000 的入口），避免两套视觉页互相内卷。
6. **长期**：面板 schema 化——把 7000 的 SP 分区从"手写渲染器"迁到 5080 的 panels/{id} schema
   （widgets: action/bool/option + visible_if/advanced_if），一次渲染器吃掉所有定制交互
   （含 LaneTurnValue 这类 min/max/step 的步进行）。

### 边界与风险

- webui `vehicle_select` **不校验 bundle**（任意串直写 CarPlatformBundle 并置 manual）——前端只发
  树内值，但直接调 API 有风险；建议给 webui 补校验（上游修复）。
- 5080 是可选依赖：所有经 /api/opui 的页面必须保持"daemon 不在 → 回退通用渲染"的约定。
- 模型切换的 offroad 门控依赖 `IsOffroad`，与 5080 一致。
