# 实施方案：把 jetlink（Android NPU）整合进本项目 sp

> **触发**：用户确认 **Snapdragon 8 Elite Gen 5 实测可跑 60Hz**（远超 20Hz 需求），**决定开整**。  
> **目标**：让 sp（在售产品，丰田威兰达 PHEV，comma C3）通过 USB 连 Android 手机，用手机 NPU 跑大模型；**无手机时零回归**。  
> **基准**：✅ **实施阶段**（非调研）。本文是移植工单，所有路径与 ordinal 已逐条核对。



---

## 0. 结论：可以搬，且比预想干净

| 核查项             | 结果                                                                                                          |
| --------------- | ----------------------------------------------------------------------------------------------------------- |
| **移植基线**        | ★ **不用 `sp/jetlink`（旧架构），改用 `origin/jetson-trt`（v0.7.2 新架构）**                                               |
| **cereal 契约冲突** | ✅ **零冲突**。sp 与本方案的 `OnroadEventSP` 都停在 `@25 bigModelReady`；`ModelDataV2SP` sp 占 `@0-2`，本方案用 `@3-5`，**完美衔接** |
| **架构复杂度**       | ✅ **比旧架构小得多**：新架构 11 文件（vs 旧 30），**capnp 零改动**                                                              |
| **许可**          | ✅ 全部 MIT（jetlink 纯 MIT / zoompilot 自有文件 MIT）                                                                |
| **关键前提**        | ⚠️ **C3 gadget 能力未实测**（P0 冒烟）                                                                               |

**核心变化**：zeph 在 v0.7.2 做了**架构重写** —— 从 `sunnypilot/accelerators/`（comma 主动拉）改成 `sunnypilot/jetlink_adapter/`（**jetlink 定义接口，comma 实现**）。这是**依赖倒置**，对移植是巨大利好：**适配器只需 ~425 行，且不动 cereal**。

---

## 1. 两代架构对比（决定用哪套）

|               | ❌ 旧（`sp/jetlink`，09-07）                              | ✅ 新（`jetson-trt`，09-29）                                                   |
| ------------- | ---------------------------------------------------- | ------------------------------------------------------------------------- |
| 目录            | `sunnypilot/accelerators/` + `accelerators/jetlink/` | `sunnypilot/jetlink_adapter/`                                             |
| 文件数           | **30**                                               | **11**                                                                    |
| 行数            | ~3500（+7795 总计）                                      | **~1500**（+3540 总计）                                                       |
| **cereal 改动** | ⚠️ 需改 `custom.capnp`（+2 enum + `ModelDataV2SP` 3 字段） | ✅ **零改动**                                                                 |
| 依赖方向          | comma 侧主动 import jetlink                             | **jetlink 定义 `jetlink.openpilot.interface.Openpilot`，comma 实现 `Adapter`** |
| cpin          | `1f0767fd`（早期）                                       | ✅ **`835ca957`（v0.7.2，含 Android）**                                        |
| 进程名           | `jetlinkd`（accelerators/jetlink/owner.py）            | `jetlinkd`（jetlink 内部 `jetlink.openpilot.owner`）                          |
| API 校验        | 无                                                    | ✅ **`API = 1` 版本校验**，不匹配即视为不可用                                            |

**结论**：**用新架构（`jetson-trt`）**。理由：文件少 2/3、不动 capnp、pin 的版本才有 Android、且自带 API 版本兼容检查。

---

## 2. 整体架构（依赖倒置）

```
┌───────────────────────────────────────────────────────────────────────┐
│  jetlink_repo（子模块，zoompilot/jetlink @ 835ca957 = v0.7.2，纯 MIT） │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  jetlink.openpilot.interface.Openpilot   ← 接口定义（Protocol）  │  │
│  │  jetlink.openpilot.owner.main()          ← jetlinkd 进程实现     │  │
│  │  jetlink.openpilot.{gadget,joining,...}  ← 协议与状态机          │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                              ▲ 实现                                    │
└──────────────────────────────┼────────────────────────────────────────┘
                               │
┌──────────────────────────────┴────────────────────────────────────────┐
│  本项目 sp                                                            │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ sunnypilot/jetlink_adapter/__init__.py（425 行，新建）           │  │
│  │   class Adapter:  ← 实现 Openpilot 接口                          │  │
│  │     params_dir / _params / get / put / remove                    │  │
│  │     chestnut_present / camera / warp_path / model_root           │  │
│  │     catalog_selector / model_face / engagement / event           │  │
│  │     make_warp                                                    │  │
│  │   class _Absent:  ← 降级兜底（jetlink 缺失/版本不符）            │  │
│  │   @_guarded 钩子：should_run / status / reason / prepare /       │  │
│  │                   attach / request_shutdown / shutdown_pending / │  │
│  │                   should_extend_catalog / extend_catalog         │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│          ▲ 调用                                                        │
│  modeld / process_config / hardwared / models / ui_state / selfdrived  │
└───────────────────────────────────────────────────────────────────────┘
```

**关键机制**：

- `_api()` 首次调用时 `_bind()`；`_bound` 缓存（**失败也缓存**，省重复 sys.path 搜索）
- `_Absent(why=None)` = 没 checkout；`_Absent(why="...")` = 版本/加载失败（why 会出现在离车告警）
- `_guarded(default)` 装饰器：**任何钩子抛异常 → 返回默认值 + 只记一次日志**（UI 5Hz 调用不能刷屏）

---

## 3. 移植工单（逐文件）

### 3.1 新增目录 `openpilot/sunnypilot/jetlink_adapter/`（11 文件）

| 文件                              | 行数      | 来源                                        | 适配要点                                            |
| ------------------------------- | ------- | ----------------------------------------- | ----------------------------------------------- |
| `__init__.py`                   | **425** | `git show origin/jetson-trt:...`          | ★ **核心**。Adapter + \_Absent + 9 个 @\_guarded 钩子 |
| `SConscript`                    | 61      | 同上（`R057` 从 `accelerators/SConscript` 改名） | warp pkl 构建，见 §3.3                              |
| `tests/__init__.py`             | 0       | 同上                                        | —                                               |
| `tests/test_adapter.py`         | **514** | 同上                                        | 适配器行为                                           |
| `tests/test_seam.py`            | **705** | 同上                                        | 接缝测试（最多）                                        |
| `tests/test_model_manager.py`   | 374     | 同上                                        | 模型管理对接                                          |
| `tests/test_tinygrad.py`        | 202     | 同上                                        | tinygrad 路径                                     |
| `tests/test_warp_build.py`      | 176     | 同上                                        | warp 构建                                         |
| `tests/test_queues.py`          | 159     | `R089` 保留                                 | 队列一致性                                           |
| `tests/test_chestnut_parity.py` | 120     | `R063` 保留                                 | 与 chestnut 行为对齐                                 |

### 3.2 修改 openpilot 侧（逐项）

| #  | 文件                                                      | 改动                                                                                                                    | 风险          |
| -- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ----------- |
| 1  | `selfdrive/modeld/modeld.py`                            | `from openpilot.sunnypilot import jetlink_adapter`；`prepare()`；`attach(small_model, w, h)`；异常处理；`acceleratorState` 发布 | **中**（实时路径） |
| 2  | `system/manager/process_config.py`                      | 加 `jetlinkd` 进程（`should_run()` 门控）                                                                                    | 低           |
| 3  | `system/hardware/hardwared.py`                          | `reason()` → 离车告警；`request_shutdown()`/`shutdown_pending()` 关机                                                        | 低           |
| 4  | `sunnypilot/models/fetcher.py`                          | `should_extend_catalog()` / `extend_catalog()` 折叠大模型目录                                                                | 低           |
| 5  | `selfdrive/ui/ui_state.py`                              | UI 状态加加速器字段                                                                                                           | 低           |
| 6  | `selfdrive/ui/sunnypilot/ui_state.py`                   | 同上                                                                                                                    | 低           |
| 7  | `selfdrive/ui/sunnypilot/accelerator_link.py`           | **新建**（`M` 表示 zp 上已存在，sp 需新建）                                                                                         | 低           |
| 8  | `selfdrive/ui/sunnypilot/layouts/settings/models.py`    | 模型页集成                                                                                                                 | 低           |
| 9  | `selfdrive/ui/sunnypilot/mici/layouts/models.py`        | mici 模型页                                                                                                              | 低           |
| 10 | `selfdrive/ui/sunnypilot/model_info.py`                 | 模型信息展示                                                                                                                | 低           |
| 11 | `selfdrive/selfdrived/selfdrived.py`                    | 加速器事件接线                                                                                                               | 低           |
| 12 | `selfdrive/selfdrived/events.py`                        | 事件定义                                                                                                                  | 低           |
| 13 | `sunnypilot/selfdrive/selfdrived/accelerator_events.py` | 加速器事件                                                                                                                 | 低           |
| 14 | `sunnypilot/selfdrive/selfdrived/events.py`             | 同上                                                                                                                    | 低           |
| 15 | `sunnypilot/modeld_v2/modeld.py`                        | modeld_v2 路径                                                                                                          | 中           |
| 16 | `sunnypilot/SConscript`                                 | 注册 `jetlink_adapter` 子目录                                                                                              | 低           |
| 17 | `selfdrive/modeld/SConscript`                           | **注释里的路径更新**（warp keyed by camera）                                                                                    | 低           |
| 18 | `sunnypilot/mads/state.py`                              | MADS 与加速器协同                                                                                                           | 低           |
| 19 | `sunnypilot/selfdrive/controls/controlsd_ext.py`        | 控车侧                                                                                                                   | 中           |
| 20 | `launch_chffrplus.sh`                                   | `ln -sfn jetlink_repo/jetlink jetlink`                                                                                | 低           |
| 21 | `.gitmodules`                                           | 加 `jetlink_repo` 子模块                                                                                                  | 低           |
| 22 | `.gitignore`                                            | 加 `/jetlink`                                                                                                          | 低           |
| 23 | `openpilot/common/params_keys.h`                        | 加 6 个 Params（见 §3.4）                                                                                                  | 低           |

### 3.3 ⚠️ 最容易漏的：warp JIT 构建

**`jetlink_adapter/SConscript`（61 行）** 的关键设计（原文注释）：

> 「jetlink runs `warp` on the comma and `run_policy` elsewhere, and **upstream no longer ships a standalone warp JIT**（commaai/openpilot#38684 fused warp and policy). Built here like `dm_warp_*.pkl` in `modeld/SConscript`: `launch_chffrplus.sh` runs `build.py` before manager… **Building it in modeld or jetlinkd instead loses the ~9 s compile to ignition and costs a drive on the small model.**」

**warp 存放位置**（`jetlink_adapter/__init__.py` 的 `WARP_DIR`）：

```python
# where the build puts the warp for each camera (SConscript) and modeld loads
# it from: in the fork's tree, never in the jetlink submodule (a file there
# leaves it dirty for the updater), and under the *.pkl ignore, which the
# release scripts add past.
# Not Paths.comma_home(), which on AGNOS is a tmpfs overlay: the pickle was gone every boot
WARP_DIR = Path(__file__).resolve().parent / 'models'

def warp_path(cam_w, cam_h, model_w, model_h) -> Path:
  return WARP_DIR / f'warp_{cam_w}x{cam_h}_{model_w}x{model_h}_tinygrad.pkl'
```

**两个必须遵守的点**：

1. **warp 放 `jetlink_adapter/models/`**，不能放 jetlink 子模块（会让子模块 dirty）也不能放 `comma_home()`（AGNOS 是 tmpfs，每次重启丢）
2. **`modeld/SConscript` 里的注释也要同步改**（`accelerators/SConscript` → `jetlink_adapter/SConscript`），否则 key 计算逻辑注释与实际不一致

### 3.4 新增 Params（6 个，`params_keys.h`）

```c
// Accelerators: what runs the large model
{"AcceleratorProgress", {CLEAR_ON_MANAGER_START, JSON}},
{"Offroad_AcceleratorUnavailable", {CLEAR_ON_MANAGER_START, JSON}},
// jetlink backend. Readiness must survive a reboot, or every ignition cycle
// would rebuild a multi-minute TensorRT engine
{"JetlinkEnabled", {PERSISTENT | BACKUP, BOOL}},
{"JetlinkEndpoint", {PERSISTENT | BACKUP, STRING}},
{"JetlinkModel", {PERSISTENT | BACKUP, STRING}},
{"JetlinkEngineReady", {PERSISTENT, STRING}},
{"JetlinkSpec", {PERSISTENT, JSON}},
{"JetlinkCachedModels", {PERSISTENT, JSON}},
```

> 注：`jetlink_adapter/__init__.py` 的 `KEYS` 里用的是 **`JetlinkLink`**（UI 设置）+ `IsOffroad` + `AcceleratorProgress` + `JetlinkSpec` + `JetlinkModelPointers` + `ModelManager_ActiveBundleChestnut` + `ModelManager_ModelsCache_Chestnut`。**以 `__init__.py` 的 `KEYS` 为准补齐**，上面 params_keys 是旧架构的键名，需以新分支实际 diff 为准（实施时用 `git show origin/jetson-trt:openpilot/common/params_keys.h` 精确取）。

### 3.5 cereal：**无需改动** ✅

已核对：

- `OnroadEventSP.EventName`：sp 与目标都停在 **`@25 bigModelReady`** → 无需新增 ordinal
- `ModelDataV2SP`：sp 占 `@0-2`（`laneTurnDirection`/`leftLaneChangeEdgeBlock`/`rightLaneChangeEdgeBlock`），目标用 `@3 bigModelAvailableDEPRECATED` + `@4 acceleratorState` + `@5 acceleratorNameDEPRECATED` → **完美衔接，无需避让**

> ⚠️ 但 `acceleratorState` 的 enum 与 `modelDataV2SP.acceleratorState` 写入点在 modeld 里（`mdv2sp_send.modelDataV2SP.acceleratorState = getattr(model, 'big_model_state', 'none')`），**移植时需一并搬**。

---

## 4. 实施顺序（可回滚，逐步验证）

### 阶段 A：骨架落地（可独立编译，功能不生效）

| 步  | 动作                                                                                            | 验收                                                                                      |
| -- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| A1 | 加 `jetlink_repo` 子模块（pin `835ca957`）+ `.gitmodules` + `.gitignore` + `launch_chffrplus.sh` 软链 | `ls jetlink` 指向正确                                                                       |
| A2 | 搬 `jetlink_adapter/`（11 文件）                                                                   | `python -c "from openpilot.sunnypilot import jetlink_adapter"` 不报错（此时走 `_Absent(None)`） |
| A3 | 补 Params（以新分支实际 diff 为准）                                                                      | `params_keys.h` 编译通过                                                                    |
| A4 | cereal 字段（`ModelDataV2SP @3-5`）+ capnp 重新生成                                                   | `scons` 通过；**此步风险最高，需单独提交**                                                             |
| A5 | `SConscript` 注册 + warp 构建                                                                     | 产物 `jetlink_adapter/models/warp_*.pkl` 生成                                               |

**A 阶段完成时**：功能完全未启用，**行为与现在逐帧一致**。

### 阶段 B：接线（可开关）

| 步  | 动作                                     | 验收                          |
| -- | -------------------------------------- | --------------------------- |
| B1 | `modeld.py` 接入（`prepare()`/`attach()`） | 关闭时 `attach()` 返回 None，走原路径 |
| B2 | `process_config.py` 加 `jetlinkd`       | 关闭时进程**不启动**                |
| B3 | `hardwared.py`（告警 + 关机）                | 关闭时无告警                      |
| B4 | `models/fetcher.py`（目录折叠）              | 关闭时目录不变                     |
| B5 | UI（`accelerator_link.py` + models 页）   | **全无设备时开关不出现**              |
| B6 | `selfdrived` 事件接线                      | 关闭时无新事件                     |

**B 阶段完成时**：`AcceleratorLink=off`（默认）→ **完全等价当前行为**。

### 阶段 C：C3 验证（**三道关**）

| 关            | 判据                                                | 失败处置                           |
| ------------ | ------------------------------------------------- | ------------------------------ |
| **C1 · 技术**  | `ls /sys/class/udc` 非空 + `CONFIG_USB_F_FS=y`      | **失败则方案对 C3 不成立**，停止           |
| **C2 · 资源**  | 接 gadget 后 core 4/7 占用不显著上升；无 `selfdrivedLagging` | 调 `_background_priority` 或改核绑定 |
| **C3 · 端到端** | 拔线 → TAKE CONTROL + 小模型一帧接管；重插 → 重连               | 回归降级链                          |


### 阶段 D：真实算力端

| 优先     | 算力端                                   | 理由        |
| ------ | ------------------------------------- | --------- |
| **D1** | **Android 手机（8 Elite Gen 5，实测 60Hz）** | ★ 用户已确认可行 |
| D2     | Mac                                   | 门槛最低，用于对照 |

> **注意**：Android 走 **`usb` 档**，`MODES = ('off', 'usb', 'ios')` **无需修改**。手机端 APK 由用户按上游 `android/README.md` 自行构建（需 Mac/Linux + Swift 6.4 + NDK 30）。

---

## 5. 工作量

| 阶段      | 工作量          | 说明                 |
| ------- | ------------ | ------------------ |
| A 骨架    | **3–4 天**    | 含 capnp 重新生成（最需小心） |
| B 接线    | **4–5 天**    | 23 处改动，多为小改        |
| C C3 验证 | **2–3 天**    | 含 CPU 亲和性调优        |
| D 真机跑通  | **2–3 天**    | 手机端 APK 构建不计入      |
| **合计**  | **~11–15 天** | 不含 APK 构建与调优       |

> 比旧方案（~20 天）**省约 30%**，因为新架构少 19 个文件且不动 capnp。

---

## 6. 风险登记

| 风险                                       | 等级    | 缓解                               |
| ---------------------------------------- | ----- | -------------------------------- |
| **C3 无 gadget 能力**                       | **高** | C1 先验证；失败即停止                     |
| **CPU 亲和性冲突**（core 4 已 99.3%）            | **高** | C2 专项；`_background_priority()`   |
| capnp 重新生成出错                             | 中高    | A4 单独提交；对照现有 ordinal             |
| warp 未编进构建                               | 中高    | A5 单独立项；判据 = pkl 产物存在            |
| 手机端未实测（60Hz 是他人数据）                       | 中     | D 阶段自测 Benchmark                 |
| **QNN 许可**（Qualcomm AI Stack，"不建议高风险应用"） | 中     | **需法务判断**                        |
| jetlink v0.7.2 API 演进                    | 中     | adapter 自带 `API = 1` 校验，不匹配即安全降级 |
| 上游同步冲突                                   | 中     | 新代码放 fork 专属目录                   |

---

## 7. 证据索引

| 结论                     | 证据                                                                                                |
| ---------------------- | ------------------------------------------------------------------------------------------------- |
| **用新架构（jetson-trt）**   | `git ls-tree -r origin/jetson-trt \| grep jetlink_adapter` → 11 文件                                |
| 新架构文件与行数               | `__init__.py` 425 / `test_seam.py` 705 / `test_adapter.py` 514 / SConscript 61 …                  |
| **capnp 零改动（新）**       | `git diff origin/develop...origin/jetson-trt -- openpilot/cereal/custom.capnp` → **空**            |
| capnp 有改动（旧）           | `git diff origin/develop...origin/sp/jetlink -- ...custom.capnp` → +2 enum +3 字段                  |
| **ordinal 无冲突**        | sp `custom.capnp:445` `bigModelReady @25`；jetson-trt 同为止于 `@25`                                   |
| ModelDataV2SP 衔接       | sp 占 `@0-2`；jetson-trt 用 `@3/4/5`                                                                 |
| Adapter 接口             | `git show origin/jetson-trt:.../jetlink_adapter/__init__.py`（`class Adapter`）                     |
| 降级兜底                   | 同上 `class _Absent` + `_guarded` + `_bind()`（`API = 1` 校验）                                         |
| warp 位置规则              | 同上 `WARP_DIR` / `warp_path()` 注释                                                                  |
| warp 构建要求              | `jetlink_adapter/SConscript` 头注释（~9s / costs a drive）                                             |
| modeld 接入              | `git diff origin/develop...origin/jetson-trt -- openpilot/selfdrive/modeld/modeld.py`             |
| `acceleratorState` 写入点 | 同上 diff（`mdv2sp_send.modelDataV2SP.acceleratorState = getattr(model, 'big_model_state', 'none')`） |
| jetlink pin = v0.7.2   | `git ls-tree origin/jetson-trt jetlink_repo` → `835ca957`                                         |
| Android 走 usb 档        | `MODES = ('off','usb','ios')`（`jetlink_adapter/__init__.py`）                                      |
| jetlink 纯 MIT          | `E:/cp/third_party/jetlink/LICENSE`                                                               |
| C3 现状（未实测）             | `E:/cp/docs/jetlink_experiment.md:155-161`                                                        |
| 本项目 CPU 现状             | `.workbuddy/memory/MEMORY.md`（core 4 99.3% → `selfdrivedLagging`）                                 |
| 前置分析                   | `docs/jetlink-android-implementation-plan.md`、`docs/phase0-license-and-egpu-decision.md`          |

---

*实施方案：2026-10-01 | 基线：sp@test(838cd92b4) · zoompilot@origin/jetson-trt · jetlink 835ca957(v0.7.2)*  
***本文为实施工单，未改动任何代码。A4（capnp）与 C1/C2（C3 验证）是本方案的两个关键节点。***
