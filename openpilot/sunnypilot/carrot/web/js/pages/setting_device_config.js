"use strict";

const DEVICE_NETWORK_REFRESH_MS = 3000;
const DEVICE_SSH_REFRESH_MS = 3000;

const DEVICE_GROUPS = [
  { id: "Device", labelKey: "device_group_info", defaultLabel: "Device Info" },
  { id: "Network", labelKey: "device_group_network", defaultLabel: "Network" },
  { id: "Toggles", labelKey: "device_group_toggles", defaultLabel: "Toggles" },
  // sunnypilot sections - the server ships each group's parameter names in the
  // settings snapshot (services/device_info.py reads them from the settings
  // catalog), and renderDeviceSpItems draws them from the catalog's labels.
  { id: "Storage", labelKey: "device_group_storage", defaultLabel: "Storage" },
  { id: "Sunnylink", labelKey: "device_group_sunnylink", defaultLabel: "sunnylink" },
  { id: "Firehose", labelKey: "device_group_firehose", defaultLabel: "Data" },
  { id: "Models", labelKey: "device_group_models", defaultLabel: "Models" },
  { id: "Bluetooth", labelKey: "device_group_bluetooth", defaultLabel: "Bluetooth" },
  { id: "Vehicle", labelKey: "device_group_vehicle", defaultLabel: "Vehicle" },
  { id: "Steering", labelKey: "device_group_steering", defaultLabel: "Steering" },
  { id: "Cruise", labelKey: "device_group_cruise", defaultLabel: "Cruise" },
  { id: "Visuals", labelKey: "device_group_visuals", defaultLabel: "Visuals" },
  { id: "Display", labelKey: "device_group_display", defaultLabel: "Display" },
  { id: "Navigation", labelKey: "device_group_navigation", defaultLabel: "Navigation" },
  { id: "Osm", labelKey: "device_group_osm", defaultLabel: "OSM" },
  { id: "Maps", labelKey: "device_group_maps", defaultLabel: "Maps" },
  { id: "Trips", labelKey: "device_group_trips", defaultLabel: "Trips" },
  { id: "Imu", labelKey: "device_group_imu", defaultLabel: "IMU" },
  { id: "Software", labelKey: "device_group_software", defaultLabel: "Software" },
  { id: "Developer", labelKey: "device_group_developer", defaultLabel: "Developer" },
];

// Groups rendered generically from the catalog metadata (name -> item meta in
// the snapshot's items_by_group). Base groups keep their hand-built layouts.
const SP_DEVICE_GROUP_IDS = new Set([
  "Models", "Vehicle", "Steering", "Cruise", "Visuals", "Display",
  "Navigation", "Osm", "Maps", "Trips", "Imu",
]);

// Sections that carry no catalog params at all: the 5080 webui daemon owns
// them (bluetooth pairing is daemon state, not Params). They render a manager
// block and are visible whenever the panel can reach that daemon.
const SP_CAPABILITY_GROUP_IDS = new Set(["Bluetooth", "Storage", "Sunnylink", "Firehose"]);

// Bool params that make a process *do* something the moment they are written
// (reboot, drop caches, recalibrate). A toggle is fine, but confirm first so a
// mis-tap cannot reboot the device or wipe a cache.
const SP_ACTION_PARAMS = new Set([
  "DoReboot", "ModelManager_ClearCache", "Mapd_ClearCache", "ImuCalibrationRequested",
  "OnroadCycleRequested", "BackupManager_CreateBackup", "OsmDbUpdatesCheck",
]);

const DEVICE_INFO_PARAMS = [
  "DeviceType",
  "DongleId",
  "HardwareSerial",
  "LanguageSetting",
  "SoftwareMenu",
];

const DEVICE_SOFTWARE_PARAMS = [
  "UpdaterCurrentDescription",
  "UpdaterState",
  "UpdateAvailable",
  "UpdaterFetchAvailable",
  "UpdateFailedCount",
  "UpdaterTargetBranch",
  "GitBranch",
  "UpdaterAvailableBranches",
  "LastUpdateTime",
  "UpdaterNewDescription",
];

const DEVICE_LANGUAGES = window.CarrotDeviceLanguageOptions || [
  { code: "en", name: "English" },
  { code: "ko", name: "한국어" },
  { code: "zh-CHS", name: "简体中文" },
  { code: "zh-CHT", name: "繁體中文" },
];

const DEVICE_TOGGLES = [
  { param: "OpenpilotEnabledToggle", labelKey: "enable_openpilot", defaultLabel: "Enable openpilot" },
  { param: "ExperimentalMode", labelKey: "experimental_mode", defaultLabel: "Experimental Mode", confirmKey: "experimental_mode_confirm", confirmedParam: "ExperimentalModeConfirmed" },
  { param: "DisengageOnAccelerator", labelKey: "disengage_on_accelerator", defaultLabel: "Disengage on Accelerator" },
  { param: "IsLdwEnabled", labelKey: "enable_ldw", defaultLabel: "Enable Lane Departure Warnings" },
  { param: "AlwaysOnDM", labelKey: "always_on_dm", defaultLabel: "Always-on DM" },
  { param: "RecordFront", labelKey: "record_front", defaultLabel: "Record and Upload Driver Camera" },
  { param: "RecordAudio", labelKey: "record_audio", defaultLabel: "Record and Upload Microphone Audio" },
  { param: "IsMetric", labelKey: "is_metric", defaultLabel: "Use Metric System" },
];

const DEVICE_DEVELOPER_TOGGLES = [
  { param: "AdbEnabled", labelKey: "enable_adb", defaultLabel: "Enable ADB", confirmKey: "adb_enable_confirm" },
  { param: "SshEnabled", labelKey: "enable_ssh", defaultLabel: "Enable SSH" },
  { param: "JoystickDebugMode", labelKey: "joystick_debug_mode", defaultLabel: "Joystick Debug Mode", disabled: true },
  { param: "LongitudinalManeuverMode", labelKey: "longitudinal_maneuver_mode", defaultLabel: "Longitudinal Maneuver Mode" },
  { param: "AlphaLongitudinalEnabled", labelKey: "alpha_longitudinal_control", defaultLabel: "openpilot Longitudinal Control (Alpha)", confirmKey: "alpha_longitudinal_confirm" },
];

const PERSONALITY_OPTIONS = [
  { value: 0, labelKey: "aggressive", defaultLabel: "Aggressive" },
  { value: 1, labelKey: "standard", defaultLabel: "Standard" },
  { value: 2, labelKey: "relaxed", defaultLabel: "Relaxed" },
  { value: 3, labelKey: "more_relaxed", defaultLabel: "MoreRelaxed" },
];

const TRAINING_STEP_COUNT = 19;

function isTruthyDeviceFlag(value) {
  return value === true || value === 1 || value === "1" || value === "true" || value === "True";
}
