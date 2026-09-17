"""Carrot tuning layout with top tabs. Auto-generated from webui panel_catalog.py."""
from collections.abc import Callable
from enum import IntEnum

import pyray as rl

from openpilot.common.params import Params
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import (
  Scroller, toggle_item_sp, option_item_sp, button_item_sp
)
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.network import NavButton
from openpilot.system.ui.sunnypilot.lib.styles import style


class TabType(IntEnum):
  START = 0
  CRUISE = 1
  NAVI = 2
  SPEED = 3
  TUNING = 4
  DISPLAY = 5
  PATH = 6
  VEHICLE = 7
  DEV = 8


class CarrotTuningLayout(Widget):
  """Carrot tuning settings with top tabs."""

  TAB_LABELS = [tr('Start'), tr('Cruise'), tr('Navigation'), tr('Speed'), tr('Tuning'), tr('Display'), tr('Path'), tr('Vehicle'), tr('Developer')]
  TAB_COUNT = len(TAB_LABELS)
  TAB_HEIGHT = 80
  TAB_TOP_MARGIN = 12

  def __init__(self, back_btn_callback: Callable):
    super().__init__()
    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(back_btn_callback)

    self._start_items = self._build_start_items()
    self._cruise_items = self._build_cruise_items()
    self._navi_items = self._build_navi_items()
    self._speed_items = self._build_speed_items()
    self._tuning_items = self._build_tuning_items()
    self._display_items = self._build_display_items()
    self._path_items = self._build_path_items()
    self._vehicle_items = self._build_vehicle_items()
    self._dev_items = self._build_dev_items()
    self._start_scroller = Scroller(self._start_items, spacing=0, line_separator=True)
    self._cruise_scroller = Scroller(self._cruise_items, spacing=0, line_separator=True)
    self._navi_scroller = Scroller(self._navi_items, spacing=0, line_separator=True)
    self._speed_scroller = Scroller(self._speed_items, spacing=0, line_separator=True)
    self._tuning_scroller = Scroller(self._tuning_items, spacing=0, line_separator=True)
    self._display_scroller = Scroller(self._display_items, spacing=0, line_separator=True)
    self._path_scroller = Scroller(self._path_items, spacing=0, line_separator=True)
    self._vehicle_scroller = Scroller(self._vehicle_items, spacing=0, line_separator=True)
    self._dev_scroller = Scroller(self._dev_items, spacing=0, line_separator=True)
    self._tab_scrollers = {
      TabType.START: self._start_scroller,
      TabType.CRUISE: self._cruise_scroller,
      TabType.NAVI: self._navi_scroller,
      TabType.SPEED: self._speed_scroller,
      TabType.TUNING: self._tuning_scroller,
      TabType.DISPLAY: self._display_scroller,
      TabType.PATH: self._path_scroller,
      TabType.VEHICLE: self._vehicle_scroller,
      TabType.DEV: self._dev_scroller,
    }
    self._current_tab = TabType.START

  def _render(self, rect):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), style.BASE_BG_COLOR)
    tab_rect = rl.Rectangle(rect.x, rect.y + self.TAB_TOP_MARGIN, rect.width, self.TAB_HEIGHT)
    self._render_tabs(tab_rect)
    back_h = self._back_button.rect.height
    content_rect = rl.Rectangle(
      rect.x,
      rect.y + self.TAB_TOP_MARGIN + self.TAB_HEIGHT,
      rect.width,
      rect.height - self.TAB_TOP_MARGIN - self.TAB_HEIGHT - back_h - 20,
    )
    self._tab_scrollers[self._current_tab].render(content_rect)
    self._back_button.set_position(rect.x + 20, rect.y + rect.height - back_h - 20)
    self._back_button.render()

  def _render_tabs(self, rect):
    tab_w = rect.width / self.TAB_COUNT
    for i, label in enumerate(self.TAB_LABELS):
      x = rect.x + i * tab_w
      tab_rect = rl.Rectangle(x, rect.y, tab_w, rect.height)
      is_active = self._current_tab == i
      bg = style.ON_BG_COLOR if is_active else style.OFF_BG_COLOR
      rl.draw_rectangle_rounded(tab_rect, 0.15, 8, bg)
      text_color = rl.WHITE if is_active else style.ITEM_TEXT_COLOR
      rl.draw_text(label, int(x + tab_w / 2 - rl.measure_text(label, 24) / 2),
                   int(rect.y + rect.height / 2 - 12), 24, text_color)
      if (rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT) and
          rl.check_collision_point_rec(rl.get_mouse_position(), tab_rect)):
        self._current_tab = i

  def show_event(self):
    for scroller in self._tab_scrollers.values():
      scroller.show_event()

  def fade_in(self):
    for scroller in self._tab_scrollers.values():
      scroller.fade_in()

  def _build_start_items(self):
    return [
      # --- Auto Start / Cruise ---
      option_item_sp(title=tr('Auto Engage'), param='AutoEngage', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Auto Cruise Speed'), param='AutoCruiseControl', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cruise On Distance'), param='CruiseOnDist', min_value=0, max_value=300, value_change_step=5),
      option_item_sp(title=tr('Eco Cruise Control'), param='CruiseEcoControl', min_value=0, max_value=3, value_change_step=1),
      # --- Button Behavior ---
      option_item_sp(title=tr('Cruise Button Mode'), param='CruiseButtonMode', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cancel Button Mode'), param='CancelButtonMode', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Soft Hold on Cancel'), param='SoftHoldOnCancel', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Cruise Button Long Press Delay'), param='CruiseButtonLongDelay', min_value=0, max_value=200, value_change_step=5),
      # --- Speed Presets ---
      option_item_sp(title=tr('Cruise Preset Speed 1'), param='CruiseSpeed1', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Cruise Preset Speed 2'), param='CruiseSpeed2', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Cruise Preset Speed 3'), param='CruiseSpeed3', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Cruise Preset Speed 4'), param='CruiseSpeed4', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Cruise Preset Speed 5'), param='CruiseSpeed5', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Cruise Preset Speed Unit'), param='CruiseSpeedUnit', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Basic Cruise Preset Speed Unit'), param='CruiseSpeedUnitBasic', min_value=0, max_value=100, value_change_step=1),
      # --- Steering Wheel Buttons ---
      option_item_sp(title=tr('LFA Button Mode'), param='LfaButtonMode', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Paddle Mode'), param='PaddleMode', min_value=0, max_value=3, value_change_step=1),
      # --- Auto Gas ---
      option_item_sp(title=tr('Auto Gas Cancel Speed'), param='AutoGasCancelSpeed', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Auto Gas Sync Speed'), param='AutoGasSyncSpeed', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Auto Gas Takeover Speed'), param='AutoGasTokSpeed', min_value=0, max_value=200, value_change_step=5),
    ]

  def _build_cruise_items(self):
    return [
      # --- Following Distance ---
      option_item_sp(title=tr('Follow Time Gap 1'), param='TFollowGap1', min_value=50, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
      option_item_sp(title=tr('Follow Time Gap 2'), param='TFollowGap2', min_value=50, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
      option_item_sp(title=tr('Follow Time Gap 3'), param='TFollowGap3', min_value=50, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
      option_item_sp(title=tr('Follow Time Gap 4'), param='TFollowGap4', min_value=50, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
      option_item_sp(title=tr('Dynamic Follow Time'), param='DynamicTFollow', min_value=0, max_value=200, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
      option_item_sp(title=tr('Dynamic Follow Time on Lane Change'), param='DynamicTFollowLC', min_value=0, max_value=200, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
      # --- Longitudinal Gains ---
      option_item_sp(title=tr('Lead Acceleration Response'), param='LeadAccelResponse', min_value=-100, max_value=100, value_change_step=5),
      option_item_sp(title=tr('Longitudinal Actuator Delay'), param='LongActuatorDelay', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Longitudinal Feedforward'), param='LongTuningKf', min_value=0, max_value=300, value_change_step=5),
      option_item_sp(title=tr('Longitudinal Integral Velocity'), param='LongTuningKiV', min_value=0, max_value=300, value_change_step=5),
      option_item_sp(title=tr('Longitudinal Proportional Velocity'), param='LongTuningKpV', min_value=0, max_value=300, value_change_step=5),
      option_item_sp(title=tr('Stopping Acceleration'), param='StoppingAccel', min_value=-200, max_value=0, value_change_step=5),
      option_item_sp(title=tr('Follow Deceleration Boost'), param='TFollowDecelBoost', min_value=0, max_value=200, value_change_step=5),
      # --- Acceleration Limits ---
      option_item_sp(title=tr('Cruise Max Acceleration 0'), param='CruiseMaxVals0', min_value=0, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f} m/s²'),
      option_item_sp(title=tr('Cruise Max Acceleration 1'), param='CruiseMaxVals1', min_value=0, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f} m/s²'),
      option_item_sp(title=tr('Cruise Max Acceleration 2'), param='CruiseMaxVals2', min_value=0, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f} m/s²'),
      option_item_sp(title=tr('Cruise Max Acceleration 3'), param='CruiseMaxVals3', min_value=0, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f} m/s²'),
      option_item_sp(title=tr('Cruise Max Acceleration 4'), param='CruiseMaxVals4', min_value=0, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f} m/s²'),
      option_item_sp(title=tr('Cruise Max Acceleration 5'), param='CruiseMaxVals5', min_value=0, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f} m/s²'),
      option_item_sp(title=tr('Cruise Max Acceleration 6'), param='CruiseMaxVals6', min_value=0, max_value=300, value_change_step=5,
                     use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f} m/s²'),
      # --- Cruise Behavior ---
      option_item_sp(title=tr('Carrot Cruise Decel'), param='CarrotCruiseDecel', min_value=-100, max_value=0, value_change_step=1),
      option_item_sp(title=tr('Carrot Cruise ATC Decel'), param='CarrotCruiseAtcDecel', min_value=-100, max_value=0, value_change_step=1),
      option_item_sp(title=tr('Stop Speed Threshold'), param='VEgoStopping', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Model Speed Compensation'), param='ApplyModelSpeed', min_value=0, max_value=2, value_change_step=1),
    ]

  def _build_navi_items(self):
    return [
      # --- Navigation Speed Control ---
      option_item_sp(title=tr('Navigation Speed Ctrl Mode'), param='AutoNaviSpeedCtrlMode', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Navigation Speed Decel Rate'), param='AutoNaviSpeedDecelRate', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Navigation Speed Safety Factor'), param='AutoNaviSpeedSafetyFactor', min_value=50, max_value=150, value_change_step=5),
      option_item_sp(title=tr('Navigation Speed Ctrl End Distance'), param='AutoNaviSpeedCtrlEnd', min_value=0, max_value=30, value_change_step=1),
      # --- Stop / Speed Camera ---
      option_item_sp(title=tr('Stop Target Distance'), param='StopDistanceCarrot', min_value=0, max_value=2000, value_change_step=10),
      toggle_item_sp(title=tr('Same Direction Speed Cam Filter'), param='SameSpiCamFilter'),
      option_item_sp(title=tr('Speed Camera Haptic Alert'), param='HapticFeedbackWhenSpeedCamera', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Traffic Stop Distance Adjust'), param='TrafficStopDistanceAdjust', min_value=-500, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Traffic Light Detect Mode'), param='TrafficLightDetectMode', min_value=0, max_value=2, value_change_step=1),
      # --- Road Speed Limits ---
      option_item_sp(title=tr('Road Speed Auto Adjust'), param='AutoRoadSpeedAdjust', min_value=-50, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Road Speed Limit Offset'), param='AutoRoadSpeedLimitOffset', min_value=-20, max_value=20, value_change_step=1),
      toggle_item_sp(title=tr('Auto Speed Up to Road Limit'), param='AutoSpeedUptoRoadSpeedLimit'),
      option_item_sp(title=tr('Speed Source PCM'), param='SpeedFromPCM', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Road Type'), param='RoadType', min_value=0, max_value=2, value_change_step=1),
      # --- Vehicle Navigation ---
      toggle_item_sp(title=tr('Vehicle Navi CAN Control'), param='VehicleNaviCanControl'),
      toggle_item_sp(title=tr('School Zone CAN Control'), param='VehicleNaviSchoolZoneControl'),
      option_item_sp(title=tr('Speed Camera Control Mode'), param='VehicleSpeedCameraControlMode', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Speed Camera Alert Time'), param='VehicleSpeedCameraDistanceTime', min_value=0, max_value=30, value_change_step=1),
      # --- Navigation Speed Bumps ---
      option_item_sp(title=tr('Speed Bump End Distance'), param='AutoNaviSpeedBumpEndDistance', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Countdown Mode'), param='AutoNaviCountDownMode', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Speed Bump Target Speed'), param='AutoNaviSpeedBumpSpeed', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Speed Bump Hold Time'), param='AutoNaviSpeedBumpTime', min_value=0, max_value=20, value_change_step=1),
    ]

  def _build_speed_items(self):
    return [
      # --- Auto Turn Control ---
      option_item_sp(title=tr('Auto Turn Control'), param='AutoTurnControl', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Auto Turn Speed Threshold'), param='AutoTurnControlSpeedTurn', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Auto Turn End Distance'), param='AutoTurnControlTurnEnd', min_value=0, max_value=500, value_change_step=10),
      toggle_item_sp(title=tr('Auto Turn on Navi Lane Change'), param='AutoTurnMapChange'),
      option_item_sp(title=tr('Auto Turn Distance Offset'), param='AutoTurnDistOffset', min_value=-200, max_value=200, value_change_step=10),
      # --- Fork Control ---
      option_item_sp(title=tr('Fork Merge Distance Offset'), param='AutoForkDistOffset', min_value=-200, max_value=200, value_change_step=10),
      option_item_sp(title=tr('Fork Merge Distance Offset (Highway)'), param='AutoForkDistOffsetH', min_value=-200, max_value=200, value_change_step=10),
      option_item_sp(title=tr('Fork Blinker Trigger Distance'), param='AutoDoForkBlinkerDist', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Fork Blinker Trigger Distance (Highway)'), param='AutoDoForkBlinkerDistH', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Fork Navi Trigger Distance'), param='AutoDoForkNavDist', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Fork Navi Trigger Distance (Highway)'), param='AutoDoForkNavDistH', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Fork Decel Trigger Distance'), param='AutoDoForkDecalDist', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Fork Decel Trigger Distance (Highway)'), param='AutoDoForkDecalDistH', min_value=0, max_value=500, value_change_step=10),
      option_item_sp(title=tr('Fork Decel Rate'), param='AutoForkDecalRate', min_value=0, max_value=300, value_change_step=10),
      option_item_sp(title=tr('Fork Decel Rate (Highway)'), param='AutoForkDecalRateH', min_value=0, max_value=300, value_change_step=10),
      option_item_sp(title=tr('Fork Minimum Speed'), param='AutoForkSpeedMin', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Fork Minimum Speed (Highway)'), param='AutoForkSpeedMinH', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Fork Keep Speed'), param='AutoKeepForkSpeed', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Fork Keep Speed (Highway)'), param='AutoKeepForkSpeedH', min_value=0, max_value=200, value_change_step=5),
      toggle_item_sp(title=tr('Auto Turn Outside Road Edge'), param='AutoTurnInNotRoadEdge'),
      # --- Curve Speed ---
      option_item_sp(title=tr('Map Turn Speed Factor'), param='MapTurnSpeedFactor', min_value=50, max_value=150, value_change_step=5),
      option_item_sp(title=tr('Turn Speed Control Mode'), param='TurnSpeedControlMode', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Curve Speed Factor'), param='AutoCurveSpeedFactor', min_value=50, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Curve Speed Factor (Highway)'), param='AutoCurveSpeedFactorH', min_value=50, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Highway Curve Aggressiveness'), param='AutoCurveSpeedAggressivenessH', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Curve Speed Lower Limit'), param='AutoCurveSpeedLowerLimit', min_value=0, max_value=100, value_change_step=5),
      # --- Road Speed Limits Override ---
      toggle_item_sp(title=tr('Auto Up Road Limit'), param='AutoUpRoadLimit'),
      toggle_item_sp(title=tr('Auto Up 40 km/h Road Limit'), param='AutoUpRoadLimit40KMH'),
      toggle_item_sp(title=tr('Auto Up Highway Limit'), param='AutoUpHighwayRoadLimit'),
      toggle_item_sp(title=tr('Auto Up 40 km/h Highway Limit'), param='AutoUpHighwayRoadLimit40KMH'),
    ]

  def _build_tuning_items(self):
    return [
      # --- Lateral Control ---
      toggle_item_sp(title=tr('Always Lateral'), param='AlwaysLateral'),
      option_item_sp(title=tr('Custom Steer Ratio'), param='CustomSR', min_value=50, max_value=200, value_change_step=1),
      option_item_sp(title=tr('Steer Delta Down'), param='CustomSteerDeltaDown', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Steer Delta Up'), param='CustomSteerDeltaUp', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Steer Delta Down (Lane Change)'), param='CustomSteerDeltaDownLC', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Steer Delta Up (Lane Change)'), param='CustomSteerDeltaUpLC', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Max Steer Angle'), param='CustomSteerMax', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Path Offset'), param='PathOffset', min_value=-100, max_value=100, value_change_step=5),
      option_item_sp(title=tr('Steer Actuator Delay'), param='SteerActuatorDelay', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Steer Ratio Rate'), param='SteerRatioRate', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Lateral Acceleration Cost'), param='LatMpcAccelCost', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Jerk Cost'), param='LatMpcJerkCost', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Motion Cost'), param='LatMpcMotionCost', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Path Cost'), param='LatMpcPathCost', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Steering Rate Cost'), param='LatMpcSteeringRateCost', min_value=0, max_value=500, value_change_step=5),
      # --- Steering Torque ---
      toggle_item_sp(title=tr('Custom Lateral Torque'), param='LateralTorqueCustom'),
      option_item_sp(title=tr('Lateral Torque Friction'), param='LateralTorqueFriction', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Torque Derivative'), param='LateralTorqueKd', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Torque Feedforward'), param='LateralTorqueKf', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Torque Integral Velocity'), param='LateralTorqueKiV', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Torque Proportional'), param='LateralTorqueKpV', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lateral Torque Accel Factor'), param='LateralTorqueAccelFactor', min_value=0, max_value=300, value_change_step=5),
      option_item_sp(title=tr('Lateral MPC Input Offset'), param='LatMpcInputOffset', min_value=-100, max_value=100, value_change_step=5),
      option_item_sp(title=tr('Lateral Smooth Seconds'), param='LatSmoothSec', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Lane Offset Adjust'), param='AdjustLaneOffset', min_value=-100, max_value=100, value_change_step=5),
      option_item_sp(title=tr('Camera Yaw Trim'), param='CameraYawTrimDeg', min_value=-10, max_value=10, value_change_step=1),
      # --- Lane Change ---
      toggle_item_sp(title=tr('Lane Change BSD'), param='LaneChangeBsd'),
      option_item_sp(title=tr('Lane Change Delay'), param='LaneChangeDelay', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Lane Change Need Torque'), param='LaneChangeNeedTorque', min_value=0, max_value=10, value_change_step=1),
      toggle_item_sp(title=tr('Continuous Lane Change'), param='ContinuousLaneChange'),
      option_item_sp(title=tr('Continuous Lane Change Count'), param='ContinuousLaneChangeCnt', min_value=0, max_value=10, value_change_step=1),
      option_item_sp(title=tr('Continuous Lane Change Interval'), param='ContinuousLaneChangeInterval', min_value=0, max_value=100, value_change_step=5),
      option_item_sp(title=tr('Lane Change Start Cost'), param='AChangeCostStarting', min_value=0, max_value=500, value_change_step=5),
      option_item_sp(title=tr('Lane Stabilization Time'), param='LaneStabTime', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('New Lane Width Difference'), param='NewLaneWidthDiff', min_value=0, max_value=100, value_change_step=5),
      option_item_sp(title=tr('Auto Enter New Lane Time'), param='AutoEnTurnNewLaneTime', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Auto Enter New Lane Time (Highway)'), param='AutoEnTurnNewLaneTimeH', min_value=0, max_value=50, value_change_step=1),
      toggle_item_sp(title=tr('Auto Turn Left'), param='AutoTurnLeft'),
      option_item_sp(title=tr('Stock Blinker Control'), param='StockBlinkerCtrl', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Extended Blinker Test'), param='ExtBlinkerCtrlTest', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Blinker Mode'), param='BlinkerMode', min_value=0, max_value=2, value_change_step=1),
      # --- Blind Spot ---
      toggle_item_sp(title=tr('Disable Blind Spot'), param='DisableBlindSpot'),
      option_item_sp(title=tr('Dynamic Blind Spot Range'), param='DynamicBlindRange', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Dynamic Blind Spot Distance'), param='DynamicBlindDistance', min_value=0, max_value=200, value_change_step=5),
      option_item_sp(title=tr('Blind Spot Delay Time'), param='BsdDelayTime', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Side Blind Spot Delay'), param='SideBsdDelayTime', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Side Relative Distance Time'), param='SideRelDistTime', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Side vRel Distance Time'), param='SidevRelDistTime', min_value=0, max_value=50, value_change_step=1),
      option_item_sp(title=tr('Side Radar Min Distance'), param='SideRadarMinDist', min_value=0, max_value=100, value_change_step=1),
      # --- ONNX ---
      toggle_item_sp(title=tr('Lane Line Check'), param='LaneLineCheck'),
      option_item_sp(title=tr('ONNX BSD Interval'), param='OnnxBsdIntervalMs', min_value=0, max_value=1000, value_change_step=10),
      option_item_sp(title=tr('ONNX BSD Smoothing'), param='OnnxBsdSmoothingMs', min_value=0, max_value=1000, value_change_step=10),
      option_item_sp(title=tr('ONNX BSD Threshold'), param='OnnxBsdThreshold', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('ONNX Lane Interval'), param='OnnxLaneIntervalMs', min_value=0, max_value=1000, value_change_step=10),
      option_item_sp(title=tr('ONNX Lane Threshold'), param='OnnxLaneThreshold', min_value=0, max_value=100, value_change_step=1),
    ]

  def _build_display_items(self):
    return [
      # --- HUD / Cluster ---
      option_item_sp(title=tr('Lateral Suspend Angle'), param='LatSuspendAngleDeg', min_value=0, max_value=90, value_change_step=1),
      option_item_sp(title=tr('Cluster Navigation Map Theme'), param='ClusterNaviMapTheme', min_value=0, max_value=5, value_change_step=1),
      option_item_sp(title=tr('Cluster Navigation Map Type'), param='ClusterNaviMapType', min_value=0, max_value=2, value_change_step=1),
      option_item_sp(title=tr('Cluster Navigation Map FPS'), param='ClusterNaviMapFps', min_value=1, max_value=60, value_change_step=1),
      option_item_sp(title=tr('Carrot Navi HUD Profile'), param='CarrotNaviHudMapProfile', min_value=0, max_value=5, value_change_step=1),
      toggle_item_sp(title=tr('Cluster HUD'), param='ClusterHud'),
      option_item_sp(title=tr('Cluster HUD Brightness'), param='ClusterHudBrightness', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Camera View Mode'), param='ClusterHudCameraViewMode', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Core Mode'), param='ClusterHudCoreMode', min_value=0, max_value=3, value_change_step=1),
      toggle_item_sp(title=tr('Cluster HUD Debug'), param='ClusterHudDebug'),
      option_item_sp(title=tr('Cluster HUD Encoder'), param='ClusterHudEncoder', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Live FPS'), param='ClusterHudLiveFps', min_value=1, max_value=60, value_change_step=1),
      toggle_item_sp(title=tr('Cluster HUD Mirror'), param='ClusterHudMirror'),
      option_item_sp(title=tr('Cluster HUD Orientation'), param='ClusterHudOrientation', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Panel Layout'), param='ClusterHudPanelLayout', min_value=0, max_value=5, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Priority'), param='ClusterHudPriority', min_value=0, max_value=3, value_change_step=1),
      toggle_item_sp(title=tr('Cluster HUD Radar Display'), param='ClusterHudRadarDisplay'),
      option_item_sp(title=tr('Cluster HUD Radar Info'), param='ClusterHudRadarInfo', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Radar Source Color'), param='ClusterHudRadarSourceColor', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Screen Mode'), param='ClusterHudScreenMode', min_value=0, max_value=3, value_change_step=1),
      option_item_sp(title=tr('Cluster HUD Theme'), param='ClusterHudTheme', min_value=0, max_value=5, value_change_step=1),
      # --- Display ---
      toggle_item_sp(title=tr('Show Camera with Cluster'), param='ShowCameraWithCluster'),
      option_item_sp(title=tr('Show Custom Brightness'), param='ShowCustomBrightness', min_value=0, max_value=100, value_change_step=1),
      toggle_item_sp(title=tr('Show Date Time'), param='ShowDateTime'),
      toggle_item_sp(title=tr('Show Debug UI'), param='ShowDebugUI'),
      toggle_item_sp(title=tr('Show Device State'), param='ShowDeviceState'),
      toggle_item_sp(title=tr('Show Lane Info'), param='ShowLaneInfo'),
      toggle_item_sp(title=tr('Show Model View'), param='ShowModelView'),
      option_item_sp(title=tr('Show Plot Mode'), param='ShowPlotMode', min_value=0, max_value=3, value_change_step=1),
      toggle_item_sp(title=tr('Show Radar Info'), param='ShowRadarInfo'),
      toggle_item_sp(title=tr('Show Route Info'), param='ShowRouteInfo'),
      toggle_item_sp(title=tr('Show TPMS'), param='ShowTpms'),
      toggle_item_sp(title=tr('Software Menu'), param='SoftwareMenu'),
      # --- Sound ---
      option_item_sp(title=tr('Sound Volume Adjust'), param='SoundVolumeAdjust', min_value=-100, max_value=100, value_change_step=5),
      option_item_sp(title=tr('Sound Volume Adjust Engage'), param='SoundVolumeAdjustEngage', min_value=-100, max_value=100, value_change_step=5),
      button_item_sp(title=tr('Sound Language'), button_text=lambda: Params().get("SoundLanguageSetting") or "auto"),
      # --- YouTube ---
      toggle_item_sp(title=tr('Carrot YouTube Live'), param='CarrotYouTubeLive'),
      option_item_sp(title=tr('Carrot YouTube Quality'), param='CarrotYouTubeQuality', min_value=0, max_value=3, value_change_step=1),
      toggle_item_sp(title=tr('Carrot YouTube Timestamp'), param='CarrotYouTubeTimestamp'),
      # --- Map ---
      option_item_sp(title=tr('Mapbox Style'), param='MapboxStyle', min_value=0, max_value=5, value_change_step=1),
    ]

  def _build_path_items(self):
    return [
      # --- Path ---
      option_item_sp(title=tr('Path Color'), param='ShowPathColor', min_value=0, max_value=10, value_change_step=1),
      option_item_sp(title=tr('Path Color Cruise Off'), param='ShowPathColorCruiseOff', min_value=0, max_value=10, value_change_step=1),
      option_item_sp(title=tr('Path Color Lane'), param='ShowPathColorLane', min_value=0, max_value=10, value_change_step=1),
      toggle_item_sp(title=tr('Show Path End'), param='ShowPathEnd'),
      option_item_sp(title=tr('Path Display Mode'), param='ShowPathMode', min_value=0, max_value=5, value_change_step=1),
      option_item_sp(title=tr('Path Display Mode Lane'), param='ShowPathModeLane', min_value=0, max_value=5, value_change_step=1),
      toggle_item_sp(title=tr('Tire Trajectory'), param='CarrotTireTrajectory'),
      toggle_item_sp(title=tr('Use Lane Line Curve Speed'), param='UseLaneLineCurveSpeed'),
      toggle_item_sp(title=tr('Use Lane Line Speed'), param='UseLaneLineSpeed'),
    ]

  def _build_vehicle_items(self):
    return [
      # --- Vehicle ---
      toggle_item_sp(title=tr('Disable Driver Monitoring'), param='DisableDM'),
      option_item_sp(title=tr('Disable Min Steer Speed'), param='DisableMinSteerSpeed', min_value=0, max_value=200, value_change_step=5),
      toggle_item_sp(title=tr('Hyundai Camera SCC'), param='HyundaiCameraSCC'),
      toggle_item_sp(title=tr('LDWS Vehicle'), param='IsLdwsCar'),
      toggle_item_sp(title=tr('HDP Use'), param='HDPuse'),
      toggle_item_sp(title=tr('Hotspot on Boot'), param='HotspotOnBoot'),
      option_item_sp(title=tr('Max Angle Frames'), param='MaxAngleFrames', min_value=0, max_value=100, value_change_step=1),
      option_item_sp(title=tr('Max Time Offroad (min)'), param='MaxTimeOffroad', min_value=0, max_value=11, value_change_step=1),
      toggle_item_sp(title=tr('Record Road Camera'), param='RecordRoadCam'),
      toggle_item_sp(title=tr('Share Data'), param='ShareData'),
      toggle_item_sp(title=tr('Use Wide Camera'), param='UseWideCamera'),
      toggle_item_sp(title=tr('Mute Door'), param='MuteDoor'),
      toggle_item_sp(title=tr('Mute Seatbelt'), param='MuteSeatbelt'),
      toggle_item_sp(title=tr('Enable Corner Radar'), param='EnableCornerRadar'),
      toggle_item_sp(title=tr('Enable Radar Tracks'), param='EnableRadarTracks'),
      toggle_item_sp(title=tr('Enable Speed TF'), param='EnableSpeedTF'),
      option_item_sp(title=tr('My Driving Mode'), param='MyDrivingMode', min_value=0, max_value=5, value_change_step=1),
      toggle_item_sp(title=tr('My Driving Mode Auto'), param='MyDrivingModeAuto'),
    ]

  def _build_dev_items(self):
    return [
      # --- Developer ---
      toggle_item_sp(title=tr('CANFD Debug'), param='CanfdDebug'),
      toggle_item_sp(title=tr('CANFD HDA2'), param='CanfdHDA2'),
      toggle_item_sp(title=tr('C3x Lite Hardware'), param='HardwareC3xLite'),
      option_item_sp(title=tr('Cruise Button Test 1'), param='CruiseButtonTest1', min_value=0, max_value=5, value_change_step=1),
      option_item_sp(title=tr('Cruise Button Test 2'), param='CruiseButtonTest2', min_value=0, max_value=5, value_change_step=1),
      option_item_sp(title=tr('Cruise Button Test 3'), param='CruiseButtonTest3', min_value=0, max_value=5, value_change_step=1),
      toggle_item_sp(title=tr('Show Debug Log'), param='ShowDebugLog'),
    ]
