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

## 2026-10-23（追加）· cp 重审计（fa32bf598）

- 116 新提交 = 36 docs + 36 cp 硬件专属（Jetson/S3/USB，不适用）+ 44 已吸收/不适用 + **3 实施项**
- 落地：① v_asm_server settings_refresh_lock 串行化整条刷新链 + bsd_generation 代际清除（10cd6868 残余，P0-P2 移植漏掉）② load() 失败预清 net ③ signal_assist_runtime 观测字节缓存（86d1e215）。10/10 测试过，ruff 合规
- 文件级 7 个 cp 独有模块全部核实：sp 均有等价（多数更强）或书面拒绝（cweb_push）
- backlog：proclogd 修剪（低）、radar tools 34 行增量（modelV2 车道线佐证）、Wildlander route 库（高）、pearl eyes（产品决策）
- ⚠️ cp 0611d489 overlay 实验已被 cp 因 C3 闪烁回退——**永远不移植**
- 反向洞察：sp 的 carrot_navi_control type-22 修复 / get_mode_lead_response 接线 / killswitch 门控领先 cp
- 报告：artifacts/cp_reaudit_2026-10-23.md

## 2026-10-23（追加 2）· YOLO 消费层 M1-M3 数据链（7ed16d83a）

- **分工定论**：cp 无 YOLO 检测（其贡献=生命周期基建，已移植）；推理核心全部抠自 Z6 `yolo_hint_server.py`（Detector/Tracker/测距，只抄逻辑不搬文件）；宿主=sp xiaoge_data
- **M1** `xiaoge/yolo_inference.py`（345 行）：letterbox（含 canvas 残影重置坑）+ NMS 0.45 + 11 类 KEEP + HIGH_RISK/VRU/VEHICLE 分离 + REAL_HEIGHT_M 单目测距；焦距构造参数化（C3 ox03c10=_ar_ox_config 2648px，与 Z6 硬编码同值，零标定）；**Y 平面直喂**（不走 Z6 全尺寸 NV12→BGR 的 100ms 坑）；Tracker 纯运动学（IoU 0.15/MAX_MISS 4/α-β/0.8s 预测）+ reset()
- **M2** v_asm_server：`YoloObstacleEnabled`（默认关，需重编 libparams_c.so）；road 线程 lane/YOLO 独立节流+背压互不挤占；切换时 tracker.reset()+清结果（同 BSD 代际纪律）；**payload version 保持 1，yolo 节可选键**（修正原方案"升 version 2"的自相矛盾——version 门会炸旧 reader，可选节则三端无需同 commit）
- **M3**：CarStateSP 追加 @12-16（Present/NearestDist/Block×2/MonoTime；0.0=无效）；xiaoge_vision 校验可选节+写摘要，**card.py 零改动**（复用单写者 apply 路径）
- 模型 `assets/yolov8n_192.onnx`（12.6MB，与 lane.onnx 同级纯二进制）
- 测试 31/31；全量 carrot 回归=既有 PC 环境基线（9 loader errors，零新增）
- **剩余**：M4 HUD overlay（UI 直订 customReservedRawData0 画框）、M5 VRU 门控（25m+方向归属，只禁 desire）、M6 YoloHudEnabled/YoloVruGateEnabled；设备侧：重编 .so → C3 实测 fps≥3 + frameDropPerc + xiaoge RSS（yolov8n-192 预估 50-120ms/帧）
- 注意：远端 test 已含另一会话的 2dc4d8de3，本批叠其上

## 2026-10-23（追加 3）· 修正："xiaoge 没有 yolo"表述错误 + 模型审计

- **onnx 图解析硬证据**：cp v_asm_model(6.2M)=352×352→(1,3) **分类器**；**sp v_asm_model(9.6M)=256×352→(1,299,6) 真 YOLO 检测**（zoompilot merge 带来的，v_asm_inference:136-142 有 (N,6) 解码，class 0 过滤后取 max conf 聚合成盲区占用标量）；Z6 yolo-model(12.6M)=192×192→(1,84,756) COCO 80 类
- **两个 YOLO 有意共存**：wide 盲区=sp v_asm 模型（单类、条带域、图内 NMS），road 障碍物=Z6 模型（11 类、前视域、代码 NMS）。不可互换：单类喂不动 11 类 KEEP/测距表、训练域不同、输出布局不同
- XIAOGE_YOLO_TIMEOUT_NS=1.5s 与 BSD 同值是 cadence 决定（同为 250ms→6 帧窗口），已加注释
- 教训：**判"某模块没有 X"必须看模型本体/资产，不能只 grep 代码字符串**（v_asm 名字掩盖了它已是 YOLO 的事实）

## 2026-10-23（追加 4）· cp xiaoge 分类器同步落地（c6566c65a + PR559 余量）

- **谱系终审修正**："zoompilot 写的新模型"系误判——git blob 谱系证明 sp 的 9.6M 检测版就是 cp 09-28 版（md5 621e8426，逐字节相同），cp 自己在 10-07（212a13a3a=cherry-pick c6566c65a）换成三分类器（6b2b2f4d）。sp 抄的是 cp 换模型之前的版本
- **已同步**（commit 67ffbe9f0 + opendbc a8b81c552）：模型换代 352×352 letterbox+严格 predictions[1]（检测版输出会 raise 而非解码垃圾）、EMA 平滑+相对迟滞（off=threshold-0.15）、阈值 94/范围 0-100、双侧持续 gate（eligibleSides 仅 2.0m 宽度门，去掉变道方向+30-120km/h 速度门，双侧轮转）、per-side 独立新鲜度（updatedMonoTimeNanosBySide 全链路）、推理前后双 generation 检查点、card.py 拆源写 @95-99（与 cp 同 ordinal；有意跳过 customReservedRawData1 心跳服务——carState 同帧携带双源，免新增 cereal 服务）
- **控车影响**：desire_helper 变道禁止+lane_turn_controller 现在吃到"全程双侧"blindspot（之前只有变道中单侧）——真实行为变化，94% 默认阈值压误报
- **环境地雷**：本机 pycapnp 2.2.4/2.1.0 在解析 openpilot 全量 schema 时**非确定性进程 abort**（exit 3，KJ fatal 无 Python 异常；解释器当日被原地升级 3.13.12→3.13.14 所致，重装 pycapnp 无效）→ 全套 carrot discover 收集期即死（opendbc/car/structs.py:10）。测试里加了 win32 条件化 capnp 桩（test_xiaoge_bsd_semantics/lifecycle 的 setUpModule），设备 Linux 不受影响。**设备端部署前必须重编 libparams_c.so（OnnxBsdThreshold 默认值变更）+ capnp 重生成（car.capnp @95-99）+ manager/整车重启**
- 批次 C（xiaoge_data TCP 7711 遥测裁剪）留待拍板：外部 xiaoge 显示设备若在用 7711 会断
