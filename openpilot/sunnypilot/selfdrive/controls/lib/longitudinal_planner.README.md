# `sunnypilot/selfdrive/controls/lib/longitudinal_planner.py` — 模块契约（负面清单式）

> 契约文档，非教程。781 行的 SP 纵向规划包装层，负责把 carrot 导航、
> 限速辅助、e2e、coasting 等 SP 扩展源仲裁成 MPC 可消费的目标速度/加速度。
> 移植或调参前先读本文确认边界。

## 这个模块做什么

- `LongitudinalPlannerSP`：在上游 `LongitudinalPlanner` 之上叠加 SP 的
  目标仲裁——cruise candidate 仲裁（`arbitrate_cruise_candidate`）、
  coasting 否决（`_coasting_vetoed`：reset_state / 非 cruise 源 /
  solution_status != 0 / stick 死区）、e2e 目标（`update_e2e_target`）、
  信号灯准备（`apply_signal_prepare`）、max_accel / cruise target 覆盖。
- 输出经 `longitudinalPlanSP`（cereal）对外发布；MPC 消费的是**本模块
  仲裁后的目标**，不是任何单一来源的原始值。

## 这个模块**不做**什么（负面清单）

- **不执行 MPC**。规划求解在上游 `LongitudinalPlanner`/mpc；本模块只在
  目标进入 MPC 前做仲裁与修饰。MPC 解不收敛（`solution_status != 0`）
  的处理是**否决扩展源**（如 coasting），不是重试求解。
- **不做执行器侧安全检查**。加速度限幅、AEB、gas/brake 执行边界在
  上游 planner、longitudinal 控制器与 panda safety；本模块的
  `get_max_accel_override` 等输出**不是安全边界**，是偏好值。
- **不直接写 Params**（构造期读配置除外）。运行期状态只进 cereal 消息，
  不持久化——重启即回到默认仲裁行为，这是有意设计。
- **不仲裁横向**。signal/转向相关只处理纵向目标里需要的部分；
  MADS / 横向状态机不在本文件。
- **不信任陈旧观测**。enabled_since 门控（guard:
  `test_signal_enabled_since`）拒绝信号灯启用前的陈旧观测；
  lead 有效性（`_has_valid_selected_lead`）同理。新接入的扩展源必须
  遵守同一新鲜度纪律，禁止绕过。
- **不覆盖限速显示**。速度限制的解析在 `speed_limit/`（见其契约文档）；
  本模块只消费其结果参与纵向目标仲裁。

## 契约（数据格式 / 新鲜度 / 失败语义）

- 输入：`SubMaster`（modelV2、radarState、carState、carControl、
  selfdriveStateSP、longitudinalPlanSP、carrot 导航包等）。所有源按
  openpilot 标准新鲜度语义（`sm.valid` + frame age）检查。
- 失败语义：任何扩展源不可用/过期 → 仲裁回退到上游默认行为；
  `_to_float(value, default)` 吞掉类型异常转默认值——**扩展链路的垃圾
  输入不允许产生异常上抛**，但必须可被 cereal 输出观测到。
- guard 绑定：coasting 否决与 enabled_since 门控的行为由
  `openpilot/sunnypilot/carrot/tests/` 内 guard 测试锁定；删除 guard
  即本模块行为契约作废。

## 自我限定

本模块的仲裁逻辑通过单元测试（≤L4 证据）不构成任何行车验证资格；
`before_after` 类结论必须按 `docs/validation-artifacts.md` 走
process_replay（≥L6）+ 实机（≥L7）才能宣称行为改善。
