"""Turn-signal origin tracking (cp desire_helper._update_auto_signal / _update_auto_turn_geometry).

sp 的 DesireHelper 保留自身的回退 FSM，灯效观测层挂在 selfdrived（SelfdriveState 的
构造发布点）。本模块把 cp 的起源追踪（TBT 转弯 / ATC 变道 / 250m 右转 / 模型观测）
拆成独立类：FSM 输入（lane_change_state、lane_turn_direction 等）由调用方注入，
自身只做灯效遥测，绝不产生 desire / actuation / 转向准入输入。
"""
import math
import time

from openpilot.cereal import custom
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_lib.constants import (
  BLINKER_NONE, BLINKER_LEFT, LaneChangeState, LaneChangeDirection,
)

# sp 的 desire_lib.constants 把 TurnDirection 别名为 log.Desire；而
# modelDataV2SP.laneTurnDirection 是 custom.ModelDataV2SP.TurnDirection，
# 两个 capnp 枚举不能混比，这里固定用后者。
TurnDirection = custom.ModelDataV2SP.TurnDirection

# cp ATC 语义：转弯类（含 prepare）与激活转弯类。
ATC_TURN_PREPARE_TYPES = ("turn left", "turn right", "turn left prepare", "turn right prepare")
ATC_TURN_ACTIVE_TYPES = ("turn left", "turn right")
# 起源标注（/dev/shm/carrot-indicator-display.json 的 origin 词表，见 common/indicator_display.py）。
ORIGIN_TURN = 'turn'
ORIGIN_TBT = 'tbt'
ORIGIN_LANE = 'lane'


class AutoSignalTracker:
  """纯灯效的自动转向灯起源追踪。输出 auto_signal_direction / auto_signal_request_id。

  - TBT 转弯：carrot atcType 的 turn(±prepare) 源，转向几何（角度+横摆率）起始与
    稳定回正终止，导航切换时重置几何。
  - 250m 分支：xTurnInfo=1/2 且距离窗口 min(250, max(40, vEgo*8+20)) 内按已行驶
    距离（xDistToTurn 递减）给出灯请求，出窗即终止。
  - ATC 变道：preLaneChange 期间锁存方向，跨越 starting/finishing 保持。
  - 驾驶员抢灯：driver_st 非零即 permitted 失效（abort）；同向准备态移交
    （turn_handoff）不算新请求；几何回正才结束（回正区分）。
  """

  def __init__(self):
    self.auto_signal_direction = LaneChangeDirection.none
    self.auto_signal_request_id = 0
    self._auto_signal_counter = time.monotonic_ns()
    self._auto_lane_completed = False
    self._auto_lane_direction = LaneChangeDirection.none
    self._auto_turn_consumed = False
    self._auto_atc_type = ""
    self._auto_turn_direction = LaneChangeDirection.none
    self._auto_turn_started = 0.0
    self._auto_turn_peak_angle = 0.0
    self._auto_turn_settled = 0.0
    # 250m TBT 源的距离保持：请求由距离窗给出后，分支 a 的导航匹配只在窗内保持。
    self._auto_tbt_hold = False
    self.last_origin = ''  # 最近一次 direction 的起源（turn/tbt/lane），供显示层使用

  def reset(self):
    enabled_direction = self.auto_signal_direction
    self.__init__()
    self.auto_signal_direction = enabled_direction

  def _update_auto_turn_geometry(self, carstate, modeldata):
    if self._auto_turn_direction == LaneChangeDirection.none:
      return
    # Cap'n Proto lists support iteration and integer indexing, but not slicing.
    rates = list(getattr(getattr(modeldata, "orientationRate", None), "z", ()) or ())
    headings = list(getattr(getattr(modeldata, "orientation", None), "z", ()) or ())
    signed_angle = getattr(carstate, "steeringAngleDeg", float("nan"))
    angle = abs(signed_angle)
    if (len(rates) < 16 or len(headings) < 16 or
        not all(math.isfinite(v) for v in (*rates[:16], *headings[:16], angle, carstate.vEgo))):
      if self._auto_turn_started < 0.3:
        self._auto_turn_started = 0.0
      self._auto_turn_settled = 0.0
      return
    moving = carstate.vEgo > 1.0
    turn_sign = 1 if self._auto_turn_direction == LaneChangeDirection.left else -1
    if moving and signed_angle * turn_sign > 20 and rates[5] * turn_sign > 0.1:
      self._auto_turn_started = min(0.3, self._auto_turn_started + DT_MDL)
      self._auto_turn_peak_angle = max(self._auto_turn_peak_angle, angle)
    elif self._auto_turn_started < 0.3:
      self._auto_turn_started = 0.0
    # This lamp-only completion must not inherit the steering FSM's early
    # turn-disable heuristic, nor mistake a stopped/slow corner for straight.
    settled = (self._auto_turn_started >= 0.3 and moving and
               angle <= min(20, self._auto_turn_peak_angle * 0.25) and
               max(abs(v) for v in rates[:16]) < 0.05 and abs(headings[15] - headings[5]) < 0.06)
    self._auto_turn_settled = self._auto_turn_settled + DT_MDL if settled else 0.0
    if self._auto_turn_settled >= 1.0:
      self._auto_turn_consumed = True
      self._auto_turn_direction = LaneChangeDirection.none

  def update(self, carstate, modeldata, carrot_man, *, enabled, lateral_active, lane_change_state, lane_change_direction,
             lane_turn_direction=TurnDirection.none, driver_st=BLINKER_NONE, previous_state=LaneChangeState.off,
             atc_enabled=False, atc_st=BLINKER_NONE, tesla_brand=False, forced_window=False):
    """每个模型帧调用一次（DT_MDL 节奏）。

    tesla_brand=True 时与 cp 相同要求 carState.turnSignalDriverValid 才信任驾驶员
    灯语义；其它品牌无该信号时退回灯位判定（遥测层，不影响任何准入）。
    """
    if not enabled:
      if self.auto_signal_direction != LaneChangeDirection.none:
        self.__init__()
      return
    atc_type = str(getattr(carrot_man, "atcType", "") or "")
    direction = LaneChangeDirection.none
    origin = ''
    turn_type = atc_type in ATC_TURN_PREPARE_TYPES
    navigation_direction = (LaneChangeDirection.left if turn_type and atc_type in ("turn left", "turn left prepare")
                            else LaneChangeDirection.right if turn_type else LaneChangeDirection.none)
    turn_handoff = atc_type in ATC_TURN_ACTIVE_TYPES and self._auto_atc_type == atc_type + " prepare"
    if atc_type != self._auto_atc_type:
      if navigation_direction not in (LaneChangeDirection.none, self._auto_turn_direction):
        self._auto_turn_direction = LaneChangeDirection.none
        self._auto_turn_started = self._auto_turn_peak_angle = self._auto_turn_settled = 0.0
      if self._auto_turn_direction == LaneChangeDirection.none:
        self._auto_turn_consumed = False
      self._auto_lane_completed = False
    self._auto_atc_type = atc_type
    if previous_state == LaneChangeState.laneChangeFinishing and lane_change_state != previous_state:
      self._auto_lane_completed = True
    if lane_change_state == LaneChangeState.laneChangeStarting and previous_state != lane_change_state:
      self._auto_lane_completed = False
    if forced_window and previous_state == LaneChangeState.off and lane_change_state == LaneChangeState.preLaneChange:
      self._auto_lane_completed = False
    self._update_auto_turn_geometry(carstate, modeldata)
    driver_valid = bool(getattr(carstate, "turnSignalDriverValid", False)) or not tesla_brand
    permitted = (lateral_active and carstate.canValid and not carstate.trailerConnected and
                 not getattr(carstate, "vehicleSensorsInvalid", False) and
                 str(getattr(carstate, "gearShifter", "drive")) == "drive" and driver_valid and
                 not driver_st and not (carstate.leftBlinker and carstate.rightBlinker))
    if not permitted or lane_change_state == LaneChangeState.off or self._auto_lane_completed:
      if not permitted and self._auto_lane_direction != LaneChangeDirection.none:
        self._auto_lane_completed = True
      self._auto_lane_direction = LaneChangeDirection.none
    elif (atc_enabled and self._auto_lane_direction == LaneChangeDirection.none and
          (lane_change_state == LaneChangeState.preLaneChange or previous_state == LaneChangeState.preLaneChange)):
      # ATC 变道源：FSM 已拥有该机动，这里只锁存灯方向。
      self._auto_lane_direction = LaneChangeDirection.left if atc_st == BLINKER_LEFT else LaneChangeDirection.right
    if permitted:
      # sp 的 atc_active/blinker_ignore 在 DesireHelper 内部，这里以灯位冲突近似：
      # 驾驶员已亮反向灯即视为冲突，抑制移交与 250m 分支。
      atc_conflict = driver_st != BLINKER_NONE and atc_st != BLINKER_NONE and driver_st != atc_st
      # 250m 源的灯按已行驶距离终止（xDistToTurn 递减出窗即失效），其余源不受限。
      tbt_alive = (not self._auto_tbt_hold or
                   (getattr(carrot_man, "xTurnInfo", 0) in (1, 2) and
                    0 < getattr(carrot_man, "xDistToTurn", 0) <= min(250, max(40, carstate.vEgo * 8 + 20))))
      if (not self._auto_turn_consumed and self._auto_turn_direction != LaneChangeDirection.none and tbt_alive and
          (navigation_direction == self._auto_turn_direction or
           (atc_type in ("", "none", "none prepare", "straight", "straight prepare") and self._auto_turn_started >= 0.3))):
        direction = self._auto_turn_direction
        origin = ORIGIN_TURN
      elif atc_enabled and lane_turn_direction != TurnDirection.none and not self._auto_turn_consumed:
        direction = LaneChangeDirection.left if lane_turn_direction == TurnDirection.turnLeft else LaneChangeDirection.right
        origin = ORIGIN_TURN
      elif self._auto_lane_direction != LaneChangeDirection.none:
        direction = self._auto_lane_direction
        origin = ORIGIN_LANE
      elif (turn_handoff and not self._auto_turn_consumed and not atc_conflict and
            self.auto_signal_direction == (LaneChangeDirection.left if atc_type == "turn left" else LaneChangeDirection.right)):
        # ATC suppresses maneuver changes for one frame, not an already requested same-direction lamp.
        direction = self.auto_signal_direction
        origin = ORIGIN_TURN
      elif (not self._auto_turn_consumed and not self._auto_lane_completed and not atc_conflict and
            getattr(carrot_man, "xTurnInfo", 0) in (1, 2) and
            atc_type in ("turn left prepare", "turn right prepare", "atc left", "atc right") and
            0 < getattr(carrot_man, "xDistToTurn", 0) <= min(250, max(40, carstate.vEgo * 8 + 20))):
        direction = LaneChangeDirection.left if carrot_man.xTurnInfo == 1 else LaneChangeDirection.right
        origin = ORIGIN_TBT
      if direction != LaneChangeDirection.none and turn_type and not self._auto_turn_consumed:
        if direction != self._auto_turn_direction:
          self._auto_turn_started = self._auto_turn_peak_angle = self._auto_turn_settled = 0.0
          self._auto_turn_direction = direction
          # 仅在新请求时更新距离保持标志：分支 a 的持续保持不得抹掉 250m 源标记。
          self._auto_tbt_hold = origin == ORIGIN_TBT
    if direction == LaneChangeDirection.none and self._auto_turn_direction != LaneChangeDirection.none:
      self._auto_turn_consumed = True
      self._auto_turn_direction = LaneChangeDirection.none
    if direction != LaneChangeDirection.none and direction != self.auto_signal_direction:
      self._auto_signal_counter += 1
    self.auto_signal_direction = direction
    self.last_origin = origin if direction != LaneChangeDirection.none else ''
    self.auto_signal_request_id = self._auto_signal_counter if direction != LaneChangeDirection.none else 0
