# AGENTS-memory — 本仓库的"活的仓库记忆"（追加式）

> 规则：**只追加、不改写**。每条记忆必须带四要素，缺一不收：
> 1. **测量证据**（可复算的命令或测试名 + 输出指纹）
> 2. **边界声明**（结论在什么条件下成立、什么条件下失效）
> 3. **回归数**（相关守卫测试数量；守卫被删即记忆作废）
> 4. **文档引用**（详细报告所在 artifacts/*.md 或 docs/*.md）
>
> 做了实验就要写进来——没有记录等于没做。冲突时以**日期更新**的条目为准。

---

## 2026-10-23 · cp→sp P0-P2 移植批次（A-E）

**范围**：P0-P2 全部实现；每项先核实 sp 侧真实消费点再决定移植/不移植。

### A. 已落地（改动 + 守卫）

| 项 | 文件 | 证据 | 守卫 |
|---|---|---|---|
| UI 渲染诊断 | `openpilot/selfdrive/ui/render_diagnostics.py`（新增） | AST 解析 OK；ruff 0 错 | — |
| UI 主线程调度降级 | `openpilot/selfdrive/ui/carrot_ui_sched.py`（新增） | 同上 | — |
| 参数快照缓存 | `openpilot/selfdrive/ui/carrot_param_cache.py`（新增） | 同上 | — |
| `drop_realtime_safe()` | `openpilot/common/realtime.py`（新增函数） | ruff 0 错 | — |
| 系统监控采样器 | `openpilot/sunnypilot/carrot/system_monitor/`（新增目录） | Windows 导入运行 OK（无 /proc 返回 None 符合预期） | — |
| capnp 契约守卫 | `openpilot/sunnypilot/carrot/tests/test_capnp_contract_guard.py` | **6/6 通过** | 本文件 |
| 几何常量收敛 | `openpilot/sunnypilot/carrot/radar_geometry.py`（单一源） | 2/2 通过 | `test_radar_geometry_constants.py` |
| signal_hud docstring 修正 | `openpilot/selfdrive/ui/sunnypilot/onroad/signal_hud.py` | ruff 0 错 | — |
| 基线 F401 顺手清理 | `openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_planner.py`（删未用 `SpeedLimitAssist` import） | ruff All checks passed | — |

### B. 安全项

| 项 | 结论 | 证据 |
|---|---|---|
| VEgoStopping（cp stopping_params.py） | **不移植**——sp 完全没有 vEgoStopping 生产消费点（`get_accel_from_plan` 无此参数、modeld `get_action_from_model` 无此参数、params_keys.h 未注册）。移植即死代码。文件已按证据移除 | `grep -rn 'vEgoStopping\|VEgoStopping' openpilot/` 除审计清单/safety_guards 白名单外为空 |
| coasting 安全门控 | **已落地**——`LongitudinalPlannerSP._coasting_vetoed()`（planner :298），父类传入 `reset_state`（:149→调用点）。门控内容：reset_state/openpilotLongitudinalControl=False/stick 死区/DEC 强制减速/MpcPlanSource 非 cruise/solution_status 非 0 时退出 coasting | ruff All checks passed；AST 验证依赖属性（CP/_coasting_percent/dec/mpc/output_should_stop/carrot_lane_change_active）全部在父类或本类定义 |

### C. cereal/params 变更

| 项 | 结论 | 证据 |
|---|---|---|
| CarState 新字段 @72-74 | `opendbc_repo/opendbc/car/car.capnp` 追加 `vCluRatio/speedLimitDistance/logCarrot`（**ordinal 只追加**，@71 后）。文本级校验：括号平衡 0、顶层 ordinal 唯一 | `test_capnp_contract_guard.py::test_appended_car_state_ordinals_are_reserved_for_this_fork` |
| vCluRatio 派生 | `opendbc_repo/opendbc/car/interfaces.py` `update()` 统一派生（vEgoCluster/vEgo，>0.5 才生效）；`carrot_functions.py` 两处静默 getattr 改显式读取 | 派生在 CI 层，card 经 `CI.update` 自动获得 |
| logCarrot 写入 | `openpilot/selfdrive/car/card.py` 补写 `CS.logCarrot = self.v_cruise_helper.log`（cruise.py:338 已有 log，此前只读不写） | 消费点 `carrot_man.py` 改为显式 `carState.logCarrot` |
| speedLimitDistance | 保持默认 0 正确——cp 唯一写入方是 Hyundai carstate（车机摄像头 CAN 信号），sp 当前 Toyota/Mazda 无数据源 | `grep -rn 'speedLimitDistance =' /e/cp/opendbc_repo` 仅 hyundai |
| enabled_since 门控 | `openpilot/sunnypilot/carrot/signal_assist_runtime.py`：记录启用时刻，拒绝启用前的陈旧观测（clock skew/残留文件） | **3/3 通过** `test_signal_enabled_since.py`；现有 atomic round-trip 场景验证不受破坏 |
| OnnxBsdEnabled 总开关 | `params_keys.h` 注册（INT 默认 "0"，PERSISTENT|BACKUP）；`v_asm_server.py` PARAM_SETTING_DEFAULTS + 初始化改 unload + 首次刷新按开关 load；`v_asm_inference.py` 加 `unload()` + `load()` 幂等 | **2/2 通过** `test_xiaoge_onnx_lifecycle.py`；推理短路点 :389/:578 均查 `inference.valid`，unload 后自动跳过 |
| ⚠️ libparams_c.so 未重编 | 设备部署前**必须**重编（`OnnxBsdEnabled` 是编译期头），否则 `UnknownKeyName` 打死进程 | 记忆既有 SOP：删 .os + 禁 cache + manager 重启 |

### D. 工程基建

| 项 | 结论 | 证据 |
|---|---|---|
| Web 实时通道分级节流 | `raw_relay.py` 轮询循环接 `device_service_interval()`（含 sp↔cp 别名反查，**cp 节流表用 cp 名而轮询 key 是 sp 名**）；空读相位补偿（有 payload 按分级间隔，空读 5ms 短重试）。默认 0.05s，carrotMan 0.1s / carrotNavi 0.5s / roadCameraState 0.25s | **3/3 通过** `server/tests/test_raw_relay_poll_schedule.py`；7 例别名解析逐一对拍 |
| RADAR_TO_CAMERA 收敛 | `radar_geometry.py` 单一源（1.52m）；生产路径 `carrot_functions.py`、`radar_motion/primary.py` 改引用；`radard.py`（上游树）保留字面量（禁上游→sunnypilot 反向依赖）；离线工具保留字面量（cp 同款取舍） | **2/2 通过** `test_radar_geometry_constants.py`（AST 抠出全部副本对拍） |
| scons_cache_lock | `openpilot/common/scons_cache_lock.py` 移植（纯 stdlib）；`SConstruct` 软接入（try/except，锁失败不阻断构建，`cache_lock_timeout` 可调，默认 120s） | Windows skip（fcntl），设备端真正执行 `common/tests/test_scons_cache_lock.py` |
| display_scheduling / startup_recovery | **不移植**——`DisplayScheduler` 强耦合 cp UI 线程架构（sp 已有 set_core_affinity + ensure_ui_sched_other + hotplug 处理）；startup_recovery 依赖 cp 特有 git 更新流程。移植即无消费者死代码 | `grep` 核实 sp realtime.py `get_available_cores` 已处理 hotplug |

### E. 方法论资产

- 本文件（AGENTS-memory.md）+ `docs/validation-artifacts.md`（验证 JSON 规范）
- 守卫测试合计：capnp 契约 6 例 + 几何常量 2 例 + enabled_since 3 例 + ONNX 生命周期 2 例 + Web 节流 3 例 + scons 锁（设备端）

### F. OnnxBsdEnabled UI 开关（2026-10-23 追问补齐）

| 项 | 内容 | 证据 |
|---|---|---|
| UI 开关 | `carrot_tuning_items.py`「ONNX Vision Detection」区块头部加 `toggle_item_sp(param='OnnxBsdEnabled')`——此前只有 SSH/7000 API 可达（正是该文件注释点名的反模式） | 冒烟 carrot_tuning **21/21 PASSED** |
| zh-CHS/zh-CHT 翻译 | 标题+描述各 2 条 msgid/msgstr；字形零新增（新旧 msgstr 字符集对拍，全部已覆盖，无需动字体） | 冒烟翻译检查 ok；字符集对拍脚本 |
| 冒烟测试 PC 可跑性 | `carrot_tuning`/`bluetooth` 两件冒烟补 PIL 桩（emoji.py 顶层 import PIL，PC 无 pillow）；navigation 本来可跑。基线对照：补桩前两件同炸 PIL=既有环境缺口 | navigation **10/10**、bluetooth exit=0 |
| 类型契约 | INT 注册 + toggle 兼容：`put_bool`→C 层 raw 写 "1"/"0"（绕过 python2cpp 类型校验），`get_bool`→`=="1"`；cp 同为 INT 注册 | params.h:96 `putBool` 直接写字符串 |
| 边界 | pot/en 不手改（既有 5 个 ONNX 字符串本就不在 pot/en，由提取工具再生）；设备端 UI 实测未做 | grep app_en.po 无 ONNX 字符串 |

### 边界声明（本次全部结论适用）

1. **PC 侧限制**：msgq.ipc_pyx 未编 → 纵向 planner 单测 PC 无法跑（基线同炸，非本次改动引起）；pycapnp 加载 schema 崩溃 → capnp 用文本级校验。**实车/设备回归未做**。
2. **未接入项**（数据通道已就绪、UI 消费方待产品决策）：信号灯观察状态接路面渲染（相机帧灯色框）。
3. `params_keys.h` 变更在重编 libparams_c.so + manager 重启前不生效。
4. 全部结论证据等级 ≤ 4（代码审查 + PC 静态/单元验证），**offroad 结论，不构成可上车依据**。
