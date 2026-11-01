"""自动转向灯起源追踪测试（sp 适配版，驱动 desire_lib.auto_signal.AutoSignalTracker）。

cp 同名测试通过完整的 cp DesireHelper（tesla_auto_signals 路径 + per-side FSM +
TeslaTurnSignals 车端灯控制器）驱动 _update_auto_signal。sp 未移植 cp 的 per-side
FSM 与车端灯控制器（desire 红线），起源追踪以独立类挂在 selfdrived 观测层，FSM
输入（lane_change_state、lane_turn_direction 等）由调用方注入。因此这里以最小
harness 直接驱动 Tracker，逐条保留 cp 的行为断言：TBT 转弯几何起始/回正终止、
250m 右转按已行驶距离终止、反向新请求不复用几何、prepare→turn 单次点灯会话、
驾驶员抢灯 abort、无效几何不终止。

未适配项（如实记录）：cp 中经由 App 请求（_auto_app_direction）、TeslaTurnSignals
回声/安全交互、stalk 计数、hazards 互锁的用例依赖 sp 未移植的车端组件与 cp FSM，
无法在本 fork 复现。

在 Windows/非设备环境运行需要 POSIX 与 params 桩（同 test_desire_helper_stalk.py）。
"""
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

from openpilot.cereal import log, custom
from openpilot.selfdrive.controls.lib.desire_lib.auto_signal import AutoSignalTracker

LCS = log.LaneChangeState
LCD = log.LaneChangeDirection
TURN = custom.ModelDataV2SP.TurnDirection


class Harness:
  """Tracker 最小驱动：FSM 输入由测试显式给定（sp 中来自 modelV2/modelDataV2SP/carrotManSP）。"""

  def __init__(self):
    self.tracker = AutoSignalTracker()
    self.lane_change_state = LCS.off
    self.previous_state = LCS.off

  def step(self, atc_type='', lane_turn=TURN.none, driver=0, lamp_left=False, lamp_right=False, speed=25., angle=0.,
           model=None, xturn=0, xdist=0, atc_enabled=None, atc_st=0, lateral=True, gear='drive', valid=True,
           lane_change_state=None, **cs_over):
    cm = NS(atcType=atc_type, xTurnInfo=xturn, xDistToTurn=xdist, carrotCmd='', carrotCmdIndex=0, carrotArg='')
    cs = NS(canValid=valid, leftBlinker=lamp_left, rightBlinker=lamp_right, vEgo=speed, steeringAngleDeg=angle,
            trailerConnected=False, vehicleSensorsInvalid=False, gearShifter=gear, turnSignalDriverValid=True)
    cs.__dict__.update(cs_over)
    self.tracker.update(cs, model if model is not None else NS(), cm, enabled=True, lateral_active=lateral,
                        lane_change_state=self.lane_change_state if lane_change_state is None else lane_change_state,
                        lane_change_direction=LCD.none, lane_turn_direction=lane_turn, driver_st=driver,
                        previous_state=self.previous_state,
                        atc_enabled=bool(lane_turn != TURN.none or atc_st) if atc_enabled is None else atc_enabled,
                        atc_st=atc_st)
    self.previous_state = self.lane_change_state if lane_change_state is None else lane_change_state
    return self.tracker


def turn_model(sign, yaw=.2, heading=.2, length=16):
  """cp 的转向几何：横摆率/航向序列，NS 版（Tracker 用 getattr 读取，兼容 capnp reader）。"""
  return NS(orientationRate=NS(z=[sign * yaw] * length), orientation=NS(z=[sign * heading] * length))


def test_turn_request_issues_and_holds_through_lamp_feedback():
  h = Harness()
  tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  assert tr.auto_signal_direction == LCD.left
  request = tr.auto_signal_request_id
  assert request
  for _ in range(5):
    tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, lamp_left=True)
    assert tr.auto_signal_request_id == request     # 已请求的同向灯不算新请求


def test_driver_abort_clears_and_geometry_does_not_relight():
  h = Harness()
  tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  request = tr.auto_signal_request_id
  assert request
  # 驾驶员抢灯：permitted 失效，请求清零。
  tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, driver=1)
  assert tr.auto_signal_request_id == 0
  # 驾驶员松开、导航仍在：几何未起始（started < 0.3）不会重新点亮同一请求。
  for _ in range(3):
    tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  assert tr.auto_signal_request_id == 0


def test_250m_tbt_request_ends_by_travelled_distance():
  h = Harness()
  tr = h.step(atc_type='turn right prepare', xturn=2, xdist=100)
  assert tr.auto_signal_direction == LCD.right
  request = tr.auto_signal_request_id
  assert request
  for _ in range(5):
    tr = h.step(atc_type='turn right prepare', xturn=2, xdist=80)
    assert tr.auto_signal_request_id == request     # 距离窗内保持
  tr = h.step(atc_type='turn right prepare', xturn=2, xdist=0)
  assert tr.auto_signal_request_id == 0             # 已行驶到弯点：终止
  tr = h.step(atc_type='turn right prepare', xturn=2, xdist=100)
  assert tr.auto_signal_request_id == 0             # 消耗后不得重燃


def test_opposite_navigation_turn_starts_a_new_request_without_reusing_geometry():
  h = Harness()
  h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  request = h.tracker.auto_signal_request_id
  model = turn_model(1)
  for _ in range(10):
    h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=4., angle=90., model=model)
  assert h.tracker._auto_turn_started >= .3         # 几何已按左转起始
  h.step(atc_type='turn right', xturn=2, lane_turn=TURN.turnRight, atc_st=2, speed=4., angle=90., model=model)
  for _ in range(10):
    tr = h.step(atc_type='turn right', xturn=2, lane_turn=TURN.turnRight, atc_st=2, speed=4., angle=90., model=model)
    assert tr.auto_signal_direction == LCD.right
    assert tr.auto_signal_request_id > request
    assert tr._auto_turn_started == 0.               # 几何不复用


def test_turn_completes_only_after_stable_straight_geometry():
  h = Harness()
  h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  request = h.tracker.auto_signal_request_id
  model = turn_model(1)
  for _ in range(10):
    tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=4., angle=90., model=model)
    assert tr.auto_signal_request_id == request
  model = turn_model(1, yaw=.01)
  for _ in range(19):
    tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=5., angle=10., model=model)
    assert tr.auto_signal_request_id == request
  tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=5., angle=10., model=model)
  assert tr.auto_signal_request_id == 0             # 回正稳定 1 秒：结束
  for _ in range(10):
    tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=5., angle=10., model=model)
    assert tr.auto_signal_request_id == 0


def test_invalid_geometry_never_completes_the_turn():
  h = Harness()
  h.tracker._auto_turn_direction = LCD.left
  h.tracker._auto_turn_started = .3
  h.tracker._auto_turn_peak_angle = 90.
  h.tracker._auto_turn_settled = .95
  model = NS(orientationRate=NS(z=[.01] * 15), orientation=NS(z=[0.] * 15))   # 序列过短
  for _ in range(40):
    h.step(speed=5., angle=5., model=model)
    assert h.tracker._auto_turn_direction == LCD.left
    assert not h.tracker._auto_turn_consumed
    assert h.tracker._auto_turn_settled == 0.
  model = NS(orientationRate=NS(z=[float('nan')] * 16), orientation=NS(z=[0.] * 16))
  for _ in range(10):
    h.step(speed=float('inf'), angle=float('nan'), model=model)
    assert h.tracker._auto_turn_settled == 0.


def test_turn_navigation_can_end_before_geometry_settles_and_abort_does_not_relight():
  h = Harness()
  h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  request = h.tracker.auto_signal_request_id
  model = turn_model(1)
  for _ in range(10):
    tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=4., angle=90., model=model)
    assert tr.auto_signal_request_id == request
  # 导航源消失（直道/无类型）：已起始的几何保持灯直至回正。
  for atc_type in ('', 'none', 'none prepare', 'straight', 'straight prepare'):
    for _ in range(20):
      tr = h.step(atc_type=atc_type, speed=4., angle=90., model=model)
      assert tr.auto_signal_request_id == request
  tr = h.step(atc_type='', speed=4., angle=90., model=model, lateral=False)
  assert tr.auto_signal_request_id == 0             # lateral 退出即终止
  tr = h.step(atc_type='', speed=4., angle=90., model=model)
  assert tr.auto_signal_request_id == 0             # 不复燃


def test_navigation_exit_hold_finishes_after_stable_geometry():
  h = Harness()
  h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  request = h.tracker.auto_signal_request_id
  model = turn_model(1)
  for _ in range(10):
    h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=4., angle=90., model=model)
  h.step(atc_type='', speed=4., angle=90., model=model)
  model = turn_model(1, yaw=.01)
  for _ in range(19):
    tr = h.step(atc_type='', speed=4., angle=10., model=model)
    assert tr.auto_signal_request_id == request
  tr = h.step(atc_type='', speed=4., angle=10., model=model)
  assert tr.auto_signal_request_id == 0


def test_turn_preparation_to_turn_keeps_one_lamp_session():
  h = Harness()
  tr = h.step(atc_type='turn left prepare', xturn=1, xdist=100)
  request = tr.auto_signal_request_id
  assert request and tr.auto_signal_direction == LCD.left
  tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  assert tr.auto_signal_request_id == request       # prepare→turn 同一会话
  tr = h.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1)
  assert tr.auto_signal_direction == LCD.left
  assert tr.auto_signal_request_id == request


def test_atc_lane_change_source_latches_from_preparation_and_ends_on_completion():
  h = Harness()
  # cp 分支 c 语义：preLaneChange 锁存方向即发请求；auto_turn_signal（保持锁存）在层里另行控制。
  tr = h.step(atc_type='atc left', atc_enabled=True, atc_st=1, lane_change_state=LCS.preLaneChange)
  request = tr.auto_signal_request_id
  assert request and tr.auto_signal_direction == LCD.left
  h.lane_change_state = LCS.laneChangeStarting
  tr = h.step(atc_type='atc left', atc_enabled=True, atc_st=1, lane_change_state=LCS.laneChangeStarting)
  assert tr.auto_signal_direction == LCD.left
  assert tr.auto_signal_request_id == request
  for _ in range(12):
    tr = h.step(atc_type='atc left', atc_enabled=True, atc_st=1, lane_change_state=LCS.laneChangeStarting)
    assert tr.auto_signal_request_id == request
  h.lane_change_state = LCS.laneChangeFinishing
  tr = h.step(atc_type='atc left', atc_enabled=True, atc_st=1, lane_change_state=LCS.laneChangeFinishing)
  assert tr.auto_signal_request_id == request       # finishing 保持
  h.lane_change_state = LCS.off
  tr = h.step(atc_type='atc left', atc_enabled=True, atc_st=1, lane_change_state=LCS.off)
  assert tr.auto_signal_request_id == 0             # 完成即清零


def test_real_capnp_model_lists_roundtrip():
  # 设备验证备注：capnp 消息构造在开发机（Windows + pycapnp）已实跑通过；
  # 若目标设备 kj abort，保留此用例标注后跳过。
  model = log.ModelDataV2.new_message()
  model.orientationRate.z = [0.2] * 33
  model.orientation.z = [0.2] * 33
  for reader in (False, True):
    h2 = Harness()
    h2.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=5., angle=90.,
            model=model.as_reader() if reader else model)
    tr = h2.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=5., angle=90.,
                 model=model.as_reader() if reader else model)
    assert tr.auto_signal_request_id
    assert tr.auto_signal_direction == LCD.left
    for _ in range(10):
      tr = h2.step(atc_type='turn left', lane_turn=TURN.turnLeft, atc_st=1, speed=5., angle=90.,
                   model=model.as_reader() if reader else model)
    assert tr._auto_turn_started >= .3          # capnp 列表（builder/reader 两种形态）都驱动几何
