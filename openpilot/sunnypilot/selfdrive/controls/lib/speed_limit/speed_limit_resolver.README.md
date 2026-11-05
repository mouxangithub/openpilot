# `sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_resolver.py` — 模块契约（负面清单式）

> 契约文档，非教程。625 行的限速来源仲裁器：把 carState（视觉）、
> Mapbox 地图、carrot 导航三个来源按用户 Policy 合并成单一限速值。

## 这个模块做什么

- `SpeedLimitResolver.update(v_ego, sm)`：每帧收集各来源限速，按
  `Policy`（carState / map / carrot 及其组合）选源，应用 `OffsetType`
  与 tiered offset，输出 `(limit, next_limit, source)` 三元组进
  `longitudinalPlanSP.SpeedLimit`。
- `SpeedLimitChangedAlertTracker`：限速变化提醒的节流/触发状态机。
- 视觉与地图来源的合并遵循 `vision_limit.merge_lower_limit`（取更保守值）；
  carrot 来源是 kph 整数经电话链路，越界（>400 等）按解析错误**拒收而非钳制**
  （钳制会把 400 静默变 250，仍然错）。

## 这个模块**不做**什么（负面清单）

- **不下令减速**。本模块只产出"当前限速是多少"；把限速变成巡航目标的
  速度包络、执行减速在 smart_cruise_control / planner 侧。修改本文件
  不应改变任何纵向执行行为。
- **不接受速度作为输入的选源条件**。Policy 仲裁只看来源可用性与新鲜度
  （`LIMIT_MAX_MAP_DATA_AGE`、GPS service 一致性），不按车速切源。
- **不持久化学习到的限速**。mapbox/carrot 数据只进 `longitudinalPlanSP`
  消息与内存缓存；除 Params 里用户显式配置（offset/tier/policy）外，
  本模块不写任何 param。
- **不验证地图限速的真实性**。Mapbox/carrot 值按"声明即事实"处理，
  仅做范围与新鲜度检查；与视觉冲突时合并策略取更保守值，但不做真值仲裁。
- **不处理龟速/倒车等退化场景**。`v_ego` 只用于 offset 计算与 e2e 联动，
  来源全部失效时输出 unset（`V_CRUISE_UNSET` 语义），由消费方决定回退。

## 契约（数据格式 / 新鲜度 / 失败语义）

- 输出类型：`custom.LongitudinalPlanSP.SpeedLimit`（cereal，字段以 schema
  为准，受 `test_capnp_contract_guard.py` 系保护——本目录不得动 schema）。
- 新鲜度界限：map 数据超龄（`LIMIT_MAX_MAP_DATA_AGE`）即弃用；
  carrot 包带时间戳，`system_time_valid` 为假时**拒收一切带时间语义的来源**
  （防设备时钟未同步时吃过期数据）。
- 失败语义：单来源失效静默降级到剩余来源；全部失效输出 unset，不抛异常、
  不触发 alert 风暴（提醒走 `SpeedLimitChangedAlertTracker` 的节流）。

## 自我限定

本模块全部为 PC 可复算逻辑（guard 测试锁定 tiered offset/合并/拒收行为），
证据 ≤L4。限速值的"正确性"（地图数据是否与实况一致）**不在本模块承诺
范围内**，也不构成任何行车验证资格。
