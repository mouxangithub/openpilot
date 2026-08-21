"""Declarative settings panels mirroring sunnypilot BIG UI (15 panels)."""

from __future__ import annotations

from typing import Any

# Widget types: bool, int, choice, readonly, action, section, html, subpanel_ref

PANELS: list[dict[str, Any]] = [
  {
    "id": "device",
    "title": "Device",
    "custom": "device",
    "widgets": [
      {"type": "readonly", "param": "DongleId", "label": "Dongle ID"},
      {"type": "separator"},
      {"type": "readonly", "param": "HardwareSerial", "label": "Serial"},
      {"type": "separator"},
      {"type": "action", "action": "pair_device", "label": "Pair Device", "button": "PAIR",
       "desc": "Pair your device with comma connect (connect.comma.ai) and claim your comma prime offer.",
       "hide_when_paired": True},
      {"type": "separator"},
      {"type": "action", "action": "reset_calibration", "label": "Reset Calibration", "button": "RESET",
       "desc": "sunnypilot requires the device to be mounted within 4° left or right and within 5° up or 9° down.",
       "dynamic_desc": "calibration",
       "confirm": "Are you sure you want to reset calibration?"},
      {"type": "separator"},
      {"type": "custom", "custom": "device_language"},
      {"type": "separator"},
      {"type": "multiple_button", "param": "DeviceBootMode", "label": "Wake Up Behavior",
       "buttons": ["Default", "Offroad"], "layout": "inline",
       "desc": "Controls state of the device after boot/sleep.\n\nDefault: Device will boot/wake-up normally & will be ready to engage.\nOffroad: Device will be in Always Offroad mode after boot/wake-up."},
      {"type": "separator"},
      {"type": "option", "param": "MaxTimeOffroad", "label": "Max Time Offroad",
       "desc": "Device will automatically shutdown after set time once the engine is turned off.\n(30h is the default)",
       "min": 0, "max": 11, "step": 1, "layout": "inline",
       "value_map": {"0": 0, "1": 5, "2": 10, "3": 15, "4": 30, "5": 60, "6": 120, "7": 180, "8": 300, "9": 600, "10": 1440, "11": 1800}},
      {"type": "dual_button",
       "left": {"label": "Quiet Mode", "param": "QuietMode", "toggle": True},
       "right": {"label": "Driver Camera Preview", "custom": "driver_camera", "offroad_only": True}},
      {"type": "dual_button",
       "left": {"label": "Regulatory", "action": "open_regulatory", "offroad_only": True},
       "right": {"label": "Training Guide", "action": "open_training", "offroad_only": True}},
      {"type": "dual_button",
       "left": {"label": "Onroad Uploads", "param": "OnroadUploads", "toggle": True},
       "right": {"label": "Reset Settings", "action": "reset_all_params", "offroad_only": True, "confirm_twice": True}},
      {"type": "custom", "custom": "always_offroad"},
      {"type": "dual_button",
       "left": {"label": "Reboot", "action": "reboot"},
       "right": {"label": "Power Off", "action": "shutdown", "offroad_only": True, "hide_when_onroad": True}},
    ],
  },
  {
    "id": "network",
    "title": "Network",
    "custom": "network",
    "widgets": [
      {"type": "subpanel", "target": "network__advanced", "label": "Advanced Network", "button": "ADVANCED"},
    ],
  },
  {
    "id": "sunnylink",
    "title": "sunnylink",
    "custom": "sunnylink",
    "widgets": [],
  },
  {
    "id": "toggles",
    "title": "Toggles",
    "widgets": [
      {"type": "bool", "param": "OpenpilotEnabledToggle", "label": "Enable sunnypilot", "needs_cycle": True,
       "icon": "selfdrive/assets/icons/chffr_wheel.png",
       "desc": "Use the sunnypilot system for adaptive cruise control and lane keep driver assistance. Your attention is required at all times to use this feature."},
      {"type": "bool", "param": "ExperimentalMode", "label": "Experimental Mode", "confirm_experimental": True,
       "icon": "selfdrive/assets/icons/experimental_white.png",
       "icon_active": "selfdrive/assets/icons/experimental.png"},
      {"type": "bool", "param": "DisengageOnAccelerator", "label": "Disengage on Accelerator Pedal",
       "icon": "selfdrive/assets/icons/disengage_on_accelerator.png",
       "desc": "When enabled, pressing the accelerator pedal will disengage sunnypilot."},
      {"type": "multiple_button", "param": "LongitudinalPersonality", "label": "Driving Personality",
       "layout": "stacked",
       "icon": "selfdrive/assets/icons/speed_limit.png",
       "buttons": ["Aggressive", "Standard", "Relaxed"],
       "desc": "Standard is recommended. In aggressive mode, sunnypilot will follow lead cars closer and be more aggressive with the gas and brake. In relaxed mode sunnypilot will stay further away from lead cars. On supported cars, you can cycle through these personalities with your steering wheel distance button."},
      {"type": "bool", "param": "IsLdwEnabled", "label": "Enable Lane Departure Warnings",
       "icon": "selfdrive/assets/icons/warning.png",
       "desc": "Receive alerts to steer back into the lane when your vehicle drifts over a detected lane line without a turn signal activated while driving over 31 mph (50 km/h)."},
      {"type": "bool", "param": "DisableDM", "label": "Disable Driver Monitoring", "needs_cycle": True,
       "icon": "selfdrive/assets/icons/monitoring.png",
       "desc": "Disable driver monitoring (no cabin camera required). Similar to LITE mode."},
      {"type": "bool", "param": "AlwaysOnDM", "label": "Always-On Driver Monitoring",
       "icon": "selfdrive/assets/icons/monitoring.png",
       "hide_if": {"param": "DisableDM", "eq": "1"},
       "desc": "The driver monitoring system can be toggled on/off, but long-term activation is recommended"},
      {"type": "multiple_button", "param": "DistractionDetectionLevel", "label": "Distraction Detection Level",
       "layout": "stacked",
       "icon": "selfdrive/assets/icons/monitoring.png",
       "buttons": ["Strict", "Moderate", "Lenient"],
       "visible_if": {"param": "AlwaysOnDM", "eq": "1"},
       "hide_if": {"param": "DisableDM", "eq": "1"},
       "desc": "Set how sensitive the driver distraction detection should be. Strict: Very sensitive, warns on minor distractions. Moderate: Balanced between sensitivity and false positives. Lenient: Only alerts on clear distractions."},
      {"type": "bool", "param": "RecordFront", "label": "Record and Upload Driver Camera", "needs_cycle": True,
       "icon": "selfdrive/assets/icons/monitoring.png",
       "hide_if": {"param": "DisableDM", "eq": "1"},
       "desc": "Upload data from the driver facing camera and help improve the driver monitoring algorithm."},
      {"type": "bool", "param": "RecordAudio", "label": "Record and Upload Microphone Audio", "needs_cycle": True,
       "icon": "selfdrive/assets/icons/microphone.png",
       "desc": "Record and store microphone audio while driving. The audio will be included in the dashcam video in comma connect."},
      {"type": "bool", "param": "SpDevBeep", "label": "Beeper Feedback", "lite_only": True, "needs_cycle": True,
       "icon": "selfdrive/assets/icons/warning.png",
       "desc": "Use the GPIO beeper for engage/disengage sounds on Lite hardware without a speaker."},
      {"type": "bool", "param": "IsMetric", "label": "Use Metric System",
       "icon": "selfdrive/assets/icons/metric.png",
       "desc": "Display speed in km/h instead of mph."},
    ],
  },
  {
    "id": "software",
    "title": "Software",
    "custom": "software",
    "widgets": [
      {"type": "action", "action": "uninstall", "label": "Uninstall", "button": "UNINSTALL",
       "confirm": "Are you sure you want to uninstall?", "offroad_only": True},
      {"type": "custom", "custom": "webui_update"},
      {"type": "bool", "param": "DisableUpdates", "label": "Disable Updates",
       "visible_if": {"param": "ShowAdvancedControls", "eq": "1"}, "offroad_only": True},
    ],
  },
  {
    "id": "models",
    "title": "Models",
    "custom": "models",
    "widgets": [
      {"type": "action", "action": "models_sync", "label": "Refresh Model List", "button": "REFRESH"},
      {"type": "action", "action": "models_clear_cache", "label": "Clear Model Cache", "button": "CLEAR",
       "confirm": "This will delete ALL downloaded models from the cache except the currently active model. Are you sure?",
       "confirm_button": "Clear Cache"},
      {"type": "bool", "param": "LaneTurnDesire", "label": "Use Lane Turn Desires",
       "desc": "If you're driving at 20 mph (32 km/h) or below and have your blinker on, the car will plan a turn in that direction at the nearest drivable path. This prevents situations (like at red lights) where the car might plan the wrong turn direction."},
      {"type": "option", "param": "LaneTurnValue", "label": "Adjust Lane Turn Speed",
       "min": 500, "max": 2000, "step": 100, "label_format": "lane_turn_speed",
       "desc": "Set the maximum speed for lane turn desires. Default is 19 mph.",
       "visible_if": {"param": "LaneTurnDesire", "eq": "1"},
       "advanced_if": {"param": "ShowAdvancedControls", "eq": "1"}},
      {"type": "bool", "param": "LagdToggle", "label": "Live Learning Steer Delay",
       "desc": "Enable this for the car to learn and adapt its steering response time. Disable to use a fixed steering response time. Keeping this on provides the stock openpilot experience."},
      {"type": "option", "param": "LagdToggleDelay", "label": "Adjust Software Delay",
       "min": 5, "max": 50, "step": 1, "label_format": "lagd_delay",
       "desc": "Adjust the software delay when Live Learning Steer Delay is toggled off. The default software delay value is 0.2",
       "visible_if": {"param": "LagdToggle", "eq": "0"},
       "advanced_if": {"param": "ShowAdvancedControls", "eq": "1"}},
      {"type": "option", "param": "CameraOffset", "label": "Adjust Camera Offset",
       "min": -35, "max": 35, "step": 1, "label_format": "camera_offset",
       "desc": "Virtually shift camera's perspective to move model's center to Left(+ values) or Right (- values)",
       "visible_if": {"state": "custom_model_active"}},
    ],
  },
  {
    "id": "steering",
    "title": "Steering",
    "widgets": [
      {"type": "bool", "param": "Mads", "label": "Modular Assistive Driving System (MADS)", "offroad_only": True,
       "desc": "Enable the beloved MADS feature. Disable toggle to revert back to stock sunnypilot engagement/disengagement."},
      {"type": "subpanel", "target": "steering__mads", "label": "Customize MADS", "button": "CUSTOMIZE",
       "requires": {"param": "Mads", "eq": "1"}, "offroad_only": True},
      {"type": "separator"},
      {"type": "subpanel", "target": "steering__lane_change", "label": "Customize Lane Change", "button": "CUSTOMIZE"},
      {"type": "separator"},
      {"type": "bool", "param": "BlinkerPauseLateralControl", "label": "Pause Lateral Control with Blinker"},
      {"type": "option", "param": "BlinkerMinLateralControlSpeed", "label": "Minimum Speed to Pause Lateral Control",
       "min": 0, "max": 255, "step": 5, "label_format": "blinker_min_speed", "layout": "stacked",
       "visible_if": {"param": "BlinkerPauseLateralControl", "eq": "1"}},
      {"type": "option", "param": "BlinkerLateralReengageDelay", "label": "Post-Blinker Delay",
       "min": 0, "max": 10, "step": 1, "label_format": "blinker_delay", "layout": "stacked",
       "desc": "Delay before lateral control resumes after the turn signal ends.",
       "visible_if": {"param": "BlinkerPauseLateralControl", "eq": "1"}},
      {"type": "separator"},
      {"type": "bool", "param": "EnforceTorqueControl", "label": "Enforce Torque Lateral Control", "offroad_only": True,
       "desc": "Enable this to enforce sunnypilot to steer with Torque lateral control."},
      {"type": "subpanel", "target": "steering__torque", "label": "Customize Torque Params", "button": "CUSTOMIZE",
       "requires": {"param": "EnforceTorqueControl", "eq": "1"}},
      {"type": "separator"},
      {"type": "bool", "param": "NeuralNetworkLateralControl", "label": "Neural Network Lateral Control (NNLC)", "offroad_only": True},
    ],
  },
  {
    "id": "cruise",
    "title": "Cruise",
    "widgets": [
      {"type": "bool", "param": "IntelligentCruiseButtonManagement", "label": "Intelligent Cruise Button Management (ICBM) (Alpha)",
       "offroad_only": True, "dynamic_desc": "icbm",
       "desc": "When enabled, sunnypilot will attempt to manage the built-in cruise control buttons by emulating button presses for limited longitudinal control."},
      {"type": "bool", "param": "DynamicExperimentalControl", "label": "Enable Dynamic Experimental Control",
       "desc": "Let the model decide when to use sunnypilot ACC or sunnypilot End to End Longitudinal.",
       "capability": "longitudinal"},
      {"type": "bool", "param": "SmartCruiseControlVision", "label": "Smart Cruise Control - Vision",
       "desc": "Use vision path predictions to estimate the appropriate speed to drive through turns ahead.",
       "capability": "scc"},
      {"type": "bool", "param": "SmartCruiseControlMap", "label": "Smart Cruise Control - Map",
       "desc": "Use map data to estimate the appropriate speed to drive through turns ahead.",
       "capability": "scc"},
      {"type": "bool", "param": "CustomAccIncrementsEnabled", "label": "Custom ACC Speed Increments",
       "offroad_only": True, "dynamic_desc": "custom_acc",
       "desc": "Enable custom Short & Long press increments for cruise speed increase/decrease.",
       "capability": "custom_acc"},
      {"type": "int", "param": "CustomAccShortPressIncrement", "label": "Short Press Increment", "min": 1, "max": 10, "step": 1,
       "visible_if": {"param": "CustomAccIncrementsEnabled", "eq": "1"}, "capability": "custom_acc"},
      {"type": "option", "param": "CustomAccLongPressIncrement", "label": "Long Press Increment",
       "min": 1, "max": 3, "step": 1, "label_format": "acc_long_press",
       "value_map": {"1": 1, "2": 5, "3": 10},
       "visible_if": {"param": "CustomAccIncrementsEnabled", "eq": "1"}, "capability": "custom_acc"},
      {"type": "subpanel", "target": "cruise__sla", "label": "Speed Limit", "button": "CUSTOMIZE"},
    ],
  },
  {
    "id": "visuals",
    "title": "Visuals",
    "widgets": [
      {"type": "bool", "param": "BlindSpot", "label": "Show Blind Spot Warnings",
       "desc": "Enabling this will display warnings when a vehicle is detected in your blind spot as long as your car has BSM supported."},
      {"type": "bool", "param": "TorqueBar", "label": "Steering Arc",
       "desc": "Display steering arc on the driving screen when lateral control is enabled."},
      {"type": "bool", "param": "RainbowMode", "label": "Enable Tesla Rainbow Mode",
       "desc": "A beautiful rainbow effect on the path the model wants to take. It does not affect driving in any way."},
      {"type": "bool", "param": "StandstillTimer", "label": "Enable Standstill Timer",
       "desc": "Show a timer on the HUD when the car is at a standstill."},
      {"type": "bool", "param": "RoadNameToggle", "label": "Display Road Name",
       "desc": "Displays the name of the road the car is traveling on. The OpenStreetMap database of the location must be downloaded from the OSM panel to fetch the road name."},
      {"type": "bool", "param": "GreenLightAlert", "label": "Green Traffic Light Alert (Beta)",
       "desc": "A chime and on-screen alert will play when the traffic light you are waiting for turns green and you have no vehicle in front of you. Note: This chime is only designed as a notification. It is the driver's responsibility to observe their environment and make decisions accordingly."},
      {"type": "bool", "param": "LeadDepartAlert", "label": "Lead Departure Alert (Beta)",
       "desc": "A chime and on-screen alert will play when you are stopped, and the vehicle in front of you start moving. Note: This chime is only designed as a notification. It is the driver's responsibility to observe their environment and make decisions accordingly."},
      {"type": "bool", "param": "TrueVEgoUI", "label": "Speedometer: Always Display True Speed",
       "desc": "For applicable vehicles, always display the true vehicle current speed from wheel speed sensors."},
      {"type": "bool", "param": "HideVEgoUI", "label": "Speedometer: Hide from Onroad Screen",
       "desc": "When enabled, the speedometer on the onroad screen is not displayed."},
      {"type": "bool", "param": "ShowTurnSignals", "label": "Display Turn Signals",
       "desc": "When enabled, visual turn indicators are drawn on the HUD."},
      {"type": "bool", "param": "RocketFuel", "label": "Real-time Acceleration Bar",
       "desc": "Show an indicator on the left side of the screen to display real-time vehicle acceleration and deceleration. This displays what the car is currently doing, not what the planner is requesting."},
      {"type": "multiple_button", "param": "ChevronInfo", "label": "Display Metrics Below Chevron",
       "dynamic_desc": "chevron",
       "buttons": ["Off", "Distance", "Speed", "Time", "All"]},
      {"type": "multiple_button", "param": "DevUIInfo", "label": "Developer UI",
       "desc": "Display real-time parameters and metrics from various sources.",
       "buttons": ["Off", "Bottom", "Right", "Right & Bottom"]},
    ],
  },
  {
    "id": "display",
    "title": "Display",
    "widgets": [
      {"type": "option", "param": "Brightness", "label": "Screen Brightness",
       "min": 0, "max": 100, "step": 5, "label_format": "offroad_brightness", "layout": "inline",
       "desc": "Screen brightness when offroad (not driving). 0 uses the device default (50%)."},
      {"type": "option", "param": "OnroadScreenOffBrightness", "label": "Onroad Brightness",
       "min": 0, "max": 22, "step": 1, "label_format": "onroad_brightness", "layout": "inline"},
      {"type": "option", "param": "OnroadScreenOffTimer", "label": "Onroad Brightness Delay",
       "min": 0, "max": 15, "step": 1, "label_format": "onroad_brightness_timer",
       "value_map": {"0": 3, "1": 5, "2": 7, "3": 10, "4": 15, "5": 30,
                     "6": 60, "7": 120, "8": 180, "9": 240, "10": 300, "11": 360,
                     "12": 420, "13": 480, "14": 540, "15": 600},
       "layout": "inline"},
      {"type": "option", "param": "InteractivityTimeout", "label": "Interactivity Timeout",
       "min": 0, "max": 120, "step": 10, "label_format": "interactivity_timeout",
       "desc": "Apply a custom timeout for settings UI. This is the time after which settings UI closes automatically if user is not interacting with the screen.",
       "layout": "inline"},
      {"type": "bool", "param": "ScreenSaverEnabled", "label": "Screen Saver",
       "desc": "Show a screen saver when the device is offroad and idle, instead of turning the screen off."},
      {"type": "option", "param": "ScreenSaverTimeout", "label": "Screen Saver Duration",
       "min": 60, "max": 600, "step": 60, "label_format": "screensaver_timeout",
       "desc": "How long the screen saver runs before the screen turns off.",
       "visible_if": {"param": "ScreenSaverEnabled", "eq": "1"}},
      {"type": "separator"},
      {"type": "custom", "custom": "stream_headless_mode", "desc_i18n": "webui_headless_mode_desc"},
      {"type": "custom", "custom": "stream_preview_quality", "desc_i18n": "webui_preview_quality_desc"},
      {"type": "custom", "custom": "stream_webcodecs"},
      {"type": "custom", "custom": "stream_diagnostics"},
    ],
  },
  {
    "id": "storage",
    "title": "Storage",
    "custom": "storage",
    "widgets": [],
  },
  {
    "id": "osm",
    "title": "OSM",
    "custom": "osm",
    "widgets": [],
  },
  {
    "id": "trips",
    "title": "Trips",
    "custom": "trips",
    "widgets": [],
  },
  {
    "id": "vehicle",
    "title": "Vehicle",
    "custom": "vehicle",
    "widgets": [],
  },
  {
    "id": "firehose",
    "title": "Data",
    "custom": "firehose",
    "widgets": [],
  },
  {
    "id": "developer",
    "title": "Developer",
    "widgets": [
      {"type": "bool", "param": "AdbEnabled", "label": "Enable ADB",
       "desc": "ADB (Android Debug Bridge) allows connecting to your device over USB or over the network. See https://docs.comma.ai/how-to/connect-to-comma for more info."},
      {"type": "bool", "param": "SshEnabled", "label": "Enable SSH"},
      {"type": "custom", "custom": "ssh_keys", "label": "SSH Keys"},
      {"type": "bool", "param": "JoystickDebugMode", "label": "Joystick Debug Mode"},
      {"type": "bool", "param": "LongitudinalManeuverMode", "label": "Longitudinal Maneuver Mode"},
      {"type": "bool", "param": "LateralManeuverMode", "label": "Lateral Maneuver Mode"},
      {"type": "bool", "param": "AlphaLongitudinalEnabled", "label": "sunnypilot Longitudinal (Alpha)",
       "needs_cycle": True},
      {"type": "bool", "param": "ShowDebugInfo", "label": "UI Debug Mode"},
      {"type": "bool", "param": "ShowAdvancedControls", "label": "Show Advanced Controls",
       "desc": "Toggle visibility of advanced sunnypilot controls. This only changes the visibility of the toggles; it does not change the actual enabled/disabled state."},
      {"type": "bool", "param": "EnableGithubRunner", "label": "GitHub Runner Service",
       "desc": "Enables or disables the GitHub runner service.",
       "visible_if": {"param": "ShowAdvancedControls", "eq": "1"}},
      {"type": "bool", "param": "EnableCopyparty", "label": "copyparty Service",
       "desc": "copyparty is a very capable file server, you can use it to download your routes, view your logs and even make some edits on some files from your browser. Requires you to connect to your comma locally via its IP address.",
       "visible_if": {"param": "ShowAdvancedControls", "eq": "1"}},
      {"type": "bool", "param": "QuickBootToggle", "label": "Quickboot Mode",
       "visible_if": {"param": "ShowAdvancedControls", "eq": "1"}},
      {"type": "action", "action": "developer_error_log", "label": "Error Log", "button": "VIEW"},
    ],
  },
]

SUBPANELS: dict[str, dict[str, Any]] = {
  "steering__mads": {
    "id": "steering__mads",
    "title": "Customize MADS",
    "parent": "steering",
    "widgets": [
      {"type": "bool", "param": "MadsMainCruiseAllowed", "label": "Toggle with Main Cruise"},
      {"type": "bool", "param": "MadsUnifiedEngagementMode", "label": "Unified Engagement Mode (UEM)"},
      {"type": "multiple_button", "param": "MadsSteeringMode", "label": "Steering Mode on Brake Pedal",
       "buttons": ["Remain Active", "Pause", "Disengage"]},
    ],
  },
  "steering__lane_change": {
    "id": "steering__lane_change",
    "title": "Customize Lane Change",
    "parent": "steering",
    "widgets": [
      {"type": "option", "param": "AutoLaneChangeTimer", "label": "Auto Lane Change by Blinker",
       "min": -1, "max": 5, "step": 1, "label_format": "lane_change_timer", "layout": "stacked",
       "desc": "Set a timer to delay the auto lane change operation when the blinker is used. "
               "No nudge on the steering wheel is required to auto lane change if a timer is set. Default is Nudge. "
               "Please use caution when using this feature. Only use the blinker when traffic and road conditions permit."},
      {"type": "separator"},
      {"type": "bool", "param": "AutoLaneChangeBsmDelay", "label": "Auto Lane Change: Delay with Blind Spot",
       "desc": "Toggle to enable a delay timer for seamless lane changes when blind spot monitoring (BSM) "
               "detects a obstructing vehicle, ensuring safe maneuvering."},
      {"type": "separator"},
      {"type": "bool", "param": "RoadEdgeLaneChangeEnabled", "label": "Block Lane Change: Road Edge Detection",
       "desc": "Blocks the lane change if the model sees a road edge on your signaled side."},
    ],
  },
  "steering__torque": {
    "id": "steering__torque",
    "title": "Customize Torque Params",
    "parent": "steering",
    "widgets": [
      {"type": "bool", "param": "LateralJerkTorqueController", "label": "Lateral Jerk Torque Controller", "offroad_only": True,
       "desc": "Looks ahead at planned steering to reduce sudden corrections, so the wheel moves more smoothly through turns. Works with Self-Tune and custom tuning. Thanks to @twilsonco for the implementation."},
      {"type": "action", "action": "torque_tune_version", "label": "Torque Control Tune Version", "button": "SELECT",
       "desc": "Select the version of Torque Control Tune to use."},
      {"type": "bool", "param": "LiveTorqueParamsToggle", "label": "Self-Tune", "offroad_only": True,
       "desc": "Enables self-tune for Torque lateral control for platforms that do not use Torque lateral control by default."},
      {"type": "bool", "param": "LiveTorqueParamsRelaxedToggle", "label": "Less Restrict Settings for Self-Tune (Beta)",
       "desc": "Less strict settings when using Self-Tune. This allows torqued to be more forgiving when learning values.",
       "visible_if": {"param": "LiveTorqueParamsToggle", "eq": "1"}, "offroad_only": True},
      {"type": "bool", "param": "CustomTorqueParams", "label": "Enable Custom Tuning", "offroad_only": True,
       "desc": "Enables custom tuning for Torque lateral control. Modifying Lateral Acceleration Factor and Friction below will override the offline values indicated in the YAML files within \"opendbc/car/torque_data\". The values will also be used live when \"Manual Real-Time Tuning\" toggle is enabled."},
      {"type": "bool", "param": "TorqueParamsOverrideEnabled", "label": "Manual Real-Time Tuning",
       "desc": "Enforces the torque lateral controller to use the fixed values instead of the learned values from Self-Tune. Enabling this toggle overrides Self-Tune values.",
       "visible_if": {"param": "CustomTorqueParams", "eq": "1"}, "offroad_only": True},
      {"type": "option", "param": "TorqueParamsOverrideLatAccelFactor", "label": "Lateral Acceleration Factor",
       "min": 1, "max": 500, "step": 1, "label_format": "torque_lat_accel",
       "visible_if": {"param": "CustomTorqueParams", "eq": "1"}},
      {"type": "option", "param": "TorqueParamsOverrideFriction", "label": "Friction",
       "min": 1, "max": 100, "step": 1, "label_format": "torque_friction",
       "visible_if": {"param": "CustomTorqueParams", "eq": "1"}},
    ],
  },
  "cruise__sla": {
    "id": "cruise__sla",
    "title": "Speed Limit",
    "parent": "cruise",
    "widgets": [
      {"type": "multiple_button", "param": "SpeedLimitMode", "label": "Speed Limit",
       "buttons": ["Off", "Info", "Warning", "Assist"]},
      {"type": "subpanel", "target": "cruise__sla__policy", "label": "Customize Source", "button": "CUSTOMIZE"},
      {"type": "multiple_button", "param": "SpeedLimitOffsetType", "label": "Speed Limit Offset",
       "buttons": ["None", "Fixed", "%"]},
      {"type": "option", "param": "SpeedLimitValueOffset", "label": "Offset Value",
       "min": -30, "max": 30, "step": 1, "label_format": "speed_limit_offset",
       "visible_if": {"param": "SpeedLimitOffsetType", "ne": "0"}},
    ],
  },
  "cruise__sla__policy": {
    "id": "cruise__sla__policy",
    "title": "Speed Limit Source",
    "parent": "cruise__sla",
    "widgets": [
      {"type": "multiple_button", "param": "SpeedLimitPolicy", "label": "Speed Limit Source",
       "buttons": ["Car Only", "Map Only", "Car First", "Map First", "Combined"]},
    ],
  },
  "network__advanced": {
    "id": "network__advanced",
    "title": "Advanced Network",
    "parent": "network",
    "custom": "network_advanced",
    "widgets": [
      {"type": "bool", "param": "GsmRoaming", "label": "Enable Roaming"},
      {"type": "bool", "param": "GsmMetered", "label": "Cellular Metered",
       "desc": "Prevent large data uploads when on a metered cellular connection"},
    ],
  },
}


def panel_ids() -> list[str]:
  return [p["id"] for p in PANELS]


def get_panel(panel_id: str) -> dict[str, Any] | None:
  if panel_id in SUBPANELS:
    return SUBPANELS[panel_id]
  for p in PANELS:
    if p["id"] == panel_id:
      return p
  return None


def panel_schema() -> dict[str, Any]:
  from webui.server.bridge.design_tokens import PANEL_ICONS, tokens_payload
  from webui.server.bridge.headless_util import is_headless_mode
  from webui.server.bridge.lite_util import is_lite_hw, should_hide_widget

  headless = is_headless_mode()
  lite = is_lite_hw()
  headless_hide_params = {
    "Brightness", "OnroadScreenOffBrightness", "OnroadScreenOffTimer",
    "InteractivityTimeout", "ScreenSaverEnabled", "ScreenSaverTimeout",
  }

  def _filter_widgets(widgets: list[dict]) -> list[dict]:
    out = []
    for w in widgets:
      if should_hide_widget(w):
        continue
      if headless and w.get("param") in headless_hide_params:
        continue
      if w.get("type") == "separator" and out and out[-1].get("type") == "separator":
        continue
      out.append(w)
    return out

  panels_out = []
  for p in PANELS:
    entry = {**p, "icon": PANEL_ICONS.get(p["id"], "")}
    widgets = _filter_widgets(list(entry.get("widgets") or []))
    if headless and p.get("id") == "display":
      entry["headless_note"] = "Built-in display settings are hidden on headless devices."
      widgets.insert(0, {
        "type": "html",
        "i18n_key": "No built-in screen — brightness and screen saver do not apply. Camera stream settings below are used by Web UI.",
      })
      widgets.insert(1, {"type": "separator"})
    entry["widgets"] = widgets
    panels_out.append(entry)
  return {
    "ok": True,
    "panels": panels_out,
    "subpanels": list(SUBPANELS.keys()),
    "headless": headless,
    "lite": lite,
    **tokens_payload(),
  }


def panel_param_keys(panel_id: str) -> list[str]:
  panel = get_panel(panel_id)
  if not panel:
    return []
  keys: list[str] = []
  for w in panel.get("widgets", []):
    for dep_key in ("visible_if", "advanced_if"):
      dep = w.get(dep_key)
      if isinstance(dep, dict) and dep.get("param"):
        keys.append(dep["param"])
    if w.get("type") == "dual_button":
      for side in ("left", "right"):
        sk = (w.get(side) or {}).get("param")
        if sk:
          keys.append(sk)
      continue
    key = w.get("param")
    if key:
      keys.append(key)
  return sorted(set(keys))
