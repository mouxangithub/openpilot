# StarPilot vs 本项目 sp 对比分析报告

**分析对象**
- **StarPilot**：`E:\StarPilot`，分支 `Dom`，remote `github.com/StarPilotHQ/StarPilot`，root LICENSE 为标准 MIT（comma 2018），含 BluePilot/sunnypilot-hkg/jetlink 等来源（CREDITS.md 记录血缘）
- **本项目 sp**：`E:\sp`，分支 `test`（HEAD `6373a9ce7a`），sunnypilot fork，丰田纵深 + carrot 导航 + 自研 `ai/` 模块
- **分析日期**：2026-11-05
- **方法**：纯静态代码分析 + 可复算命令。证据等级：L1=清单 / L2=静态读 / L3=实跑单测 / L4=CI 配置 / L5=复现运行。本报告所有数量统计均为主线程实测，子代理结论已经主理人独立复核（未复跑的项已标注"静态推断"）。

> 注意：StarPilot 的 `flm/README.md` 记录的冻结基线 `latcontrol_vehicle_tunes.py` SHA256 `2a7793c6...` 与本项目同文件（现 SHA `a3279b6e...`）**同源**——两边 FLM 是同一血统的两个演化方向，不是一方向另一方的单向移植关系。

---

## 一、结论先行

| 判断 | 内容 |
|---|---|
| **两者是同源异构** | 同为 openpilot/sunnypilot 二次开发。StarPilot 走**多品牌 + 工程治理纵深**（证据门禁、契约文档、车型安全测试矩阵）；本项目走**丰田纵深 + 生态广度**（carrot 导航、ai/、信号分析工具链） |
| **StarPilot 强在哪** | ①**车型级安全测试矩阵**（safety 测试 196 vs 25 文件，丰田 21 vs 1）；②**可执行契约门禁**（schema_policy / fleet_coverage / vendor check，且真实接 CI）；③**证据工件文化**（CI 留存、拒绝覆盖、`vehicle_qualification: not_established` 诚实声明）；④**模块契约文档**（"这个模块不做什么"写进 README） |
| **本项目强在哪** | ①**验证产物制度**（`docs/validation-artifacts.md` 8 级证据分级 + guard_tests + skip=0 规则，制度上比 StarPilot 严——但缺执行器）；②**AI 协作基建**（13 个嵌套 AGENTS.md / 1088 行，StarPilot 为 0 且主动禁 hook）；③**carrot 导航层 + ai/ 模块 + 信号分析工具链**；④**上游自动同步 workflow**（StarPilot 无 workflow，全人工）；⑤车型数 351 vs 335 |
| **最高价值借鉴** | ①**丰田/SecOC 安全测试**（21 个现成测试覆盖 RAV4_TSS2/RAV4H/RAV4_PRIME/SecOC，含真实 CAN 字节夹具）；②**cereal 保留槽白名单门禁**（实测我们有洞）；③**把 validation-artifacts 制度配上校验器**（S 级成本） |
| **不要搬的** | StarPilot 的 vendored 依赖布局（会丢 submodule 独立发版能力）、344 文件的 flm/ 全量（两边 FLM 都活，血统相同）、galaxy/手机生态（与 carrot 定位重叠且体量大） |
| **意外发现（与对比无关的本项目故障）** | `.github/workflows/upstream-sync.yml` 引用的 **9 个脚本全部不存在**（磁盘无、git 历史从未有过）——该 workflow 当前必然失败 |

---

## 二、规模与结构总览（实测）

| 维度 | StarPilot | 本项目 sp |
|---|---|---|
| 自研代码层 | `openpilot/starpilot/` 50+ 子包，细粒度（lateral/ 60 文件、longitudinal/ 30+、speed_limits/ 21） | `openpilot/sunnypilot/` 13 子包，粗粒度（carrot/ 384 文件为主体） |
| safety 测试 | **196 文件 / 40162 行** | **25 文件 / 9570 行** |
| 特征测试（fork 层） | **249341 行**（starpilot/ 内 test_*.py） | **47417 行**（sunnypilot/ 内） |
| openpilot 测试文件总数 | 1565 | 435 |
| 丰田安全测试 | **21 个**（RAV4_TSS2×3/RAV4H/RAV4_PRIME/PRIUS/SecOC/CAMRY/COROLLA/SIENNA/SDSU/pedal 全覆盖） | **1 个**（上游标准 test_toyota.py 506 行） |
| 真实 CAN 字节夹具测试 | **20** | **2** |
| MISRA 基建 | misra/{checkers,main.c,suppressions,test_misra.sh,test_mutation.py} | **完全相同**（+我们多 safety_replay/helpers.py） |
| 模块契约 .md | 42 篇 / 2817 行（lateral、aol、speed_limits、curve_speed、conditional_mode 各有 README，写明"不做什么"） | 12 篇 / 2998 行（集中在 carrot/sunnylink，controls 层几乎没有） |
| AGENTS.md | **0**（且 `core.hooksPath=/dev/null` 主动禁 hook） | **13 个 / 1088 行** |
| 支持车型 | 335 | **351** |
| 依赖管理 | **vendored 普通目录**（0 submodule）+ `upstream-sync.json` 钉 commit+tree hash | **10 个 git submodule**（指向自有 fork）+ upstream-sync.yml 自动合并 |
| 根 LICENSE | 标准 MIT（comma 2018），第三方集中在 CREDITS.md + THIRD_PARTY_NOTICES.md | sunnypilot 自定义 MIT（商用/闭源需书面授权） |

**安全测试品牌分布**（safety/tests/test_*.py 前缀统计）：

| 品牌 | StarPilot | 本项目 |
|---|---|---|
| hyundai | 44 | 2 |
| gm | 36 | 1 |
| **toyota** | **21** | **1** |
| subaru | 14 | 2 |
| ford | 10 | 1 |
| honda | 9 | 1 |
| volkswagen | 8 | 4 |
| tesla | 8 | 1 |
| chrysler | 4 | 2 |
| mazda | 3 | 1 |

> 结论：MISRA/回放基建两边持平，**差距全部在车型级功能安全测试**。对我们最刺眼的是丰田行：21 vs 1。

---

## 三、值得借鉴（按优先级）

### P0-1 修复本项目自身的 upstream-sync 断链（先于一切对标）

`.github/workflows/upstream-sync.yml` 引用 9 个 `.github/scripts/upstream_sync_*.sh`，全部缺失：
```
$ for s in $(grep -oE "\.github/scripts/[a-z_]+\.sh" .github/workflows/upstream-sync.yml | sort -u); do [ -f "$s" ] || echo "MISSING: $s"; done
→ 9/9 MISSING
$ git log --all --diff-filter=A -- ".github/scripts/"  → 空（从未提交过）
```
该 workflow（workflow_dispatch + repository_dispatch 触发）当前**必然失败**。需确认脚本是丢失还是在别的仓，找回或补写。顺带引入 StarPilot 的 `check_workflows.py`（actionlint + 被引用文件存在性检查）防复发。

### P0-2 丰田/SecOC 安全测试移植（最高价值的跨 fork 借鉴）

StarPilot 的丰田测试直接覆盖我们的主力平台（TOYOTA_RAV4_TSS2/RAV4H/RAV4_PRIME/PRIUS/SECOC_TX_MSGS 实测出现在其测试常量中）。最值得搬的：

| 测试 | 行数 | 验证的安全不变量 | 工作量 |
|---|---|---|---|
| `test_toyota_secoc_aol.py` | 327 | SecOC 平台无 0x3BC GEAR_PACKET，档位须从 0x127 混合动力包读取（含校验和/长度/过期/总线错误拒绝）；AOL 扭矩跟随档位；LTA 保持封锁；radar keepalive 精确且 profile 限定。**用真实 CAN 字节夹具**（REAL_1D3/REAL_620/REAL_262） | **M**（需适配我们的 MADS 而非其 AOL） |
| `test_toyota_rav4h_filter.py` | 268 | RAV4H 原生滤波字精确匹配（0x1449 系），复用真实 Toyota RX fixture，relay 故障/前向黑名单 | S |
| `test_toyota_angle_filter.py` | 24 | 继承完整 LTA/纵向套件 + 原生滤波异常精确性 | S |
| `test_toyota_eps8_sdsu.py` | 148 | EPS8/SDSU pedal 变体的 native word 组合（0x8049~0x8649）与 alternative experience | S-M |
| `test_canpacket_abi.py` | 跨车型 | 编译探针 C 库验证 CANPacket_t 的 sizeof/alignof/offsetof/拷贝语义——防 Python FFI 与 C 结构体布局漂移（我们 libsafety 绑定同有此风险） | S |
| `test_mutation_infra.py` | 跨车型 | 变异测试基础设施自检（我们已有 mutation.py 但无此自检层） | S |

**注意**：这些测试依赖 StarPilot 的 safety model 扩展（AOL hooks 等），直接拷贝不能跑；正确姿势是**按测试意图重写**到我们的 MADS/rx_checks 体系上，夹具字节（真实 SecOC/混合动力帧）可直接复用。

### P1-1 cereal 保留槽白名单门禁（实测我们有洞）

**事实链**（全部实测）：
- openpilot 在 custom.capnp 为 fork 预留槽位（`@0x81c2f05a394cf4af` 等），设计上允许各 fork 共用
- 我们的上游 sunnypilot 已消费 slot 0-9（SelfdriveStateSP/ModelManagerSP/.../ModelDataV2SP），我们的 typeID 全部继承自 sunnypilot——**对上游无风险**
- StarPilot **独立地**用了同一批槽（其 `StarPilotCarControl @0x81c2f05a394cf4af` 与我们 `SelfdriveStateSP` 同 ID）——跨 fork 互为 wire 别名（同 ordinal 解析出不同字段），但这是 fork 生态的设计使然，非 bug
- **真实缺口**：我们的守卫 `openpilot/sunnypilot/carrot/tests/test_capnp_contract_guard.py`（6 测试）只钉了 3 个 carrot 共享 ID + CarState ordinal。若有人往 custom.capnp 加一个占用"我们未用的上游保留槽"（如 `CustomReserved11 @0xc2243c65e0340384`）的结构体，**当前无任何门禁会拦截**（CI 审计员变异测试：6 passed 未抓到；StarPilot 的 policy 抓到）

**借鉴**（取最小版，勿抄其 27KB 手工策略文件）：
1. 写生成脚本从 `custom.capnp`+`log.capnp` 自动产出基线（结构体 ID 清单 + log.capnp 保留 ordinal→typeID 映射 + 上游 schema sha256）
2. 门禁规则：保留槽池封闭白名单（新增顶层结构体必须落在我们自有 ZP 槽或显式登记）、保留 ordinal 不许重定向、上游 schema 改动即报警
3. 基准换成 `commaai/openpilot`（保留槽的真正定义者；我们 `cereal_validation.yaml` 已在 checkout 它，直接接上）
4. **接进 CI**——StarPilot 自己的 `schema_policy.py` 反而没接 workflow（0 引用，只被未接线的 `run_predeploy.py` 引用），这是它该被超越的点

### P1-2 给 validation-artifacts 制度配校验器（S 级，把强项变门禁）

我们的 `docs/validation-artifacts.md` 定义了完整 schema（8 级证据、skip=0、guard_tests 绑定、boundaries 必填、rollback.verified），**制度上严于 StarPilot**（其无任何 `*_validation.json`）。但实测：
```
$ grep -rn "_validation\.json" --include="*.py" --include="*.yml" . | grep -v docs/
→ 仅 radar_validation_replay.py 一处无关引用
$ ls docs/*_validation.json | wc -l  → 1
```
**无任何工具强制执行**。借鉴 StarPilot"门禁即产物生成器"的思想，写 `scripts/lint/check_validation_artifacts.py`：字段完整性、level ≤ 实际证据、skip>0 必带 skip_reason、guard_tests 指向的测试文件必须存在、`baseline_revision` 不得为 "worktree-uncommitted"（现有产物正是这么写的，应改为真实 SHA）。

### P2-1 依赖 provenance 三件套（S+S+S）

不迁移 vendored（会丢 submodule 指向自有 fork 的独立发版能力——C3 适配工作流的核心），只取三层防护：
1. **`upstream-sync.json`**（布局不变）：记 upstream commit + 每 submodule 的 commit + **tree hash**（`git -C <sub> rev-parse HEAD^{tree}`），lint 比对工作区 → 可回答"我们的 opendbc 相对上游 pristine tree 改了什么"，上游合并时 opendbc 不再是盲区
2. **打包器拒 gitlink**：`tools/release/release_files.py` 加 `mode == b"160000"` → raise（约 10 行，抄 StarPilot `:37`）
3. **updater 拒 gitlink 分支**：`updated.py` 配套检查（抄其 `:801` + 3 个单测的思路）

### P2-2 CI 证据工件留存（S）

StarPilot `safety.yaml` 每个 gate `upload-artifact` + `if-no-files-found: error`；`fleet_coverage.py` 用预检+`open("x")` 双层**拒绝覆盖已有证据**。我们 CI 失败时只有会被截断的日志。动作：`tests.yaml` 各 job 加 `upload: always()`；`tools/test_runner.py` 加 `--json-output`（其 records 结构已具备，约 10 行）。

### P3 模块契约文档（每模块 README 写"这个模块不做什么"）

StarPilot 的模块 README 模式：先说边界（"selection.select_limit 不接受速度、不下令、不读设置"），再说契约（数据格式、新鲜度界限、失败语义），最后**自我限定**（"这不构成 X 资格"）。`fleet_coverage.py` 输出永远带 `vehicle_qualification: not_established`——即使全绿。我们 controls 层（latcontrol_vehicle_tunes 4902 行、longitudinal_planner 781 行、speed_limit_resolver 625 行）没有等价文档。**写文档不是抄代码**，成本半天/模块，收益是移植/调参/新人上手时不再需要通读源码确认边界。

### P3 FLM 架构思想（明确不搬代码）

两边 FLM 同源且都活（实测）：
- 我们：`latcontrol_torque.py:17-19` import override 三件套，`:198` 摩擦阈值读取，`:107/116/126` 写入——**override 直达扭矩控制器**
- StarPilot：`latcontrol_torque.py:1` `from openpilot.starpilot.flm import torque_stages as auto_stages`、`:17` `live as flm`、`:68` `GmLiveSource`、`:139-143` `flm.base_threshold/flm.stages/auto_stages.apply_stages`、`:161` `flm.angle_assist`；`controlsd.py:47-49` 接 global_runtime/evidence_hooks/application_wire。其 README 的 "pure, inactive reconstruction" **仅指 Ioniq 6 torque_surface 子模块**，非整个 FLM

可借鉴的是**分层思想**而非 344 个文件：把「扭矩面 surface（可学习参数）」与「施加顺序 stage（固定管线）」与「能力绑定 live（capability→profile 匹配）」与「证据回写 evidence」解耦，使控制律可审计、可单测、可回滚。落点：我们 4902 行的 `latcontrol_vehicle_tunes.py` 在下一次大改时按此四层重组，而不是现在推倒重来。**反向值得学**：他们给每个 FLM 子模块写"本模块不改 PID/不写 Params/不做最终执行器输出"的负面清单，这正是我们 override 字典缺的护栏。

---

## 四、不建议搬的

| 项 | 理由 |
|---|---|
| **vendored 依赖布局** | 我们 submodule 指向 `mouxangithub/*` 自有 fork 并承载 C3 适配独立发版/独立 PR；vendored 化把成本转移到主仓（PR 噪音、体积膨胀）而不消除成本 |
| **galaxy/galaxy_bluetooth/companion 手机生态** | 182 文件 35k 行 + 83 文件 18k 行，与我们 carrot/webui/7000 API 定位重叠；体量远超我们可维护范围 |
| **starport 投屏/蓝牙音频/Spotify（soloist）** | 67 文件，与驾驶安全无关的娱乐层，优先级低 |
| **344 文件 flm/ 全量** | 血统同源、两边都活；全量移植等于把自己已演化的 4902 行换回他们 fork 的版本 |
| **其 27KB 手工 schema-policy.json** | 维护负担高（上游每次升级须人工重审）；用生成脚本自动产出基线替代 |

---

## 五、我们已有对等能力的对照（避免误判"缺失"）

| StarPilot 能力 | 我们的等价物 | 判读 |
|---|---|---|
| capnp 契约守卫 | `test_capnp_contract_guard.py`（3 个共享 ID + ordinal append-only） | 有，但范围窄（见 P1-1） |
| MISRA 套件 | **完全相同**的 misra/ 目录 | 持平 |
| safety_replay | 我们**多**一个 helpers.py | 我们略强 |
| 版本化参数迁移 | `params_migration.py`（版本常量 + 索引映射） | 持平 |
| 限速来源仲裁 | `speed_limit_resolver.py` 625 行（Policy/OffsetType/tiered_offset/vision_limit 合并） | 持平 |
| 证据分级制度 | `docs/validation-artifacts.md` 8 级 + skip=0 + guard_tests | **我们更严**（缺执行器） |
| 上游同步 | `upstream-sync.yml` 自动合并 + OpenCode 解冲突（**脚本断链待修**） | 思路更自动，实现当前不可用 |
| commit-msg hook | `.githooks/commit-msg`（拒 AI 署名/em dash/72 字符）经 `tools/op.sh:223` 安装 | **我们更强**（StarPilot 无且禁 hook） |
| curve_speed | `carrot/curve_speed.py`（三点中值滤波 + 距离包络，文档完整） | 持平 |
| 模块 README | carrot/sunnylink 侧 2998 行 | 分布不同（controls 层缺） |

---

## 六、许可边界（移植前必读）

- StarPilot root LICENSE 是**标准 MIT**（comma 2018），其自有代码 0 个文件带 sunnypilot 自定义许可头（实测）
- 但其**内嵌第三方**须逐个核对：BluePilot lateral v0.2.1（`opendbc_repo/opendbc/bluepilot_lateral/`，MIT + 自有声明）、sunnypilot hkg-angle-steering 血统代码（CREDITS.md 声明"不选择两者许可哪个适用，同时保留"）、jetlink（MIT）、Ultralytics AGNL-3.0 的 V-ASM 模型（**AGPL 传染性**，我们不该碰这个模型）
- **本项目 tree 受 LICENSE.md（sunnypilot 自定义 MIT）约束**：从 StarPilot 拷入的任何文件，其原有声明必须保留并在 NOTICE.md 登记；若拷入文件自身是标准 MIT（如 test_canpacket_abi.py 这类纯 comma 血统文件），与我们 LICENSE.md 并存无冲突，但需按 NOTICE.md 表格登记来源

---

## 七、行动清单（建议排期）

| # | 动作 | 成本 | 优先级 |
|---|---|---|---|
| 1 | 找回/重写 `.github/scripts/upstream_sync_*.sh` 9 个脚本；加 actionlint + 引用文件存在性检查 | M | **P0** |
| 2 | 移植 `test_canpacket_abi.py` + `test_mutation_infra.py`（跨车型，无平台依赖） | S | P0 |
| 3 | 按测试意图重写 `test_toyota_secoc_aol.py` / `test_toyota_rav4h_filter.py` 到 MADS 体系（复用其真实 CAN 字节夹具） | M | **P0** |
| 4 | 保留槽白名单门禁最小版（生成脚本产基线 + 接 CI） | M | P1 |
| 5 | `check_validation_artifacts.py` 校验器 + 补 `baseline_revision` 真实 SHA | S | P1 |
| 6 | `upstream-sync.json`（tree hash）+ 打包器/updater 拒 gitlink | S-M | P2 |
| 7 | CI 工件留存 + test_runner `--json-output` | S | P2 |
| 8 | controls 层三个大文件的契约 README（负面清单式） | S/each | P3 |
| 9 | `latcontrol_vehicle_tunes.py` 下次大改时按 surface/stage/live/evidence 四层重组 | L（缓行） | P3 |

---

## 八、本报告的未验证项

- 所有 L3 结论仅限静态可跑的守卫测试（`test_capnp_contract_guard.py` 6 项曾实跑通过）；**未在任何 fork 上实跑完整 safety 测试套件**（需 Linux + scons 构建）
- StarPilot CI 的实际通过率/时长未查 GitHub API（仅 L4 配置分析）
- `fleet_coverage.py` / `run_safety_qualification.py` 未实跑（需输入工件与 Linux 工具链），其行为描述为 L2 源码精读
- 安全测试的"移植工作量"为静态推断（L2），未经实际移植验证
- 本报告不构成任何"可上车"判断——按本项目 `docs/validation-artifacts.md` 口径，静态分析最高为 L2/L4 级证据，行车结论需 ≥8 级
