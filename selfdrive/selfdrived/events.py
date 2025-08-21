#!/usr/bin/env python3
import bisect
import math
import os
from enum import IntEnum
from collections.abc import Callable

from cereal import log, car
import cereal.messaging as messaging
from openpilot.common.conversions import Conversions as CV
from openpilot.common.git import get_short_branch
from openpilot.common.params import Params
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.locationd.calibrationd import MIN_SPEED_FILTER

AlertSize = log.SelfdriveState.AlertSize
AlertStatus = log.SelfdriveState.AlertStatus
VisualAlert = car.CarControl.HUDControl.VisualAlert
AudibleAlert = car.CarControl.HUDControl.AudibleAlert
EventName = log.OnroadEvent.EventName


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
      event = log.OnroadEvent.new_message()
      event.name = event_name
      for event_type in EVENTS.get(event_name, {}):
        setattr(event, event_type, True)
      ret.append(event)
    return ret


class Alert:
  def __init__(self,
               alert_text_1: str,
               alert_text_2: str,
               alert_status: log.SelfdriveState.AlertStatus,
               alert_size: log.SelfdriveState.AlertSize,
               priority: Priority,
               visual_alert: car.CarControl.HUDControl.VisualAlert,
               audible_alert: car.CarControl.HUDControl.AudibleAlert,
               duration: float,
               creation_delay: float = 0.):

    self.alert_text_1 = alert_text_1
    self.alert_text_2 = alert_text_2
    self.alert_status = alert_status
    self.alert_size = alert_size
    self.priority = priority
    self.visual_alert = visual_alert
    self.audible_alert = audible_alert

    self.duration = int(duration / DT_CTRL)

    self.creation_delay = creation_delay

    self.alert_type = ""
    self.event_type: str | None = None

  def __str__(self) -> str:
    return f"{self.alert_text_1}/{self.alert_text_2} {self.priority} {self.visual_alert} {self.audible_alert}"

  def __gt__(self, alert2) -> bool:
    if not isinstance(alert2, Alert):
      return False
    return self.priority > alert2.priority

EmptyAlert = Alert("" , "", AlertStatus.normal, AlertSize.none, Priority.LOWEST,
                   VisualAlert.none, AudibleAlert.none, 0)

class NoEntryAlert(Alert):
  def __init__(self, alert_text_2: str,
               alert_text_1: str = "openpilot 不可用",
               visual_alert: car.CarControl.HUDControl.VisualAlert=VisualAlert.none):
    super().__init__(alert_text_1, alert_text_2, AlertStatus.normal,
                     AlertSize.mid, Priority.LOW, visual_alert,
                     AudibleAlert.refuse, 3.)


class SoftDisableAlert(Alert):
  def __init__(self, alert_text_2: str):
    super().__init__("立即接管方向盘", alert_text_2,
                     AlertStatus.userPrompt, AlertSize.full,
                     Priority.MID, VisualAlert.steerRequired,
                     AudibleAlert.warningSoft, 2.),


# 用户触发的轻度解除
class UserSoftDisableAlert(SoftDisableAlert):
  def __init__(self, alert_text_2: str):
    super().__init__(alert_text_2),
    self.alert_text_1 = "openpilot 即将解除"


class ImmediateDisableAlert(Alert):
  def __init__(self, alert_text_2: str):
    super().__init__("立即接管方向盘", alert_text_2,
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
  def __init__(self, alert_text_1: str, alert_text_2: str = "请始终双手握住方向盘并注意道路", alert_status=AlertStatus.normal):
    super().__init__(alert_text_1, alert_text_2,
                     alert_status, AlertSize.mid,
                     Priority.LOWER, VisualAlert.none, AudibleAlert.none, 5.),



# ********** helper functions **********
def get_display_speed(speed_ms: float, metric: bool) -> str:
  speed = int(round(speed_ms * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)))
  unit = 'km/h' if metric else 'mph'
  return f"{speed} {unit}"


# ********** alert callback functions **********

AlertCallbackType = Callable[[car.CarParams, car.CarState, messaging.SubMaster, bool, int, log.ControlsState], Alert]


def soft_disable_alert(alert_text_2: str) -> AlertCallbackType:
  def func(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
    if soft_disable_time < int(0.5 / DT_CTRL):
      return ImmediateDisableAlert(alert_text_2)
    return SoftDisableAlert(alert_text_2)
  return func

def user_soft_disable_alert(alert_text_2: str) -> AlertCallbackType:
  def func(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
    if soft_disable_time < int(0.5 / DT_CTRL):
      return ImmediateDisableAlert(alert_text_2)
    return UserSoftDisableAlert(alert_text_2)
  return func

def startup_master_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  branch = get_short_branch()  # Ensure get_short_branch is cached to avoid lags on startup
  if "REPLAY" in os.environ:
    branch = "replay"

  return StartupAlert("警告：此分支未经过测试", branch, alert_status=AlertStatus.userPrompt)


def below_engage_speed_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  return NoEntryAlert(f"请保持速度高于 {get_display_speed(CP.minEnableSpeed, metric)} 以接管自动驾驶")
def below_steer_speed_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  return Alert(
    f"低于 {get_display_speed(CP.minSteerSpeed, metric)} 无法转向",
    "",
    AlertStatus.userPrompt, AlertSize.small,
    Priority.LOW, VisualAlert.steerRequired, AudibleAlert.none, 0.4)


def calibration_incomplete_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  first_word = '重新标定' if sm['liveCalibration'].calStatus == log.LiveCalibrationData.Status.recalibrating else '标定'
  return Alert(
    f"{first_word}进行中：{sm['liveCalibration'].calPerc:.0f}%",
    f"请保持速度高于 {get_display_speed(MIN_SPEED_FILTER, metric)}",
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .2)


def torque_nn_load_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  model_name = Params().get("NNFFModelName", encoding='utf-8')
  if model_name == "":
    return Alert(
      "NNFF 扭矩控制器不可用",
      "请向 Twilsonco 提交日志以获取支持！",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, 6.0)
  else:
    return Alert(
      "NNFF 扭矩控制器已加载",
      model_name,
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, 5.0)


# *** debug alerts ***

def out_of_space_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  full_perc = round(100. - sm['deviceState'].freeSpacePercent)
  return NormalPermanentAlert("存储空间不足", f"已用 {full_perc}%")

def posenet_invalid_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  mdl = sm['modelV2'].velocity.x[0] if len(sm['modelV2'].velocity.x) else math.nan
  err = CS.vEgo - mdl
  msg = f"速度误差: {err:.1f} m/s"
  return NoEntryAlert(msg, alert_text_1="Posenet 速度无效")

def process_not_running_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  not_running = [p.name for p in sm['managerState'].processes if not p.running and p.shouldBeRunning]
  msg = ', '.join(not_running)
  return NoEntryAlert(msg, alert_text_1="进程未运行")

def comm_issue_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  bs = [s for s in sm.data.keys() if not sm.all_checks([s, ])]
  msg = ', '.join(bs[:4])  # 一行显示太多会换行
  return NoEntryAlert(msg, alert_text_1="进程间通信异常")

def camera_malfunction_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  all_cams = ('roadCameraState', 'driverCameraState', 'wideRoadCameraState')
  bad_cams = [s.replace('State', '') for s in all_cams if s in sm.data.keys() and not sm.all_checks([s, ])]
  return NormalPermanentAlert("摄像头故障", ', '.join(bad_cams))

def calibration_invalid_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  rpy = sm['liveCalibration'].rpyCalib
  yaw = math.degrees(rpy[2] if len(rpy) == 3 else math.nan)
  pitch = math.degrees(rpy[1] if len(rpy) == 3 else math.nan)
  angles = f"请重新安装设备 (俯仰: {pitch:.1f}°, 偏航: {yaw:.1f}°)"
  return NormalPermanentAlert("标定无效", angles)

def paramsd_invalid_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  if not sm['liveParameters'].angleOffsetValid:
    angle_offset_deg = sm['liveParameters'].angleOffsetDeg
    title = "检测到方向盘偏移"
    text = f"角度偏差过大 (偏差: {angle_offset_deg:.1f}°)"
  elif not sm['liveParameters'].steerRatioValid:
    steer_ratio = sm['liveParameters'].steerRatio
    title = "转向比异常"
    text = f"方向机几何可能异常 (比值: {steer_ratio:.1f})"
  elif not sm['liveParameters'].stiffnessFactorValid:
    stiffness_factor = sm['liveParameters'].stiffnessFactor
    title = "轮胎刚度异常"
    text = f"请检查轮胎、胎压或四轮定位 (系数: {stiffness_factor:.1f})"
  else:
    return NoEntryAlert("paramsd 临时错误")

  return NoEntryAlert(alert_text_1=title, alert_text_2=text)

def overheat_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  cpu = max(sm['deviceState'].cpuTempC, default=0.)
  gpu = max(sm['deviceState'].gpuTempC, default=0.)
  temp = max((cpu, gpu, sm['deviceState'].memoryTempC))
  return NormalPermanentAlert("系统过热", f"{temp:.0f} °C")

def low_memory_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  return NormalPermanentAlert("内存不足", f"已使用 {sm['deviceState'].memoryUsagePercent}%")



def high_cpu_usage_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  x = max(sm['deviceState'].cpuUsagePercent, default=0.)
  return NormalPermanentAlert("High CPU Usage", f"{x}% used")


def modeld_lagging_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  return NormalPermanentAlert("Driving Model Lagging", f"{sm['modelV2'].frameDropPerc:.1f}% frames dropped")


def wrong_car_mode_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  text = "Enable Adaptive Cruise to Engage"
  if CP.brand == "honda":
    text = "Enable Main Switch to Engage"
  return NoEntryAlert(text)


def joystick_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  gb = sm['carControl'].actuators.accel / 4.
  steer = sm['carControl'].actuators.torque
  vals = f"Gas: {round(gb * 100.)}%, Steer: {round(steer * 100.)}%"
  return NormalPermanentAlert("Joystick Mode", vals)


def longitudinal_maneuver_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  ad = sm['alertDebug']
  audible_alert = AudibleAlert.prompt if 'Active' in ad.alertText1 else AudibleAlert.none
  alert_status = AlertStatus.userPrompt if 'Active' in ad.alertText1 else AlertStatus.normal
  alert_size = AlertSize.mid if ad.alertText2 else AlertSize.small
  return Alert(ad.alertText1, ad.alertText2,
               alert_status, alert_size,
               Priority.LOW, VisualAlert.none, audible_alert, 0.2)


def personality_changed_alert(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  personality = str(personality).title()
  return NormalPermanentAlert(f"Driving Personality: {personality}", duration=1.5)

def car_parser_result(CP: car.CarParams, CS: car.CarState, sm: messaging.SubMaster, metric: bool, soft_disable_time: int, personality) -> Alert:
  results = Params().get("CanParserResult")
  if results is None:
    results = ""
  return Alert(
    "CAN Error: Check Connections!!",
    results,
    AlertStatus.normal, AlertSize.small,
    Priority.LOW, VisualAlert.none, AudibleAlert.none, 1., creation_delay=1.)


EVENTS: dict[int, dict[str, Alert | AlertCallbackType]] = {
  # ********** events with no alerts **********

  EventName.stockFcw: {},
  EventName.actuatorsApiUnavailable: {},

  # ********** events only containing alerts displayed in all states **********

  EventName.joystickDebug: {
    ET.WARNING: joystick_alert,
    ET.PERMANENT: NormalPermanentAlert("操纵杆模式"),
  },

  EventName.longitudinalManeuver: {
    ET.WARNING: longitudinal_maneuver_alert,
    ET.PERMANENT: NormalPermanentAlert("纵向操作模式",
                                       "确保前方道路清晰"),
  },

  EventName.selfdriveInitializing: {
    ET.NO_ENTRY: NoEntryAlert("系统初始化中"),
  },

  EventName.startup: {
    ET.PERMANENT: StartupAlert("随时准备接管"),
  },

  EventName.startupMaster: {
    ET.PERMANENT: startup_master_alert,
  },

  EventName.startupNoControl: {
    ET.PERMANENT: StartupAlert("行车记录仪模式"),
    ET.NO_ENTRY: NoEntryAlert("行车记录仪模式"),
  },

  EventName.startupNoCar: {
    ET.PERMANENT: StartupAlert("不支持的车辆行车记录仪模式"),
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
    ET.PERMANENT: NormalPermanentAlert("无效的 LKAS 设置",
                                       "切换原车 LKAS 开或关以启用"),
    ET.NO_ENTRY: NoEntryAlert("无效的 LKAS 设置"),
  },


  EventName.cruiseMismatch: {
    #ET.PERMANENT: ImmediateDisableAlert("openpilot failed to cancel cruise"),
  },

  # openpilot doesn't recognize the car. This switches openpilot into a
  # read-only mode. This can be solved by adding your fingerprint.
  # See https://github.com/commaai/openpilot/wiki/Fingerprinting for more information
  EventName.carUnrecognized: {
    ET.PERMANENT: NormalPermanentAlert("行车记录仪模式",
                                       "车辆未识别",
                                       priority=Priority.LOWEST),
  },

  EventName.aeb: {
    ET.PERMANENT: Alert(
      "刹车！",
      "紧急制动：存在碰撞风险",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.stopStop, 2.),
    ET.NO_ENTRY: NoEntryAlert("AEB：存在碰撞风险"),
  },

  EventName.stockAeb: {
    ET.PERMANENT: Alert(
      "刹车！",
      "原厂 AEB：存在碰撞风险",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.stopStop, 2.),
    ET.NO_ENTRY: NoEntryAlert("原厂 AEB：存在碰撞风险"),
  },

  EventName.fcw: {
    ET.PERMANENT: Alert(
      "刹车！",
      "存在碰撞风险",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.stopStop, 2.),
  },

  EventName.ldw: {
    ET.PERMANENT: Alert(
      "车道偏离检测",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.ldw, AudibleAlert.prompt, 3.),
  },


  # ********** events only containing alerts that display while engaged **********

  EventName.steerTempUnavailableSilent: {
    ET.WARNING: Alert(
      "转向暂不可用",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.none, 1.8),
  },

  EventName.preDriverDistracted: {
    ET.WARNING: Alert(
      "注意安全",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.promptDriverDistracted: {
    ET.WARNING: Alert(
      "注意安全",
      "司机在干嘛？？？",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.steerRequired, AudibleAlert.promptDistracted, .1),
  },

  EventName.driverDistracted: {
    ET.WARNING: Alert(
      "立即接管",
      "司机在干嘛？",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1),
  },

  EventName.preDriverUnresponsive: {
    ET.WARNING: Alert(
      "请扶方向盘",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.none, .1),
  },

  EventName.promptDriverUnresponsive: {
    ET.WARNING: Alert(
      "请扶方向盘",
      "司机没反应？",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.steerRequired, AudibleAlert.promptDistracted, .1),
  },

  EventName.driverUnresponsive: {
    ET.WARNING: Alert(
      "立即接管",
      "驾驶员无响应",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1),
  },

  EventName.manualRestart: {
    ET.WARNING: Alert(
      "接管控制",
      "手动恢复驾驶",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.resumeRequired: {
    ET.WARNING: Alert(
      "按“恢复”退出停止状态",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.belowSteerSpeed: {
    ET.WARNING: below_steer_speed_alert,
  },


  EventName.preLaneChangeLeft: {
    ET.WARNING: Alert(
      "安全时向左打方向以开始变道",
      "",
      AlertStatus.normal, AlertSize.none,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.preLaneChangeRight: {
    ET.WARNING: Alert(
      "安全时向右打方向以开始变道",
      "",
      AlertStatus.normal, AlertSize.none,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.laneChangeBlocked: {
    ET.WARNING: Alert(
      "盲区有车辆",
      "",
      AlertStatus.userPrompt, AlertSize.none,
      Priority.LOW, VisualAlert.none, AudibleAlert.bsdWarning, .1),
  },

  EventName.laneChange: {
    ET.WARNING: Alert(
      "正在变道",
      "",
      AlertStatus.normal, AlertSize.none,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.steerSaturated: {
    ET.WARNING: Alert(
      "接管控制",
      "转向超过限制",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 1.),
  },

  # 当风扇超过50%功率但不转动时触发
  EventName.fanMalfunction: {
    ET.PERMANENT: NormalPermanentAlert("风扇故障", "可能为硬件问题"),
  },

  # 摄像头不输出图像帧
  EventName.cameraMalfunction: {
    ET.PERMANENT: camera_malfunction_alert,
    ET.SOFT_DISABLE: soft_disable_alert("摄像头故障"),
    ET.NO_ENTRY: NoEntryAlert("摄像头故障：请重启设备"),
  },

  # 摄像头帧率过低
  EventName.cameraFrameRate: {
    ET.PERMANENT: NormalPermanentAlert("摄像头帧率低", "请重启设备"),
    ET.SOFT_DISABLE: soft_disable_alert("摄像头帧率低"),
    ET.NO_ENTRY: NoEntryAlert("摄像头帧率低：请重启设备"),
  },

  # 未使用
  EventName.locationdTemporaryError: {
    ET.NO_ENTRY: NoEntryAlert("locationd 临时错误"),
    ET.SOFT_DISABLE: soft_disable_alert("locationd 临时错误"),
  },

  EventName.locationdPermanentError: {
    ET.NO_ENTRY: NoEntryAlert("locationd 永久错误"),
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("locationd 永久错误"),
    ET.PERMANENT: NormalPermanentAlert("locationd 永久错误"),
  },

  # openpilot通过观察车辆对驾驶和控制的响应学习某些参数
  # 包括：
  # - 转向比：转向器齿轮比，转向角/轮胎角
  # - 轮胎刚度：轮胎抓地力
  # - 角度偏移：大多数转向角传感器有偏移，直行时测到非零角度
  # 当这些参数超过合理范围时会触发该警告
  EventName.paramsdTemporaryError: {
    ET.NO_ENTRY: paramsd_invalid_alert,
    ET.SOFT_DISABLE: soft_disable_alert("paramsd 临时错误"),
  },

  EventName.paramsdPermanentError: {
    ET.NO_ENTRY: NoEntryAlert("paramsd 永久错误"),
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("paramsd 永久错误"),
    ET.PERMANENT: NormalPermanentAlert("paramsd 永久错误"),
  },

  # ********** 影响控制状态转换的事件 **********

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
    ET.NO_ENTRY: NoEntryAlert("取消按下"),
  },

  EventName.brakeHold: {
    ET.WARNING: Alert(
      "按“恢复”退出刹车保持",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.parkBrake: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("驻车制动已拉起"),
  },

  EventName.pedalPressed: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("踏板被踩下",
                              visual_alert=VisualAlert.brakePressed),
  },

  EventName.preEnableStandstill: {
    ET.PRE_ENABLE: Alert(
      "松开刹车以启用",
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
    ET.NO_ENTRY: NoEntryAlert("按“设置”以启用"),
  },

  EventName.wrongCruiseMode: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("自适应巡航已禁用"),
  },

  EventName.steerTempUnavailable: {
    ET.SOFT_DISABLE: soft_disable_alert("转向暂不可用"),
    ET.NO_ENTRY: NoEntryAlert("转向暂不可用"),
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
      "可能的硬件问题",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, .2, creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("传感器数据无效"),
    ET.SOFT_DISABLE: soft_disable_alert("传感器数据无效"),
  },

  EventName.noGps: {
    ET.PERMANENT: Alert(
      "GPS信号弱",
      "确保设备无遮挡物，可看到天空",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, .2, creation_delay=600.)
  },

  EventName.tooDistracted: {
    ET.NO_ENTRY: NoEntryAlert("注意力分散过高"),
  },

  EventName.overheat: {
    ET.PERMANENT: overheat_alert,
    ET.SOFT_DISABLE: soft_disable_alert("系统过热"),
    ET.NO_ENTRY: NoEntryAlert("系统过热"),
  },

  EventName.wrongGear: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("档位不在D挡"),
  },


  # This alert is thrown when the calibration angles are outside of the acceptable range.
  # For example if the device is pointed too much to the left or the right.
  # Usually this can only be solved by removing the mount from the windshield completely,
  # and attaching while making sure the device is pointed straight forward and is level.
  # See https://comma.ai/setup for more information
  EventName.calibrationInvalid: {
    ET.PERMANENT: calibration_invalid_alert,
    ET.SOFT_DISABLE: soft_disable_alert("校准无效：请重新安装设备并校准"),
    ET.NO_ENTRY: NoEntryAlert("校准无效：请重新安装设备并校准"),
  },

  EventName.calibrationIncomplete: {
    ET.PERMANENT: calibration_incomplete_alert,
    ET.SOFT_DISABLE: soft_disable_alert("校准未完成"),
    ET.NO_ENTRY: NoEntryAlert("校准进行中"),
  },

  EventName.calibrationRecalibrating: {
    ET.PERMANENT: calibration_incomplete_alert,
    ET.SOFT_DISABLE: soft_disable_alert("检测到设备重新安装：正在重新校准"),
    ET.NO_ENTRY: NoEntryAlert("检测到重新安装：正在重新校准"),
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
    ET.SOFT_DISABLE: soft_disable_alert("电量过低"),
    ET.NO_ENTRY: NoEntryAlert("电量过低"),
  },

  EventName.commIssue: {
    ET.SOFT_DISABLE: soft_disable_alert("进程间通信异常"),
    ET.NO_ENTRY: comm_issue_alert,
  },
  EventName.commIssueAvgFreq: {
    ET.SOFT_DISABLE: soft_disable_alert("进程间通信速率低"),
    ET.NO_ENTRY: NoEntryAlert("进程间通信速率低"),
  },

  EventName.selfdrivedLagging: {
    ET.SOFT_DISABLE: soft_disable_alert("系统延迟"),
    ET.NO_ENTRY: NoEntryAlert("Selfdrive进程延迟：请重启设备"),
  },

  EventName.processNotRunning: {
    ET.NO_ENTRY: process_not_running_alert,
    ET.SOFT_DISABLE: soft_disable_alert("进程未运行"),
  },

  EventName.radarFault: {
    ET.SOFT_DISABLE: soft_disable_alert("雷达故障：请重启车辆"),
    ET.NO_ENTRY: NoEntryAlert("雷达故障：请重启车辆"),
  },

  EventName.radarTempUnavailable: {
    ET.SOFT_DISABLE: soft_disable_alert("雷达暂不可用"),
    ET.NO_ENTRY: NoEntryAlert("雷达暂不可用"),
  },

  EventName.modeldLagging: {
    ET.SOFT_DISABLE: soft_disable_alert("驾驶模型延迟"),
    ET.NO_ENTRY: NoEntryAlert("驾驶模型延迟"),
    ET.PERMANENT: modeld_lagging_alert,
  },

  EventName.posenetInvalid: {
    ET.SOFT_DISABLE: soft_disable_alert("Posenet速度无效"),
    ET.NO_ENTRY: posenet_invalid_alert,
  },

  EventName.deviceFalling: {
    ET.SOFT_DISABLE: soft_disable_alert("设备脱落"),
    ET.NO_ENTRY: NoEntryAlert("设备脱落"),
  },

  EventName.lowMemory: {
    ET.SOFT_DISABLE: soft_disable_alert("内存不足：请重启设备"),
    ET.PERMANENT: low_memory_alert,
    ET.NO_ENTRY: NoEntryAlert("内存不足：请重启设备"),
  },

  EventName.accFaulted: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("巡航故障：请重启车辆"),
    ET.PERMANENT: NormalPermanentAlert("巡航故障：请重启车辆以启用"),
    ET.NO_ENTRY: NoEntryAlert("巡航故障：请重启车辆"),
  },

  EventName.espActive: {
    ET.SOFT_DISABLE: soft_disable_alert("电子稳定控制已激活"),
    ET.NO_ENTRY: NoEntryAlert("电子稳定控制已激活"),
  },

  EventName.controlsMismatch: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("控制状态不匹配"),
    ET.NO_ENTRY: NoEntryAlert("控制状态不匹配"),
  },

  EventName.usbError: {
    ET.SOFT_DISABLE: soft_disable_alert("USB错误：请重启设备"),
    ET.PERMANENT: NormalPermanentAlert("USB错误：请重启设备", ""),
    ET.NO_ENTRY: NoEntryAlert("USB错误：请重启设备"),
  },

  EventName.canError: {
    ET.PERMANENT: car_parser_result,
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("CAN错误"),
    ET.NO_ENTRY: NoEntryAlert("CAN错误：检查连接"),
  },

  EventName.canBusMissing: {
    ET.PERMANENT: car_parser_result,
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("CAN总线断开"),
    ET.NO_ENTRY: NoEntryAlert("CAN总线断开：检查连接"),
  },

  EventName.steerUnavailable: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("LKAS故障：请重启车辆"),
    ET.PERMANENT: ImmediateDisableAlert("LKAS故障：请重启车辆以启用"),
    ET.NO_ENTRY: NoEntryAlert("LKAS故障：请重启车辆"),
  },

  EventName.reverseGear: {
    ET.PERMANENT: Alert(
      "倒档",
      "",
      AlertStatus.normal, AlertSize.none,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.reverseGear, .2, creation_delay=0.5),
    ET.SOFT_DISABLE: SoftDisableAlert("倒档"),
    ET.NO_ENTRY: NoEntryAlert("倒档"),
  },

  EventName.cruiseDisabled: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("巡航已关闭"),
  },

  EventName.relayMalfunction: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("线束继电器故障"),
    ET.PERMANENT: NormalPermanentAlert("线束继电器故障", "检查硬件"),
    ET.NO_ENTRY: NoEntryAlert("线束继电器故障"),
  },

  EventName.speedTooLow: {
    ET.IMMEDIATE_DISABLE: Alert(
      "openpilot已取消",
      "速度过低",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.disengage, 3.),
  },

  EventName.speedTooHigh: {
    ET.WARNING: Alert(
      "速度过高",
      "模型在此速度下不稳定",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.promptRepeat, 4.),
    ET.NO_ENTRY: NoEntryAlert("降低速度以启用"),
  },

  EventName.vehicleSensorsInvalid: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("车辆传感器无效"),
    ET.PERMANENT: NormalPermanentAlert("车辆传感器校准中", "驾驶以校准"),
    ET.NO_ENTRY: NoEntryAlert("车辆传感器校准中"),
  },

  EventName.personalityChanged: {
    ET.WARNING: personality_changed_alert,
  },

  EventName.softHold: {
    ET.WARNING: Alert(
      "软保持",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },
  EventName.trafficStopping: {
    ET.WARNING: EngagementAlert(AudibleAlert.stopping),
  },
  EventName.audioPrompt: {
     ET.WARNING: EngagementAlert(AudibleAlert.prompt),
  },
  EventName.audioRefuse: {
     ET.WARNING: EngagementAlert(AudibleAlert.refuse),
  },
  EventName.stopStop: {
     ET.WARNING: EngagementAlert(AudibleAlert.stopStop),
  },
  EventName.audioLaneChange: {
     ET.WARNING: EngagementAlert(AudibleAlert.laneChange),
  },
  EventName.audioTurn: {
     ET.WARNING: EngagementAlert(AudibleAlert.audioTurn),
  },
  EventName.trafficSignGreen: {
    ET.WARNING: EngagementAlert(AudibleAlert.trafficSignGreen),
  },
  EventName.trafficSignChanged: {
    ET.WARNING: Alert(
      "信号已更改",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.trafficSignChanged, 1.),
  },
  EventName.turningLeft: {
    ET.WARNING: Alert(
      "左转中",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.turningRight: {
    ET.WARNING: Alert(
      "右转中",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.audio1: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio1),
  },
  EventName.audio2: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio2),
  },
  EventName.audio3: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio3),
  },
  EventName.audio4: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio4),
  },
  EventName.audio5: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio5),
  },
  EventName.audio6: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio6),
  },
  EventName.audio7: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio7),
  },
  EventName.audio8: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio8),
  },
  EventName.audio9: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio9),
  },
  EventName.audio10: {
     ET.WARNING: EngagementAlert(AudibleAlert.audio10),
  },
  EventName.audio0: {
     ET.WARNING: EngagementAlert(AudibleAlert.longDisengaged),
  },
  EventName.torqueNNLoad: {
    ET.PERMANENT: torque_nn_load_alert,
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
        alert = alert(CP, CS, sm, False, 1, log.LongitudinalPersonality.standard)
      alerts_by_type[et][alert.priority].append(event_names[i])

  all_alerts: dict[str, list[tuple[Priority, list[str]]]] = {}
  for et, priority_alerts in alerts_by_type.items():
    all_alerts[et] = sorted(priority_alerts.items(), key=lambda x: x[0], reverse=True)

  for status, evs in sorted(all_alerts.items(), key=lambda x: x[0]):
    print(f"**** {status} ****")
    for p, alert_list in evs:
      print(f"  {repr(p)}:")
      print("   ", ', '.join(alert_list), "\n")
