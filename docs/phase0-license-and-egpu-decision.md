# 阶段 0：许可尽调与 eGPU 兼容性决策（2026-09-30）

> 承接 `docs/cp-zoompilot-integration-analysis.md` 阶段 0。
> **用户约束**：主力设备为 **comma C3**；后期考虑引入 eGPU；**必须兼容无 eGPU 的情况**。
> 状态：**调研完成，待决策后开工**。本文未改任何生产代码。

---

## 0. 结论速览

| # | 问题 | 结论 | 信心 |
|---|---|---|---|
| 1 | jetlink 许可能否用于在售产品？ | **✅ 可以**。`third_party/jetlink` 是**纯 MIT**（`Copyright (c) 2026 Zeph Leggett`），**不受 sunnypilot Custom MIT 约束** | 高（有 LICENSE 文件） |
| 2 | zoompilot 的 accelerators 接入层能否用？ | **✅ 可以**。文件头均为 `Copyright (c) 2026-, Zeph Leggett.` → **自有文件 MIT** | 高（逐文件核实 111 个） |
| 3 | C3 能否作为 jetlink 的 gadget 端？ | **⚠️ 有条件可以**。cp 明确支持 C3（README:41）；gadget 只需 AGNOS 的 `CONFIG_USB_F_FS`。但 **C3 未经实测验证**（cp 的测量全在 C4） | 中（有代码依据，无实测） |
| 4 | 无 eGPU 时能否零回归？ | **✅ 可以，且这是设计目标**。zoompilot 抽象层的 `_NoBackend` 就是"零成本否定默认值"的教科书实现 | 高（有完整源码） |
| 5 | sp 是否已有接入基础？ | **✅ 有**。sp `modeld/helpers.py:74-138` **已有 USB eGPU 检测**（注明 "ported from CarrotPilot cluster support"） | 高（已存在代码） |
| 6 | 阶段 0 是否可放行？ | **✅ 放行**，但有 3 个前置决策（见 §7） | — |

---

## 一、许可尽调（核心交付物）

### 1.1 三方许可归属（逐文件核实）

| 代码源 | 许可 | 证据 | **在售产品可用？** |
|---|---|---|---|
| **cp 本体** | **MIT** | `E:/cp/LICENSE:1` = `Copyright (c) 2018, Comma.ai, Inc.` | ✅ **可用** |
| **jetlink**（`third_party/jetlink`） | **MIT** | `E:/cp/third_party/jetlink/LICENSE:1-3` = `MIT License / Copyright (c) 2026 Zeph Leggett` | ✅ **可用** |
| **zoompilot 自有文件** | **MIT** | 文件头 `Copyright (c) 2026-, Zeph Leggett.`，共 **111 个**文件 | ✅ **可用**（保留声明） |
| **zoompilot 整体** | **Custom MIT** | `E:/zoompilot/LICENSE.md:3`（需书面授权） | ❌ **不可整体使用** |
| **zoompilot 继承的 sunnypilot 代码** | **Custom MIT** | 同上 | ❌ 同 sp 现状，无新增风险 |

### 1.2 关键澄清：jetlink 的许可地位

这是本次尽调**最重要的发现**：

```
E:/cp/third_party/jetlink/UPSTREAM.md:
  Source: https://github.com/zoompilot/jetlink
  Revision: 194ff6dc71cd27282378fff155e94daa7770152b (0.3.0a1)
  The jetlink/ package is copied without modifications. See LICENSE.

E:/cp/third_party/jetlink/LICENSE:
  MIT License
  Copyright (c) 2026 Zeph Leggett
```

**含义**：
- jetlink 虽然托管在 `zoompilot` 组织下，但其**独立包是纯 MIT**
- `UPSTREAM.md` 明确说"**copied without modifications**"——cp 是原样 vendor
- 因此 **sp 可以直接 vendor jetlink**，与引入任何 MIT 第三方库同等，**不触发 sunnypilot 的商用授权条款**

### 1.3 zoompilot 自有 MIT 文件清单（可用部分）

`grep -rl "Copyright (c) 2026-, Zeph Leggett"` 共 **111 个**，其中对本次任务关键的：

| 类别 | 文件 | 用途 |
|---|---|---|
| **接入抽象** | `sunnypilot/accelerators/__init__.py` | ★ 核心参考：降级设计 |
| | `sunnypilot/accelerators/jetlink/{backend,model_state,joining,provision,fallback,helpers,status,owner,spec_cache,compile_warp}.py` | 接入层全套 |
| | `sunnypilot/accelerators/jetlink/tests/*.py`（11 个） | 测试 |
| **UI** | `ui/sunnypilot/accelerator_link.py` | ★ 加速器设置页 |
| | `ui/sunnypilot/tests/test_accelerator_ui.py` | UI 测试 |
| **横向控制** | `controls/lib/{latcontrol_torque_v2,steer_limit,lane_change_smoothing,torque_tune}.py` | 阶段 2 用 |
| | `controls/lib/latcontrol_torque_ext*.py` | 同上 |

### 1.4 合规结论

| 使用方式 | 合规性 | 说明 |
|---|---|---|
| vendor jetlink（MIT） | ✅ **合规** | 与原包同许可，保留 copyright 即可 |
| 参考 / 移植 zoompilot 自有文件 | ✅ **合规** | 保留 `Copyright (c) 2026-, Zeph Leggett.` 声明 |
| 整体 fork zoompilot | ❌ **不合规** | 引入 Custom MIT 商用限制 |
| 移植 zoompilot 继承的 sunnypilot 代码 | ⚠️ **视情形** | 与 sp 现状同许可，需确认是否已在上游 |
| 移植 cp 的 carrot 代码 | ✅ **合规** | MIT |

**建议合规动作**：
1. vendor jetlink 时**保留 `LICENSE` 与 `UPSTREAM.md`**（记录 source + revision）
2. 移植 zoompilot 自有文件时**保留原始文件头**
3. 在 `NOTICE.md`（若存在）或 `docs/` 记录第三方来源清单
4. **不要**在 sp 中引入 zoompilot 的非自有文件

---

## 二、jetlink 技术架构（兼容性设计的基础）

### 2.1 组件构成

```
jetlink (MIT, 9317 行 py, 47 文件)
├── protocol.py        wire 协议：32 字节 header, MAGIC=0x4B4E4C4A, VERSION=2
├── client.py          客户端（device 侧发起）
├── spec.py            ModelSpec / CHUNK / DEFAULT_FRAME_SKIP
├── transport/         ★ 三种传输，可按硬件选择
│   ├── ffs.py         FunctionFS USB gadget（comma 端做 device）
│   ├── usbbulk.py     libusb bulk（host 端，Jetson/Mac）
│   ├── tcp.py         TCP:5599（以太网/基准测试）
│   ├── priority.py    线程优先级 + CPU 亲和性
│   └── watchdog.py    写看门狗
├── server/            服务端（host 侧运行大模型）
│   ├── backends/      ★ 多后端：ort / tinygrad / trt
│   ├── builder.py / cache.py / control.py
│   └── main.py
└── registry/          模型目录（catalog / lfs / cli）
```

### 2.2 关键：传输层决定硬件要求

| 传输 | comma 角色 | 对端角色 | 硬件要求 | C3 可行性 |
|---|---|---|---|---|
| **ffs**（FunctionFS） | **USB device**（gadget） | USB host | AGNOS 内置 `CONFIG_USB_F_FS` | ✅ **docs 明示 AGNOS 已内置** |
| **usbbulk**（libusb） | USB host | USB device | 无内核驱动，走 usbfs | — （对端用） |
| **tcp** | 任意 | 任意 | 网络可达 | ⚠️ 需以太网/WiFi，非主路径 |

> `ffs.py:8-11` 原文：
> 「On a comma this is the comma end. The roles look backwards and are not: **AGNOS has CONFIG_USB_F_FS built in**, while a host needs no kernel driver at all」

**这意味着 C3 作为 gadget 端在**内核能力层面没有障碍** —— 只要 AGNOS 有 `CONFIG_USB_F_FS`（sp 也是 AGNOS，与 cp 同源根文件系统）。

### 2.3 C3 的实测验证状态（重要风险）

cp 的验证记录 `docs/jetlink_experiment.md:155-161`：

```
## Validation record (2026-09-25)
The actual C4 to Orin Nano Super connection negotiated 5 Gbit/s; ...
Vehicle observations were parked, disengaged, with no steering or acceleration
commands enabled. C3, Mac and driving behavior are not established by these
observations.
```

**明确结论**：cp 的实测**全部在 C4 上**，**C3 未经验证**。这是阶段 0 必须记录的核心风险。

同时 `docs/jetlink_deployment_review.md:96` 的 boot 流程写「**等待 C3/C4 连接**」，说明**设计上支持 C3**，只是缺少实测数据。

**C3 与 C4 的潜在差异**：

| 项 | C3（tici） | C4 | 影响 |
|---|---|---|---|
| USB 控制器 | DWC3 | DWC3 | 相近，`ffs.py` 已处理 DWC3 replay 问题 |
| 实测协商速率 | 未知 | **5 Gbit/s** | ⚠️ C3 可能更低，影响推理延迟 |
| CPU/GPU | 较弱 | 较强 | 影响 warp 编译、native fallback 性能 |
| 已有 eGPU 检测 | sp 已有 `usbgpu_present()` | 同 | ✅ 可复用 |
| 热管理 | 更受限 | — | 长时间推理可能降频 |

---

## 三、无 eGPU 兼容设计（用户的核心约束）

### 3.1 zoompilot 的降级架构（可直接借鉴）

**这是"必须兼容无 eGPU"的最佳参考答案**。zoompilot 的 `accelerators/__init__.py` 设计原则（原文注释）：

```
Every function is a thin call into jetlink.backend and is safe on any device:
feature off costs a param read, package absent answers the negative default.
present(), ready(), progress() and enabled() are polled by the UI at 5 Hz and
must stay cheap.
```

**三层降级保护**：

```
第 1 层：包不存在 → _NoBackend（否定默认值类）
    ├─ 所有函数返回安全值：present()=False, ready()=False, load()=None
    ├─ 惰性解析：_resolved 缓存，首次调用才 import
    └─ 只吞 jetlink 缺失，其他 ModuleNotFoundError 照常抛出（不掩盖真实错误）

第 2 层：包存在但硬件不在 → backend 内部判断
    ├─ present() 探测 USB
    ├─ ready() 只读 Params（不碰硬件）
    └─ load() 返回 None → modeld 继续用小的

第 3 层：link 启用但失败 → fallback + 状态上报
    ├─ UI 显示 unavailable_reason()
    └─ modeld 保持小模型，无中断
```

**关键代码**（`accelerators/__init__.py:41-53`）：

```python
def _backend():
  global _resolved
  if _resolved is None:
    try:
      from openpilot.sunnypilot.accelerators.jetlink import backend
    except ModuleNotFoundError as e:
      # 只吞 jetlink 包缺失；其他 import 错误照常抛
      if (e.name or '').split('.')[0] != 'jetlink':
        raise
      backend = _NoBackend
    _resolved = backend   # 失败也缓存，避免重复 sys.path 搜索（实测 185us/次）
  return _resolved
```

### 3.2 选择逻辑（chestnut 优先，eGPU 兜底）

zoompilot 的优先级（`accelerators/__init__.py:9-11`）：

```
if chestnut_present(): native elif accelerators.ready(): jetlink
```

**对 sp 的映射**（sp 已有 chestnut 概念）：

```
if chestnut_present() and chestnut_compiled():   小模型/大模型 native
elif accelerators.ready():                        jetlink 外置
else:                                             当前行为（零变化）
```

### 3.3 sp 已有的接入基础（降低工作量）

**关键发现**：sp **已经有 eGPU 检测骨架**（`openpilot/selfdrive/modeld/helpers.py:74-138`）：

```python
# USB eGPU detection (ported from CarrotPilot cluster support).
#
# sp is a Chestnut-AI-accelerator build and has no production USB eGPU model
# pipeline, so usbgpu_compiled() is conservative (False): ...
# usbgpu_present() is real hardware probing so a user who plugs a supported
# bridge is detected even though sp never compiles for it.

USBGPU_USB_IDS = ((0xADD1, 0x0001), (0x3801, 0x0001))
USBGPU_MIN_SPEED_MBPS = 5000

def usb_device_present(usb_ids, min_speed_mbps=0) -> bool: ...
def usbgpu_present() -> bool: ...                     # ✅ 真实探测
def wait_for_usbgpu_present(timeout, poll_interval=0.1) -> bool: ...
def refresh_usbgpu_device_cache() -> None: ...
def usbgpu_pcie_not_ready(error) -> bool: ...
```

**这意味着**：
- `usbgpu_present()` 已经是**可用的硬件探测**，无需重写
- `usbgpu_compiled()` 保守返回 False 的注释**明确说明**"sp 无生产 eGPU 管线"——正是本次要补的部分
- 接入点已经预留：把 `usbgpu_compiled()` 从保守 False 改为真实判定即可

### 3.4 兼容性设计原则（给 sp 的实施约束）

| 原则 | 做法 | 验证方式 |
|---|---|---|
| **默认关闭** | 新增 `AcceleratorLink` 类 Params，默认 `off` | 新装设备行为与现在**逐帧一致** |
| **包可缺** | jetlink vendor 进 `third_party/`，缺失时 `_NoBackend` 兜底 | 不 vendor 时全部单测通过 |
| **零成本关闭** | 关闭时只读一个 Params | UI 5Hz 轮询不引入延迟 |
| **不阻塞启动** | `jetlinkd` 用 `always_run` + `should_run=lambda: enabled()` | 关闭时进程不启动 |
| **失败不中断驾驶** | `load()` 失败 → 继续小模型 | 拔线测试 |
| **状态可观测** | `unavailable_reason()` + UI 面板 | 面板正确显示 |
| **C3 需实测** | 先在 C3 上做只读冒烟（不接控车） | 见 §6 |

---

## 四、工作量与风险（C3 优先路径）

### 4.1 C3 路径的最小可行范围

**只做"C3 连一个外置算力盒跑大模型"这一条**，不碰 cluster / HUD / 显示回传：

| 组件 | 来源 | 工作量 | 说明 |
|---|---|---|---|
| jetlink 包 vendor | cp `third_party/jetlink`（MIT） | 0.5 天 | 原样复制 + 保留 LICENSE/UPSTREAM |
| `accelerators/__init__.py` 抽象层 | zoompilot 自有 MIT | 1 天 | 改 import 路径到 sp 命名空间 |
| `accelerators/jetlink/backend.py` 等 | zoompilot 自有 MIT | 2–3 天 | 需适配 sp 的 models 层 |
| `jetlinkd` owner 进程 | zoompilot 自有 MIT | 1 天 | 挂到 `process_config` |
| modeld 接入（prepare/load） | zoompilot 模式 | 1–2 天 | sp modeld 与 zp 同构（507 vs 513 行） |
| UI 面板 | zoompilot `accelerator_link.py` | 1–2 天 | 设置页 + 状态显示 |
| gadget 启动脚本 | cp `setup_gadget.sh`（MIT） | 0.5 天 | 需接入 sp 的 launch 流程 |
| **C3 实测与调优** | — | **不确定** | ★ 主要风险 |
| **合计（不含实测）** | | **7–11 天** | |

### 4.2 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| **C3 未经验证** | **高** | 阶段 0 先做**只读 gadget 冒烟**（不接控车），确认 FunctionFS 与协商速率 |
| C3 USB 带宽不足 | 中高 | 实测协商速率；若 <5Gbps 需评估推理延迟 |
| C3 算力被挤占 | 中 | 已知 card/selfdrived/controlsd 已 99.3% 单核；需评估 gadget/warp 线程开销 |
| AGNOS kernel 缺 `CONFIG_USB_F_FS` | 中 | C3 启动后 `ls /sys/kernel/config/usb_gadget` 验证 |
| VID/PID 冲突 | 中 | jetlink 用 `0x1209/0x0001`（pid.codes 测试号），**分发前需申请正式 PID**（`setup_gadget.sh:29` 已注明） |
| 大模型体积 | 中 | 1.7GB，C3 磁盘空间需评估（`PROGRESS_MIN_INTERVAL` 注释提到 440 个 4MB chunk） |
| 上游同步冲突 | 中 | 新代码放 fork 专属路径，不改 upstream 文件 |
| 许可遗漏 | 低 | 已核实；保留 LICENSE + UPSTREAM.md |

### 4.3 回滚方案

- 所有新增以**独立 commit** 提交
- 默认 `AcceleratorLink=off`，关闭即**完全等价于当前行为**
- vendor 的 jetlink 包可整体删除，不影响其他功能
- `modeld` 接入点用**守卫条件**包裹，失败即走原路径

---

## 五、决策矩阵

| 方案 | 说明 | 适合度 |
|---|---|---|
| **A. C3 + 外置算力盒（只推理）** | 最小范围，发挥 C3 已有硬件，不碰显示 | ⭐⭐⭐ **推荐作为第一阶段** |
| B. C3 + 完整 jetlink（含显示/Cluster） | cp 的完整能力，但显示部分在 C3 未验证 | ⭐⭐ 第二阶段 |
| C. 等 C4 | 绕过 C3 未验证风险 | ⭐ 用户以 C3 为主 |
| D. 不做 | 保持现状 | ⭐⭐ 可接受（没有 eGPU 损失也不大） |

---

## 六、建议的 C3 冒烟验证（动手前先做）

**目的**：在写任何接入代码前，先确认 C3 的 gadget 能力。**纯只读，不接控车**。

```bash
# 1. 内核能力（最关键）
ls /sys/kernel/config/usb_gadget          # 应存在（configfs 挂载）
cat /proc/config.gz | gunzip | grep -i "USB_F_FS\|CONFIGFS"    # 应有 CONFIG_USB_F_FS=y
ls /sys/class/udc                        # 应有 UDC 控制器（DWC3）

# 2. 现有 gadget 占用情况
ls /sys/kernel/config/usb_gadget/        # 看是否有已注册 gadget

# 3. USB 角色（C3 是否支持 device 模式）
cat /sys/class/udc/*/state

# 4. 协商能力
lsusb -t 2>/dev/null | head -20

# 5. sp 现有检测是否可用
python3.12 -c "
import sys; sys.path.insert(0,'/data/openpilot')
from openpilot.selfdrive.modeld.helpers import usbgpu_present, usbgpu_compiled
print('usbgpu_present:', usbgpu_present())
print('usbgpu_compiled:', usbgpu_compiled())
"
```

**判据**：`/sys/class/udc` 非空 + `CONFIG_USB_F_FS=y` → C3 具备 gadget 能力，方案 A 可行。

---

## 七、阶段 0 待决策项（需用户确认）

| # | 决策项 | 选项 | 建议 |
|---|---|---|---|
| **D1** | 外置算力盒选型 | (a) Jetson Orin / (b) Mac / (c) NVIDIA Linux PC / (d) 暂不定 | 先定**协议**（USB gadget），盒子可后选；`usbbulk.py` 的 host 侧三种都支持 |
| **D2** | 是否先做 C3 冒烟 | (a) 立刻做（需 SSH 授权） / (b) 先写代码后验 | **(a) 先冒烟**——避免在不可行平台上写代码 |
| **D3** | VID/PID | (a) 用测试号 `0x1209/0x0001` / (b) 申请正式 PID | 内部验证用 (a)；**分发前必须 (b)** |
| **D4** | 大模型托管 | (a) 复用 cp 的下载源 / (b) 自建 | 需确认 cp 的模型源是否稳定；sp 已有 `models/fetcher.py` 可复用 |

---

## 八、下一步（阶段 0 收尾后）

1. **D2 冒烟**（若授权）：在 C3 上执行 §6 命令，确认 gadget 能力 → 决定方案 A 是否可行
2. **vendor jetlink**：复制 `third_party/jetlink`（含 LICENSE + UPSTREAM.md）+ 记录 revision `194ff6dc`
3. **移植抽象层**：`accelerators/__init__.py` + `_NoBackend`（改命名空间）
4. **补 `usbgpu_compiled()`**：把 sp 现有的保守 False 改为真实判定
5. **UI 与 Params**：新增 `AcceleratorLink`（默认 off）
6. **测试**：移植 zoompilot 的 11 个 accelerators 测试 + `test_comma_layer.py`（守卫"不 import 重量级模块"）

---

## 九、证据索引

| 结论 | 证据 |
|---|---|
| jetlink 纯 MIT | `E:/cp/third_party/jetlink/LICENSE:1-3` |
| jetlink 原样 vendor | `E:/cp/third_party/jetlink/UPSTREAM.md`（Source + Revision `194ff6dc`） |
| cp 本体 MIT | `E:/cp/LICENSE:1` |
| zoompilot 整体 Custom MIT | `E:/zoompilot/LICENSE.md:3` |
| zoompilot 自有文件 MIT | `grep -rl "Copyright (c) 2026-, Zeph Leggett" /e/zoompilot/openpilot/` → 111 个 |
| AGNOS 内置 FunctionFS | `E:/cp/third_party/jetlink/jetlink/transport/ffs.py:8-11` |
| 传输层三种 | `E:/cp/third_party/jetlink/jetlink/transport/{ffs,usbbulk,tcp}.py` |
| TCP 不可走 USB 线 | `tcp.py:6-9`（AGNOS 无 host 侧 USB 以太网驱动） |
| C3 未实测 | `E:/cp/docs/jetlink_experiment.md:155-161` |
| 设计上支持 C3 | `E:/cp/docs/jetlink_deployment_review.md:96`（"C3/C4 연결을 기다린다"） |
| cp 支持 C3 设备 | `E:/cp/README.md:41` |
| gadget 启动脚本 | `E:/cp/tools/jetlink/setup_gadget.sh` |
| VID/PID 测试号 | `setup_gadget.sh:29-31`（`0x1209/0x0001`，注明分发前需正式 PID） |
| 降级抽象层 | `E:/zoompilot/openpilot/sunnypilot/accelerators/__init__.py:41-113` |
| chestnut 优先逻辑 | 同上 `:9-11` |
| 惰性 import 守卫 | `E:/zoompilot/openpilot/sunnypilot/accelerators/jetlink/tests/test_comma_layer.py` |
| modeld 接入点 | `E:/zoompilot/openpilot/selfdrive/modeld/modeld.py:271,324` |
| daemon 注册 | `E:/zoompilot/openpilot/system/manager/process_config.py:181` |
| **sp 已有 eGPU 检测** | `E:/sp/openpilot/selfdrive/modeld/helpers.py:74-138` |
| sp/usbgpu_compiled 保守 False | 同上 `:77-81` 注释 |
| sp 与 zp modeld 同构 | `E:/sp/openpilot/selfdrive/modeld/modeld.py`(507) vs zp(513) 行 |
| sp 已有 chestnut 概念 | `E:/sp/openpilot/selfdrive/modeld/helpers.py:55-71` |
| jetlink 体量 | 47 文件 / 9317 行 py |

---

*阶段 0 分析：2026-09-30 | 依据：cp@carrot-wip(2b491763) · zoompilot@develop(c9a482071) · sp@test(838cd92b4)*
*纯静态分析，未做仿真或实车验证。C3 能力需按 §6 实测确认。*
