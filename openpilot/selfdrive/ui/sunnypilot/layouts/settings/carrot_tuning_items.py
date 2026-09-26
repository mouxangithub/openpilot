"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Carrot tuning settings items.

Each `_build_*_items()` supplies the contents of one page in `carrot_tuning.py`.
Groups inside a page are separated by `LineSeparatorSP`, matching how the rest of
the sunnypilot settings pages express grouping (see steering.py, models.py).
"""
from openpilot.common.params import Params
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import (
  LineSeparatorSP, button_item_sp, option_item_sp, section_heading_sp, toggle_item_sp,
)

def build_start_items():
  return [
    section_heading_sp(tr('Auto Start / Cruise')),
    section_heading_sp(tr('Auto Gas')),
    option_item_sp(title=tr('Auto Gas Sync Speed'), param='AutoGasSyncSpeed', min_value=0, max_value=200, value_change_step=5,
                   description=tr('Speed at which cruise set speed is re-synchronized. Tesla BYD only.')),
    option_item_sp(title=tr('Eco Cruise Control'), param='CruiseEcoControl', min_value=0, max_value=3, value_change_step=1),

  ]

def build_cruise_items():
  return [
    section_heading_sp(tr('Cruise Buttons & Speed')),
    option_item_sp(title=tr('Cruise Speed Unit'), param='CruiseSpeedUnit', min_value=1, max_value=20, value_change_step=1),
    option_item_sp(title=tr('Cruise Speed Unit (Basic)'), param='CruiseSpeedUnitBasic', min_value=1, max_value=20, value_change_step=1),
    option_item_sp(title=tr('Cruise Speed 1'), param='CruiseSpeed1', min_value=0, max_value=200, value_change_step=1),
    option_item_sp(title=tr('Cruise Speed 2'), param='CruiseSpeed2', min_value=0, max_value=200, value_change_step=1),
    option_item_sp(title=tr('Cruise Speed 3'), param='CruiseSpeed3', min_value=0, max_value=200, value_change_step=1),
    option_item_sp(title=tr('Cruise Speed 4'), param='CruiseSpeed4', min_value=0, max_value=200, value_change_step=1),
    option_item_sp(title=tr('Cruise Speed 5'), param='CruiseSpeed5', min_value=0, max_value=200, value_change_step=1),
    option_item_sp(title=tr('Cruise Button Mode'), param='CruiseButtonMode', min_value=0, max_value=3, value_change_step=1),
    option_item_sp(title=tr('Cruise Button Long Delay'), param='CruiseButtonLongDelay', min_value=10, max_value=100, value_change_step=1),
    option_item_sp(title=tr('Cancel Button Mode'), param='CancelButtonMode', min_value=0, max_value=3, value_change_step=1),
    option_item_sp(title=tr('LFA Button Mode'), param='LfaButtonMode', min_value=0, max_value=2, value_change_step=1),
    option_item_sp(title=tr('Cruise On Distance'), param='CruiseOnDist', min_value=0, max_value=200, value_change_step=1),
    option_item_sp(title=tr('Apply Model Speed'), param='ApplyModelSpeed', min_value=0, max_value=100, value_change_step=1),
    option_item_sp(title=tr('Auto Engage'), param='AutoEngage', min_value=0, max_value=2, value_change_step=1),
    section_heading_sp(tr('Following Distance')),
    # How many gap levels the distance button cycles. Belongs with follow distance,
    # not with the navigation section it was briefly placed in.
    option_item_sp(title=tr('Cruise Gap Levels'), param='CruiseGapLevels', min_value=2, max_value=4, value_change_step=1),
    option_item_sp(title=tr('Follow Time Gap 1'), param='TFollowGap1', min_value=50, max_value=300, value_change_step=5,
                   use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
    option_item_sp(title=tr('Follow Time Gap 2'), param='TFollowGap2', min_value=50, max_value=300, value_change_step=5,
                   use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
    option_item_sp(title=tr('Follow Time Gap 3'), param='TFollowGap3', min_value=50, max_value=300, value_change_step=5,
                   use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
    option_item_sp(title=tr('Follow Time Gap 4'), param='TFollowGap4', min_value=50, max_value=300, value_change_step=5,
                   use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),
    option_item_sp(title=tr('Dynamic Follow Time on Lane Change'), param='DynamicTFollowLC', min_value=0, max_value=200, value_change_step=5,
                   use_float_scaling=True, label_callback=lambda v: f'{v / 100.0:.2f}s'),

    section_heading_sp(tr('Longitudinal Gains')),
    option_item_sp(title=tr('Lead Acceleration Response'), param='LeadAccelResponse', min_value=-100, max_value=100, value_change_step=5,
                   description=tr('How aggressively the car reacts to lead car acceleration changes.')),
    option_item_sp(title=tr('Follow Deceleration Boost'), param='TFollowDecelBoost', min_value=0, max_value=200, value_change_step=5),


  ]

def build_navi_items():
  return [
    section_heading_sp(tr('Navigation Speed Control')),
    option_item_sp(title=tr('Navigation Speed Ctrl Mode'), param='AutoNaviSpeedCtrlMode', min_value=0, max_value=3, value_change_step=1,
                   description=tr('0=Off, 1=Limit to nav speed, 2=Limit with early decel.')),
    option_item_sp(title=tr('Navigation Speed Decel Rate'), param='AutoNaviSpeedDecelRate', min_value=0, max_value=500, value_change_step=10),
    option_item_sp(title=tr('Navigation Speed Safety Factor'), param='AutoNaviSpeedSafetyFactor', min_value=50, max_value=150, value_change_step=5,
                   description=tr('Percent of nav speed to use as target (100 = exact limit).')),
    option_item_sp(title=tr('Navigation Speed Ctrl End Distance'), param='AutoNaviSpeedCtrlEnd', min_value=0, max_value=30, value_change_step=1,
                   description=tr('Distance after the speed limit point to resume normal cruise.')),

    section_heading_sp(tr('Stop / Speed Camera')),
    toggle_item_sp(title=tr('Same Direction Speed Cam Filter'), param='SameSpiCamFilter'),
    option_item_sp(title=tr('Traffic Stop Distance Adjust'), param='TrafficStopDistanceAdjust', min_value=-500, max_value=500, value_change_step=10,
                   description=tr('Fine-tune stop distance for traffic lights (cm).')),
    option_item_sp(title=tr('Traffic Light Detect Mode'), param='TrafficLightDetectMode', min_value=0, max_value=2, value_change_step=1),

    section_heading_sp(tr('Road Speed Limits')),
    option_item_sp(title=tr('Speed Source PCM'), param='SpeedFromPCM', min_value=0, max_value=2, value_change_step=1,
                   description=tr('BYD only: with 1 the car reports its own ACC set speed over CAN.')),
    option_item_sp(title=tr('Road Speed Limit Offset'), param='AutoRoadSpeedLimitOffset', min_value=-20, max_value=20, value_change_step=1),
    option_item_sp(title=tr('Road Type'), param='RoadType', min_value=0, max_value=2, value_change_step=1),

    section_heading_sp(tr('Vehicle CAN Speed Arbitration')),
    option_item_sp(title=tr('Speed Camera Alert Time'), param='VehicleSpeedCameraDistanceTime', min_value=10, max_value=200, value_change_step=1,
                   description=tr('Synthesises a camera distance when the car sends only an enforcement speed. 0.1 s units; 60 = 6.0 s.')),
    option_item_sp(title=tr('Vehicle Navi CAN Control'), param='VehicleNaviCanControl', min_value=0, max_value=3, value_change_step=1, description=tr('Send navigation-based speed limits to the car over CAN.')),
    toggle_item_sp(title=tr('School Zone CAN Control'), param='VehicleNaviSchoolZoneControl'),
    option_item_sp(title=tr('Speed Camera Control Mode'), param='VehicleSpeedCameraControlMode', min_value=0, max_value=3, value_change_step=1),

    section_heading_sp(tr('Speed Bumps')),
    option_item_sp(title=tr('Speed Bump End Distance'), param='AutoNaviSpeedBumpEndDistance', min_value=0, max_value=500, value_change_step=10),
    option_item_sp(title=tr('Countdown Mode'), param='AutoNaviCountDownMode', min_value=0, max_value=2, value_change_step=1),
    option_item_sp(title=tr('Speed Bump Target Speed'), param='AutoNaviSpeedBumpSpeed', min_value=0, max_value=100, value_change_step=1),
    option_item_sp(title=tr('Speed Bump Hold Time'), param='AutoNaviSpeedBumpTime', min_value=0, max_value=20, value_change_step=1),
  ]

def build_speed_items():
  return [
    section_heading_sp(tr('ATC Turn Control')),
    option_item_sp(title=tr('Auto Turn Control'), param='AutoTurnControl', min_value=0, max_value=3, value_change_step=1,
                   description=tr('0=Off, 1=Speed only, 2=Speed + steering.')),
    option_item_sp(title=tr('Auto Turn Speed Threshold'), param='AutoTurnControlSpeedTurn', min_value=0, max_value=200, value_change_step=5,
                   description=tr('Speed below which auto turn activates.')),
    option_item_sp(title=tr('Auto Turn End Distance'), param='AutoTurnControlTurnEnd', min_value=0, max_value=500, value_change_step=10,
                   description=tr('Distance before the turn to end control.')),
    toggle_item_sp(title=tr('Auto Turn on Navi Lane Change'), param='AutoTurnMapChange'),
    option_item_sp(title=tr('Auto Turn Distance Offset'), param='AutoTurnDistOffset', min_value=-200, max_value=200, value_change_step=10,
                   description=tr('Shift the auto turn trigger point earlier or later.')),

    section_heading_sp(tr('Fork Control')),
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

    section_heading_sp(tr('Turn Speed')),
    option_item_sp(title=tr('Map Turn Speed Factor'), param='MapTurnSpeedFactor', min_value=50, max_value=150, value_change_step=5,
                   description=tr('Percent of the nav-recommended turn speed to use.')),
    option_item_sp(title=tr('Turn Speed Control Mode'), param='TurnSpeedControlMode', min_value=0, max_value=3, value_change_step=1),
    section_heading_sp(tr('Curve Speed')),
    option_item_sp(title=tr('Curve Speed Factor'), param='AutoCurveSpeedFactor', min_value=50, max_value=200, value_change_step=5,
                   description=tr('How much lateral acceleration to allow below 80 km/h, in percent. '
                                  'Higher takes curves faster. 100 is neutral.')),
    option_item_sp(title=tr('Normal Road Curve Aggressiveness'), param='AutoCurveSpeedAggressiveness', min_value=0, max_value=200, value_change_step=5,
                   description=tr('How early to react to curves on normal roads. Lower reacts to gentler '
                                  'curves. Only applies while Smart Cruise Control (Vision) is on.')),
    option_item_sp(title=tr('Curve Speed Factor (Highway)'), param='AutoCurveSpeedFactorH', min_value=50, max_value=200, value_change_step=5,
                   description=tr('How much lateral acceleration to allow at or above 80 km/h, in percent. '
                                  'Higher takes curves faster. 100 is neutral.')),
    option_item_sp(title=tr('Highway Curve Aggressiveness'), param='AutoCurveSpeedAggressivenessH', min_value=0, max_value=200, value_change_step=5,
                   description=tr('How early to react to curves on the highway. Lower reacts to gentler '
                                  'curves. Only applies while Smart Cruise Control (Vision) is on.')),
    option_item_sp(title=tr('Curve Speed Lower Limit'), param='AutoCurveSpeedLowerLimit', min_value=0, max_value=100, value_change_step=5),

    section_heading_sp(tr('Road Limit Raising')),
    toggle_item_sp(title=tr('Auto Up Road Limit'), param='AutoUpRoadLimit'),
    option_item_sp(title=tr('Auto Up 40 km/h Road Limit'), param='AutoUpRoadLimit40KMH', min_value=0, max_value=60, value_change_step=5),
    toggle_item_sp(title=tr('Auto Up Highway Limit'), param='AutoUpHighwayRoadLimit'),
    option_item_sp(title=tr('Auto Up 40 km/h Highway Limit'), param='AutoUpHighwayRoadLimit40KMH', min_value=0, max_value=60, value_change_step=5),
  ]

def build_tuning_items():
  return [


    section_heading_sp(tr('Blind Spot')),
    toggle_item_sp(title=tr('Disable Blind Spot'), param='DisableBlindSpot'),
    option_item_sp(title=tr('Dynamic Blind Spot Range'), param='DynamicBlindRange', min_value=0, max_value=200, value_change_step=5),
    option_item_sp(title=tr('Dynamic Blind Spot Distance'), param='DynamicBlindDistance', min_value=0, max_value=200, value_change_step=5),
    option_item_sp(title=tr('Side Blind Spot Delay'), param='SideBsdDelayTime', min_value=0, max_value=50, value_change_step=1),
    option_item_sp(title=tr('Side Relative Distance Time'), param='SideRelDistTime', min_value=0, max_value=50, value_change_step=1),
    option_item_sp(title=tr('Side vRel Distance Time'), param='SidevRelDistTime', min_value=0, max_value=50, value_change_step=1),

  ]

def build_display_items():
  return [
    section_heading_sp(tr('Steering Suspend')),
    option_item_sp(title=tr('Lateral Suspend Angle'), param='LatSuspendAngleDeg', min_value=45, max_value=300, value_change_step=1,
                   label_callback=lambda v, *_: f'{v}\u00b0',
                   description=tr('Steering angle at which lateral control pauses while you steer. '
                                  '300\u00b0 effectively disables it. CarrotPilot stores 0.1-degree units for this '
                                   'parameter but its code, like this port, compares the raw value against the '
                                   'steering angle, so the number reads as degrees here.')),
    section_heading_sp(tr('Cluster Map')),
    option_item_sp(title=tr('Cluster Navigation Map Theme'), param='ClusterNaviMapTheme', min_value=0, max_value=2, value_change_step=1,
                   label_callback=lambda v, *_: {0: tr('Auto'), 1: tr('Dark'), 2: tr('Light')}.get(v, str(v))),
    option_item_sp(title=tr('Cluster Navigation Map Type'), param='ClusterNaviMapType', min_value=0, max_value=10, value_change_step=1),
    option_item_sp(title=tr('Cluster Navigation Map FPS'), param='ClusterNaviMapFps', min_value=1, max_value=60, value_change_step=1,
                   description=tr('Refresh rate of the external cluster map, in frames per second.')),
    toggle_item_sp(title=tr('Cluster Map Profile'), param='CarrotNaviHudMapProfile',
                   description=tr('Enable the cluster map HUD profile overlay.')),
    section_heading_sp(tr('Cluster HUD (external display required)')),
    # These 16 knobs drive CarrotPilot's USB/GPU external cluster renderer. This port
    # exposes them for unified sunnypilot control and so the value survives across
    # sessions; the renderer itself is not ported yet (see the webui/gui notes).
    toggle_item_sp(title=tr('Cluster HUD'), param='ClusterHud',
                   description=tr('Master switch for the external cluster HUD renderer.')),
    option_item_sp(title=tr('Cluster HUD Brightness'), param='ClusterHudBrightness', min_value=0, max_value=100, value_change_step=1,
                   label_callback=lambda v, *_: f'{v}%'),
    option_item_sp(title=tr('Cluster HUD Camera View Mode'), param='ClusterHudCameraViewMode', min_value=0, max_value=4, value_change_step=1,
                   label_callback=lambda v, *_: {0: tr('Default'), 1: tr('Ego Bottom'), 2: tr('Road Camera'),
                                                  3: tr('Wide Camera'), 4: tr('Auto Camera')}.get(v, str(v))),
    option_item_sp(title=tr('Cluster HUD Core Mode'), param='ClusterHudCoreMode', min_value=0, max_value=10, value_change_step=1),
    toggle_item_sp(title=tr('Cluster HUD Debug'), param='ClusterHudDebug',
                   description=tr('Show debug overlays on the external cluster.')),
    option_item_sp(title=tr('Cluster HUD Encoder'), param='ClusterHudEncoder', min_value=0, max_value=3, value_change_step=1,
                   label_callback=lambda v, *_: {0: tr('Auto'), 1: tr('JPEG'), 2: tr('Hardware H.264'),
                                                  3: tr('Software H.264')}.get(v, str(v))),
    option_item_sp(title=tr('Cluster HUD Live FPS'), param='ClusterHudLiveFps', min_value=1, max_value=60, value_change_step=1),
    toggle_item_sp(title=tr('Cluster HUD Mirror'), param='ClusterHudMirror',
                   description=tr('Mirror the external cluster display horizontally.')),
    option_item_sp(title=tr('Cluster HUD Orientation'), param='ClusterHudOrientation', min_value=0, max_value=3, value_change_step=1),
    option_item_sp(title=tr('Cluster HUD Panel Layout'), param='ClusterHudPanelLayout', min_value=0, max_value=1, value_change_step=1,
                   label_callback=lambda v, *_: {0: tr('Driving Left'), 1: tr('Driving Right')}.get(v, str(v))),
    option_item_sp(title=tr('Cluster HUD Priority'), param='ClusterHudPriority', min_value=0, max_value=100, value_change_step=1),
    toggle_item_sp(title=tr('Cluster HUD Radar Display'), param='ClusterHudRadarDisplay',
                   description=tr('Draw radar tracks on the external cluster.')),
    option_item_sp(title=tr('Cluster HUD Radar Info'), param='ClusterHudRadarInfo', min_value=0, max_value=4, value_change_step=1,
                   label_callback=lambda v, *_: {0: tr('None'), 1: tr('Vehicle Speed'), 2: tr('Speed + Distance'),
                                                  3: tr('All Speeds'), 4: tr('All Speeds + Distance')}.get(v, str(v))),
    toggle_item_sp(title=tr('Cluster HUD Radar Source Color'), param='ClusterHudRadarSourceColor',
                   description=tr('Color radar tracks by their detection source.')),
    option_item_sp(title=tr('Cluster HUD Screen Mode'), param='ClusterHudScreenMode', min_value=0, max_value=6, value_change_step=1,
                   label_callback=lambda v, *_: {0: tr('Default'), 1: tr('Debug'), 2: tr('Debug System'),
                                                  3: tr('Debug Graph'), 4: tr('Debug Graph Right'),
                                                  5: tr('Trip Report'), 6: tr('Navi')}.get(v, str(v))),
    option_item_sp(title=tr('Cluster HUD Theme'), param='ClusterHudTheme', min_value=0, max_value=2, value_change_step=1,
                   label_callback=lambda v, *_: {0: tr('Auto'), 1: tr('Dark'), 2: tr('Light')}.get(v, str(v))),
  ]

def build_vehicle_items():
  return [
    section_heading_sp(tr('Radar / Tracks')),
    toggle_item_sp(title=tr('Enable Radar Tracks'), param='EnableRadarTracks',
                   description=tr('BYD only: feed corner-radar tracks into the radar interface.')),
    option_item_sp(title=tr('Alert Volume'), param='SoundVolumeAdjust', min_value=5, max_value=200, value_change_step=5,
                   description=tr('Scale every alert sound, in percent. 100 keeps the current loudness.')),
    option_item_sp(title=tr('Engage Chime Volume'), param='SoundVolumeAdjustEngage', min_value=5, max_value=200, value_change_step=5,
                   description=tr('Scale the engage / disengage / reverse chimes, in percent.')),
    # Values: 1 = linear scale, 0 = off, -1/-2/-3 = speed breakpoint profiles
    # (30/60/90, 40/80/120, 50/100/150 km/h). The code reads all of them, so this cannot
    # be a toggle - one could only ever write 0 or 1 and the profiles were unreachable.
    option_item_sp(title=tr('Speed-dependent Follow Time'), param='EnableSpeedTF', min_value=-3, max_value=1, value_change_step=1,
                   label_callback=lambda v, *_: {1: tr('Linear'), 0: tr('Off'),
                                                -1: '30/60/90', -2: '40/80/120', -3: '50/100/150'}.get(v, str(v)),
                   description=tr('Shrink the follow distance as speed rises. Off disables it; the three '
                                  'profiles differ in how far up the speed range the gap keeps tightening.')),
    section_heading_sp(tr('Driving Mode')),
    option_item_sp(title=tr('My Driving Mode'), param='MyDrivingMode', min_value=1, max_value=4, value_change_step=1),
    option_item_sp(title=tr('My Driving Mode Auto'), param='MyDrivingModeAuto', min_value=0, max_value=2, value_change_step=1),
  ]

def build_dev_items():
  return [
    section_heading_sp(tr('Hardware / Tests')),
    toggle_item_sp(title=tr('Show Debug Log'), param='ShowDebugLog'),

    # Unified-control killswitches. Both default OFF: they change vehicle
    # behaviour, so they are grouped here and opt-in.
    section_heading_sp(tr('Navigation Control (advanced)')),
    toggle_item_sp(title=tr('Traffic Congestion Slowdown'), param='CarrotTrafficCongestionEnabled',
                   description=tr('Fold the phone app traffic congestion report into map-based cruise '
                                   'control. Only ever lowers the target speed. Needs Smart Cruise '
                                   'Control - Map to be on as well.')),
    toggle_item_sp(title=tr('Lane Guide Blocking'), param='CarrotNavLaneGuideBlockEnabled',
                   description=tr('Let the phone app guided-lane arrows block lane changes toward '
                                   'non-guided lanes. Only ever adds blocking.')),

  ]


def build_egpu_items():
  from openpilot.selfdrive.ui.sunnypilot.layouts.settings.carrot_tuning_egpu import EgpuPanelWidget

  return [
    EgpuPanelWidget(),
  ]
