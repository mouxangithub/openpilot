# cp × zoompilot 结合路径分析（2026-09-30）

> 决策输入文档。承接 `docs/cp-to-sp-borrow-analysis.md`（cp → sp 借鉴）与 `docs/zoompilot-vs-sp-comparison.md`（zoompilot vs sp 对比）。  
> 本文回答：**E:/cp 与 E:/zoompilot 如何结合，以及结合产物如何回灌本项目 sp**。  
> 基准：cp = `E:/cp`（CarrotPilot，分支 `carrot-wip`）；zoompilot = `E:/zoompilot`（分支 `develop`）；sp = `E:/sp`（分支 `test`）。  
> ⚠️ 本文为**纯静态分析**，未改码、未验证。

---

## 0. 结论速览

| # | 判断                                                          | 依据                                                                                                                          |
| - | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1 | **cp 与 zoompilot 基座不同**，不是同一 upstream 的两个分支                 | cp 基于 `commaai/openpilot`（纯 MIT）；zoompilot 基于 `sunnypilot`（Custom MIT）                                                      |
| 2 | **两者已有一个天然交集：jetlink**                                      | cp `third_party/jetlink/jetlink/protocol.py` 与 zoompilot `jetlink_repo` 作者头均为 `Copyright (c) 2026-, Zeph Leggett.`，**同源代码** |
| 3 | **结合的正确形态不是"代码合并"**，而是 **cp 当能力源、zoompilot 当方法学源、sp 当集成宿主** | 三者基座/许可/车型互斥，直接 merge 会产生不可维护的三方冲突                                                                                          |
| 4 | **最高价值的结合点是 jetlink 加速器**                                   | cp 有完整客户端+服务端+多后端（ORT/TinyGrad/TRT）；zoompilot 有 sunnypilot 侧抽象层 `accelerators/`；sp **两者都没有**                                |
| 5 | **cp 的第二价值是纵向栈**（sp 完全缺失）                                   | cp `controls/lib/` 有 cutin/fast_radar/gap_recovery/preview/stopping_lead/turn_accel，sp 全无                                   |
| 6 | **zoompilot 的价值在方法学而非代码**                                   | 限值分类、不变量测试、参数播种、文档范式均可移植；但代码受 Custom MIT 约束+马自达专有                                                                           |

---

## 一、三方身份对照（关键：基座不同）

| 维度              | **cp**（CarrotPilot）                                  | **zoompilot**                                | **sp**（本项目）                             |
| --------------- | ---------------------------------------------------- | -------------------------------------------- | --------------------------------------- |
| 仓库              | `E:/cp`，remote `ajouatom/openpilot`                  | `E:/zoompilot`，remote `zoompilot/zoompilot`  | `E:/sp`，remote `mouxangithub/openpilot` |
| 分支              | `carrot-wip`（rolling）                                | `develop`                                    | `test`                                  |
| **upstream 基座** | **`commaai/openpilot`**（README:11,114 明示）            | **`sunnypilot`**（README:3 明示）                | **`sunnypilot`**                        |
| 目标车型            | **现代 / 起亚 / 捷尼赛思**                                   | **马自达 CX-5 / CX-9**                          | **丰田**（威兰达 PHEV 等）                      |
| 命名空间            | `openpilot/selfdrive/carrot/`（**无** `sunnypilot/` 层） | `openpilot/sunnypilot/accelerators/`         | `openpilot/sunnypilot/carrot/`          |
| **许可证**         | **MIT**（`LICENSE` = Comma.ai 2018）                   | sunnypilot **Custom MIT**（商用需授权）             | sunnypilot **Custom MIT**               |
| 自有代码许可          | —                                                    | `Copyright (c) 2026-, Zeph Leggett.` 部分为 MIT | —                                       |
| carrot 层体量      | **314 文件 / 124,731 行**                               | 无 carrot 层                                   | 91 文件 / 28,008 行                        |
| server 层体量      | **30,818 行**                                         | 无                                            | 5,349 行                                 |

> **第一个关键认知**：cp 不是"另一个 sunnypilot fork"，而是**从 openpilot 直接分叉的独立项目**。这解释了为什么 sp 移植 cp 的 carrot 层是"移植"而非"同步"——两边**没有共同祖先的 sunnypilot 基线**。

---

## 二、cp ↔ zoompilot 的天然交集：jetlink

这是本次分析最重要的发现。

### 2.1 证据：同一作者，同源代码

```
cp:        third_party/jetlink/jetlink/protocol.py
           """Copyright (c) 2026-, Zeph Leggett. This file is part of jetlink..."""
           MAGIC = 0x4B4E4C4A  # b'JLNK'   VERSION = 2   HEADER_SIZE = 32

zoompilot: jetlink_repo  (submodule → github.com/zoompilot/jetlink.git)
           openpilot/sunnypilot/accelerators/jetlink/backend.py
           """Copyright (c) 2026-, Zeph Leggett. This file is part of zoompilot..."""
           from jetlink.comma import gadget
```

**`zoompilot/jetlink.git` 子模块 = cp `third_party/jetlink` 的同源上游**。两者共享 wire protocol（同一个 `JLNK` magic、同一个 32 字节 header）。

### 2.2 但两侧的**集成方式完全不同**（这正是结合的重点）

| 维度            | cp 的集成                                                                                                                      | zoompilot 的集成                                                                                                        |
| ------------- | --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 客户端位置         | `openpilot/selfdrive/modeld/jetlink/`（`link.py`/`daemon.py`/`mac.py`/`warp.py`/`phase.py`）                                  | `openpilot/sunnypilot/accelerators/jetlink/`（`backend.py`/`model_state.py`/`linking.py`/`provision.py`）              |
| 抽象层           | **无**（modeld 直接调 jetlink）                                                                                                   | **有** `sunnypilot/accelerators/__init__.py`——薄门面，`present()/ready()/progress()/enabled()`，UI 5Hz 轮询，**无硬件时返回否定默认值**  |
| 主机侧           | `third_party/jetlink/jetlink/server/`（ORT / **TinyGrad** / **TensorRT** 三后端 + Metal）                                        | `jetlink_repo`（同源）                                                                                                   |
| 硬件目标          | **Jetson**（`tools/jetlink/inspect_jetson.py`、`requirements-jetson.txt`）+ **Cinque v2**                                      | **Mac / Jetson / NVIDIA Linux / iPhone** + **Cinque v3**                                                             |
| 与 chestnut 关系 | Jetson 为独立路径                                                                                                                | **明确声明**：`chestnut` 走原生，`accelerators` 只在没有板子时介入（`if chestnut_present(): native elif accelerators.ready(): jetlink`） |
| 文档沉淀          | `docs/jetlink_*.md` **10 篇**（deployment_review / apple_feasibility / boot_optimization / sd_image / updates / mac_testing…） | `CHANGELOG.md` 一段 + `docs/zoompilot/` 少量                                                                             |
| CI            | `.github/workflows/jetlink-checks.yaml`                                                                                     | 无专门 workflow                                                                                                         |
| 测试            | `test_jetlink.py` / `test_jetlink_mac.py` / `test_jetlink_phase.py`                                                         | `accelerators/tests/`（6 文件，含 `test_comma_layer.py` **守卫"不 import 重量级模块"**）                                           |

### 2.3 结论：jetlink 是"结合"的最佳切入面

```
        ┌─────────────────────────────────────────┐
        │  zoompilot/jetlink.git  （同源 wire 协议）  │
        └─────────────────────────────────────────┘
                    ▲                    ▲
        ┌───────────┘                    └───────────┐
        │                                            │
   【cp 集成】                                  【zoompilot 集成】
   客户端 + 服务端多后端                          sunnypilot 侧薄抽象层
   3 个后端 + Metal                              present/ready/progress 否定默认
   Jetson / Cinque v2                            Mac / Jetson / iPhone / Cinque v3
   docs 10 篇 + CI + 3 组测试                    accelerators 抽象 + 惰性 import 守卫
        │                                            │
        └────────────────┬───────────────────────────┘
                         ▼
              【sp 需要的"结合产物"】
         多后端服务端（cp）+ 抽象接入层（zoompilot）
                    = 完整的 jetlink 方案
```

**两侧严格互补**：cp 强在**工程落地**（多后端、多硬件、CI、文档、测试），zoompilot 强在**架构接入**（对 sunnypilot 友好的抽象层 + 惰性加载 + 否定默认值）。sp 若要做 jetlink，**应当从 cp 取服务端、从 zoompilot 取接入层**，而不是二选一。

---

## 三、能力矩阵：cp / zoompilot / sp 三方互补关系

| 能力域                       | cp                                         | zoompilot                 | sp                                             | 结合建议                       |
| ------------------------- | ------------------------------------------ | ------------------------- | ---------------------------------------------- | -------------------------- |
| **jetlink 加速器（服务端+后端）**   | ✅ 完整（ORT/TinyGrad/TRT/Metal）               | ⚠️ 仅接入层                   | ❌ **无**                                        | **<u>cp 服务端 + zp 接入层</u>** |
| **jetlink 接入抽象**          | ❌ 无                                        | ✅ `accelerators/`         | ❌ **无**                                        | 取 zp                       |
| **纵向增强栈**                 | ✅ 完整（见 §4）                                 | ⚠️ 马自达专有 ICBM/arbiter     | ❌ **无 cutin/fast_radar/preview/stopping_lead** | **取 cp**                   |
| **横向扭矩调校**                | ⚠️ 韩系 `latcontrol_torque.py`               | ✅✅ v0/v1/v2 + steer_limit | ⚠️ 仅 v0/ext                                    | **取 zp 方法学**               |
| **carrot web 前端**         | ✅ 563 文件 / 150,197 行                       | ❌ 无                       | ⚠️ 91 文件 / 28,008 行                            | 按需取 cp                     |
| **cluster（仪表盘 UI）**       | ✅ 44 文件 / 70,623 行                         | ❌ 无                       | ❌ 无                                            | **取 cp**（对威兰达有实际价值，见 §6）   |
| **radar 层**               | ✅ `carrot/radar/` 406 行 + can_batch        | ❌ 无                       | ⚠️ `radar_motion/`                             | 取 cp                       |
| **realtime 层（native 加速）** | ✅ `compact_state.py` 652 行 + **850 行 C++** | ❌ 无                       | ⚠️ `raw_protocol.py`                           | 取 cp（性能关键）                 |
| **多后端模型服务**               | ✅ ORT/TinyGrad/TRT                         | ❌                         | ❌                                              | 取 cp                       |
| **行为不变量测试**               | ⚠️ 有测试但非不变量式                               | ✅ `v2≡v0 frame-for-frame` | ❌                                              | **取 zp 方法学**               |
| **控制器仿真台架**               | ⚠️                                         | ✅ 3 个 harness             | ❌                                              | **取 zp 方法学**               |
| **参数版本化播种**               | ❌                                          | ✅ `_seed_*` + marker      | ❌                                              | **取 zp**                   |
| **Constants+route 文档范式**  | ⚠️ docs 多但无此范式                             | ✅✅ 14 篇带 route 锚点         | ❌                                              | **取 zp**                   |
| **契约隔离（嵌套 SP 结构）**        | ⚠️ `custom.capnp` 271 行                    | ✅ `CarStateZP` 嵌套         | ⚠️ 直接追加 ordinal                                | **取 zp 思路**                |
| **上游自动同步**                | ❌                                          | ❌                         | ✅ `upstream-sync.yml`                          | **sp 已有，保持**               |
| **调参项体系**                 | ✅ **186 项** + 4 组 menu                     | ⚠️ 少量                     | ⚠️ 84 项无 UI 入口                                 | 取 cp（原有分析已定）               |
| **多语言文档**                 | ✅ 韩/英/中                                    | ❌                         | ❌                                              | 可选参考                       |

---

## 四、重点：cp 的纵向增强栈（sp 的完全空白）

这是 sp 相对 cp 的**最大结构性缺口**。核验结果：

```
cp:  openpilot/selfdrive/controls/lib/
  longitudinal_cutout.py          31 行
  longitudinal_fast_radar.py     270 行
  longitudinal_gap_recovery.py   155 行
  longitudinal_preview.py        308 行
  longitudinal_stopping_lead.py  133 行
  cutin_alert.py                  69 行
  cutin_helpers.py               483 行
  cutin_predecel.py               70 行
  turn_accel.py                  110 行
  lane_planner_2.py              291 行
  cruise_coasting.py              ???
  ldw.py / lateral_planner.py     ???

sp:  openpilot/selfdrive/controls/lib/
  longcontrol.py / longitudinal_planner.py / longitudinal_mpc_lib  ← 仅上游基础
  （以上 cp 独有文件全部不存在）
```

**逐项意义**：

| cp 模块                                                       | 作用                                 | 对威兰达 PHEV 的价值                        |
| ----------------------------------------------------------- | ---------------------------------- | ------------------------------------ |
| `longitudinal_fast_radar.py`                                | 快速雷达融合（低延迟前车）                      | ⚠️ 威兰达用 PCM/原厂雷达，需评估                 |
| `cutin_helpers.py` + `cutin_predecel.py` + `cutin_alert.py` | 加塞识别 + 预减速 + 告警                    | ✅ **高**——加塞预减速是纯策略层，与车型无关            |
| `longitudinal_gap_recovery.py`                              | 跟车距离恢复                             | ✅ 中                                  |
| `longitudinal_preview.py`                                   | 纵向前瞻                               | ✅ 中（与 sp 的 carrot 曲线减速可能重叠）          |
| `longitudinal_stopping_lead.py`                             | 前车停止处理                             | ✅ **高**——直接对症此前"停止/起步"体验             |
| `turn_accel.py`                                             | 转弯加速                               | ✅ 中                                  |
| `lane_planner_2.py`                                         | 车道规划 v2                            | ⚠️ 评估与 carrot 车道封锁的关系                |
| `driving_mode.py`（carrot 下）                                 | Eco/Safe/Normal/High 四模式 + 交通流持久证据 | ✅ **高**——sp 的 `EcoMode` 已有雏形，cp 是完整版 |

> **注意**：cp 是韩系车专用，其 cutin/radar 参数针对现代起亚调过。**策略层可借，参数层必须重标**。这与 zoompilot 的情况同构（马自达参数不能直接用）。

---

## 五、结合方案：三种路径对比

### 方案 A：代码合并（❌ 不推荐）

把 cp 与 zoompilot 代码 merge 成一个仓库。

**否决理由**：

1. **基座不同**——cp 基于 openpilot，zoompilot 基于 sunnypilot，无共同祖先，merge 即冲突风暴
2. **许可冲突**——cp 是 MIT，zoompilot 整体是 Custom MIT（商用需授权），合并后整体许可被污染
3. **车型互斥**——韩系 vs 马自达，两套车型适配代码无交集
4. **本项目在售**——引入 Custom MIT 代码有合规风险

### 方案 B：能力汇编（✅ 推荐）

**不与任一项目合并，而是把 cp / zoompilot 当"能力源"，由 sp 按能力域分别取材。**

```
【cp：能力源 · MIT · 可直接用】
  ├─ jetlink 服务端 + 多后端（ORT/TinyGrad/TRT）
  ├─ 纵向增强栈（cutin / fast_radar / preview / stopping_lead / gap_recovery / turn_accel）
  ├─ cluster 仪表盘（44 文件 / 70,623 行）
  ├─ radar 层（406 行 + can_batch）
  ├─ realtime native 加速（850 行 C++）
  └─ 调参项体系（186 项 + menu）

【zoompilot：方法学源 · 部分 MIT · 需许可审查】
  ├─ accelerators 抽象层（jetlink 接入的正确形态）★ 自有文件 MIT
  ├─ 横向扭矩 v0/v2 分层 + steer_limit 分类法
  ├─ 行为不变量测试（v2≡v0 frame-for-frame）
  ├─ 控制器仿真台架（3 个 harness）
  ├─ 参数版本化播种（_seed_* + marker）
  ├─ 契约隔离（嵌套 CarStateZP）
  └─ Constants + route 锚点文档范式

           ↓ 汇聚 ↓

【sp：集成宿主 · 已有 upstream-sync + carrot 生态 + ai/ 模块】
```

### 方案 C：上游化（⚠️ 长期）

把 cp / zoompilot 的能力**先上游化到 sunnypilot**，再由 sp 通过 `upstream-sync.yml` 自动同步。

- 优点：一次投入，长期零成本同步；符合开源协作
- 缺点：依赖上游接受度；周期长
- 建议：**作为方案 B 的延伸**——先在 sp 内部验证成熟，再向上游提 PR

---

## 六、对威兰达 PHEV 的实际收益评估

| cp / zoompilot 能力          | 威兰达 PHEV 适用性       | 收益                                | 落地难度        |
| -------------------------- | ------------------ | --------------------------------- | ----------- |
| **jetlink 外置算力**           | ✅ 车型无关             | ⭐⭐⭐ C3 算力受限，外置推理收益**可能比韩系/马自达更大** | 高（需硬件 + 工程） |
| **cluster 仪表盘**（胎压/导航/前车）  | ✅ 车型无关（读 cereal）   | ⭐⭐ 补充仪表显示，cp 已有 70K 行成熟实现         | 中           |
| **纵向 cutin 预减速**           | ✅ 策略层可移植           | ⭐⭐⭐ 加塞预减速是**纯策略**，不依赖车型           | 中（需重标参数）    |
| **纵向 stopping_lead**       | ✅ 策略层可移植           | ⭐⭐ 与既有"停止/起步"体验直接相关               | 中           |
| **driving_mode 四模式**       | ✅ 车型无关             | ⭐⭐ sp `EcoMode` 的完整版              | 低           |
| **realtime native 加速**     | ✅ 平台相关（C3 arm64）   | ⭐⭐ 缓解此前定位的 **core 4 满负荷**问题       | 中高（需编译）     |
| **zoompilot 限值分类法**        | ⚠️ 需重标 15/25       | ⭐⭐ 治「及时接管」类误报                     | 中           |
| **zoompilot 横向 v2 机制**     | ⚠️ 部分可移植           | ⭐⭐ 变道平滑、松手处理可直接用                  | 低-中         |
| **cp radar 层**             | ⚠️ 韩系 radar CAN 专有 | ⭐ 需评估威兰达 CAN 结构                   | 高           |
| **zoompilot ICBM/arbiter** | ❌ PCM 掌管设定速度       | —                                 | 不适用         |

> **一个重要交叉发现**：sp 既有问题是「card/selfdrived/controlsd 全绑 core 4，实测 99.3% 单核」导致 `selfdrivedLagging`。cp 的 **realtime native 加速层**（`compact_state_native.cc` 850 行 C++）思路正好对症——**把热路径下沉到 C++**。这条此前在 cp→sp 分析里没被识别。



---

## 七、结合实施路线（分阶段）

### 阶段 0：决策与合规（先做，1–2 天）

1. **许可尽调**：明确 sp 作为在售产品可用的代码范围
   - ✅ cp 代码：MIT，可用
   - ⚠️ zoompilot 代码：整体 Custom MIT，**仅 `Copyright (c) 2026-, Zeph Leggett.` 头文件可参考**
   - ⚠️ jetlink：`Copyright (c) 2026-, Zeph Leggett.` → **自有文件 MIT**（cp 的 `third_party/jetlink` 头即为此）
2. **确认硬件**：是否引入 eGPU/Jetson/Cinque 硬件（决定 jetlink 是否立项）

### 阶段 1：低风险高收益（1–2 周）

| 项 | 来源 | 落点 | 说明 |
|---|---|---|---|
| 调参项 UI 补全 | cp | sp `carrot_tuning_items.py` | 承接原分析（84 项已注册仅差 UI） |
| `driving_mode` 四模式 | cp | sp carrot | 纯策略、车型无关、sp 已有 EcoMode 雏形 |
| 文档范式迁移 | zoompilot | sp `docs/` | 零成本，含 Constants 表 + route 锚点 |
| commit-msg hook | zoompilot | sp `.githooks/` | 零成本 |
| 不变量测试方法学 | zoompilot | sp 测试 | 为既有控制器建等价性护栏 |

### 阶段 2：纵向栈补齐（3–6 周）

| 项 | 来源 | 前置条件 |
|---|---|---|
| `cutin_helpers` + `cutin_predecel` + `cutin_alert` | cp | 参数重标（韩系 → 丰田） |
| `longitudinal_stopping_lead` | cp | 与 PCM 纵向交互验证 |
| `longitudinal_gap_recovery` | cp | — |
| `turn_accel` | cp | — |
| 横向：变道平滑 + 松手处理 | zoompilot | 低风险可直接移植 |

### 阶段 3：平台能力（2–3 月，需专项）

| 项 | 来源 | 说明 |
|---|---|---|
| **jetlink 接入** | **cp 服务端 + zoompilot 接入层** | 需硬件决策 |
| cluster 仪表盘 | cp | 44 文件 / 70K 行，按需裁剪 |
| realtime native 加速 | cp | 对症 core 4 满负荷 |
| radar 层 | cp | 需威兰达 CAN 适配 |

### 阶段 4：上游化（长期）

把阶段 1–3 中通用性强的部分（jetlink 抽象、不变量测试、纵向策略、文档范式）**提 PR 到 sunnypilot**，再由 `upstream-sync.yml` 自动同步，形成"一次投入、长期受益"的闭环。

---

## 八、风险与回滚

| 风险 | 等级 | 缓解 |
|---|---|---|
| **许可污染**（引入 Custom MIT 代码到在售产品） | **高** | 阶段 0 尽调；优先用 cp（MIT）；zoompilot 只取方法学与自有 MIT 文件 |
| **基座漂移**（cp 基于 openpilot，与 sp 的 sunnypilot 基线持续分化） | 高 | 不整层移植，只取独立模块；每次移植记 `docs/` 并标注来源 commit |
| **参数错配**（韩系/马自达参数用于丰田） | **中高** | 策略层与参数层**分离移植**；参数必须重标 + 实车验证 |
| **车型专有耦合**（radar/cluster 读韩系 CAN） | 中 | 先做可行性核验（威兰达是否有对应报文）再动手 |
| **三方命名空间冲突**（cp `selfdrive/carrot/` vs sp `sunnypilot/carrot/`） | 中 | 移植时统一到 sp 命名空间，不保留 cp 路径 |
| **上游同步冲突**（新增模块与 upstream 合并冲突） | 中 | 新模块放 fork 专属目录，避免改 upstream 文件 |

**回滚策略**：每项独立 commit + 独立 Params 开关（默认关）+ 保留原实现。控车相关项必须台架 → 封闭场地 → 实车分级验证。

---

## 九、直接回答"怎么结合"

**一句话**：不要让 cp 和 zoompilot 互相合并 —— 它们基座不同（openpilot vs sunnypilot）、车型互斥（韩系 vs 马自达）、许可不同（MIT vs Custom MIT）。**正确做法是让二者共同服务于 sp**：

1. **cp 是"能力源"**（MIT 可直接用）：取它的 **jetlink 服务端与多后端**、**纵向增强栈**（sp 完全空白）、**cluster**、**realtime native 加速**
2. **zoompilot 是"方法学源"**（需许可审查）：取它的 **jetlink 接入抽象层**、**横向扭矩分层与限值分类**、**不变量测试与台架**、**参数播种**、**文档范式**
3. **二者的真正结合点在 jetlink**——cp 出服务端、zoompilot 出接入层，**拼起来才是 sp 需要的完整方案**。这是唯一一个"cp 和 zoompilot 直接互相结合"成立的地方，因为两者共享同源 wire protocol（同一作者 Zeph Leggett）
4. **sp 是集成宿主**：用已有的 `upstream-sync.yml` + carrot 生态 + ai/ 模块做承载，新增模块放 fork 专属目录避免上游冲突

**优先级**：阶段 0 合规尽调（**必须先做**）→ 阶段 1 低风险项（调参 UI / driving_mode / 文档范式 / hook）→ 阶段 2 纵向栈 + 横向方法学 → 阶段 3 jetlink / cluster / native 加速 → 阶段 4 上游化。

---

## 十、证据索引

| 结论 | 证据路径 |
|---|---|
| cp 基于 openpilot 非 sunnypilot | `E:/cp/README.md:11,114,197`；`E:/cp/pyproject.toml` 无 sunnypilot；`find -name sunnypilot` 为空 |
| cp 许可 = MIT | `E:/cp/LICENSE:1` = `Copyright (c) 2018, Comma.ai, Inc.` |
| zoompilot 基于 sunnypilot | `E:/zoompilot/README.md:3` |
| zoompilot 许可 = Custom MIT | `E:/zoompilot/LICENSE.md:3` |
| jetlink 同源 | `E:/cp/third_party/jetlink/jetlink/protocol.py` 作者头 = `Copyright (c) 2026-, Zeph Leggett.`；`E:/zoompilot/.gitmodules:24-26` → `zoompilot/jetlink.git` |
| jetlink wire 协议 | `E:/cp/third_party/jetlink/jetlink/protocol.py` `MAGIC=0x4B4E4C4A` / `VERSION=2` / `HEADER_SIZE=32` |
| zoompilot 加速器抽象 | `E:/zoompilot/openpilot/sunnypilot/accelerators/__init__.py`（`present/ready/progress/enabled`，chestnut 优先） |
| zoompilot jetlink 接入 | `E:/zoompilot/openpilot/sunnypilot/accelerators/jetlink/backend.py:21` `from jetlink.comma import gadget` |
| cp jetlink 客户端 | `E:/cp/openpilot/selfdrive/modeld/jetlink/{link,daemon,mac,warp,phase}.py` |
| cp jetlink 多后端 | `E:/cp/third_party/jetlink/jetlink/server/backends/{ort,tinygrad,trt}/` |
| cp jetlink 文档 10 篇 | `E:/cp/docs/jetlink_*.md` |
| cp jetlink CI | `E:/cp/.github/workflows/jetlink-checks.yaml` |
| cp 纵向栈 | `E:/cp/openpilot/selfdrive/controls/lib/{longitudinal_*,cutin_*,turn_accel,lane_planner_2}.py` |
| sp 缺纵向栈 | `E:/sp/openpilot/selfdrive/controls/lib/` 仅 `longcontrol.py`/`longitudinal_planner.py`/`longitudinal_mpc_lib` |
| cp carrot 体量 | `E:/cp/openpilot/selfdrive/carrot/` = 314 文件 / 124,731 行 |
| cp server 体量 | `E:/cp/openpilot/selfdrive/carrot/server/` = 30,818 行；sp = 5,349 行 |
| cp cluster | `E:/cp/openpilot/selfdrive/carrot/cluster/` = 44 文件 / 70,623 行（含 `CUTIN_VALIDATION.md`） |
| cp web 前端 | `E:/cp/openpilot/selfdrive/carrot/web/` = 563 文件 / 150,197 行 |
| cp radar 层 | `E:/cp/openpilot/selfdrive/carrot/radar/` = 406 行（`radarcan.py`/`radard_dpath.py`/`can_batch.py`） |
| cp realtime native | `E:/cp/openpilot/selfdrive/carrot/realtime/compact_state_native.cc` = 850 行 C++ |
| cp driving_mode | `E:/cp/openpilot/selfdrive/carrot/driving_mode.py`（Eco/Safe/Normal/High） |
| cp 调参 186 项 | `E:/cp/openpilot/selfdrive/carrot_settings.json`（`params` 186 项 + 4 组 `menu`） |
| sp 独有优势 | `E:/sp/.github/workflows/upstream-sync.yml`；`E:/sp/openpilot/sunnypilot/carrot/` 91 文件；`E:/sp/ai/` |

---

*分析时间：2026-09-30 | 基准：cp@carrot-wip(2b491763) · zoompilot@develop(c9a482071) · sp@test(838cd92b4)*
*本报告为纯静态分析，未做仿真或实车验证。*
