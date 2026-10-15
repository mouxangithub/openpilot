# Jetlink Android NPU 支持分析（2026-09-30）

> 用户发现：jetlink 似乎支持用安卓手机的 NPU/GPU 跑大模型。
> **核实结论：✅ 完全正确。** 上游 jetlink 自 **v0.7.0（2026-09-29）** 起正式支持 Android，用 **Snapdragon NPU（Hexagon）** 跑大模型。
> ⚠️ **但本地 vendored 版本（0.3.0a1）完全没有 Android 代码** —— 这是一个重要的版本落差。
> 本文为源码级 + 上游文档级分析，**无实机验证**。

---

## 0. 结论速览

| # | 问题 | 结论 |
|---|---|---|
| 1 | jetlink 支持 Android 吗？ | ✅ **支持**（v0.7.0 起，2026-09-29） |
| 2 | 用 NPU 还是 GPU？ | **两者都用** —— 默认 `NPU + GPU` 混合，vision 模型在 NPU，其余在 GPU |
| 3 | 什么 NPU？ | **高通 Hexagon**，通过 **Qualcomm QNN runtime** |
| 4 | 什么推理栈？ | **ONNX Runtime + QNN Execution Provider**（`onnxruntime-android-qnn`） |
| 5 | 本地能直接用吗？ | ❌ **不能** —— 本地是 `0.3.0a1`，**早于 v0.5.0 的 Swift 重写**，连 iOS 都没有 |
| 6 | 门槛高吗？ | ⚠️ **较高**：需 Snapdragon 8 Gen 2+、USB 3、USB3 带供电 hub、从源码构建 |
| 7 | 实测了吗？ | ❌ **官方明说 "not yet run on a phone"**，性能是**估计值** |
| 8 | 对 C3 有意义吗？ | ⭐⭐⭐ **有，且思路很有意思**（见 §6） |

---

## 一、版本落差（最重要的发现）

### 1.1 三个不同版本的 jetlink

| 来源 | 版本 | 日期 | Android？ |
|---|---|---|---|
| **本地 cp vendored** | `194ff6dc` / **0.3.0a1** | 2026-09-10 | ❌ **无** |
| **本地 zoompilot 子模块** | `7273fd02` | — | ❌（本地未 checkout 内容） |
| **上游 latest** | **v0.7.2** | **2026-09-30** | ✅ **有**（v0.7.0 起） |

证据：
- `E:/cp/third_party/jetlink/UPSTREAM.md`：`Revision: 194ff6dc... (0.3.0a1)`
- 上游 README（今日）：标题已含 "macOS (native GUI), CUDA laptops, and Jetson Orin Nano"

**这解释了为什么我在本地全库搜索 `android`/`nnapi`/`qnn` 全部为空** —— 不是不支持，是**版本太老**。

### 1.2 v0.3.0a1 → v0.7.2 之间发生了什么（关键重构）

| 版本 | 日期 | 关键变化 |
|---|---|---|
| **v0.3.0a1** | 09-10 | 分平台容器镜像（jetson/cuda） |
| v0.4.0 | 09-26 | Jetson/Linux 安装脚本；Mac M1 Pro+、ANE+GPU 拆分 |
| v0.4.2 | 09-27 | Mac 签名公证 |
| **v0.5.0** | 09-28 | ★ **iPhone/iPad 支持**；**统一 Swift 引擎**；**移除 tinygrad 后端**；`Accelerator Link` = Off/USB/iOS |
| v0.6.0 | 09-28 | Mac 纯 Swift，体积 120MB → **14MB** |
| **v0.7.0** | 09-29 | ★ **Android 支持**；**"One Swift engine everywhere"**；**No Docker**（原生运行）；**新链路协议**（comma 与 Jetlink 须同更）；USB 传输 8.5ms → **2.2ms**；回复 74KB → **8KB**（hidden state 留服务端） |
| v0.7.1 | 09-29 | 掉线显示 TAKE CONTROL 5s 并继续小模型；小模型**一帧内接管**；replug 立即重连 |
| **v0.7.2** | 09-30 | 当前 latest；模型列表稳定性修复 |

> ⚠️ **重大影响**：v0.7.0 是 **"new link protocol"**，意味着**本地 vendored 的 0.3.0a1 与上游 v0.7.2 协议不兼容**。若要跟进上游，需整体升级 vendored 版本，而非打补丁。

---

## 二、Android 端技术架构

### 2.1 整体结构

```
┌────────────────────────────────────────────────────────┐
│  Android APK（arm64 only，因 QNN runtime 仅 arm64）      │
│                                                        │
│  ┌─────────────────────┐   ┌────────────────────────┐  │
│  │ Kotlin + Compose    │   │  libjetlink.so         │  │
│  │ （UI 外壳）          │←→│  （Swift 编译到 Android）│  │
│  │  · 屏幕 / 前台服务   │   │  由 Swift SDK for      │  │
│  │  · USB 权限          │   │  Android 交叉编译       │  │
│  │  · 手机健康状态      │   │                        │  │
│  └─────────────────────┘   └────────────────────────┘  │
│         ↑ JNI: io.zoompilot.jetlink.server.Native      │
└────────────────────────────────────────────────────────┘
                          ↕ USB 3 bulk（usbdevfs）
              ┌───────────────────────────┐
              │  comma（C3/C4）FunctionFS  │
              │  gadget 端                │
              └───────────────────────────┘
```

**关键点**：**Kotlin 不含任何 server 逻辑**。Java/Kotlin 只是**外壳**（UI + 前台服务 + USB 权限 + 健康监控），真正的 server 是 **Swift 代码交叉编译成 `libjetlink.so`**，通过 JNI 调用。

### 2.2 推理栈（回答"NPU 还是 GPU"）

看 `android/README.md` 的组件表：

| 组件 | 说明 |
|---|---|
| `JetlinkKit` | server、模型注册表、ONNX 准备，**与所有平台共享** |
| **`JetlinkORT/OrtBackend.swift`** | ★ **onnxruntime 的 profile；`htp`、`htp-whole` 和 `gpu` 使用它的 QNN provider，跑在 Snapdragon 的 NPU 和 GPU 上** |
| `JetlinkServer/UsbfsPipes.swift`, `CUsbfs` | comma 的 bulk 对，通过 usbdevfs |
| `JetlinkKit/AppSnapshot.swift` | 应用状态快照 |
| `JetlinkAndroid` | JNI 函数 |
| `android/app` | Kotlin + Compose 界面 |

**关键技术栈链条**：

```
ONNX Runtime (onnxruntime-android-qnn)
    └── QNN Execution Provider (Qualcomm)
            ├── htp       → Hexagon Tensor Processor（NPU）
            ├── htp-whole → 整个模型在 NPU
            └── gpu       → Adreno GPU
```

依赖（`android/README.md` 许可证段）：
> 「The APK carries onnxruntime (MIT) and **Qualcomm's QNN runtime libraries from Maven** (`com.qualcomm.qti:qnn-runtime`, which `onnxruntime-android-qnn` depends on)」

### 2.3 Processor 设置（四档）

| 档位 | 含义 |
|---|---|
| **NPU + GPU**（默认） | vision 模型在 NPU，其余在 GPU —— **与 Mac 的拆分方式相同** |
| **NPU** | 整个模型在 NPU |
| **GPU** | 当别的东西占用 NPU 时用 |
| **CPU** | 仅用于模拟器 |

### 2.4 手机兼容性表（官方）

| Snapdragon | NPU | 预期 |
|---|---|---|
| 8 Elite Gen 5 / 8 Elite / 8 Gen 3 | v81 / v79 / v75 | **Fast enough（估计）** |
| 8 Gen 2 / 8s Gen 3 | v73 | Maybe |
| 8+ Gen 1 / 8 Gen 1 | v69 | Probably too slow |
| 888 及更老、7 系列 | v68 及更老 | **NPU 不支持 fp16** |

> ⚠️ 「The estimates are from Qualcomm's published numbers for similar models; **no phone has been measured**.」

### 2.5 硬件与连接要求

- Android 12+，**Snapdragon 8 Gen 2 或更新**
- **USB 3**（手机 + hub + 线材都要）—— 标题显示 "Connected over USB 3"，显示 **USB 2（橙色）表示不达标**
- **USB 3 hub + USB-C 供电直通**（手机要边跑边充电）
- 每个模型约 **3GB** 空间
- **需要 Mac 或 Linux PC 构建 APP**（无 Play Store 版本，APK 用 debug key 签名，只能侧载）
- 构建难度：**JDK 17+、Android SDK platform 37、NDK 30.0.16248370、Swift 6.4.0 开源工具链 + Swift SDK for Android**

### 2.6 实时性设计（值得借鉴）

| 机制 | 说明 |
|---|---|
| **Benchmark** | 1 分钟 / 10 分钟，判定 **Fast Enough**（P99 ≤35ms 且无 >50ms）/ **Tight**（P99 <50ms）/ **Too Slow** |
| **50ms 预算** | 与 comma 时间 + 线缆共用同一预算 |
| **Headroom 磁贴** | 显示剩余余量（Good/Tight/Over Budget） |
| **Keep NPU Awake** | 帧间保持 NPU 全速（默认开，费电） |
| **Keep CPU Awake** | 通过 Android performance hints 保持 CPU 频率 |
| **前台服务 + 通知** | 熄屏/切后台仍继续服务；Android 内存不足可能杀掉 → comma 回退小模型 |
| **热管理** | 明确警示手机过热会掉帧；**10 分钟基准**测热衰减 |

---

## 三、架构演进：从 Python 到 "One Swift engine everywhere"

这是本次分析最值得注意的**架构决策**：

```
v0.3.0a1        分平台容器镜像（jetson/cuda）
                     ↓
v0.5.0          iPhone 支持 → 引入 Swift 引擎（Mac 与 iOS 共用一个）
                     ↓
v0.6.0          Mac 去 Python（120MB → 14MB）
                     ↓
v0.7.0          ★ "One Swift engine everywhere"
                · Jetson / Linux PC / Mac / iPhone / Android 共用同一 Swift server
                · 移除 Python server、Docker 镜像
                · Jetson/PC 改原生运行
                · 新增 openpilot 适配器模块（开发者接口）
```

**为什么这个决策重要**：
1. **一套 server 代码跨 5 个平台**（含 NPU/GPU/CUDA/ANE 四种加速器抽象）
2. v0.7.0 声称 Jetson 上输出与 v0.6.0 **逐位一致**，同时 **CPU 占用减半**
3. 这也意味着**若要跟进上游，必须整体接受 Swift 化的重构**，无法局部移植

---

## 四、与本地/navipilot 的关系

**注意区分**：
- **本项目 navipilot**（`github.com/jixiexiaoge/navipilot`）= **Android App，作导航/控制客户端**（走 7000/7705/8082 端口），**不是** jetlink 的算力端
- **jetlink Android App**（`io.zoompilot.jetlink`）= **算力端**，跑大模型，走 USB bulk

**两者完全不同的定位**，不要混淆。但有一个有趣的交叉点：**你的手机已经在车上**（navipilot 场景），如果这台手机是 Snapdragon 8 Gen 2+，**理论上同一台手机可以同时承担"导航客户端"和"算力端"两个角色** —— 这是一个值得评估的组合（见 §5）。

---

## 五、对 C3 + eGPU 方案的影响（回答用户约束）

### 5.1 三个可选路径对比

| 路径 | 硬件 | 性能（官方） | 门槛 | C3 兼容 |
|---|---|---|---|---|
| **A. Jetson Orin Nano** | Jetson（须独立供电） | **实测**：26.3ms 往返，p99 26.8，0/290 帧超预算，corr **0.999994** | 中（装 JetPack） | ✅（设计支持 C3） |
| **B. Mac（Apple silicon）** | M1 Pro+，16GB | 实测 CoreML GPU **43ms**、ANE **33ms** | 低（有 DMG） | ✅ |
| **C. Android 手机** | **Snapdragon 8 Gen 2+ + USB3** | **估计**：8 Gen 3 "Fast enough"，**未实测** | **高**（需源码构建 + hub + USB3） | ✅（协议同） |

### 5.2 Android 路径的吸引力与代价

**吸引力**：
1. **零新增硬件** —— 如果现有手机达标（8 Gen 3 及以上），不需要买 Jetson/Mac
2. **NPU 能效比高** —— 手机 NPU 跑 20Hz 推理，功耗远低于独显
3. **v0.7.1 已解决掉线体验** —— TAKE CONTROL 5s + 小模型一帧接管 + replug 立即重连

**代价**（务必先看）：
1. **未经验证** —— 官方明确 "not yet run on a phone"，性能全是**估计值**
2. **USB 3 硬门槛** —— 很多 USB-C 手机实际只有 USB 2；需要 **USB3 带供电直通的 hub**（额外配件）
3. **构建链复杂** —— Swift 6.4 跨编译到 Android + NDK + QNN runtime，**必须 Mac 或 Linux**
4. **发热** —— 手机边跑模型边充电，官方专门警告热衰减，要跑 10 分钟基准
5. **许可** —— `com.qualcomm.qti:qnn-runtime` 受 **Qualcomm AI Stack License** 约束（仅可在 app 内再分发；且**不建议高风险应用**——车载辅助驾驶是否算需自行判断）
6. **升级滞后** —— 本地是 0.3.0a1，与上游协议不兼容

### 5.3 对"C3 为主 + 后期 eGPU + 必须兼容无 eGPU"的建议

**原阶段 0 结论不变**（`docs/phase0-license-and-egpu-decision.md`），但**新增一条决策维度**：

```
Phase A（现在）：C3 单独跑小模型 —— 现状，零改动
Phase B（后期）：C3 + 外置算力端
    ├── 方案 A1：Jetson Orin Nano（实测最充分，26.3ms）  ← 稳妥
    ├── 方案 A2：Mac（有 DMG，门槛最低，43ms）           ← 最易上手
    └── 方案 A3：Android 手机（零新增硬件，但未实测）    ← 最省成本、最不确定
```

**推荐顺序**：**先 A2（最易验证）→ 再 A1（性能最好）→ A3 作为"如果手头正好有 8 Gen 3 手机"的零成本试验**。

**"兼容无 eGPU"的设计不变**：
- 无论哪个方案，**关键都是 `accelerators/__init__.py` 那套否定默认值 + `_NoBackend`**
- 无外置算力端时，**完全等价于当前 C3 单独跑小模型**
- 这与算力端是 Jetson / Mac / Android **无关** —— 抽象层把差异吃掉

---

## 六、真正值得学的三个设计点

### 6.1 "一个引擎跑遍所有平台"的抽象

v0.7.0 的 `JetlinkKit` 用**一套 Swift server** 支撑：
- Jetson（TensorRT）
- Linux PC（TensorRT）
- Mac（CoreML / ANE）
- iPhone（ANE + GPU）
- **Android（QNN: NPU htp / htp-whole / gpu）**

**platform 差异被收敛到 backends 层**，上层协议/队列/模型管理完全共享。这个思路（**把加速器差异收敛成一层可插拔 backend**）正是 sp 若要接外置算力应该照搬的。

### 6.2 性能预算的"共享 50ms"概念

> 「Headroom: Room left in the **50 ms frame budget** at P99... **The comma's time and the cable come out of the same 50 ms.**」

**关键洞察**：外置算力不是"免费的加速"，而是**从同一个 50ms 预算里切走**（comma 侧 warp/传输 + 线缆 + 手机推理）。这提示 sp 在设计时必须**端到端测预算**，不能只看推理耗时。

### 6.3 降级链的完整定义（v0.7.1 的改进）

| 层级 | 行为 |
|---|---|
| 正常 | 大模型在外置端，20Hz |
| 掉线/滞后 | 显示 **TAKE CONTROL 5s**，**继续用小模型驾驶**（不是 soft disable） |
| 小模型接管 | **一帧内**完成（v0.7.1 前 >1s，会误报 "Driving Model Lagging"） |
| 服务端无响应 | **0.2s** 内捕获（v0.7.1 前 0.5s） |
| Replug | 立即重连（v0.7.1 前最多等 1 分钟） |

> ⚠️ **这条对本项目特别重要**：sp 已知有 `selfdrivedLagging` 问题（card/selfdrived/controlsd 绑 core 4，99.3% 单核）。**若引入外置算力端，端到端延迟会更容易触发 Lagging 告警** —— v0.7.1 把"小模型一帧内接管"专门修好，正是为了这个原因。设计时必须继承这一点。

---

## 七、证据索引

| 结论 | 证据 |
|---|---|
| 本地版本 0.3.0a1 | `E:/cp/third_party/jetlink/UPSTREAM.md`（`Revision: 194ff6dc... (0.3.0a1)`） |
| 本地无 Android 代码 | `grep -rni "android\|nnapi\|qnn\|adreno" E:/cp/third_party/jetlink/` → **空** |
| 本地只有 3 后端 | `E:/cp/third_party/jetlink/jetlink/server/backends/` = `{ort,tinygrad,trt}` |
| NAMES 三元组 | `.../backends/__init__.py`：`NAMES = ('trt', 'tinygrad', 'ort')` |
| 本地 iOS 仅在 zoompilot 层 | `E:/zoompilot/openpilot/sunnypilot/accelerators/__init__.py:207`：`LINK_MODES = ('off','usb','ios')` |
| Mac/iPhone 可行性评审 | `E:/cp/docs/jetlink_apple_feasibility_20260928.md`（评审上游 `df954e50`） |
| 上游标题含 Android | `github.com/zoompilot/jetlink` README（今日抓取） |
| **Android 用户文档** | `zoompilot/jetlink/blob/main/docs/android-app.md` |
| **Android 构建文档** | `zoompilot/jetlink/blob/main/android/README.md` |
| QNN provider 组件表 | `android/README.md`：「`JetlinkORT/OrtBackend.swift` — onnxruntime's profiles; `htp`, `htp-whole` and `gpu` use its **QNN provider** on a Snapdragon's NPU and GPU」 |
| Kotlin 无 server 逻辑 | `android/README.md`：「Kotlin holds no server logic」 |
| QNN 依赖与许可 | `android/README.md` Licenses 段（`com.qualcomm.qti:qnn-runtime`，Qualcomm AI Stack License） |
| 手机兼容表 | `docs/android-app.md`（8 Elite/8 Gen 3 = "Fast enough (estimated)"） |
| NPU 默认拆分 | `docs/android-app.md` Settings：`NPU + GPU`(默认) / `NPU` / `GPU` / `CPU` |
| 未实测 | `docs/android-app.md`：「Experimental, and **not yet run on a phone**」 |
| 50ms 共享预算 | `docs/android-app.md` Headroom 磁贴 |
| 构建依赖 | `android/README.md`：JDK 17、SDK 37、NDK 30.0.16248370、Swift 6.4.0 + Swift SDK for Android |
| 版本时间线 | `github.com/zoompilot/jetlink/releases`（v0.7.0 = Android，v0.5.0 = iOS，latest = v0.7.2） |
| Jetson 实测 26.3ms | 上游 commit `54bf5f10` message |
| 平台清单 | `docs/platforms.md`（Mac / Linux NVIDIA / Windows WSL2 / Jetson） |

---

*分析：2026-09-30 | 本地基准：cp@carrot-wip(2b491763) jetlink 0.3.0a1 · 上游基准：jetlink v0.7.2*
***本文部分结论基于上游官方文档（含明确标注的"估计值"），未做任何实机验证。***
