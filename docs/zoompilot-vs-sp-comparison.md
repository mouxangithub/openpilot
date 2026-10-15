# zoompilot vs 本项目 sp 对比分析报告

**分析对象**
- **zoompilot**：`E:\zoompilot`，分支 `develop`，remote `github.com/zoompilot/zoompilot`，作者 Zeph Leggett，面向**马自达 CX-5 / CX-9** 的 sunnypilot fork
- **本项目 sp**：`E:\sp`，分支 `test`（HEAD `838cd92b4`，2026-09-29），面向**丰田**（主力车型 21 款威兰达 PHEV）的 sunnypilot fork，含自研 `ai/` 模块 + `carrot/` 导航层 + `webui` 子模块
- **分析日期**：2026-09-30
- **说明**：zoompilot 的 `opendbc_repo` / `panda` 子模块**未 checkout（空目录）**，涉及这两个仓库的实现细节只能依据调用点语义推断，已在正文标注。本报告为**纯静态代码分析，未做仿真或实车验证**。

---

## 一、结论先行

| 判断 | 内容 |
|---|---|
| **两者是同源异构** | 同为 sunnypilot 二次开发，但**走了两条完全不同的路线**：zoompilot 是**纵向深挖单车型**（马自达），sp 是**横向铺开生态**（导航/App/AI/多通道） |
| **zoompilot 强在哪** | ①**控制层深度**（横向扭矩 v0/v2 分层 + 限值分类器 + 变道平滑）；②**契约隔离**（嵌套 `CarStateZP`）；③**行为不变量测试 + 台架**；④**带 route 锚点的设计文档**；⑤**参数版本化播种** |
| **sp 强在哪** | ①**功能广度**（Carrot 导航 91 文件/28008 行、xiaoge 视觉、7000 API、配套 App）；②**自研 AI 模块**；③**上游自动同步**（`upstream-sync.yml`，zoompilot 没有）；④参数体量 689 vs 323 |
| **对威兰达 PHEV 最高价值** | `lane_change_smoothing`（**零标定可直接移植**）、`steer_limit` 分类法（**可治其「及时接管」误报**）、参数播种机制、不变量测试方法学、文档范式 |
| **法定风险提示** | zoompilot 整体受 sunnypilot **Custom MIT 许可**约束（`LICENSE.md`），**商用/闭源需书面授权**；但其自有文件（`Copyright (c) 2026-, Zeph Leggett.`）单独以 **标准 MIT** 提供（`NOTICE.md`）。本项目为**在售产品**，**不可整体搬用**，仅自有文件部分可参考，且需保留声明 |

---

## 二、定位与规模总览

| 维度 | zoompilot | sp（本项目） |
|---|---|---|
| 目标车型 | 马自达 CX-5 2022+ / CX-9 / CX-8，含 EPS 换装 | 丰田（威兰达 PHEV 等），兼容 **SecOC** 平台 |
| 横向控制 | **自研 v0/v1/v2 三版扭矩调校 + 限值分类器** | 沿用上游 `latcontrol_torque_ext` + 自研 carrot 感知 |
| 纵向控制 | **自研 ICBM + cruise_arbiter + stock_ecu_handback** | 沿用上游 ICBM（128 行）+ carrot 地图减速 |
| 导航 / App 层 | 无 | **carrot/ 91 文件 / 28008 行**，7705/7706/7709/7710/7711/7713/7714 + 7000 全通道 |
| AI 模块 | 无 | **`ai/` 自研 OP 助手（车机 5090 端口）** |
| `params_keys.h` | 323 行 | **689 行** |
| 测试文件数 | 168（sunnypilot 下 94） | 142（sunnypilot 下 70） |
| 自研设计文档 | **`docs/zoompilot/` 14 篇 / 3165 行**（含 route 锚点） | `docs/` 23 篇 / 1701 行 |
| CI workflows | 24（含 `zoompilot-tests.yaml`、`zoompilot-prebuilt.yaml`） | 25（含 **`upstream-sync.yml`**） |
| git hooks | **`.githooks/commit-msg`** | 无 |
| 独有子模块 | `jetlink_repo`（外置算力加速） | `ai`、`webui` |

---

## 三、维度一：新增功能对比

### 3.1 横向控制（zoompilot 的核心差异化）

zoompilot 把「转向手感」做成了一条完整的自研技术栈，**这是本项目完全没有对应物的一块**。核验结果：

```
latcontrol_torque_v2.py          sp:no   zoom:YES
steer_limit.py                   sp:no   zoom:YES
lane_change_smoothing.py         sp:no   zoom:YES
torque_tune.py                   sp:no   zoom:YES
latcontrol_torque_versions.json  sp:只有 v0/v1，zoom 有 v0/v1/v2
```

四个机制（依据 `docs/zoompilot/lateral-tune-roadmap.md` + `lateral-tune.md`）：

| 机制 | 实现位置 | 做什么 | 关键证据 |
|---|---|---|---|
| **速度相关扭矩上限** | `latcontrol_torque_ext.py:23,31-34` + opendbc `get_steer_rail_schedule` | EPS 实际能施加的力矩随速度下降，把这条曲线编码进控制器，避免"指令超天花板 → 积分器空转 → 松手过冲" | `mazda-lateral.md:111-129`，11,408,748 帧实测：>32.5mph 无 1 帧超 620 counts，<18mph 无 1 帧超 1148 |
| **速度分箱自学习** | `latcontrol_torque_ext.py:128-185` | 上游只学**一个** latAccelFactor / friction，zoompilot 学 **7 个速度区间** | `ext.py:146` `get_speed_dep_config_for_car`；CX-5 bins 6.5/9.5/12/16.4/21/28/35 m/s |
| **rate-matched 指令** | `steer_limit.py:29` | 上游要 10 counts/帧，EPS 实际接受 12 → 用满 12，力矩上升更快 | `mazda-lateral.md:32-57`，11.7M 帧 p99/p99.9 均为 12 |
| **变道平滑** | `lane_change_smoothing.py:88-138` | 变道进入/回卷/释放三段 taper，可配节奏，默认关 | `CHANGELOG.md` "Lane Change Smoothing...Off by default" |

**限值分类器**是其中最具方法学价值的设计（`steer_limit.py:46-78`）：

```
limited = mismatch and not at_rail and deepening
```
上游只用一个布尔 `steer_limited_by_safety`（`|CC.actuators.torque - carOutput.torque| > 0.01`），在马自达这类**限速率**的 torque 车上**普通行驶就误触发** → 积分器大半时间被冻结 + 真实饱和告警永远发不出。zoompilot 把它拆成 `rate_limited / at_rail / driver_limited` 三类，并给积分器做**方向性冻结**（只在会加深误差时冻结）。

> 这与本项目已知问题「**及时接管：转向超过限制**」属**同一类误报问题**（把"限速率/暂时性限制"与"真实故障"混为一谈），方法学可直接借用。

### 3.2 v2 的四个增量机制（`latcontrol_torque_v2.py`）

每一条都有 leave-one-out 回放归因（`lateral-tune-roadmap.md`）：

| 机制 | 代码 | 效果（实测） |
|---|---|---|
| 滤波 jerk 摩擦输入 | `v2.py:26-27,45-50` | 车道中心 <1Hz 指令运动 −12%（hf_rms 0.0372→0.0327） |
| KD 按压门控 | `v2.py:38-40` | 低速出弯反摆消除约 85%（0.415→0.313） |
| 松开方向盘处理 | `v2.py:36-37,93-96` | 一次性 `i *= 0.8` + 0.3s 误差 ramp，前馈不 ramp |
| 曲率缓冲 + 非激活预热 | `v2.py:56-57` | 避免速度变化被误读为 jerk |

**同时明确「试过但被否决」的清单**（`lateral-tune-roadmap.md` "What left"）——这份否定清单与肯定清单**同等有价值**。

### 3.3 纵向控制（zoompilot 重构了上游的按钮接管层）

| 模块 | zoom | sp | 说明 |
|---|---|---|---|
| `cruise_arbiter.py` | 319 行 | **无** | 按钮意图分类（普通/驳回/提示）+ SLA 会话仲裁 |
| `stock_ecu_handback.py` | 161 行 | **无** | 马自达雷达 UDS 交还 |
| `card_ext.py` | 55 行 | **无** | card 扩展挂点 |
| `intelligent_cruise_button_management/controller.py` | **316 行** | 128 行 | zoompilot 重建了整套按钮伺服 |
| `dec/dec.py` | 13KB（Kalman + ModeTransitionManager） | 不同实现（`DecSignals` + `ModeHysteresis`） | 上游 dec 在马自达上被判为"broken" |

**对丰田的关键差异**：zoompilot 的 arbiter 在 `pcm_machine_owns_sla = opLong and pcmCruise and pcmCruiseSpeed` 时**不适用**（`cruise_arbiter.py:55-59`），丰田 ICBM 在 `pcmCruiseSpeed` 直接 return。**这意味着 zoompilot 花最大力气的纵向层，对威兰达 PHEV 恰好是"不适用"的部分**。

### 3.4 传感器接入与设备功能（马自达专有）

- **前向雷达**：读取距离/角度/接近速度，最多 4 车前车，与摄像头融合（制动/油门仍交给原厂）
- **盲区监测**：原厂盲区传感器数据接入，变道前可用
- **限速牌识别**：复用原厂摄像头读到的限速，接入 speed-limit assist
- **jetlink 加速器**：`openpilot/sunnypilot/accelerators/jetlink/`（265KB，34 文件 + `jetlink_repo` 子模块）——把大模型推理放到 Mac / Jetson / NVIDIA Linux / iPhone 上跑

> **jetlink 是本报告中最值得关注的"跨车型可迁移"功能**：它不依赖马自达，本质是把 modeld 推理外置到更强算力。本项目主力平台是 **comma C3**（算力有限），理论上价值更高。但工程量极大，属于长期项。

---

## 四、维度二：架构与代码组织

### 4.1 契约隔离：嵌套 fork 结构（zoompilot 明显更优）

**zoompilot 做法**（`openpilot/cereal/custom.capnp`）：
```capnp
struct CarStateSP {          # @474
  speedLimit @0 :Float32;
  zoompilot @1 :CarStateZP;  # @476  ← fork 字段全部收进这一个嵌套结构
}
struct CarStateZP @0xc879af11c43cb400 {  # @562
  ...
}
struct CarControlZP @0xaadf9bc39b7bd41e { # @607
  ...
}
```
注释里写明了设计意图（`custom.capnp:557-561`）：
> 「每个 SP 结构至多挂一个 fork 字段，故**上游 append 永不落到 fork ordinal**」

**本项目做法**（`openpilot/cereal/custom.capnp:542-600`）：在 `CarStateSP` **直接追加** `carrotLaneValid@1 … engineOff@9 / engineRpm@10`，文件内的注释自述了代价：
> 「另一侧已占用 @1-@8，故把 engineOff 从原 @1/@2 改到 @9/@10，**ordinal 是 wire 契约**」

| 对比项 | zoompilot（嵌套） | sp（直接追加） |
|---|---|---|
| 上游同步成本 | **低**（上游追加落在外层，不撞内层） | 高（每次上游加字段都要人工避让） |
| ordinal 冲撞风险 | 收敛到一个嵌套字段 | 逐字段暴露 |
| schema 耦合度 | 低 | 高 |
| 迁移成本 | — | **高**（sp 已有 10 个 carrot ordinal 在位，重构需重新生成 capnp + 全链路回归） |

### 4.2 分层显式性

zoompilot `controls/lib/`：**一个关注点一个文件 + Ext/Base/Override 显式三段**
```
latcontrol_torque_v0.py / v2.py        ← 算法版本
latcontrol_torque_ext.py               ← 共享扩展（rail + 速度分箱）
latcontrol_torque_ext_base.py          ← 扩展基类（jerk 摩擦）
latcontrol_torque_ext_override.py      ← 手动覆盖
torque_tune.py                         ← 版本选择的单一事实源
steer_limit.py                         ← 限值分类
lane_change_smoothing.py               ← 变道平滑
```

本项目 `controls/lib/`：**上游层与 fork 层混杂**（同时存在 `auto_lane_change.py`（上游）、`carrot_longitudinal_source.py`（fork）、`desire_arbiter.py`（fork）、`traffic_light_fusion.py`（fork））。

### 4.3 carrot 层的耦合代价（本项目最大架构负债）

| 项 | sp carrot | zoompilot 对应层 |
|---|---|---|
| 文件数 | **91** | 25（`sunnypilot/selfdrive/car/`） |
| 行数 | **28008** | 4490 |
| 单文件最大 | `carrot_man.py` 137,685 字节 | — |
| 与车型耦合 | **直接 import opendbc/CarState**（`carrot_functions.py`、`carrot_navi_fusion.py`、`xiaoge/xiaoge_vision.py`） | 隔离在 `car/` 层 |

carrot 层带来的是**功能广度**（导航、多 App 通道、xiaoge 视觉），代价是与车型控制逻辑强耦合 → 上游同步时冲突面大。

### 4.4 上游同步：本项目反而领先

- sp 有 **`upstream-sync.yml`**（脚本合并上游 + 自动解冲突），zoompilot **没有**自动同步 workflow
- 这是本项目在工程实践上的一个**明确优势**，应保持

---

## 五、维度三：性能与稳定性

| 项 | zoompilot | sp | 评价 |
|---|---|---|---|
| **限值误判治理** | `steer_limit.classify` 方向性冻结 + at_rail 剥离 | 沿用上游布尔标志 | **zoompilot 优**（马自达场景） |
| **控制器饱和可见性** | EPS ceiling clamp，让饱和**对控制器可见** | 无对应处理 | **zoompilot 优**（若丰田有同类天花板） |
| **panda 与控制器速率一致性** | 文档记录 25 vs 12 的 rate-down 不匹配导致 171 连续帧被拒（1.7s LKAS 空洞）+ 摄像头锁死 → 修复为参数门控 | — | **方法学极有价值**：控制器与 panda 信封必须逐帧对齐 |
| **CPU 亲和性 / 省电** | 未见专门处理 | **有专门修复**（`a5c0849b2`：`set_core_affinity` 吞 EINVAL、`set_power_save` 保留 6/7 核） | **sp 优** |
| **已知延迟问题治理** | — | 定位 `selfdrivedLagging`（card/selfdrived/controlsd 全绑 core 4 → 99.3% 单核） | **sp 优（已定位）** |
| **依赖静默降级** | — | 已识别 cv2/shapely 静默降级风险并引导 | **sp 优** |
| **GPS/模型推理外置** | jetlink（可选外置算力） | 无 | **zoompilot 优**（概念） |

### 关于 steer_limit 与本项目"及时接管"的关联

本项目已知告警「及时接管：转向超过限制」被定位为 **MADS Toyota 转向角超限告警**，触发条件是 IGNITION 不稳反复 onroad/offroad。这**不是**同一个 bug（一个是扭矩速率限值，一个是转向角阈值），但**误报治理的方法学同源**：zoompilot 的思路是——**在告警之前先把"限制"按成因拆开**，只对真实故障升级。本项目可以把这套分类法套用到自身告警链上（详见第七章 P0-2）。

---

## 六、维度四：交互与用户体验

| 项 | zoompilot | sp |
|---|---|---|
| 设置页结构 | `ui/sunnypilot/layouts/settings/{steering_sub_layouts,cruise_sub_layouts,vehicle/brands}` | 同构（沿用上游） |
| 转向子页 | `lane_change_settings.py` / `mads_settings.py` / `torque_settings.py` | 无 lane_change 子页 |
| 巡航子页 | `speed_limit_policy.py` / `speed_limit_settings.py` | 有 speed_limit（沿用上游） |
| mici UI | `mici/layouts/settings/{developer,device,firehose,network,settings,software,toggles}.py` | 同目录存在 |
| UI 文件数 | 174 | 180 |
| 告警文案 | 「档位/蜂鸣/白色方向盘图标」逐项按场景定制；把 4s WARNING 与 NO_ENTRY 分级区分 | 沿用上游 |
| 默认值体验 | **零配置**：`_seed_mazda_torque_defaults` 一次性把最好设置播种为默认（README："让车自己教软件"） | 需要用户自行在设置里配置 |

**zoompilot 的 UX 哲学（README 明确写出）**：
```
Under steering: turn on torque control, then self-tune, then speed-dependent self-tune.
Leave custom tune and manual real-time off. Let the car teach the software. That's the point.
```
即：**默认值即最优解，自学习代替手工调参**。这一点由 4.4 节的播种机制支撑，是本项目可借鉴的**产品化思路**。

---

## 七、维度五：可维护性与工程实践

### 7.1 测试：行为不变量 + 台架（zoompilot 明显领先）

| 项 | zoompilot | sp |
|---|---|---|
| 测试文件总数 | 168（sunnypilot 94） | 142（sunnypilot 70） |
| **不变量型断言** | ✅ `test_latcontrol_torque_v2.py:120-134`：断言"KD/deadzone/jerk filter 归零后，**v2 IS v0 frame-for-frame**"，逐帧比对 error/p/i/d/f | ❌ 无同类 |
| **控制器仿真台架** | ✅ `icbm_servo_harness.py`、`sla_loop_harness.py`、`vision_harness.py` | ❌ `find -name '*harness*'` 为空 |
| 渲染冒烟 | 有 | **有且更细**（carrot_tuning / navigation / bluetooth render smoke） |
| carrot 行为测试 | — | 23 文件 / 6633 行（**数量领先**，但侧重服务端行为） |

**为什么"不变量式"测试重要**：它为「新增机制」提供了**可验证的等价性护栏**——证明了 v2 在关闭所有新机制时与 v0 **逐帧相同**，因此任何行为差异都可归因于新机制而非重构副作用。这是 zoompilot 敢于持续调参而不回退的**根本工程保障**。

### 7.2 文档：Constants 表 + Tried-and-rejected + route 锚点

zoompilot `docs/zoompilot/` 的范式（`README.md` 自述 + `mazda-lateral.md:489-544` 实例）：

```markdown
## Constants
| Constant | Value | Measurement | Routes |
| STEER_DELTA_UP/DOWN | 12/12 | delivered step p99+p99.9 = 12, 11.7M frames | corpus; CX-9 2022 62k; CX-5 2022 318k |
| STEER_DRIVER_MARGIN | 2 counts | 0 frames over panda ceiling at 30/50ms staleness | 00000139, 00000148 |
...

## Tried and rejected
- A winddown faster than 12 counts/frame: EPS still walks at 12...
- Gating latch entry on steeringPressed: route 00000148 seg 10 spent 203 frames...
```

**三要素**：①每个常量都有**测量方式**；②每个结论都有 **route ID 锚点**；③**被否决的方案也记录在案**（含否决理由与反例 route）。

对比本项目：`docs/` 23 篇 / 1701 行（多为上游继承），而核心结论堆在 `.workbuddy/memory/MEMORY.md`（16,649 字符）+ 日记（单日最大 140KB）。

**可维护性差异**：

| | zoompilot docs | sp MEMORY.md |
|---|---|---|
| 版本化 | ✅ 随 code 走 | ❌ 不在 git 中 |
| 可 review | ✅ 走 PR | ❌ 不可 |
| route 证据锚点 | ✅ 有 | ⚠️ 部分有 |
| 丢失风险 | 低 | **高**（本文件本轮就因超限被截断） |

### 7.3 参数版本化播种（解决"默认值无法下沉"）

`interfaces.py:33-60` `_seed_mazda_torque_defaults`，注释点明了根因：

> 「**manager_init 会在 card 运行前把声明默认值写到磁盘**，所以'未设置'永不到达此处」（`interfaces.py:38-40`）

因此用**带版本标记**的一次性播种（`params_keys.h:320,322`）：
- `MazdaTorqueDefaultsApplied`（BOOL）：三个开关只播种一次
- `MazdaTorqueTuneSeeded`（FLOAT）：**按值播种** → 后续 tune 版本 bump 可再次覆盖，而**播种后用户自己改的选择被保留**

本项目**无等价机制**（`grep` 为空）。本项目 `params_keys.h` 有 689 个键，此类"出厂默认值"需求只会更多。

### 7.4 CI / hooks

| | zoompilot | sp |
|---|---|---|
| workflows | 24（含 `zoompilot-tests.yaml`、`zoompilot-prebuilt.yaml`、`zoompilot-agnos-tici-boot.yaml`） | 25（含 **`upstream-sync.yml`**、`ai-pr-automation.yml`、`opencode-pr.yml`） |
| commit 规范 hook | ✅ `.githooks/commit-msg`（禁 AI 署名、subject ≤72 字符、禁 em dash、强制 `area:` 前缀） | ❌ 无 |
| 上游自动同步 | ❌ 无 | ✅ **有** |

---

## 八、维度六：zoompilot 相较本项目的具体优点

按"证据强度 × 可迁移性"排序：

| # | 优点 | 证据 | 是否可迁移到丰田 |
|---|---|---|---|
| 1 | **控制层关注点分离**（一文件一关注点 + Ext/Base/Override） | `controls/lib/` 全目录 | ✅ 高 |
| 2 | **行为不变量测试**（v2 ≡ v0 frame-for-frame） | `test_latcontrol_torque_v2.py:120-134` | ✅ 高（方法学） |
| 3 | **限值分类器**治误报 | `steer_limit.py:46-78` | ✅ 中（需重标定） |
| 4 | **控制器仿真台架** | `*_harness.py` ×3 | ✅ 高 |
| 5 | **常量表 + route 锚点 + 否定清单文档范式** | `mazda-lateral.md:489-544` | ✅ 最高（零成本） |
| 6 | **参数版本化播种** | `interfaces.py:33-60` | ✅ 高 |
| 7 | **契约隔离**（嵌套 ZP 结构） | `custom.capnp:474-476,562,607` | ⚠️ 高成本 |
| 8 | **零配置默认值 UX 哲学** | README "recommended setup" | ✅ 高 |
| 9 | **变道平滑**（独立、可配、默认关） | `lane_change_smoothing.py:88-138` | ✅ **可直接移植** |
| 10 | **jetlink 外置算力** | `accelerators/jetlink/` 265KB | ⚠️ 长期项（工程量极大） |
| 11 | **commit-msg hook** | `.githooks/commit-msg` | ✅ 零成本 |
| 12 | **panda↔控制器速率逐帧对齐方法学** | `mazda-lateral.md:59-67` | ✅ 中 |

**注意**：zoompilot 的**纵向层（ICBM/arbiter/handback，投入最大的一块）对丰田 pcmCruise 车型不适用**——这部分不是"优点未利用"，而是**场景不匹配**。

---

## 九、对 21 款威兰达 PHEV 的适用性分析

### 9.1 车型前提核对（来自本项目 opendbc）

| 前提 | 威兰达 PHEV 实际 | 证据 | 对迁移的影响 |
|---|---|---|---|
| 车型已适配 | ✅ `TOYOTA_WILDLANDER_PHEV` | `opendbc/car/toyota/values.py:327-330` | 无需新增指纹 |
| SecOC 平台 | ✅ 是，但**已有 `EPS_BYPASS_SECOC` 绕过** | `values.py:325` + `ToyotaSecOCPlatformConfig.init():149` | **不阻塞横向控制**（转向 EPS 侧已绕过，用户已在实车使用） |
| 转向角控制 / EPS 类型 | 常规丰田 EPS（**非 steer-to-zero**） | 无 `STEER_TO_ZERO_EPS` 概念 | rail schedule / steer-to-zero 专项失效 |
| `STEER_MAX` | **恒定 1500** | `values.py:37` | 无速度相关天花板 → **机制 (a) 不适用** |
| `STEER_DELTA_UP/DOWN` | **15 / 25**，**与速度无关** | `values.py:65-69` | rate-matched 必须按 15/25 重标定 |
| `STEER_ERROR_MAX` | 恒定 350 | `values.py:38` | 无速度相关项 |
| 设定速度归属 | **PCM 掌管**（`pcmCruise` + `pcmCruiseSpeed`） | 本项目既有结论 | zoompilot 纵向层不适用 |
| 转向比例 | `steerRatio = 16.88` | `values.py:329` | 与马自达 18.1 不同，LAF 需重学 |
| `CarSpecs` | mass 4155lb、wheelbase 2.69 | `values.py:329` | 与马自达不同，需重标 |

### 9.2 逐项适用性结论

| zoompilot 机制 | 威兰达 PHEV 结论 | 理由 |
|---|---|---|
| **变道平滑** `lane_change_smoothing.py` | ✅ **可直接移植** | 只依赖 `modelV2` / `CS`，与 EPS 特性和车型无关，且默认关闭、风险可控 |
| **限值分类器** `steer_limit.classify` | ✅ **方法可移植，参数需重标** | 分类逻辑（rate/rail/driver 三分 + 方向性冻结）平台无关；`RATE_STEP_FRACTION=0.9`、`RAIL_EPS=1e-3` 需按丰田 15/25 与恒定 1500 重算；`at_rail` 分支在无 rail schedule 时恒为 `mag >= 1.0 - 1e-3`，语义仍成立 |
| **松开方向盘处理**（`i *= 0.8` + 0.3s ramp） | ✅ **可直接移植** | 只依赖 `steeringPressed` 边沿，与 EPS 无关；对丰田同样能消除"松手瞬间 P 项一次性打满" |
| **曲率缓冲 + 非激活预热** | ✅ **可直接移植** | 纯算法，与车型无关 |
| **滤波 jerk 摩擦输入** | ⚠️ 需重标定 | 依赖 `FRICTION_THRESHOLD=0.3`、`LP_FILTER_CUTOFF_HZ=1.2`，这些是马自达 EPS 实测值；丰田摩擦特性不同 |
| **KD 按压门控** | ⚠️ 需重标定 | `KD_INTERP_SPEEDS/V` 是马自达低速回摆的拟合；丰田低速行为不同 |
| **速度相关扭矩上限** | ❌ **不适用** | 丰田 `STEER_MAX` 恒定、无速度天花板；`get_steer_rail_schedule` 返回 `None` 时 `rail_scale` 恒 1.0，整条路径退化为空操作 |
| **速度分箱自学习** | ⚠️ **可做但需建种子** | 框架可复用，但需为丰田测 7 个区间的 LAF/friction 种子；且因无 rail schedule 会走非 per-count 分支（`latcontrol_torque_ext.py` 的 else 路径），**学习精度下降** |
| **ICBM / cruise_arbiter / stock_ecu_handback** | ❌ **不适用** | 丰田 `pcmCruiseSpeed` 下 arbiter 的 `applicable=False`；PCM 掌管 ACC 加减键 |
| **DEC（dec/dec.py 实现）** | ⚠️ **仅思路可借鉴** | sp 已有不同实现（`DecSignals` + `ModeHysteresis` + carrot 地图减速） |
| **jetlink 外置算力** | 🔷 **概念高价值** | 与车型无关；C3 算力有限，外置推理受益可能比马自达更大；但工程量极大 |
| **契约隔离（嵌套 ZP）** | ⚠️ 高成本 | sp 已有 10 个 carrot ordinal，重构需重新生成 capnp + 全链路回归 |
| **参数播种机制** | ✅ **可直接移植** | 平台无关的 Params 设计模式 |
| **不变量测试 + 台架** | ✅ **方法可直接移植** | 平台无关的测试方法学 |
| **文档范式** | ✅ **零成本可移植** | 纯写作规范 |
| **commit-msg hook** | ✅ **零成本可移植** | 纯工具 |

### 9.3 对威兰达 PHEV 的潜在价值排序

1. **变道平滑** —— 唯一"零标定、纯收益、可开关"的用户可感改进
2. **松手处理 + 曲率缓冲** —— 纯算法，直接改善 MADS 下的人机共驾手感
3. **限值分类法** —— 直接对症本项目「及时接管」类**误报**问题
4. **不变量测试 + 台架** —— 让上述改动能被安全验证、可回滚
5. **参数播种 + 零配置默认** —— 提升出厂体验，减少支持成本
6. **jetlink** —— 长期战略项（C3 算力受限，收益可能最大但工程量也最大）

---

## 十、借鉴清单：优先级与可落地性评估

### P0 —— 高价值 / 低成本 / 低风险（建议立即做）

| # | 建议 | 落地方式 | 成本 | 风险 | 验收标准 |
|---|---|---|---|---|---|
| **P0-1** | **移植 `lane_change_smoothing.py`** | 直接搬文件 + 新增 Params 键 + 设置页入口（默认关）+ 单元测试 | 1–2 天 | **低**（默认关，只影响变道横向） | 单元测试通过；无头渲染冒烟通过；实车开启后变道无明显迟滞 |
| **P0-2** | **引入"限制成因分类"方法学**，套用到本项目「转向超过限制」告警链 | 仿 `steer_limit.py` 写丰田版分类器（重标 15/25、无 rail 分支）；先在告警侧做**分级**（真故障 vs 暂时限制） | 2–4 天 | 中（告警行为变更需实车验证） | 静态分析 + 离线回放 246 路由；告警频次下降且不漏真故障 |
| **P0-3** | **建立 `docs/` 文档范式**（Constants 表 + Tried-and-rejected + route 锚点） | 把 `MEMORY.md` 中**已有 route 证据**的结论迁入 `docs/`；新结论一律按范式写 | 0.5–1 天（起步） | **无** | 至少 3 篇文档按范式落地；MEMORY.md 体积回落 |
| **P0-4** | **移植 `.githooks/commit-msg`** | 抄文件 + `op post-commit` 类安装脚本 | < 1 小时 | **无** | hook 可拦截不合规 commit |

### P1 —— 高价值 / 中成本（近期规划）

| # | 建议 | 落地方式 | 成本 | 风险 | 验收标准 |
|---|---|---|---|---|---|
| **P1-1** | **参数版本化播种机制** | 仿 `_seed_*` + `*Seeded` marker，为丰田/本项目出厂默认值做一次性播种 | 2–3 天 | 低（只写参数） | 新设备首启后默认值正确；用户改过的值不被覆盖 |
| **P1-2** | **控制器不变量测试 + 台架** | 为既有横向控制器建 harness，断言"新机制关闭时与基线逐帧等价" | 1–2 周 | 低（测试代码） | 至少 1 个控制器有 frame-for-frame 等价断言；CI 可跑 |
| **P1-3** | **移植"松手处理 + 曲率缓冲"** | 从 `v2.py:36-37,56-57,93-96` 提取纯算法，接到本项目横向层 | 3–5 天 | 中（控车） | 台架通过 + 实车低速验证；无回摆退化 |
| **P1-4** | **零配置默认值产品化** | 结合 P1-1，把本项目最优设置作为出厂默认 | 2–3 天 | 低 | 新装设备开箱即可用 |

### P2 —— 中价值 / 高成本 / 需专项（中期评估）

| # | 建议 | 落地方式 | 成本 | 风险 | 验收标准 |
|---|---|---|---|---|---|
| **P2-1** | **契约隔离重构**（fork 字段收进嵌套 SP 结构） | 新 ordinal + 重新生成 capnp + 全链路回归 | 2–4 周 | **高**（wire 契约变更） | 全量单测 + 设备端冒烟 + 与 navipilot App 联调通过 |
| **P2-2** | **丰田速度分箱自学习** | 复用框架 + 为丰田测种子（需 route 数据） | 2–4 周 | 中高 | 离线回放验证 LAF/friction 收敛 |
| **P2-3** | **carrot 层与车型控制解耦** | 引入接口层，切断 carrot → opendbc 直接依赖 | 3–6 周 | 中 | 上游同步冲突面下降；单测覆盖 |

### P3 —— 长期探索

| # | 建议 | 说明 |
|---|---|---|
| **P3-1** | **jetlink 式外置算力** | 概念价值高（C3 算力受限），但需评估 `jetlink_repo` 依赖与工程可行性；建议先做**可行性调研**而非开发 |
| **P3-2** | **EPS 天花板实测** | 丰田 `STEER_MAX` 名义恒定，但**实际 EPS 是否有速度相关天花板未知**——若有，则 P0-2 的 `at_rail` 分支价值大增。建议从 246 路由实测 `STEER_RATE` 类信号（若丰田有此报文） |

---

## 十一、本项目应保持的优势（不要为了对齐而丢失）

1. **`upstream-sync.yml` 上游自动同步** —— zoompilot 没有，这是本项目对抗 fork 漂移的核心工程能力
2. **carrot 导航生态**（91 文件 / 28008 行、7705/7706/7709/7710/7711/7713/7714 + 7000 全通道）—— 功能广度远超 zoompilot
3. **配套 App（navipilot）+ 7000 API** —— 完整的端到端产品闭环
4. **`ai/` 自研模块** —— zoompilot 无对应物
5. **CPU 亲和性 / 省电修复** —— 已解决 `EINVAL` 与 isolcpus 保留问题
6. **carrot 行为测试密度**（23 文件 / 6633 行）—— 绝对数量领先

---

## 十二、证据附录（关键文件定位）

### zoompilot

| 模块 | 路径 | 说明 |
|---|---|---|
| 横向 v0 | `openpilot/sunnypilot/selfdrive/controls/lib/latcontrol_torque_v0.py` | 154 行，PID 速度调度基线 |
| 横向 v2 | `.../latcontrol_torque_v2.py` | 171 行，4 个增量机制 |
| 共享扩展 | `.../latcontrol_torque_ext.py` | rail schedule + 速度分箱 |
| 限值分类 | `.../steer_limit.py` | 78 行，`classify()` |
| 变道平滑 | `.../lane_change_smoothing.py` | 138 行 |
| 版本选择 | `.../torque_tune.py` + `latcontrol_torque_versions.json` | v0/v1/v2 |
| 巡航仲裁 | `.../selfdrive/car/cruise_arbiter.py` | 319 行 |
| 按钮伺服 | `.../car/intelligent_cruise_button_management/controller.py` | 316 行 |
| 参数播种 | `.../car/interfaces.py:33-60` | `_seed_mazda_torque_defaults` |
| 契约 | `openpilot/cereal/custom.capnp:474-476,562,607` | 嵌套 `CarStateZP`/`CarControlZP` |
| 加速器 | `openpilot/sunnypilot/accelerators/jetlink/` | 265KB / 34 文件 |
| 不变量测试 | `.../controls/tests/test_latcontrol_torque_v2.py:120-134` | v2 ≡ v0 |
| 台架 | `.../car/tests/{icbm_servo,sla_loop}_harness.py` | 控制器仿真 |
| 文档 | `docs/zoompilot/*.md` | 14 篇 / 3165 行 |
| 许可 | `LICENSE.md`（sunnypilot 约束）+ `NOTICE.md`（自有文件 MIT） | **商用需授权** |

### 本项目 sp（车型前提证据）

| 项 | 路径:行 | 值 |
|---|---|---|
| 车型定义 | `opendbc_repo/opendbc/car/toyota/values.py:327-330` | `TOYOTA_WILDLANDER_PHEV` |
| SecOC 绕过 | `values.py:325` | `flags=ToyotaFlags.EPS_BYPASS_SECOC` |
| SecOC 默认标志 | `values.py:149` | `TSS2｜NO_STOP_TIMER｜NO_DSU｜SECOC` |
| `STEER_MAX` | `values.py:37` | 1500（恒定） |
| `STEER_ERROR_MAX` | `values.py:38` | 350（恒定） |
| 转向速率 | `values.py:65-69` | UP 15 / DOWN 25 |
| 转向比例 | `values.py:329` | 16.88 |
| 契约（现状） | `openpilot/cereal/custom.capnp:542-600` | 直接追加 10 个 ordinal |
| 横向层现状 | `openpilot/sunnypilot/selfdrive/controls/lib/` | 有 v0/ext，**无 v2/steer_limit/lane_change_smoothing** |
| carrot 层 | `openpilot/sunnypilot/carrot/` | 91 文件 / 28008 行 |

---

## 十三、风险与限制声明

1. **静态分析**：本报告全部结论来自代码阅读与文件对比，**未做仿真、未做实车验证**。任何控车改动（P0-1/P0-2/P1-3）**必须**经过台架 → 封闭场地 → 实车分级验证。
2. **zoompilot 子模块缺失**：`opendbc_repo`、`panda` 为空目录，`get_steer_rail_schedule`、`get_speed_dep_config_for_car`、`MazdaFlags` 的具体实现**无法阅读**，相关结论为**基于调用点的语义推断**（已在正文标注）。
3. **许可风险**：zoompilot 整体受 sunnypilot Custom MIT 约束，**商用/闭源需书面授权**；本项目为在售产品，**不得整体搬用**。仅 `Copyright (c) 2026-, Zeph Leggett.` 头文件的自有代码以标准 MIT 提供，可参考但需保留声明。**建议任何代码级借鉴前先做许可合规审查**。
4. **SecOC 说明修正**：威兰达 PHEV 确属 SecOC 平台，但 `EPS_BYPASS_SECOC` 已在位（转向 EPS 侧已绕过），**不构成横向控制的新增阻塞**。
5. **回滚**：本报告未产生任何代码变更，无需回滚。后续落地建议须**逐项独立提交**并保留回滚点。

---

*报告生成：2026-09-30 | 分析依据：E:\zoompilot@develop、E:\sp@test(838cd92b4)*
