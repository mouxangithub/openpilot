#!/usr/bin/env python3
import bisect
import math
import os
from enum import IntEnum
from collections.abc import Callable
from types import SimpleNamespace

from cereal import log, car
import cereal.messaging as messaging
from openpilot.common.conversions import Conversions as CV
from openpilot.common.git import get_short_branch
from openpilot.common.params import Params
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.locationd.calibrationd import MIN_SPEED_FILTER

AlertSize = log.ControlsState.AlertSize
AlertStatus = log.ControlsState.AlertStatus
VisualAlert = car.CarControl.HUDControl.VisualAlert
AudibleAlert = car.CarControl.HUDControl.AudibleAlert
EventName = car.CarEvent.EventName


# Alert priorities
class Priority(IntEnum):
  LOWEST = 0
  LOWER = 1
  LOW = 2
  MID = 3
  HIGH = 4
  HIGHEST = 5


# Event types
class ET:
  ENABLE = 'enable'
  PRE_ENABLE = 'preEnable'
  OVERRIDE_LATERAL = 'overrideLateral'
  OVERRIDE_LONGITUDINAL = 'overrideLongitudinal'
  NO_ENTRY = 'noEntry'
  WARNING = 'warning'
  USER_DISABLE = 'userDisable'
  SOFT_DISABLE = 'softDisable'
  IMMEDIATE_DISABLE = 'immediateDisable'
  PERMANENT = 'permanent'


# get event name from enum
EVENT_NAME = {v: k for k, v in EventName.schema.enumerants.items()}


class Events:
  def __init__(self):
    self.events: list[int] = []
    self.static_events: list[int] = []
    self.event_counters = dict.fromkeys(EVENTS.keys(), 0)

  @property
  def names(self) -> list[int]:
    return self.events

  def __len__(self) -> int:
    return len(self.events)

  def add(self, event_name: int, static: bool=False) -> None:
    if static:
      bisect.insort(self.static_events, event_name)
    bisect.insort(self.events, event_name)

  def clear(self) -> None:
    self.event_counters = {k: (v + 1 if k in self.events else 0) for k, v in self.event_counters.items()}
    self.events = self.static_events.copy()

  def contains(self, event_type: str) -> bool:
    return any(event_type in EVENTS.get(e, {}) for e in self.events)

  def create_alerts(self, event_types: list[str], callback_args=None):
    if callback_args is None:
      callback_args = []

    ret = []
    for e in self.events:
      types = EVENTS[e].keys()
      for et in event_types:
        if et in types:
          alert = EVENTS[e][et]
          if not isinstance(alert, Alert):
            alert = alert(*callback_args)

          if DT_CTRL * (self.event_counters[e] + 1) >= alert.creation_delay:
            alert.alert_type = f"{EVENT_NAME[e]}/{et}"
            alert.event_type = et
            ret.append(alert)
    return ret

  def add_from_msg(self, events):
    for e in events:
      bisect.insort(self.events, e.name.raw)

  def to_msg(self):
    ret = []
    for event_name in self.events:
      event = car.CarEvent.new_message()
      event.name = event_name
      for event_type in EVENTS.get(event_name, {}):
        setattr(event, event_type, True)
      ret.append(event)
    return ret


class Alert:
  def __init__(self,
               alert_text_1: str,
               alert_text_2: str,
               alert_status: log.ControlsState.AlertStatus,
               alert_size: log.ControlsState.AlertSize,
               priority: Priority,
               visual_alert: car.CarControl.HUDControl.VisualAlert,
               audible_alert: car.CarControl.HUDControl.AudibleAlert,
               duration: float,
               alert_rate: float = 0.,
               creation_delay: float = 0.):

    self.alert_text_1 = alert_text_1
    self.alert_text_2 = alert_text_2
    self.alert_status = alert_status
    self.alert_size = alert_size
    self.priority = priority
    self.visual_alert = visual_alert
    self.audible_alert = audible_alert

    self.duration = int(duration / DT_CTRL)

    self.alert_rate = alert_rate
    self.creation_delay = creation_delay

    self.alert_type = ""
    self.event_type: str | None = None

  def __str__(self) -> str:
    return f"{self.alert_text_1}/{self.alert_text_2} {self.priority} {self.visual_alert} {self.audible_alert}"

  def __gt__(self, alert2) -> bool:
    if not isinstance(alert2, Alert):
      return False
    return self.priority > alert2.priority


class NoEntryAlert(Alert):
  def __init__(self, alert_text_2: str,
               alert_text_1: str = "openpilot 不可用",
               visual_alert: car.CarControl.HUDControl.VisualAlert=VisualAlert.none):
    super().__init__(alert_text_1, alert_text_2, AlertStatus.normal,
                     AlertSize.mid, Priority.LOW, visual_alert,
                     AudibleAlert.refuse, 3.)


class SoftDisableAlert(Alert):
  def __init__(self, alert_text_2: str):
    super().__init__("立即接管控制", alert_text_2,
                     AlertStatus.userPrompt, AlertSize.full,
                     Priority.MID, VisualAlert.steerRequired,
                     AudibleAlert.warningSoft, 2.),


# less harsh version of SoftDisable, where the condition is user-triggered
class UserSoftDisableAlert(SoftDisableAlert):
  def __init__(self, alert_text_2: str):
    super().__init__(alert_text_2),
    self.alert_text_1 = "openpilot 即将退出"


class ImmediateDisableAlert(Alert):
  def __init__(self, alert_text_2: str):
    super().__init__("立即接管控制", alert_text_2,
                     AlertStatus.critical, AlertSize.full,
                     Priority.HIGHEST, VisualAlert.steerRequired,
                     AudibleAlert.warningImmediate, 4.),


class EngagementAlert(Alert):
  def __init__(self, audible_alert: car.CarControl.HUDControl.AudibleAlert):
    super().__init__("", "",
                     AlertStatus.normal, AlertSize.none,
                     Priority.MID, VisualAlert.none,
                     audible_alert, .2),


class NormalPermanentAlert(Alert):
  def __init__(self, alert_text_1: str, alert_text_2: str = "", duration: float = 0.2, priority: Priority = Priority.LOWER, creation_delay: float = 0.):
    super().__init__(alert_text_1, alert_text_2,
                     AlertStatus.normal, AlertSize.mid if len(alert_text_2) else AlertSize.small,
                     priority, VisualAlert.none, AudibleAlert.none, duration, creation_delay=creation_delay),


class StartupAlert(Alert):
  def __init__(self, alert_text_1: str, alert_text_2: str = "请始终保持双手握住方向盘并注视道路", alert_status=AlertStatus.normal):
    super().__init__(alert_text_1, alert_text_2,
                     alert_status, AlertSize.mid,
                     Priority.LOWER, VisualAlert.none, AudibleAlert.none, 5.),


# ********** helper functions **********
def get_display_speed(speed_ms: float, metric: bool) -> str:
  speed = int(round(speed_ms * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)))
  unit = 'km/h' if metric else 'mph'
  return f"{speed} {unit}"


# ********** alert callback functions **********

AlertCallbackType = Callable[[car.CarParams, car.CarState, messaging.SubMaster, bool, int], Alert]


def soft_disable_alert(alert_text_2: str) -> AlertCallbackType:
  def func(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
    if soft_disable_time < int(0.5 / DT_CTRL):
      return ImmediateDisableAlert(alert_text_2)
    return SoftDisableAlert(alert_text_2)
  return func

def user_soft_disable_alert(alert_text_2: str) -> AlertCallbackType:
  def func(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
    if soft_disable_time < int(0.5 / DT_CTRL):
      return ImmediateDisableAlert(alert_text_2)
    return UserSoftDisableAlert(alert_text_2)
  return func

def startup_master_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  branch = get_short_branch()  # Ensure get_short_branch is cached to avoid lags on startup
  if "REPLAY" in os.environ:
    branch = "replay"

  return StartupAlert("警告：此分支未经测试", branch, alert_status=AlertStatus.userPrompt)

def below_engage_speed_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  return NoEntryAlert(f"车速超过 {get_display_speed(CP.minEnableSpeed, metric)} 才能启用")


def below_steer_speed_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  return Alert(
    f"转向不可用（低于{get_display_speed(CP.minSteerSpeed, metric)}）",
    "",
    AlertStatus.userPrompt, AlertSize.small,
    Priority.LOW, VisualAlert.steerRequired, AudibleAlert.prompt, 0.4)


def calibration_incomplete_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  first_word = '重新校准' if sm['liveCalibration'].calStatus == log.LiveCalibrationData.Status.recalibrating else '校准'
  return Alert(
    f"{first_word} 进行中: {sm['liveCalibration'].calPerc:.0f}%",
    f"请保持车速高于{get_display_speed(MIN_SPEED_FILTER, metric)}",
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .2)


# *** debug alerts ***

def out_of_space_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  full_perc = round(100. - sm['deviceState'].freeSpacePercent)
  return NormalPermanentAlert("存储空间不足", f"已使用{full_perc}%存储空间")


def posenet_invalid_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  mdl = sm['modelV2'].velocity.x[0] if len(sm['modelV2'].velocity.x) else math.nan
  err = CS.vEgo - mdl
  msg = f"速度误差: {err:.1f} 米/秒"
  return NoEntryAlert(msg, alert_text_1="Posenet 速度无效")


def process_not_running_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  not_running = [p.name for p in sm['managerState'].processes if not p.running and p.shouldBeRunning]
  msg = ', '.join(not_running)
  return NoEntryAlert(msg, alert_text_1="进程未运行")


def comm_issue_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  bs = [s for s in sm.data.keys() if not sm.all_checks([s, ])]
  msg = ', '.join(bs[:4])  # can't fit too many on one line
  return NoEntryAlert(msg, alert_text_1="进程间通信问题")


def camera_malfunction_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  all_cams = ('roadCameraState', 'driverCameraState', 'wideRoadCameraState')
  bad_cams = [s.replace('State', '') for s in all_cams if s in sm.data.keys() and not sm.all_checks([s, ])]
  return NormalPermanentAlert("摄像头故障", ', '.join(bad_cams))


def calibration_invalid_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  rpy = sm['liveCalibration'].rpyCalib
  yaw = math.degrees(rpy[2] if len(rpy) == 3 else math.nan)
  pitch = math.degrees(rpy[1] if len(rpy) == 3 else math.nan)
  angles = f"Remount Device (Pitch: {pitch:.1f}°, Yaw: {yaw:.1f}°)"
  return NormalPermanentAlert("校准无效", angles)


def overheat_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  cpu = max(sm['deviceState'].cpuTempC, default=0.)
  gpu = max(sm['deviceState'].gpuTempC, default=0.)
  temp = max((cpu, gpu, sm['deviceState'].memoryTempC))
  return NormalPermanentAlert("系统过热", f"温度: {temp:.0f}°C")


def low_memory_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  return NormalPermanentAlert("内存不足", f"内存使用率: {sm['deviceState'].memoryUsagePercent}%")


def high_cpu_usage_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  x = max(sm['deviceState'].cpuUsagePercent, default=0.)
  return NormalPermanentAlert("CPU 使用率过高", f"CPU使用率: {x}%")


def modeld_lagging_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  return NormalPermanentAlert("驾驶模型延迟", f"帧丢失率: {sm['modelV2'].frameDropPerc:.1f}%")


def wrong_car_mode_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  if frogpilot_toggles.has_cc_long:
    text = "启用巡航控制以激活"
  elif CP.carName == "honda":
    text = "启用主开关以激活"
  else:
    text = "启用自适应巡航以激活"
  return NoEntryAlert(text)


def joystick_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  axes = sm['testJoystick'].axes
  gb, steer = list(axes)[:2] if len(axes) else (0., 0.)
  vals = f"Gas: {round(gb * 100.)}%, Steer: {round(steer * 100.)}%"
  return NormalPermanentAlert("操纵杆模式", vals)


# FrogPilot Alerts
def custom_startup_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  return StartupAlert(frogpilot_toggles.startup_alert_top, frogpilot_toggles.startup_alert_bottom, alert_status=AlertStatus.frogpilot)


def forcing_stop_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  model_length = sm['frogpilotPlan'].forcingStopLength
  model_length_msg = f"{model_length:.1f} 米" if metric else f"{model_length * CV.METER_TO_FOOT:.1f} 英尺"

  return Alert(
    f"强制车辆停止在 {model_length_msg}",
    "请踩下油门踏板或恢复按钮以启动",
    AlertStatus.frogpilot, AlertSize.mid,
    Priority.MID, VisualAlert.none, AudibleAlert.prompt, 1.)


def holiday_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  holiday_messages = {
    "new_years": "新年快乐！🎉",
    "valentines": "情人节快乐！❤️",
    "st_patricks": "圣帕特里克节快乐！🍀",
    "world_frog_day": "世界青蛙日快乐！🐸",
    "april_fools": "愚人节快乐！🤡",
    "easter_week": "复活节快乐！🐰",
    "may_the_fourth": "愿原力与你同在！🚀",
    "cinco_de_mayo": "五月五日节快乐！🌮",
    "stitch_day": "史迪奇日快乐！💙",
    "fourth_of_july": "美国独立日快乐！🎆",
    "halloween_week": "万圣节快乐！🎃",
    "thanksgiving_week": "感恩节快乐！🦃",
    "christmas_week": "圣诞节快乐！🎄",
  }

  return Alert(
    holiday_messages.get(frogpilot_toggles.current_holiday_theme),
    "",
    AlertStatus.normal, AlertSize.small,
    Priority.LOWEST, VisualAlert.none, AudibleAlert.startup, 5.)


def no_lane_available_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  lane_width = sm['frogpilotPlan'].laneWidthLeft if CS.leftBlinker else sm['frogpilotPlan'].laneWidthRight
  lane_width_msg = f"{lane_width:.1f} 米" if metric else f"{lane_width * CV.METER_TO_FOOT:.1f} 英尺"

  return Alert(
    "当前没有可用的车道线",
    f"检测到的车道宽度仅为 {lane_width_msg}",
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .2)


def torque_nn_load_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, params: Params, frogpilot_toggles: SimpleNamespace) -> Alert:
  model_name = params.get("NNFFModelName", encoding='utf-8')
  if model_name is None:
    return Alert(
      "NNFF 扭矩控制器不可用",
      "提供日志给 Twilsonco 以获得您的车辆支持！",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, 10.0)
  else:
    return Alert(
      "NNFF 扭矩控制器已加载",
      model_name,
      AlertStatus.frogpilot, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.engage, 5.0)


EVENTS: dict[int, dict[str, Alert | AlertCallbackType]] = {
  # ********** events with no alerts **********

  EventName.stockFcw: {},
  EventName.actuatorsApiUnavailable: {},

  # ********** events only containing alerts displayed in all states **********

  EventName.joystickDebug: {
    ET.WARNING: joystick_alert,
    ET.PERMANENT: NormalPermanentAlert("操纵杆模式"),
  },

  EventName.controlsInitializing: {
    ET.NO_ENTRY: NoEntryAlert("系统初始化中"),
  },

  EventName.startup: {
    ET.PERMANENT: StartupAlert("随时准备接管")
  },

  EventName.startupMaster: {
    ET.PERMANENT: startup_master_alert,
  },

  # Car is recognized, but marked as dashcam only
  EventName.startupNoControl: {
    ET.PERMANENT: StartupAlert("行车记录仪模式"),
    ET.NO_ENTRY: NoEntryAlert("行车记录仪模式"),
  },

  # Car is not recognized
  EventName.startupNoCar: {
    ET.PERMANENT: StartupAlert("行车记录仪模式：车辆不支持"),
  },

  EventName.startupNoFw: {
    ET.PERMANENT: StartupAlert("车辆未识别",
                               "检查 comma 电源连接",
                               alert_status=AlertStatus.userPrompt),
  },

  EventName.startupNoSecOcKey: {
    ET.PERMANENT: NormalPermanentAlert("行车记录仪模式",
                                       "安全密钥不可用",
                                       priority=Priority.HIGH),
  },

  EventName.dashcamMode: {
    ET.PERMANENT: NormalPermanentAlert("行车记录仪模式",
                                       priority=Priority.LOWEST),
  },

  EventName.invalidLkasSetting: {
    ET.PERMANENT: NormalPermanentAlert("原厂 LKAS 已启用",
                                       "关闭原厂 LKAS 以启用"),
  },

  EventName.cruiseMismatch: {
    #ET.PERMANENT: ImmediateDisableAlert("openpilot 未能取消巡航"),
  },

  # openpilot doesn't recognize the car. This switches openpilot into a
  # read-only mode. This can be solved by adding your fingerprint.
  # See https://github.com/commaai/openpilot/wiki/Fingerprinting for more information
  EventName.carUnrecognized: {
    ET.PERMANENT: NormalPermanentAlert("行车记录仪模式",
                                       "车辆未识别",
                                       priority=Priority.LOWEST),
  },

  EventName.stockAeb: {
    ET.PERMANENT: Alert(
      "BRAKE!",
      "原厂自动紧急制动：碰撞风险",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.none, 2.),
    ET.NO_ENTRY: NoEntryAlert("原厂自动紧急制动：碰撞风险"),
  },

  EventName.fcw: {
    ET.PERMANENT: Alert(
      "BRAKE!",
      "碰撞风险",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.warningSoft, 2.),
  },

  EventName.ldw: {
    ET.PERMANENT: Alert(
      "检测到车道偏离",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.ldw, AudibleAlert.prompt, 3.),
  },

  # ********** events only containing alerts that display while engaged **********

  EventName.steerTempUnavailableSilent: {
    ET.WARNING: Alert(
      "转向暂时不可用",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.prompt, 1.8),
  },

  EventName.preDriverDistracted: {
    ET.PERMANENT: Alert(
      "请注意",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.promptDriverDistracted: {
    ET.PERMANENT: Alert(
      "请注意",
      "驾驶员分心",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.steerRequired, AudibleAlert.promptDistracted, .1),
  },

  EventName.driverDistracted: {
    ET.PERMANENT: Alert(
      "立即解除",
      "驾驶员分心",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1),
  },

  EventName.preDriverUnresponsive: {
    ET.PERMANENT: Alert(
      "请触摸方向盘：未检测到人脸",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.none, .1, alert_rate=0.75),
  },

  EventName.promptDriverUnresponsive: {
    ET.PERMANENT: Alert(
      "请触摸方向盘",
      "驾驶员无反应",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.steerRequired, AudibleAlert.promptDistracted, .1),
  },

  EventName.driverUnresponsive: {
    ET.PERMANENT: Alert(
      "立即解除",
      "驾驶员无反应",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1),
  },

  EventName.manualRestart: {
    ET.WARNING: Alert(
      "请手动接管",
      "即将恢复手动驾驶",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.resumeRequired: {
    ET.WARNING: Alert(
      "Press Resume to Exit Standstill",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.belowSteerSpeed: {
    ET.WARNING: below_steer_speed_alert,
  },

  EventName.preLaneChangeLeft: {
    ET.WARNING: Alert(
      "Steer Left to Start Lane Change Once Safe",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1, alert_rate=0.75),
  },

  EventName.preLaneChangeRight: {
    ET.WARNING: Alert(
      "Steer Right to Start Lane Change Once Safe",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1, alert_rate=0.75),
  },

  EventName.laneChangeBlocked: {
    ET.WARNING: Alert(
      "Car Detected in Blindspot",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, .1),
  },

  EventName.laneChange: {
    ET.WARNING: Alert(
      "Changing Lanes",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.steerSaturated: {
    ET.WARNING: Alert(
      "Take Control",
      "Turn Exceeds Steering Limit",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.promptRepeat, 2.),
  },

  # Thrown when the fan is driven at >50% but is not rotating
  EventName.fanMalfunction: {
    ET.PERMANENT: NormalPermanentAlert("风扇故障", "可能是硬件问题"),
  },

  # Camera is not outputting frames
  EventName.cameraMalfunction: {
    ET.PERMANENT: camera_malfunction_alert,
    ET.SOFT_DISABLE: soft_disable_alert("摄像头故障"),
    ET.NO_ENTRY: NoEntryAlert("摄像头故障: Reboot Your Device"),
  },
  # Camera framerate too low
  EventName.cameraFrameRate: {
    ET.PERMANENT: NormalPermanentAlert("摄像头帧率低", "请重启设备"),
    ET.SOFT_DISABLE: soft_disable_alert("摄像头帧率低"),
    ET.NO_ENTRY: NoEntryAlert("摄像头帧率低: Reboot Your Device"),
  },

  # Unused

  EventName.locationdTemporaryError: {
    ET.NO_ENTRY: NoEntryAlert("locationd 临时错误"),
    ET.SOFT_DISABLE: soft_disable_alert("locationd 临时错误"),
  },

  EventName.locationdPermanentError: {
    ET.NO_ENTRY: NoEntryAlert("locationd Permanent Error"),
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("locationd Permanent Error"),
    ET.PERMANENT: NormalPermanentAlert("locationd Permanent Error"),
  },

  # openpilot tries to learn certain parameters about your car by observing
  # how the car behaves to steering inputs from both human and openpilot driving.
  # This includes:
  # - steer ratio: gear ratio of the steering rack. Steering angle divided by tire angle
  # - tire stiffness: how much grip your tires have
  # - angle offset: most steering angle sensors are offset and measure a non zero angle when driving straight
  # This alert is thrown when any of these values exceed a sanity check. This can be caused by
  # bad alignment or bad sensor data. If this happens consistently consider creating an issue on GitHub
  EventName.paramsdTemporaryError: {
    ET.NO_ENTRY: NoEntryAlert("paramsd 临时错误"),
    ET.SOFT_DISABLE: soft_disable_alert("paramsd 临时错误"),
  },

  EventName.paramsdPermanentError: {
    ET.NO_ENTRY: NoEntryAlert("paramsd Permanent Error"),
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("paramsd Permanent Error"),
    ET.PERMANENT: NormalPermanentAlert("paramsd Permanent Error"),
  },

  # ********** events that affect controls state transitions **********

  EventName.pcmEnable: {
    ET.ENABLE: EngagementAlert(AudibleAlert.engage),
  },

  EventName.buttonEnable: {
    ET.ENABLE: EngagementAlert(AudibleAlert.engage),
  },

  EventName.pcmDisable: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
  },

  EventName.buttonCancel: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("取消已按下"),
  },

  EventName.brakeHold: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("刹车保持激活"),
  },

  EventName.parkBrake: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("驻车刹车已启用"),
  },

  EventName.pedalPressed: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("踏板已按下",
                              visual_alert=VisualAlert.brakePressed),
  },

  EventName.preEnableStandstill: {
    ET.PRE_ENABLE: Alert(
      "Release Brake to Engage",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .1, creation_delay=1.),
  },

  EventName.gasPressedOverride: {
    ET.OVERRIDE_LONGITUDINAL: Alert(
      "",
      "",
      AlertStatus.normal, AlertSize.none,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.steerOverride: {
    ET.OVERRIDE_LATERAL: Alert(
      "",
      "",
      AlertStatus.normal, AlertSize.none,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.wrongCarMode: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: wrong_car_mode_alert,
  },

  EventName.resumeBlocked: {
    ET.NO_ENTRY: NoEntryAlert("按下设置以启用"),
  },

  EventName.wrongCruiseMode: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("自适应巡航已禁用"),
  },

  EventName.steerTempUnavailable: {
    ET.SOFT_DISABLE: soft_disable_alert("转向暂时不可用"),
    ET.NO_ENTRY: NoEntryAlert("转向暂时不可用"),
  },

  EventName.steerTimeLimit: {
    ET.SOFT_DISABLE: soft_disable_alert("车辆转向时间限制"),
    ET.NO_ENTRY: NoEntryAlert("车辆转向时间限制"),
  },

  EventName.outOfSpace: {
    ET.PERMANENT: out_of_space_alert,
    ET.NO_ENTRY: NoEntryAlert("存储空间不足"),
  },

  EventName.belowEngageSpeed: {
    ET.NO_ENTRY: below_engage_speed_alert,
  },

  EventName.sensorDataInvalid: {
    ET.PERMANENT: Alert(
      "传感器数据无效",
      "Possible Hardware Issue",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, .2, creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("传感器数据无效"),
    ET.SOFT_DISABLE: soft_disable_alert("传感器数据无效"),
  },

  EventName.noGps: {
  },

  EventName.soundsUnavailable: {
    ET.PERMANENT: NormalPermanentAlert("未找到扬声器", "请重启设备"),
    ET.NO_ENTRY: NoEntryAlert("未找到扬声器"),
  },

  EventName.tooDistracted: {
    ET.NO_ENTRY: NoEntryAlert("注意力分散程度过高"),
  },

  EventName.overheat: {
    ET.PERMANENT: overheat_alert,
    ET.SOFT_DISABLE: soft_disable_alert("系统过热"),
    ET.NO_ENTRY: NoEntryAlert("系统过热"),
  },

  EventName.wrongGear: {
    ET.SOFT_DISABLE: user_soft_disable_alert("档位未在 D 档"),
    ET.NO_ENTRY: NoEntryAlert("档位未在 D 档"),
  },

  # This alert is thrown when the calibration angles are outside of the acceptable range.
  # For example if the device is pointed too much to the left or the right.
  # Usually this can only be solved by removing the mount from the windshield completely,
  # and attaching while making sure the device is pointed straight forward and is level.
  # See https://comma.ai/setup for more information
  EventName.calibrationInvalid: {
    ET.PERMANENT: calibration_invalid_alert,
    ET.SOFT_DISABLE: soft_disable_alert("校准无效: Remount Device & Recalibrate"),
    ET.NO_ENTRY: NoEntryAlert("校准无效: Remount Device & Recalibrate"),
  },

  EventName.calibrationIncomplete: {
    ET.PERMANENT: calibration_incomplete_alert,
    ET.SOFT_DISABLE: soft_disable_alert("校准未完成"),
    ET.NO_ENTRY: NoEntryAlert("Calibration in Progress"),
  },

  EventName.calibrationRecalibrating: {
    ET.PERMANENT: calibration_incomplete_alert,
    ET.SOFT_DISABLE: soft_disable_alert("检测到设备重新安装：重新校准中"),
    ET.NO_ENTRY: NoEntryAlert("Remount Detected: Recalibrating"),
  },

  EventName.doorOpen: {
    ET.SOFT_DISABLE: user_soft_disable_alert("车门未关"),
    ET.NO_ENTRY: NoEntryAlert("车门未关"),
  },

  EventName.seatbeltNotLatched: {
    ET.SOFT_DISABLE: user_soft_disable_alert("安全带未系"),
    ET.NO_ENTRY: NoEntryAlert("安全带未系"),
  },

  EventName.espDisabled: {
    ET.SOFT_DISABLE: soft_disable_alert("电子稳定控制已禁用"),
    ET.NO_ENTRY: NoEntryAlert("电子稳定控制已禁用"),
  },

  EventName.lowBattery: {
    ET.SOFT_DISABLE: soft_disable_alert("电量低"),
    ET.NO_ENTRY: NoEntryAlert("电量低"),
  },

  # Different openpilot services communicate between each other at a certain
  # interval. If communication does not follow the regular schedule this alert
  # is thrown. This can mean a service crashed, did not broadcast a message for
  # ten times the regular interval, or the average interval is more than 10% too high.
  EventName.commIssue: {
    ET.SOFT_DISABLE: soft_disable_alert("进程间通信问题"),
    ET.NO_ENTRY: comm_issue_alert,
  },
  EventName.commIssueAvgFreq: {
    ET.SOFT_DISABLE: soft_disable_alert("进程间通信速率低"),
    ET.NO_ENTRY: NoEntryAlert("进程间通信速率低"),
  },

  EventName.controlsdLagging: {
    ET.SOFT_DISABLE: soft_disable_alert("Controls Lagging"),
    ET.NO_ENTRY: NoEntryAlert("控制进程延迟：重启设备"),
  },

  # Thrown when manager detects a service exited unexpectedly while driving
  EventName.processNotRunning: {
    ET.NO_ENTRY: process_not_running_alert,
    ET.SOFT_DISABLE: soft_disable_alert("进程未运行"),
  },

  EventName.radarFault: {
    ET.SOFT_DISABLE: soft_disable_alert("雷达错误：重启车辆"),
    ET.NO_ENTRY: NoEntryAlert("雷达错误：重启车辆"),
  },

  # Every frame from the camera should be processed by the model. If modeld
  # is not processing frames fast enough they have to be dropped. This alert is
  # thrown when over 20% of frames are dropped.
  EventName.modeldLagging: {
    ET.SOFT_DISABLE: soft_disable_alert("驾驶模型延迟"),
    ET.NO_ENTRY: NoEntryAlert("驾驶模型延迟"),
    ET.PERMANENT: modeld_lagging_alert,
  },

  # Besides predicting the path, lane lines and lead car data the model also
  # predicts the current velocity and rotation speed of the car. If the model is
  # very uncertain about the current velocity while the car is moving, this
  # usually means the model has trouble understanding the scene. This is used
  # as a heuristic to warn the driver.
  EventName.posenetInvalid: {
    ET.SOFT_DISABLE: soft_disable_alert("Posenet 速度无效"),
    ET.NO_ENTRY: posenet_invalid_alert,
  },

  # When the localizer detects an acceleration of more than 40 m/s^2 (~4G) we
  # alert the driver the device might have fallen from the windshield.
  EventName.deviceFalling: {
    ET.SOFT_DISABLE: soft_disable_alert("设备从支架脱落"),
    ET.NO_ENTRY: NoEntryAlert("设备从支架脱落"),
  },

  EventName.lowMemory: {
    ET.SOFT_DISABLE: soft_disable_alert("内存不足: Reboot Your Device"),
    ET.PERMANENT: low_memory_alert,
    ET.NO_ENTRY: NoEntryAlert("内存不足: Reboot Your Device"),
  },

  EventName.highCpuUsage: {
    #ET.SOFT_DISABLE: soft_disable_alert("系统故障：重启设备"),
    #ET.PERMANENT: NormalPermanentAlert("System Malfunction", "请重启设备"),
    ET.NO_ENTRY: high_cpu_usage_alert,
  },

  EventName.accFaulted: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("Cruise Fault: Restart the Car"),
    ET.PERMANENT: NormalPermanentAlert("Cruise Fault: Restart the car to engage"),
    ET.NO_ENTRY: NoEntryAlert("Cruise Fault: Restart the Car"),
  },

  EventName.controlsMismatch: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("控制不匹配"),
    ET.NO_ENTRY: NoEntryAlert("控制不匹配"),
  },

  EventName.roadCameraError: {
    ET.PERMANENT: NormalPermanentAlert("摄像头 CRC 错误 - 道路",
                                       duration=1.,
                                       creation_delay=30.),
  },

  EventName.wideRoadCameraError: {
    ET.PERMANENT: NormalPermanentAlert("摄像头 CRC 错误 - 道路 Fisheye",
                                       duration=1.,
                                       creation_delay=30.),
  },

  EventName.driverCameraError: {
    ET.PERMANENT: NormalPermanentAlert("摄像头 CRC 错误 - 驾驶员",
                                       duration=1.,
                                       creation_delay=30.),
  },

  # Sometimes the USB stack on the device can get into a bad state
  # causing the connection to the panda to be lost
  EventName.usbError: {
    ET.SOFT_DISABLE: soft_disable_alert("USB 错误：重启设备"),
    ET.PERMANENT: NormalPermanentAlert("USB 错误：重启设备", ""),
    ET.NO_ENTRY: NoEntryAlert("USB 错误：重启设备"),
  },

  # This alert can be thrown for the following reasons:
  # - No CAN data received at all
  # - CAN data is received, but some message are not received at the right frequency
  # If you're not writing a new car port, this is usually cause by faulty wiring
  EventName.canError: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("CAN 错误"),
    ET.PERMANENT: Alert(
      "CAN 错误: Check Connections",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 1., creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("CAN 错误: Check Connections"),
  },

  EventName.canBusMissing: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("CAN 总线断开"),
    ET.PERMANENT: Alert(
      "CAN 总线断开: Likely Faulty Cable",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 1., creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("CAN 总线断开: Check Connections"),
  },

  EventName.steerUnavailable: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("LKAS 故障：重启车辆"),
    ET.PERMANENT: NormalPermanentAlert("LKAS Fault: Restart the car to engage"),
    ET.NO_ENTRY: NoEntryAlert("LKAS 故障：重启车辆"),
  },

  EventName.reverseGear: {
    ET.PERMANENT: Alert(
      "Reverse\nGear",
      "",
      AlertStatus.normal, AlertSize.full,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .2, creation_delay=0.5),
    ET.USER_DISABLE: ImmediateDisableAlert("倒车档"),
    ET.NO_ENTRY: NoEntryAlert("倒车档"),
  },

  # On cars that use stock ACC the car can decide to cancel ACC for various reasons.
  # When this happens we can no long control the car so the user needs to be warned immediately.
  EventName.cruiseDisabled: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("巡航已关闭"),
  },

  # When the relay in the harness box opens the CAN bus between the LKAS camera
  # and the rest of the car is separated. When messages from the LKAS camera
  # are received on the car side this usually means the relay hasn't opened correctly
  # and this alert is thrown.
  EventName.relayMalfunction: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("Harness Relay Malfunction"),
    ET.PERMANENT: NormalPermanentAlert("Harness Relay Malfunction", "检查硬件"),
    ET.NO_ENTRY: NoEntryAlert("Harness Relay Malfunction"),
  },

  EventName.speedTooLow: {
    ET.IMMEDIATE_DISABLE: Alert(
      "openpilot Canceled",
      "Speed too low",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.disengage, 3.),
  },

  # When the car is driving faster than most cars in the training data, the model outputs can be unpredictable.
  EventName.speedTooHigh: {
    ET.WARNING: Alert(
      "Speed Too High",
      "当前速度下模型预测不可靠",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.promptRepeat, 4.),
    ET.NO_ENTRY: NoEntryAlert("Slow down to engage"),
  },

  EventName.lowSpeedLockout: {
    ET.PERMANENT: NormalPermanentAlert("Cruise Fault: Restart the car to engage"),
    ET.NO_ENTRY: NoEntryAlert("Cruise Fault: Restart the Car"),
  },

  EventName.lkasDisabled: {
    ET.PERMANENT: NormalPermanentAlert("LKAS 已禁用：启用 LKAS 以继续"),
    ET.NO_ENTRY: NoEntryAlert("LKAS Disabled"),
  },

  EventName.vehicleSensorsInvalid: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("Vehicle Sensors Invalid"),
    ET.PERMANENT: NormalPermanentAlert("车辆传感器校准中", "行驶以完成校准"),
    ET.NO_ENTRY: NoEntryAlert("Vehicle Sensors Calibrating"),
  },

  # FrogPilot Events
  EventName.blockUser: {
    ET.PERMANENT: Alert(
      "请勿使用'Development'开发分支！",
      "为了您的安全，强制启用'行车记录仪模式'",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.HIGHEST, VisualAlert.none, AudibleAlert.none, 1.),
  },

  EventName.customStartupAlert: {
    ET.PERMANENT: custom_startup_alert,
  },

  EventName.forcingStop: {
    ET.WARNING: forcing_stop_alert,
  },

  EventName.goatSteerSaturated: {
    ET.WARNING: Alert(
      "JESUS TAKE THE WHEEL!!",
      "Turn Exceeds Steering Limit",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.goat, 2.),
  },

  EventName.greenLight: {
    ET.WARNING: Alert(
      "Light turned green",
      "",
      AlertStatus.frogpilot, AlertSize.small,
      Priority.MID, VisualAlert.none, AudibleAlert.prompt, 3.),
  },

  EventName.holidayActive: {
    ET.PERMANENT: holiday_alert,
  },

  EventName.laneChangeBlockedLoud: {
    ET.WARNING: Alert(
      "Car Detected in Blindspot",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.warningSoft, .1),
  },

  EventName.leadDeparting: {
    ET.WARNING: Alert(
      "Lead departed",
      "",
      AlertStatus.frogpilot, AlertSize.small,
      Priority.MID, VisualAlert.none, AudibleAlert.prompt, 3.),
  },

  EventName.noLaneAvailable: {
    ET.WARNING: no_lane_available_alert,
  },

  EventName.openpilotCrashed: {
    ET.IMMEDIATE_DISABLE: Alert(
      "openpilot crashed",
      "请在 FrogPilot Discord 中提交 '错误日志'！",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGHEST, VisualAlert.none, AudibleAlert.prompt, .1),

    ET.NO_ENTRY: Alert(
      "openpilot crashed",
      "请在 FrogPilot Discord 中提交 '错误日志'！",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGHEST, VisualAlert.none, AudibleAlert.prompt, .1),
  },

  EventName.pedalInterceptorNoBrake: {
    ET.WARNING: Alert(
      "Braking Unavailable",
      "Shift to L",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.HIGH, VisualAlert.wrongGear, AudibleAlert.promptRepeat, 4.),
  },

  EventName.speedLimitChanged: {
    ET.WARNING: Alert(
      "Speed limit changed",
      "",
      AlertStatus.frogpilot, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, 3.),
  },

  EventName.thisIsFineSteerSaturated: {
    ET.WARNING: Alert(
      "This is fine ☕",
      "Turn Exceeds Steering Limit",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.thisIsFine, 2.),
  },

  EventName.torqueNNLoad: {
    ET.PERMANENT: torque_nn_load_alert,
  },

  EventName.trafficModeActive: {
    ET.WARNING: Alert(
      "交通模式已启用",
      "",
      AlertStatus.frogpilot, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, 3.),
  },

  EventName.trafficModeInactive: {
    ET.WARNING: Alert(
      "交通模式已禁用",
      "",
      AlertStatus.frogpilot, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, 3.),
  },

  EventName.turningLeft: {
    ET.WARNING: Alert(
      "Turning left",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .1, alert_rate=0.75),
  },

  EventName.turningRight: {
    ET.WARNING: Alert(
      "Turning right",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .1, alert_rate=0.75),
  },

  # Random Events
  EventName.accel30: {
    ET.WARNING: Alert(
      "UwU u went a bit fast there!",
      "(⁄ ⁄•⁄ω⁄•⁄ ⁄)",
      AlertStatus.frogpilot, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.uwu, 4.),
  },

  EventName.accel35: {
    ET.WARNING: Alert(
      "I ain't giving you no tree-fiddy",
      "You damn Loch Ness Monsta!",
      AlertStatus.frogpilot, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.nessie, 4.),
  },

  EventName.accel40: {
    ET.WARNING: Alert(
      "Great Scott!",
      "🚗💨",
      AlertStatus.frogpilot, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.doc, 4.),
  },

  EventName.dejaVuCurve: {
    ET.WARNING: Alert(
      "♬♪ Deja vu! ᕕ(⌐■_■)ᕗ ♪♬",
      "🏎️",
      AlertStatus.frogpilot, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.dejaVu, 4.),
  },

  EventName.firefoxSteerSaturated: {
    ET.WARNING: Alert(
      "IE Has Stopped Responding...",
      "Turn Exceeds Steering Limit",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.firefox, 4.),
  },

  EventName.hal9000: {
    ET.WARNING: Alert(
      "I'm sorry Dave",
      "I'm afraid I can't do that...",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.hal9000, 4.),
  },

  EventName.openpilotCrashedRandomEvent: {
    ET.IMMEDIATE_DISABLE: Alert(
      "openpilot crashed 💩",
      "请在 FrogPilot Discord 中提交 '错误日志'！",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGHEST, VisualAlert.none, AudibleAlert.fart, 10.),

    ET.NO_ENTRY: Alert(
      "openpilot crashed 💩",
      "请在 FrogPilot Discord 中提交 '错误日志'！",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGHEST, VisualAlert.none, AudibleAlert.fart, 10.),
  },

  EventName.toBeContinued: {
    ET.WARNING: Alert(
      "To be continued...",
      "⬅️",
      AlertStatus.frogpilot, AlertSize.mid,
      Priority.MID, VisualAlert.none, AudibleAlert.continued, 7.),
  },

  EventName.vCruise69: {
    ET.WARNING: Alert(
      "Lol 69",
      "",
      AlertStatus.frogpilot, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.noice, 2.),
  },

  EventName.yourFrogTriedToKillMe: {
    ET.WARNING: Alert(
      "Your Frog tried to kill me...",
      "👺",
      AlertStatus.frogpilot, AlertSize.mid,
      Priority.MID, VisualAlert.none, AudibleAlert.angry, 5.),
  },

  EventName.youveGotMail: {
    ET.WARNING: Alert(
      "You've got mail! 📧",
      "",
      AlertStatus.frogpilot, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.mail, 3.),
  },
}


if __name__ == '__main__':
  # print all alerts by type and priority
  from cereal.services import SERVICE_LIST
  from collections import defaultdict

  event_names = {v: k for k, v in EventName.schema.enumerants.items()}
  alerts_by_type: dict[str, dict[Priority, list[str]]] = defaultdict(lambda: defaultdict(list))

  CP = car.CarParams.new_message()
  CS = car.CarState.new_message()
  sm = messaging.SubMaster(list(SERVICE_LIST.keys()))

  for i, alerts in EVENTS.items():
    for et, alert in alerts.items():
      if callable(alert):
        alert = alert(CP, CS, sm, False, 1)
      alerts_by_type[et][alert.priority].append(event_names[i])

  all_alerts: dict[str, list[tuple[Priority, list[str]]]] = {}
  for et, priority_alerts in alerts_by_type.items():
    all_alerts[et] = sorted(priority_alerts.items(), key=lambda x: x[0], reverse=True)

  for status, evs in sorted(all_alerts.items(), key=lambda x: x[0]):
    print(f"**** {status} ****")
    for p, alert_list in evs:
      print(f"  {repr(p)}:")
      print("   ", ', '.join(alert_list), "\n")
