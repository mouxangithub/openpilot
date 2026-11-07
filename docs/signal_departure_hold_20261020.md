# 停车红灯记忆在离开停车速度后退役 — 2026-10-20

## 现象与根因

两条辅助红灯闸门（`signal_assist.SignalAssist` 的 `hold`、`signal_start_guard.SignalStartGuard`
的 `hold`）只在**静止**时上锁，却没有任何速度上界。跟随前车通过停车点时，`carrot_functions`
里 `lead_in_stop_range` 只是**逐帧** `replace(decision, hold=False)`，闸门内部的
`self.hold` / `self.commited` 一直为真。前车一走开、车已在路速，`lead_in_stop_range`
失效，旧记忆立刻把 `signal_hold` 重新拉高：

```python
if signal_hold:
  self._x_state = XState.e2eStopped
  self._actual_stop_distance = 0.0
  stop_dist = 0.0
  v_cruise = 0.0
```

即**在任意车速把目标速度压 0、停车距离压 0**。另外 `SignalStartGuard.update` 的时钟回滚
分支返回 `StartDecision(self.hold, ...)`，即回滚时保留旧 hold，同样会在路速重挂。

上游 navipilot 在同一族代码上记录了一次真实故障（`988b4623c`）：76.5 km/h 处 planner
目标 −4.4967 m/s²、carOutput −4.0、实测 −3.6156 m/s²，故障前 6.45 s 内 74 条观测全是空
track —— 说明这不是新证据，是残留的停车记忆。我们的两份闸门与该修复前的代码同构，所以
本仓库存在同一缺陷。

## 改动

1. `sunnypilot/carrot/signal_assist.py` 新增 `departed_signal_stop(speed)`：`|v| > 5 km/h`
   即视为已离开停车/蠕行阶段。`SignalAssist.update` 在 `_observe` **之前**退役旧 hold，
   因此本帧不会从旧记忆报红，之后重新停车必须重新确认。
2. `sunnypilot/carrot/signal_start_guard.py` 在**时钟回滚检查之前**退役，缺观测 / 上下文
   无效 / 回滚都无法把旧 hold 留在路速。退役判据额外要求 `self.hold` 为真：未上锁的行驶
   进入仍走原有 `moving_no_entry` 分支（那里同样会 reset），公开 reason 保持兼容。
3. `sunnypilot/carrot/carrot_functions.py` 新增 `_signal_stop_owned` 所有权位与
   `_retire_departed_signal_stop(v_ego)`：闸门注入的 `e2eStopped` 必须随 latch 一起退役，
   否则会出现"latch 没了但注入的停车还在"的孤儿状态。退役块放在 `_update_x_state` 之前
   （我们的注入在 `update()` 末尾，与上游位置相反）。显式驾驶员停车（`_user_stop_distance`）
   与 `_carrot_stay_stop` 保留所有权。
4. 最终输出闸门：`signal_hold` 在 `|v| > 5 km/h` 时被释放，不再进入上面那个无条件压 0
   的分支。只释放信号 veto，**不**撤销 MPC / 模型障碍物 / 前车已经请求的刹车。

保留的行为：低速丢 lead 后重新挂停、正常前车障碍、之后再次停车时新红灯需新确认、同灯绿色
确认、mode 0、道路类别策略、mode 2 的预减速。

## 5 km/h 这个边界的含义

它**只是作用域上限**，不是"判断路口是否已通过"的新检测器。与既有 stop/prepare 转换同一
量级。超过它不代表绿灯，也不授予加速；只是说明"停车记忆不再是证据"。

## 验证

- `openpilot/sunnypilot/carrot/tests/test_signal_departure.py`：22 例，覆盖边界值、蠕行保留、
  丢 lead 后不得重挂、之后的 fresh moving-red 仍可请求模型距离停车、回滚不得重挂、无效
  上下文仍退役、重新停车需新确认、`_signal_stop_owned` 的 11 种所有权组合（含禁用的闸门
  不得留孤儿 stop、反向运动、NaN 速度不算离开）。
- 本机 `unittest discover -s openpilot/sunnypilot/carrot`：521 → 564 例，errors 13 → 13
  （全部为既有的缺 opendbc/zstandard），其中新增 11 例在本机 skip、在车机执行。
- 车机（`comma@192.168.7.233`，`c2df04b19`）：三个新模块合跑 **51/51 通过，0 skip**（含
  `CarrotPlanner._retire_departed_signal_stop` 的 11 例所有权组合）。carrot 全套
  **610 例全绿**。
- 未做：路测、真实红灯光学输入回放、closed-loop 轨迹对比。设备 `SignalAssistMode=0` 时整条
  信号控制链休眠，本次改动对现车行为无影响；**打开 mode 2 之前必须补齐上述车机验证**。

## 回滚

单一 commit 内三处退役 + 一道输出闸门，`git revert` 即可；不涉及参数、capnp 或进程拓扑。
