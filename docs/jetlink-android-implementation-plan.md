# 实现方案：zoompilot + jetlink Android NPU 调用手机算力跑大模型

> **目标**：让本项目 sp（在售产品，丰田威兰达 PHEV，comma C3）通过 USB 连接 Android 手机，用手机的 **Snapdragon Hexagon NPU** 跑大模型；**无手机时完全等价于当前行为**。
> **依据**：`docs/phase0-license-and-egpu-decision.md`、`docs/jetlink-android-npu-analysis.md`、`docs/cp-zoompilot-integration-analysis.md`
> **状态**：方案设计完成，**未实施**。本文所有代码位置均为已核实的真实路径。
> ⚠️ **纯静态分析 + 上游文档分析，无实机验证。**

---

## 0. 可行性结论（先说答案）

| 维度 | 判断 |
|---|---|
| **技术上可行吗** | ✅ **可行**。zoompilot 有专门的 `sp/jetlink` 分支（sunnypilot 侧移植，67 文件 / +7795 行），其 `jetson-trt` 分支 pin 的 jetlink 正是 **含 Android 的 v0.7.2** |
| **有现成参考吗** | ✅ **有，且很完整**。`origin/sp/jetlink` 就是"把 jetlink 接进 sunnypilot"的成品参考；sp 与 zoompilot 的 modeld/models 层同构（507 vs 513 行） |
| **许可干净吗** | ✅ **干净**。jetlink = 纯 MIT；zoompilot 自有文件（含全部 `accelerators/**`）= MIT；cp 的 carrot = MIT |
| **最大风险** | ⚠️ **两重**：① C3 未经验证（cp 实测全在 C4）；② **Android 未在任何手机上跑过**（官方明说） |
| **建议做吗** | ⚠️ **先做 P0 验证（C3 gadget 冒烟 + Mac 端先跑通），再决定是否投入 Android** |

**核心判断**：**方案可行，但不要一上来就做 Android**。理由见 §7。

---

## 1. 架构总览（三方职责）

```
┌───────────────────────────────────────────────────────────────────────┐
│  comma C3（本项目 sp）                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ modeld                                                          │  │
│  │  ├─ 无加速器 → 小模型（现状，零改动）            ← 降级路径 A    │  │
│  │  ├─ chestnut 在位 → 大模型 native                ← 降级路径 B    │  │
│  │  └─ accelerators.ready() → jetlink 外置          ← 目标路径 C   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────┐  ┌──────────────────────────────────────────┐ │
│  │ jetlinkd           │  │ accelerators/（抽象层）                   │ │
│  │ 持有 FunctionFS    │  │  _NoBackend 兜底 · present/ready/present │ │
│  │ gadget（always_run）│  │  ← 移植自 zoompilot（MIT）               │ │
│  └────────────────────┘  └──────────────────────────────────────────┘ │
└──────────────────────────────┬────────────────────────────────────────┘
                               │ USB 3 bulk（FunctionFS gadget）
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Android 手机（Snapdragon 8 Gen 2+）                                   │
│  Kotlin+Compose 外壳 ──JNI──> libjetlink.so（Swift 编译）              │
│                                    │                                  │
│                    ONNX Runtime + QNN EP（htp / htp-whole / gpu）     │
│                                    ▼                                  │
│                            Snapdragon Hexagon NPU                     │
└───────────────────────────────────────────────────────────────────────┘
```

**三方代码来源**（均 MIT，可自由使用）：

| 来源 | 提供什么 | 路径 |
|---|---|---|
| **cp** | jetlink 包（原样 vendor）+ gadget 脚本 | `E:/cp/third_party/jetlink/`、`E:/cp/tools/jetlink/setup_gadget.sh` |
| **zoompilot `sp/jetlink` 分支** | ★ **sunnypilot 侧完整移植参考**（67 文件 / +7795 行） | `origin/sp/jetlink` |
| **zoompilot `jetson-trt` 分支** | ★ **pin 了含 Android 的 jetlink v0.7.2** | `origin/jetson-trt`（gitlink `835ca957`） |
| **上游 jetlink** | Android APK 源码 + v0.7.2 全部平台支持 | `github.com/zoompilot/jetlink` |

---

## 2. 关键发现：已有一个"sunnypilot 侧移植成品"

**这是本方案最重要的依据。** zoompilot 仓库里有一条 **`sp/jetlink` 分支**，其提交信息直白说明它就是"把 jetlink 接进 sunnypilot"：

```
f2fa4a3eb accelerators: native-equivalence tests and a merge replay script
24b1642fc hardwared, manager, boot: jetlink opt-in, alert, bounded shutdown
35e8cd3a7 ui: an accelerator view beside the native chestnut state
fa1040e90 models: stock runner under the jetlink override, effective small bundle
2d3bdcc04 selfdrived: an accelerator adapter beside the native big model block
dbae3f398 modeld: jetlink path beside the native chestnut block
0f613734f accelerators: a jetlink module API and the jetlink backend
```

**规模**：`67 files changed, 7795 insertions(+), 48 deletions(-)`

**这意味着一件事**：接入工作量不是"从零设计"，而是"**把 `sp/jetlink` 的改造搬到本项目**"。而且它改的恰好是 sp 也有的那些文件（`modeld.py`、`process_config.py`、`models/helpers.py`、`ui/.../ui_state.py`）。

### 2.1 `sp/jetlink` 分支暴露的 API（与本项目对接面）

`openpilot/sunnypilot/accelerators/__init__.py` 对外接口（比 develop 分支更成熟）：

```python
def present() -> bool                      # 加速器在不在（USB 无关）
def ready() -> bool                        # 大模型现在能不能跑（只读 Params）
def unavailable_reason() -> str | None     # 为何不可用（离车告警用）
def prepare() -> bool                      # modeld 进 realtime 前的最后否决
def make_model_state(cam_w, cam_h, small)  # 交给 modeld 的模型对象
def make_status_publisher(pm, model)       # ChestnutState 位置的替代
def uses_stock_runner() -> bool            # 是否用 stock modeld
def model_choices() -> list[dict]          # 大模型候选列表
def select_model(name: str) -> None        # 选模型
def active_model_name() -> str | None
def daemons() -> list[Daemon]              # 给 process_config 建进程
def progress() / report_progress() / clear_progress()
def shutdown(reason, timeout)
```

### 2.2 集成点清单（`sp/jetlink` 实际改的地方 → 本项目对应位置）

| # | 改动文件（zoompilot sp/jetlink） | 本项目对应文件 | 改动内容 | 行数 |
|---|---|---|---|---|
| 1 | `selfdrive/modeld/modeld.py` | `E:/sp/openpilot/selfdrive/modeld/modeld.py` | 加 `JETLINK = not CHESTNUT and accelerators.ready() and accelerators.prepare()`；`make_model_state` 替代小模型；异常时 re-raise | ~20 |
| 2 | `system/manager/process_config.py` | 同路径 | `+ *[PythonProcess(d.name, d.module, ...) for d in accelerators.daemons()]` | 3 |
| 3 | `system/hardware/hardwared.py` | 同路径 | 离车告警 `Offroad_AcceleratorUnavailable` + 关机前 `accelerators.shutdown()` | ~10 |
| 4 | `sunnypilot/models/helpers.py` | 同路径 | `effective_small_bundle()`（加速器接管时用 stock 小模型） | 12 |
| 5 | `selfdrive/selfdrived/selfdrived.py` | 同路径 | 加速器适配层 + Big Model Ready 提示音 | 19 |
| 6 | `selfdrive/ui/sunnypilot/ui_state.py` | 同路径 | UI 状态加加速器字段 | 67 |
| 7 | `selfdrive/ui/ui_state.py` | 同路径 | 同上（基础层） | 8 |
| 8 | `selfdrive/ui/sunnypilot/accelerator_link.py` | **新建** | UI 设置组件（Off/USB/iOS） | 42 |
| 9 | `selfdrive/ui/sunnypilot/{layouts/settings,mici/layouts}/models.py` | 同路径 | 模型页集成 | 75+66 |
| 10 | `sunnypilot/SConscript` + `accelerators/SConscript` | 同路径 | **构建 warp JIT**（关键，见 §3.3） | 62 |
| 11 | `sunnypilot/accelerators/**`（30 文件） | **新建** | 抽象层 + jetlink backend + jetlinkd + helpers + warp_cache… | ~3500 |
| 12 | `tools/jetlink_bench.py`、`jetlink_replay.py`、`jetlink_live_bench.sh` | **新建** | 基准与回放工具 | 438 |

---

## 3. 技术难点与对策（逐条）

### 3.1 难点一：jetlink 版本落差（本地 0.3.0a1 vs 需要 v0.7.2）

**问题**：本地 `E:/cp/third_party/jetlink` 是 `0.3.0a1`（无 Android），且 v0.7.0 换了**新链路协议**，无法与新 App 配对。

**对策**：
- **不从 cp vendor，改用 `jetson-trt` 分支 pin 的那个版本**（gitlink `835ca957` = v0.7.2）
- `sp/jetlink` 分支用的是更早的 `1f0767fd`，**需要升级到 `835ca957`**
- 保留 `UPSTREAM.md` 记录 revision；保留 `LICENSE`（MIT）

**风险**：v0.7.2 是 Swift 化 + No Docker 版本，"**comma 与 Jetlink 须同版本更新**"。若后续跟随上游，需整体升级。

### 3.2 难点二：`wrapper` 层的 Python ↔ Swift 差异

**问题**：v0.7.0 起服务端是 **Swift**（`JetlinkKit`）；comma 侧仍是 **Python**（`jetlink.comma.*`）。

**对策**：comma 侧只依赖 `jetlink.comma`（gadget / owner / lending），这是 Python 层，**不随 Swift 化改变**。Android App 由用户自行从源码构建（§5.3），本方案**不承担 Android 端开发**。

### 3.3 难点三：warp JIT 需要自己编译（**最容易踩的坑**）

**问题**（`sp/jetlink` 的 `accelerators/SConscript` 注释原文）：

> 「jetlink runs `warp` on the comma and `run_policy` on the Jetson, and **upstream no longer ships a standalone warp JIT**（commaai/openpilot#38684 fused warp and policy). Built here like `dm_warp_*.pkl` in `modeld/SConscript`: `launch_chffrplus.sh` runs `build.py` before manager, so a tinygrad bump has a fresh warp before ignition. **Building it in modeld or jetlinkd instead loses the ~9 s compile to ignition and costs a drive on the small model.**」

**对策**：**必须**在 `accelerators/SConscript` 里把 warp pkl 作为构建产物，由 `launch_chffrplus.sh` → `build.py` 在 manager 之前编好。判据 `jetlink_installed()` = `jetlink_repo/jetlink` 目录存在（空子模块则跳过）。

**若漏掉**：每次点火都要在 modeld/jetlinkd 里现场编译 ~9s，**代价是整趟行程退回小模型**。

### 3.4 难点四：gadget 归属与进程生命周期

**问题**：FunctionFS gadget 必须有人持有，否则 comma 不会枚举；且 **owner 中途被杀会留下需要重启才能清的状态**。

**对策**（`sp/jetlink` 的 `jetlinkd.py` docstring 原文）：

| 设计 | 说明 |
|---|---|
| `jetlinkd` `always_run` | 持有 gadget 一整趟行程；车机点火时 manager 用 SIGINT 停、5s 后 SIGKILL |
| **每次长等待都轮询 `stop`** | 避免 FunctionFS owner 在传输中被杀导致 gadget 卡死 |
| **offroad/onroad 交接** | `jetlinkd` offroad 持有，`modeld` onroad 持有；交接时 gadget 短暂 unbind，对端重新枚举 |
| `DORMANT_HOLD` | 引擎就绪后释放 gadget → 常电的算力端可以睡眠；下次有活时重新呈现（`modeld` 的 bind 即唤醒） |
| 离车告警 | `hardwared` 上报 `Offroad_AcceleratorUnavailable`（不可用原因） |
| 关机 | `hardwared` 关机前调 `accelerators.shutdown()`（有界超时） |

**注意**：develop 分支是 `and_(always_run, ...)`，`sp/jetlink` 分支是 `and_(only_offroad, ...)` —— **两者不同**。本项目应取 `sp/jetlink` 的 offroad 版（更保守）。

### 3.5 难点五：CPU 亲和性冲突（**本项目特有**）

**问题**：`_present_early` 的注释说明了真实风险：

> 「modeld's main thread is already **SCHED_FIFO 54 on core 7**, and the FunctionFS reader the open creates would **inherit that and preempt the frame loop**（see `joining._background_priority`）」

**本项目更严重**：已知 `card`/`selfdrived`/`controlsd` **全绑 core 4，实测 99.3% 单核**，任何额外线程都可能触发 `selfdrivedLagging`。

**对策**：
1. `_background_priority()`：把 gadget 相关线程降级到非实时调度
2. **必须实测**：加 gadget 线程后的 core 4/7 占用，与现状对比
3. 若超标，考虑把 `jetlinkd` 绑到隔离核之外

### 3.6 难点六：C3 与 C4 的差异

**问题**：cp 的所有 jetlink 实测都在 **C4**（5 Gbit/s 协商）。`jetlink_experiment.md:160` 明确 "**C3, Mac and driving behavior are not established**"。

**对策**：**先做 §5.1 的 C3 gadget 冒烟**，确认：
- `/sys/class/udc` 非空
- `CONFIG_USB_F_FS=y`
- USB 3 协商速率（C3 可能低于 C4 的 5 Gbit/s）

---

## 4. 降级设计（"必须兼容无手机"）

**核心照搬 `accelerators/__init__.py` 的三层保护**：

```
第 1 层：jetlink 包不存在
    → _NoBackend：present()=False, ready()=False, prepare()=False, make_model_state()=None
    → 只吞 jetlink 的 ModuleNotFoundError；其他错误照常抛
    → _resolved 失败也缓存（省 185us/次）

第 2 层：包在，硬件不在
    → present() 探测 USB（不用 gadget，所以关闭时无副作用）
    → ready() 只读 Params
    → UI 5Hz 轮询仍是 cheap

第 3 层：启用但失败
    → modeld 保持小模型；hardwared 报 Offroad_AcceleratorUnavailable
    → 掉线时（v0.7.1 行为）：TAKE CONTROL 5s + 继续小模型 + 小模型一帧内接管
```

**关键设计约束**（给实施者）：

| 约束 | 验证方式 |
|---|---|
| 默认 `AcceleratorLink=off`（新 Params，默认关） | 新装设备行为与现在**逐帧一致** |
| `jetlinkd` 用 `should_run=lambda: enabled()` | 关闭时进程**根本不启动** |
| 关闭时只读一个 Params | UI 5Hz 轮询不引入延迟 |
| 不 vendor jetlink 时全部单测通过 | `_NoBackend` 路径测试 |
| 拔线/超时不中断驾驶 | 拔线测试 |

**UI 可见性**（`accelerator_link.py` 的 `link_toggle_meaningful()`）：

```python
if ui_state.chestnut_present:
    return False                              # chestnut 在位时不显示（它自己跑大模型）
return (accelerators.installed() or accelerators.present() or accelerators.ready()
        or link_mode() != "off" or accelerators.unavailable_reason() is not None)
```

即：**包没装、没插东西、没设置、没报错 → 开关根本不出现**。这对"无 eGPU 用户零打扰"至关重要。

---

## 5. 实施路线（分阶段，含验证门槛）

### P0 —— 可行性验证（**先做，决定后续是否投入**）

| # | 任务 | 判据 | 授权需求 |
|---|---|---|---|
| **P0-1** | **C3 gadget 冒烟**（纯只读） | `ls /sys/class/udc` 非空 + `CONFIG_USB_F_FS=y` + USB 速率 | SSH 只读 |
| **P0-2** | **迁移面评估**：把 `sp/jetlink` 的 67 文件改动与 sp 现状逐文件比对 | 产出"可直接搬 / 需适配 / 冲突"三分清单 | 无 |
| **P0-3** | **确认 jetlink v0.7.2 的 comma 侧 Python API 是否兼容** | `jetlink.comma.{gadget,owner,lending}` 存在且接口稳定 | 无 |
| **P0-4** | 硬件决策：是否有 Snapdragon 8 Gen 2+ 手机 | 有/无 | 用户 |

> **P0 是决策门**：若 P0-1 失败（C3 无 gadget 能力）→ 本方案对 C3 不成立，只能走 C4。
> 若用户无 8 Gen 2+ 手机 → **Android 路径降到 P3**，先做 Mac（`docs/phase0-...md` §5.3）。

### P1 —— 移植骨架（不含 Android）

| # | 任务 | 来源 | 工作量 |
|---|---|---|---|
| P1-1 | vendor jetlink `835ca957`（v0.7.2）+ LICENSE + UPSTREAM.md | cp / zoompilot | 0.5d |
| P1-2 | 移植 `accelerators/__init__.py` + `_NoBackend` | `sp/jetlink` | 1d |
| P1-3 | 移植 `jetlink/` backend + helpers + joining + model_state + status | `sp/jetlink` | 3d |
| P1-4 | 移植 `jetlinkd.py`（gadget owner + provisioning） | `sp/jetlink` | 2d |
| P1-5 | `process_config` + `hardwared` + `models/helpers` 集成 | `sp/jetlink` | 1d |
| P1-6 | `modeld.py` 接入（JETLINK 分支） | `sp/jetlink` | 1d |
| P1-7 | **`accelerators/SConscript` 编译 warp pkl** | `sp/jetlink` | 1d |
| P1-8 | UI（`accelerator_link.py` + models 页） | `sp/jetlink` | 2d |
| P1-9 | 移植测试（11 文件 / ~2500 行参考） | `sp/jetlink` | 2d |
| **合计** | | | **~13.5d** |

### P2 —— 端到端跑通（先 Mac，再 Jetson）

| # | 任务 | 说明 |
|---|---|---|
| P2-1 | **Mac 端跑通**（有签名 DMG，门槛最低） | 验证 gadget/协议/降级链全链路 |
| P2-2 | C3 + Mac 实测延迟与 CPU 占用 | **重点测 core 4/7 是否触发 Lagging** |
| P2-3 | 拔线/掉线/重连测试 | 验证降级链（TAKE CONTROL + 小模型一帧接管） |

### P3 —— Android 接入

| # | 任务 | 说明 | 前置 |
|---|---|---|---|
| P3-1 | 构建 Android APK（需 Mac/Linux + Swift 6.4 + NDK 30） | **本方案不承担**，用户自行按上游 `android/README.md` 构建 | 有 8 Gen 2+ 手机 |
| P3-2 | 手机侧 Benchmark（1min + 10min） | 判定 Fast Enough / Tight / Too Slow | P3-1 |
| P3-3 | `LINK_MODES` 扩展 | 上游 v0.7.2 已是 `('off','usb','ios')`，Android 走 **USB** 档，**无需改** | — |
| P3-4 | parity 验证 | `scripts/verify_parity.py`（Mac 同 Wi-Fi）+ `jetlink_live_bench.sh` | P3-2 |

> **好消息**：Android 走的就是 `usb` 档，**comma 侧代码完全不用改**。所有 Android 差异都在手机 App 里。

---

## 6. 工作量与风险评估

### 6.1 总量

| 阶段 | 工作量 | 风险 |
|---|---|---|
| P0 验证 | 1–2 天 | **决定性**（C3 能否 gadget） |
| P1 骨架 | ~13.5 天 | 中（移植 + 构建） |
| P2 跑通 | 3–5 天 | 中（C3 CPU / 延迟） |
| P3 Android | 2–3 天（不含 APK 构建） | 高（未实测） |
| **合计** | **~20 天**（不含 APK 构建与调优） | — |

### 6.2 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| **C3 无 gadget 能力** | **高** | P0-1 先验证；失败则本方案不成立 |
| **Android 无任何实测** | **高** | P3 放最后；官方明说 "not yet run on a phone" |
| **CPU 亲和性冲突**（core 4 已 99.3%） | **高**（本项目特有） | `_background_priority()` + 必须实测；可能需重新规划核绑定 |
| warp pkl 未编进构建 | 中高 | P1-7 单独立项；漏掉会导致每次点火退回小模型 |
| 版本锁死（v0.7.2 需 comma+app 同版本） | 中 | 记录 revision；升级须整体验证 |
| jetlink 许可（**QNN 部分**） | 中 | jetlink 本体 MIT；但 **QNN runtime 受 Qualcomm AI Stack License**，明示"不建议高风险应用" → **需法务判断** |
| VID/PID 用测试号 | 中 | `0x1209/0x0001`，**分发前须申请正式 PID** |
| 上游同步冲突 | 中 | 新代码放 fork 专属目录；不改 upstream 文件 |
| `sp/jetlink` 分支 pin 的是旧版 | 中 | 需升级到 `835ca957`（v0.7.2） |

### 6.3 回滚

- 每项独立 commit；`AcceleratorLink` 默认 `off`
- 关闭 = 完全等价当前行为
- vendor 的 jetlink 可整体删除
- 不 vendor 时 `_NoBackend` 保证一切正常

---

## 7. 结论与建议

### 7.1 可行性总评

**✅ 可行**，且**比预期简单** —— 因为 `sp/jetlink` 分支几乎就是成品，本项目主要是"搬运 + 适配"，而不是"重新设计"。

**但有三条必须先过的关**：

```
关 1（技术）：C3 有 FunctionFS gadget 能力吗？       → P0-1 冒烟
关 2（硬件）：有 Snapdragon 8 Gen 2+ 手机吗？        → P0-4 确认
关 3（合规）：QNN 的 Qualcomm AI Stack License       → 法务判断
              "不建议高风险应用" 是否适用于车载辅助驾驶？
```

### 7.2 我的建议顺序

```
第 1 步（1–2 天）：P0 验证
        └─ 失败 → 停止，本方案对 C3 不成立
        └─ 成功 → 继续

第 2 步（~13.5 天）：P1 骨架 + P2 用 Mac 先跑通
        └─ 理由：Mac 有签名 DMG，门槛最低，能最快验证"全链路通不通"
        └─ 同时暴露 C3 的 CPU/延迟问题（本项目最大未知）

第 3 步（3–5 天）：P3 Android
        └─ 只在"手头正好有 8 Gen 2+ 手机"时做
        └─ 否则优先 Jetson（实测 26.3ms，最稳）
```

**为什么不建议直接做 Android**：
1. 官方明说未在手机上跑过，性能全是**估计值**
2. 需要 **USB3 + 带供电 hub**，很多手机/线材不达标
3. APK 需自行从源码构建（Swift 6.4 跨编译，链路复杂）
4. **comma 侧代码对 Android 与 Mac/Jetson 完全相同**（都走 `usb` 档）→ **先做 Mac 能验证 90% 的 comma 侧工作**

### 7.3 与阶段 0 结论的关系

阶段 0 的结论**全部仍然有效**，本方案是其**具体化**：

| 阶段 0 结论 | 本方案的落实 |
|---|---|
| jetlink 纯 MIT，可 vendor | P1-1 |
| 照搬 zoompilot 降级设计 | §4，`_NoBackend` |
| sp 已有 `usbgpu_present()` 钩子 | P1-6 把 `usbgpu_compiled()` 改真实判定 |
| C3 未经实测 | **P0-1 先冒烟** |
| 无 eGPU 零回归 | 默认 off + `_NoBackend` + UI 隐藏 |

---

## 8. 证据索引

| 结论 | 证据 |
|---|---|
| **存在 sp/jetlink 分支（sunnypilot 侧移植）** | `git log --oneline origin/develop..origin/sp/jetlink` → 10 提交；`git diff --stat origin/develop...origin/sp/jetlink` → **67 files, +7795/-48** |
| 该分支改的文件 | 同上 diff（`modeld.py`/`process_config.py`/`hardwared.py`/`models/helpers.py`/`ui_state.py`/`SConscript` 等） |
| **jetson-trt pin 含 Android 的 jetlink** | `git ls-tree origin/jetson-trt jetlink_repo` → **`835ca957`**（= v0.7.2） |
| develop/iphone pin 旧版 | 同上 → `7273fd02`（v0.5.0 iOS） |
| sp/jetlink pin 更早 | 同上 → `1f0767fd` |
| 加速器 API 全清单 | `git show origin/sp/jetlink:openpilot/sunnypilot/accelerators/__init__.py` |
| warp JIT 必须自编 | `git show origin/sp/jetlink:openpilot/sunnypilot/accelerators/SConscript` 头注释 |
| gadget 生命周期设计 | `git show origin/sp/jetlink:openpilot/sunnypilot/accelerators/jetlink/jetlinkd.py` docstring |
| modeld 接入 diff | `git diff origin/develop...origin/sp/jetlink -- openpilot/selfdrive/modeld/modeld.py` |
| process_config 接入 | 同上（`*[PythonProcess(d.name, d.module, ...) for d in accelerators.daemons()]`） |
| hardwared 告警 | 同上（`Offroad_AcceleratorUnavailable`） |
| UI 可见性逻辑 | `git show origin/develop:openpilot/selfdrive/ui/sunnypilot/accelerator_link.py` → `link_toggle_meaningful()` |
| LINK_MODES | `E:/zoompilot/.../accelerators/__init__.py:207` = `('off','usb','ios')` → **Android 走 usb** |
| 降级三层保护 | `E:/zoompilot/.../accelerators/__init__.py:41-113` |
| 线程优先级风险 | `E:/zoompilot/.../jetlink/backend.py` `_present_early` docstring（SCHED_FIFO 54 / core 7） |
| Android 技术栈 | `github.com/zoompilot/jetlink` → `docs/android-app.md`、`android/README.md` |
| C3 未实测 | `E:/cp/docs/jetlink_experiment.md:155-161` |
| QNN 许可 | `android/README.md` Licenses 段 |
| 本项目 CPU 现状 | `E:/sp/.workbuddy/memory/MEMORY.md`（core 4 99.3% 单核 → `selfdrivedLagging`） |
| sp 已有 eGPU 钩子 | `E:/sp/openpilot/selfdrive/modeld/helpers.py:74-138` |
| sp/zp modeld 同构 | 507 行 vs 513 行 |

---

*方案文档：2026-09-30 | 依据：sp@test(838cd92b4) · zoompilot@origin/{sp/jetlink, jetson-trt, develop} · jetlink upstream v0.7.2*
***本文为设计方案，未实施任何代码改动，未做实机验证。§7.2 的三道关必须先过。***
