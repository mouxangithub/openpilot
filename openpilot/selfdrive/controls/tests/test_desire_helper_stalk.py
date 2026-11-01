"""Stalk/lever 与手动灯准入测试（sp 适配版）。

cp 同名测试围绕 cp 的 per-side FSM（stalk 队列、BlinkerLatchedTurn 的机动分类、
queued_lane_change 等）。sp 的 desire_helper 保留自己的回退架构，移植整套 FSM 会
触碰 desire/转向准入红线，因此这里针对 sp 实际拥有的灯效层组件：

- desire_lib.lever：LeverRequestWait（LaneChangeLeverWait 参数的消费类）、
  LaneCrossing、lever_maneuver（模块级行为，与 cp TestLaneChangeLeverWait 等价）。
- desire_lib.boundary_indicator：ManualLaneChangeIndicator 参数链的消费端——
  边界投影准入（min(1.2, 0.9+速率*0.3)）、3 秒重试窗、own/filter_lamp 灯隔离。
- selfdrived.indicator_layer：默认零等价（参数全关时输出全为缺省值）。

未适配项（如实记录）：cp TestDesireHelperStalkRequest / TestBlinkerLatchedTurn
依赖 cp FSM 内部状态（maneuver_type、queued_lane_change、next_lane_change、
turn_disable_count），sp 没有这些状态，无法在不动 desire 的前提下适配。

在 Windows/非设备环境运行需要 POSIX 与 params 桩（libparams_c.so 仅设备编译）。
"""
import math
import sys
import types

for _name in ('fcntl', 'termios'):
  if _name not in sys.modules:
    try:
      __import__(_name)
    except ImportError:
      _m = types.ModuleType(_name)
      _m.ioctl = lambda *a, **k: None
      sys.modules[_name] = _m

if 'openpilot.common.params' not in sys.modules:
  try:
    import openpilot.common.params  # noqa: F401
  except OSError:
    _pm = types.ModuleType('openpilot.common.params')

    class Params:
      def __init__(self, *a, **k):
        pass

      def get_bool(self, key, **kw):
        return False

      def get_int(self, key, **kw):
        return 0

      def get_float(self, key, **kw):
        return 0.0

      def get_str(self, key, **kw):
        return None

      def get(self, key, **kw):
        return None

    _pm.Params = Params
    sys.modules['openpilot.common.params'] = _pm

from types import SimpleNamespace as NS

from openpilot.cereal import log

from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_lib.lever import (
  LEVER_LATCHED, LEVER_ONE_TOUCH, LEVER_RELEASED, LaneCrossing, LeverRequestWait, lever_maneuver,
)
from openpilot.selfdrive.controls.lib.desire_lib.boundary_indicator import BoundaryIndicator


class TestLeverRequestWait:
  """LaneChangeLeverWait：被阻塞的一触请求保持 5 次闪灯后放弃（模块级，等价 cp 语义）。"""

  def make(self):
    return LeverRequestWait(), NS()

  def feed(self, lw, seconds, press=False, lever=LEVER_RELEASED, lamp_side=1, state=log.LaneChangeState.preLaneChange):
    out = False
    for _ in range(round(seconds / DT_MDL)):
      if press:
        lw.__init__()
        press = False
        lw.update(True, 1, lever, lamp_side, state)  # press edge frame
        continue
      out = lw.update(True, 0, lever, lamp_side, state)
    return out

  def test_blocked_request_holds_then_gives_up(self):
    lw, _ = self.make()
    lw.update(True, 1, LEVER_RELEASED, 1, log.LaneChangeState.preLaneChange)
    assert not self.feed(lw, 4.0 - DT_MDL)
    assert self.feed(lw, 0.2)                       # 5 次闪灯后放弃（灯仍亮时返回 True）
    assert not lw.update(True, 0, LEVER_RELEASED, 0, log.LaneChangeState.preLaneChange)  # 灯灭后复位

  def test_clearing_within_the_wait(self):
    lw, _ = self.make()
    lw.update(True, 1, LEVER_RELEASED, 1, log.LaneChangeState.preLaneChange)
    self.feed(lw, 2.0)
    lw.update(True, 0, LEVER_RELEASED, 1, log.LaneChangeState.laneChangeStarting)   # 请求已开始：撤销等待
    assert lw.side == 0
    assert lw.update_hold(log.LaneChangeState.laneChangeStarting, 1) == 0

  def test_a_new_press_restarts_the_count(self):
    lw, _ = self.make()
    lw.update(True, 1, LEVER_RELEASED, 1, log.LaneChangeState.preLaneChange)
    self.feed(lw, 3.0)
    lw.update(True, 1, LEVER_RELEASED, 1, log.LaneChangeState.preLaneChange)        # 新按压：计时重启
    assert not self.feed(lw, 3.0)

  def test_latched_lever_clears_the_request(self):
    lw, _ = self.make()
    lw.update(True, 1, LEVER_LATCHED, 1, log.LaneChangeState.preLaneChange)
    assert lw.side == 0                             # 杆保持是驾驶员自己持灯：无超时请求
    assert lw.update(True, 0, LEVER_LATCHED, 1, log.LaneChangeState.preLaneChange) is False

  def test_disabled_resets(self):
    lw, _ = self.make()
    lw.update(True, 1, LEVER_RELEASED, 1, log.LaneChangeState.preLaneChange)
    lw.update(False, 0, LEVER_RELEASED, 1, log.LaneChangeState.preLaneChange)
    assert lw.side == 0 and lw.gave_up is False


class TestLaneCrossing:
  """模型车道线重标记（NEAR_M 内贴近 + JUMP_M 跳变）判定中心已越线。"""

  def model(self, left_y, right_y=-1.9):
    # LaneCrossing 读取 laneLines[1]（左）/laneLines[2]（右），要求 ≥3 条线。
    return NS(laneLines=[NS(y=[left_y - 3.5]), NS(y=[left_y]), NS(y=[right_y])])

  def test_relabel_after_close_approach_fires(self):
    crossing = LaneCrossing()
    for y in (-1.3, -0.9, -0.5, -0.34):
      assert crossing.update(self.model(y), left=True) < 0.0
    assert crossing.update(self.model(-2.5), left=True) == 0.0    # 重标记跳变：越线时刻
    assert crossing.update(self.model(-2.6), left=True) == DT_MDL

  def test_no_crossing_without_a_close_approach(self):
    crossing = LaneCrossing()
    for y in (-2.0, -2.5, -3.0):
      assert crossing.update(self.model(y), left=True) < 0.0

  def test_missing_lane_lines_never_fires(self):
    crossing = LaneCrossing()
    assert crossing.update(NS(), left=True) < 0.0


class TestLeverManeuver:
  """BlinkerLatchedTurn 速度门（模块级）：门限以下仅强转手势判 turn，其它杆位判变道。"""

  def test_above_speed_is_always_lane_change(self):
    assert lever_maneuver(LEVER_LATCHED, 15.0, 50 / 3.6) == ("lane_change", False)

  def test_forced_gesture_is_a_turn_below_speed(self):
    assert lever_maneuver(LEVER_LATCHED, 10.0, 50 / 3.6, forced_turn=True) == ("turn", False)

  def test_one_touch_is_undecided_below_speed(self):
    assert lever_maneuver(LEVER_ONE_TOUCH, 10.0, 50 / 3.6) == ("lane_change", True)
    assert lever_maneuver(LEVER_LATCHED, 10.0, 50 / 3.6) == ("lane_change", False)

  def test_off_disables_the_rule(self):
    assert lever_maneuver(LEVER_LATCHED, 1.0, 0.0) == (None, False)


class TestBoundaryIndicatorManualRequest:
  """ManualLaneChangeIndicator 消费端：边界投影准入、3 秒重试、灯隔离。"""

  NOW0 = 1000.0

  @staticmethod
  def cs(now, torque=1.0, pressed=True):
    return NS(canValid=True, gearShifter='drive', trailerConnected=False, steerFaultTemporary=False,
              steerFaultPermanent=False, vEgo=10.0, steeringTorque=torque, steeringPressed=pressed,
              leftBlinker=False, rightBlinker=False, blinkerLever=0, steeringAngleDeg=0.0,
              laneLineInfoMonoTime=int(now * 1e9), leftLaneLine=11, rightLaneLine=11)

  @staticmethod
  def md(frame, inner_left, right):
    """内车道线贴近（inner_left: -1.8 -> 0-），右线同速率外移，外线/路缘保持刚性车道。"""
    def line(off):
      return [off - 0.1 * k for k in range(9)]
    return NS(frameId=frame,
              laneLines=[NS(y=line(inner_left - 3.5)), NS(y=line(inner_left)), NS(y=line(right)), NS(y=line(right + 3.5))],
              laneLineProbs=[0.8, 0.8, 0.8, 0.8],
              roadEdges=[NS(y=line(inner_left - 3.0)), NS(y=line(right + 3.0))],
              roadEdgeStds=[0.1, 0.1])

  def approach(self, boundary, frames, start_frame=0, torque=1.0):
    """喂一段接近几何；返回 (期间出现过的请求方向, 首次请求时刻, 结束时刻)。

    请求窗口只有 0.2 秒（cp：request_time 过期即清零），必须逐帧采集。
    """
    now = self.NOW0 + start_frame * DT_MDL
    direction, request_time = 0, 0.0
    for j in range(frames):
      inner = -1.8 + 0.05 * j
      right = 1.9 + 0.05 * j
      boundary.update(now, self.cs(now, torque=torque), self.md(start_frame + j, inner, right),
                      enabled=True, valid=True, busy=False)
      if boundary.request_direction and not direction:
        direction, request_time = boundary.request_direction, boundary.request_time
      now += DT_MDL
    return (direction, request_time), now

  def calm(self, boundary, seconds, start_frame):
    now = self.NOW0 + start_frame * DT_MDL
    for j in range(round(seconds / DT_MDL)):
      boundary.update(now, self.cs(now, torque=0.0, pressed=False), self.md(start_frame + j, -0.6, 2.0),
                      enabled=True, valid=True, busy=False)
      now += DT_MDL
    return now

  def ramp(self, boundary, start_frame, from_inner=-0.6, from_right=2.0):
    """把几何从静止位渐变到接近起点（每帧 ≤0.4 m，避免触发 2 秒 relabel 门）。"""
    now = self.NOW0 + start_frame * DT_MDL
    for j in range(5):
      f = (j + 1) / 5.0
      inner = from_inner + (-1.8 - from_inner) * f
      right = from_right + (1.9 - from_right) * f
      boundary.update(now, self.cs(now), self.md(start_frame + j, inner, right),
                      enabled=True, valid=True, busy=False)
      now += DT_MDL
    return start_frame + 5

  def test_boundary_projection_admits_the_request(self):
    boundary = BoundaryIndicator()
    (direction, request_time), _ = self.approach(boundary, 40)
    assert direction == 1
    assert math.isfinite(request_time) and request_time > 0
    # 灯反馈隔离：本侧灯被 own() 屏蔽，另一侧放行。
    assert boundary.filter_lamp(1) == 0
    assert boundary.filter_lamp(2) == 2

  def test_three_second_quiet_gate_before_a_retry(self):
    boundary = BoundaryIndicator()
    (_, first_time), now = self.approach(boundary, 40)
    assert first_time > 0
    # 收敛后进入静止：episode 超时结束，request_direction 过期清零。
    now = self.calm(boundary, 1.0, 40)
    assert boundary.request_direction == 0
    # 3 秒静默窗内的新接近不得再次准入。
    start_frame = round((now - self.NOW0) / DT_MDL)
    (retry_direction, _), _ = self.approach(boundary, 20, start_frame=start_frame)
    assert retry_direction == 0
    # 静默窗之后（且灯已暗 1 秒）新的接近重新准入；先渐变锚定几何避免 relabel 门。
    now = self.calm(boundary, 3.4 - (now - (self.NOW0 + start_frame * DT_MDL)), start_frame + 20)
    start_frame = self.ramp(boundary, round((now - self.NOW0) / DT_MDL))
    (direction, retry), _ = self.approach(boundary, 30, start_frame=start_frame)
    assert direction == 1 and retry > first_time

  def test_disabled_never_requests(self):
    boundary = BoundaryIndicator()
    self.approach(boundary, 40)
    boundary.update(self.NOW0 + 2.0, self.cs(self.NOW0 + 2.0), self.md(40, -0.5, 1.9),
                    enabled=False, valid=True, busy=False)
    # cp 语义：enabled=False 只停新检测；已 own 的隔离（blocked）按 12 秒独立寿命保留。
    assert boundary.request_direction == 0
    assert boundary.blocked == 1 and boundary.isolate_until > self.NOW0 + 2.0


class TestIndicatorLayerBypass:
  """默认零等价：三个参数全关时观测层旁路，全部输出保持 capnp 缺省值。"""

  def test_disabled_layer_outputs_defaults(self):
    from openpilot.selfdrive.selfdrived.indicator_layer import IndicatorLayer
    layer = IndicatorLayer(params=__import__('openpilot.common.params', fromlist=['Params']).Params())
    layer.update(None, None)
    assert layer.manual_lane_indicator == 0
    assert layer.observed_indicator == 0 and layer.observed_indicator_source == ''
    assert layer.indicator_isolation_mask == 0
    assert layer.indicator_prepare_direction == 0 and layer.indicator_prepare_source == ''
    assert layer.auto_turn_signal == 0 and layer.auto_turn_signal_lane_change is False
    assert layer.auto_signal_direction == 0 and layer.auto_signal_request_id == 0
    assert layer.enabled is False
