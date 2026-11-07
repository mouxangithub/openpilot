"""Turn-signal observation layer hosted in selfdrived (SelfdriveState publisher).

cp 把灯效观测层跑在 modeld 的 DesireHelper 里、字段写进 modelV2.meta；sp 的 15 个
灯效字段加在 SelfdriveState 上（log.capnp 禁改，字段已就位），而 modelV2.meta 没有
承载字段，所以本层挂在 selfdrived（selfdriveState 消息的构造/发布点），用模型帧
frameId 去重保持 cp 的模型帧节奏（DT_MDL）。

纯灯效遥测：绝不影响 desire / actuation / 转向准入。默认零等价——三个参数
（ManualLaneChangeIndicator / ModelDesireIndicator / ModelPathIndicator，均挂在
AutoBlinkerControl 链上）默认关闭时本层完全旁路，所有字段保持 capnp 缺省值。
"""
import json
import math
import time
from pathlib import Path

from openpilot.cereal import log, custom
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_lib.auto_signal import AutoSignalTracker
from openpilot.selfdrive.controls.lib.desire_lib.boundary_indicator import BoundaryIndicator
from openpilot.selfdrive.controls.lib.desire_lib.indicator_observer import ModelIndicator
from openpilot.sunnypilot.carrot.bluetooth.model import read_json

RUNTIME = Path('/dev/shm/carrot-bluetooth')
INDICATOR_JOURNAL = RUNTIME / 'boundary-indicator.json'
INDICATOR_DISPLAY_PATH = Path('/dev/shm/carrot-indicator-display.json')

LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection
TurnDirection = custom.ModelDataV2SP.TurnDirection

BLINKER_NONE, BLINKER_LEFT, BLINKER_RIGHT = 0, 1, 2

# sp desire_helper._update_atc_blinker 的 ATC 类型表（遥测镜像，见 _atc_state）。
ATC_TURN_TYPES = ("turn left", "turn right")
ATC_FORK_TYPES = ("fork left", "fork right", "atc left", "atc right")

# 显示 JSON 的 origin 词表（common/indicator_display.py）。
SOURCE_ORIGINS = {'model_turn': 'model_turn', 'model_desire': 'model_desire', 'model_path': 'model_path', 'manual': 'manual'}


class IndicatorLayer:
  def __init__(self, params=None, tesla_brand=False):
    self.params = params if params is not None else Params()
    self._tesla_brand = tesla_brand
    self.frame = 0
    self.boundary_indicator = BoundaryIndicator(read_json(INDICATOR_JOURNAL, {}))
    self.model_indicator = ModelIndicator()
    self.tracker = AutoSignalTracker()

    self.boundary_indicator_enabled = False
    self.model_desire_indicator_enabled = False
    self.model_path_indicator_enabled = False
    self.indicator_journal_time = 0.

    # ATC 遥测镜像状态（与 sp desire_helper._update_atc_blinker 对齐的最小子集）。
    self._atc_active = 0  # 0: none, 1: ATC lamp, 2: conflict with driver lamp
    self._atc_type_last = ""
    self._atc_type = ""
    self._carrot_cmd_index_last = 0
    self._forced_count = 0
    self._forced_blinker = BLINKER_NONE

    self._last_model_frame = -1
    self._previous_state = LaneChangeState.off
    self._last_display = None
    self._last_display_write = 0.

    # SelfdriveState 输出（缺省即 capnp 默认值）。
    self.manual_lane_indicator = 0
    self.manual_lane_indicator_monotime = 0
    self.observed_indicator = 0
    self.observed_indicator_monotime = 0
    self.observed_indicator_source = ''
    self.indicator_isolation_mask = 0
    self.indicator_journal_monotime = 0
    self.indicator_prepare_direction = 0
    self.indicator_prepare_source = ''
    self.auto_turn_signal = LaneChangeDirection.none
    self.auto_turn_signal_lane_change = False
    self.auto_signal_direction = LaneChangeDirection.none
    self.auto_signal_request_id = 0

  @property
  def enabled(self):
    return self.boundary_indicator_enabled or self.model_desire_indicator_enabled or self.model_path_indicator_enabled

  def _update_params(self):
    # cp desire_helper._update_params_periodic: ManualLaneChangeIndicator 挂
    # AutoBlinkerControl 链（灯控开启且非 CAN-FD 灯控时才允许本 fork 检测手动灯）。
    lamp_mode = self.params.get_int("AutoBlinkerControl") in (1, 2) and not self.params.get_bool("CanfdBlinkerControl")
    self.boundary_indicator_enabled = lamp_mode and self.params.get_bool("ManualLaneChangeIndicator")
    self.model_desire_indicator_enabled = lamp_mode and self.params.get_bool("ModelDesireIndicator")
    self.model_path_indicator_enabled = lamp_mode and self.params.get_bool("ModelPathIndicator")
    # 低速 TBT 源在发灯前等待该所有权确认；同时跨进程重启恢复隔离掩码。
    journal = read_json(INDICATOR_JOURNAL, {})
    stamp, direction = journal.get('time'), journal.get('mask', journal.get('direction'))
    now = time.monotonic()
    if (type(stamp) in (int, float) and math.isfinite(stamp) and self.indicator_journal_time < stamp <= now and
        now - stamp < 20 and type(direction) is int and direction in (1, 2, 3)):
      self.boundary_indicator.own(now, direction)
      self.indicator_journal_time = stamp

  def _atc_state(self, cm, driver_st):
    """sp desire_helper._update_atc_blinker 的遥测镜像（无 bluetooth/blinker_ignore）。

    返回 (atc_st, atc_enabled, forced_window)。仅供灯效遥测，不反馈给任何控制路径。
    """
    atc_type = str(getattr(cm, "atcType", "") or "")
    forced_window = False
    atc_st = BLINKER_NONE
    if self._forced_count > 0:
      self._forced_count -= 1
      atc_st = self._forced_blinker
      forced_window = True
    elif int(getattr(cm, "carrotCmdIndex", 0)) != self._carrot_cmd_index_last and \
        str(getattr(cm, "carrotCmd", "") or "") == "LANECHANGE":
      self._carrot_cmd_index_last = int(getattr(cm, "carrotCmdIndex", 0))
      self._forced_count = int(0.2 / DT_MDL)
      self._forced_blinker = BLINKER_LEFT if str(getattr(cm, "carrotArg", "") or "") == "LEFT" else BLINKER_RIGHT
      atc_st = self._forced_blinker
      forced_window = True
    elif atc_type in ATC_TURN_TYPES:
      if self._atc_active != 2:
        atc_st = BLINKER_LEFT if atc_type == "turn left" else BLINKER_RIGHT
        self._atc_active = 1
    elif atc_type in ATC_FORK_TYPES:
      if self._atc_active != 2:
        atc_st = BLINKER_LEFT if atc_type in ("fork left", "atc left") else BLINKER_RIGHT
        self._atc_active = 1
    else:
      self._atc_active = 0

    if driver_st != BLINKER_NONE and atc_st != BLINKER_NONE and driver_st != atc_st:
      atc_st = BLINKER_NONE
      self._atc_active = 2
    atc_enabled = atc_st in (BLINKER_LEFT, BLINKER_RIGHT)
    if self._atc_type_last != atc_type:
      atc_enabled = False
    self._atc_type_last = atc_type
    self._atc_type = atc_type
    return atc_st, atc_enabled, forced_window

  def _update_display(self, CS, now):
    """写 /dev/shm/carrot-indicator-display.json（词表见 common/indicator_display.py）。"""
    observation = self.model_indicator.active
    if observation is not None:
      display = {'state': 'confirmed', 'origin': SOURCE_ORIGINS.get(observation.source, 'model_desire'),
                 'direction': 'left' if observation.direction == 1 else 'right',
                 'reason': observation.reason if observation.reason != 'active' else 'active'}
    elif self.boundary_indicator_enabled and self.boundary_indicator.episode:
      display = {'state': 'prepare', 'origin': 'manual',
                 'direction': 'left' if self.boundary_indicator.episode['direction'] == 1 else 'right',
                 'reason': 'boundary'}
    elif self.model_indicator.candidate is not None:
      candidate = self.model_indicator.candidate
      display = {'state': 'prepare', 'origin': SOURCE_ORIGINS.get(candidate[1], 'model_desire'),
                 'direction': 'left' if candidate[0] == 1 else 'right', 'reason': 'confirming'}
    elif self.tracker.auto_signal_direction != LaneChangeDirection.none:
      display = {'state': 'request', 'origin': self.tracker.last_origin or 'turn',
                 'direction': 'left' if self.tracker.auto_signal_direction == LaneChangeDirection.left else 'right',
                 'reason': 'active'}
    else:
      display = None
    if display is None and self._last_display is not None:
      display = {'state': 'ended', 'origin': self._last_display['origin'], 'direction': self._last_display['direction'],
                 'reason': 'ended'}
      self._last_display = None
    elif display is not None:
      unchanged = self._last_display == display
      self._last_display = display
      if unchanged and now - self._last_display_write < .5:
        return
    if display is None:
      return
    left, right = bool(CS.leftBlinker), bool(CS.rightBlinker)
    display.update(version=1, stamp=now, lamp='both' if left and right else 'left' if left else 'right' if right else 'off')
    self._last_display_write = now
    try:
      with INDICATOR_DISPLAY_PATH.open('w') as f:
        f.write(json.dumps(display))
    except OSError:
      pass

  def update(self, sm, CS):
    self.frame += 1
    if self.frame == 1 or self.frame % 20 == 0:
      self._update_params()
    if not self.enabled:
      # 默认零等价：参数全关时整层旁路，输出回到 capnp 缺省值（中途关参数同样清零）。
      self.tracker.update(None, None, None, enabled=False, lateral_active=False,
                          lane_change_state=LaneChangeState.off, lane_change_direction=LaneChangeDirection.none)
      self.auto_turn_signal = LaneChangeDirection.none
      self.auto_turn_signal_lane_change = False
      self.auto_signal_direction = LaneChangeDirection.none
      self.auto_signal_request_id = 0
      self.manual_lane_indicator = 0
      self.manual_lane_indicator_monotime = 0
      self.observed_indicator = 0
      self.observed_indicator_monotime = 0
      self.observed_indicator_source = ''
      self.indicator_isolation_mask = 0
      self.indicator_prepare_direction = 0
      self.indicator_prepare_source = ''
      return
    now = time.monotonic()
    md = sm['modelV2']
    # 模型帧去重：观测器按模型帧节奏推进（cp 在 modeld 内以模型帧率驱动）。
    if md.frameId <= self._last_model_frame:
      return
    self._last_model_frame = md.frameId
    valid = md.valid and all(sm.valid[k] and sm.alive[k] and 0 <= now - sm.recv_time[k] < .35
                             for k in ('carState', 'carControl'))
    # carrotManSP is an optional observational feed (ignored by the comm-issue
    # check); its first frame can lag or it may never run. Skip the ATC mirror
    # rather than index a missing service and take selfdrived down.
    if not sm.seen.get('carrotManSP'):
      return
    cm = sm['carrotManSP']
    lamps = (int(CS.leftBlinker), int(CS.rightBlinker))
    driver_st = BLINKER_LEFT if lamps == (1, 0) else BLINKER_RIGHT if lamps == (0, 1) else BLINKER_NONE
    atc_st, atc_enabled, forced_window = self._atc_state(cm, driver_st)

    # 导航准备不是驾驶员意图；只把执行中的变道视为 busy（cp 同注释语义）。
    lane_change_state = md.meta.laneChangeState
    lane_change_direction = md.meta.laneChangeDirection
    lane_turn_direction = sm['modelDataV2SP'].laneTurnDirection
    busy = lane_change_state in (LaneChangeState.laneChangeStarting, LaneChangeState.laneChangeFinishing)

    self.boundary_indicator.update(now, CS, md, enabled=self.boundary_indicator_enabled, valid=valid, busy=busy)
    if self.model_indicator.active and self.model_indicator.active.source == 'manual' and not self.boundary_indicator_enabled:
      self.model_indicator.active = None
    self.model_indicator.update(now, CS, md, valid=valid, lateral_active=sm['carControl'].latActive,
                                desire_enabled=self.model_desire_indicator_enabled,
                                path_enabled=self.model_path_indicator_enabled, busy=busy,
                                isolation=self.boundary_indicator, manual_edge=self.boundary_indicator.request_direction,
                                command_curvature=sm['carControl'].actuators.curvature,
                                # cp 经 physical-hold.json 识别一触杆回声；该文件生产者未随本 fork
                                # 移植，传 None 时回声恒不匹配（观测在物理杆按住期间暂停，cp 同）。
                                feedback=None)
    self.tracker.update(CS, md, cm, enabled=True, lateral_active=sm['carControl'].latActive,
                        lane_change_state=lane_change_state, lane_change_direction=lane_change_direction,
                        lane_turn_direction=lane_turn_direction, driver_st=driver_st,
                        previous_state=self._previous_state, atc_enabled=atc_enabled, atc_st=atc_st,
                        tesla_brand=self._tesla_brand, forced_window=forced_window)
    self._previous_state = lane_change_state

    # cp desire_helper.update 末尾的 autoTurnSignal 锁存：仅 ATC 起源，无转向请求。
    turning = lane_turn_direction != TurnDirection.none
    driver_enabled = driver_st in (BLINKER_LEFT, BLINKER_RIGHT)
    atc_lane_change_only = self._atc_type in ATC_FORK_TYPES and atc_enabled and not driver_enabled
    changing = busy if self.auto_turn_signal_lane_change else turning
    if not changing or lane_change_direction != self.auto_turn_signal:
      self.auto_turn_signal = LaneChangeDirection.none
    if self.auto_turn_signal == LaneChangeDirection.none and atc_enabled and not driver_enabled and self._atc_active == 1:
      if turning and self._atc_type in ATC_TURN_TYPES:
        self.auto_turn_signal = lane_change_direction
        self.auto_turn_signal_lane_change = False
      elif lane_change_state == LaneChangeState.laneChangeStarting and atc_lane_change_only:
        self.auto_turn_signal = lane_change_direction
        self.auto_turn_signal_lane_change = True

    # SelfdriveState 字段（cp modeld.py 594-608 的对应物）。
    self.manual_lane_indicator = self.boundary_indicator.request_direction
    self.manual_lane_indicator_monotime = int(self.boundary_indicator.request_time * 1e9)
    observation = self.model_indicator.active
    self.observed_indicator = observation.direction if observation else 0
    self.observed_indicator_monotime = int(self.model_indicator.request_time * 1e9)
    self.observed_indicator_source = self.model_indicator.reason
    self.indicator_isolation_mask = self.boundary_indicator.blocked
    self.indicator_journal_monotime = int(self.indicator_journal_time * 1e9)
    preparation = self.model_indicator.candidate
    if preparation and not (self.model_path_indicator_enabled if preparation[1] == 'model_path' else self.model_desire_indicator_enabled):
      preparation = None
    if self.boundary_indicator_enabled and self.boundary_indicator.episode:
      preparation = (self.boundary_indicator.episode['direction'], 'manual')
    self.indicator_prepare_direction = preparation[0] if preparation and not observation else 0
    self.indicator_prepare_source = preparation[1] if preparation and not observation else ''
    self.auto_signal_direction = self.tracker.auto_signal_direction
    self.auto_signal_request_id = self.tracker.auto_signal_request_id

    self._update_display(CS, now)
