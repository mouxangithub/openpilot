# `latcontrol_vehicle_tunes.py` — 模块契约（负面清单式）

> 本文件是契约文档，不是使用教程。规则沿用本仓 13 个 AGENTS.md 的精神：
> 先说边界，再说契约，最后自我限定。4902 行的文件，移植/调参/新人上手
> 时应读本文而不是通读源码来确认边界。

## 这个模块做什么

横向控制（FLM，friction learning machine）的**车辆级参数与运行时覆盖表**：

- 每个车型族（Toyota Prius、GM、HKG CANFD、Ioniq 6 2025 等）的摩擦阈值、
  前馈缩放、助力因子等**静态 tune 数据**；
- **运行时覆盖三件套**：`set_flm_runtime_overrides` / `clear_flm_runtime_overrides`
  / `flm_runtime_overrides_active`——FLM 分析器（flm_workspace.py）把学习结果
  写入 `FLMActiveOverrides` param，本模块把它发布成进程级覆盖表；
- 覆盖表被 `latcontrol_torque.py:17-19` 消费，直达扭矩控制律
  （`get_*_friction_threshold` 系列在 `:198` 读取，`:107/116/126` 写入）。

## 这个模块**不做**什么（负面清单）

- **不改 PID / 不做最终执行器输出**。扭矩指令的最终计算、限幅、饱和在
  `latcontrol_torque.py` 与 panda safety 层；本模块只提供参数与阈值。
  修改本文件永远不应改变任何 `steer_torque_cmd_checks` 边界。
- **不写 Params**。运行时覆盖来自 `FLMActiveOverrides` 的**读取**；本模块
  自己不持久化任何参数（学习结果的落盘在 flm_workspace / 分析器侧）。
- **不读 CAN**。所有输入是 `CarState`/数值标量（`v_ego`、`desired_lateral_accel`…）；
  本模块不 import messaging，不订阅任何报文。
- **不校验覆盖值的物理合理性**。`normalize_flm_overrides` 只做结构规范化
  （key 白名单、类型、可 JSON 化），不做安全边界钳制——把摩擦阈值覆盖成
  负数不会被这里拦截，拦截点在消费方与 panda safety。
- **不做车型自动识别兜底**。平台别名（`_CarAlias`）未知时静默返回 None，
  tune 组不命中即回退默认值——这是**有意静默**，不抛异常、不写日志风暴。
- **不承诺线程安全**。override 表是进程级全局；写它的调用方
  （paramsd/FLM 分析器路径）单线程，勿从别处并发调 `set_flm_runtime_overrides`。

## 契约（数据格式 / 新鲜度 / 失败语义）

- 覆盖表结构以 `normalize_flm_overrides` 的 key 白名单为准；结构外的 key
  被丢弃，不报错。
- 新鲜度：`set_flm_runtime_overrides` 是**立即生效、无时间戳**的覆盖；
  清除只能显式 `clear_flm_runtime_overrides` 或进程重启。没有 TTL。
- 失败语义：param 读取失败/为空 → 覆盖不激活（`flm_runtime_overrides_active()`
  返回 False），控制律走静态 tune 默认值，**不降级重启**。
- 冻结基线：本文件历史基线 SHA256 见 StarPilot `flm/README.md` 的同源记录；
  任何大改前先跑 `openpilot/sunnypilot/` 内的 guard 测试与行为对比。

## 自我限定

调参拟合结果经过本模块生效**不构成任何行车验证资格**。按
`docs/validation-artifacts.md` 口径，本模块改动属代码层证据（≤L4）；
宣称"该调参可上车"需要 ≥8 级证据。FLM 四层（surface/stage/live/evidence）
重组为既定架构方向（见 `docs/starpilot-vs-sp-comparison.md` 行动清单 #9），
下次大改时执行，不在小改动里顺手做。
