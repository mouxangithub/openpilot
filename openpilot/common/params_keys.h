#pragma once

#include <string>
#include <unordered_map>

#include "openpilot/cereal/gen/cpp/log.capnp.h"

inline static std::unordered_map<std::string, ParamKeyAttributes> keys = {
    {"AccessToken", {CLEAR_ON_MANAGER_START | DONT_LOG, STRING}},
    {"AdbEnabled", {PERSISTENT | BACKUP, BOOL}},
    {"AlwaysOnDM", {PERSISTENT | BACKUP, BOOL}},
    {"ApiCache_Device", {PERSISTENT, STRING}},
    {"ApiCache_FirehoseStats", {PERSISTENT, JSON}},
    {"AssistNowToken", {PERSISTENT, STRING}},
    {"AthenadPid", {PERSISTENT, INT}},
    {"AthenadUploadQueue", {PERSISTENT, JSON}},
    {"AthenadRecentlyViewedRoutes", {PERSISTENT, STRING}},
    {"BootCount", {PERSISTENT, INT}},
    {"CalibrationParams", {PERSISTENT, BYTES}},
    {"CameraDebugExpGain", {CLEAR_ON_MANAGER_START, STRING}},
    {"CameraDebugExpTime", {CLEAR_ON_MANAGER_START, STRING}},
    {"CarBatteryCapacity", {PERSISTENT, INT}},
    {"CarParams", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BYTES}},
    {"CarParamsCache", {CLEAR_ON_MANAGER_START, BYTES}},
    {"CarParamsPersistent", {PERSISTENT, BYTES}},
    {"CarParamsPrevRoute", {PERSISTENT, BYTES}},
    {"CompletedTrainingVersion", {PERSISTENT, STRING, "0"}},
    {"ControlsReady", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BOOL}},
    {"CurrentBootlog", {PERSISTENT, STRING}},
    {"CurrentRoute", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, STRING}},
    {"DisableLogging", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BOOL}},
    {"DisablePowerDown", {PERSISTENT | BACKUP, BOOL}},
    {"DisableUpdates", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"DisengageOnAccelerator", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"DongleId", {PERSISTENT, STRING}},
    {"DoReboot", {CLEAR_ON_MANAGER_START, BOOL}},
    {"DoShutdown", {CLEAR_ON_MANAGER_START, BOOL}},
    {"DoUninstall", {CLEAR_ON_MANAGER_START, BOOL}},
    {"DriverTooDistracted", {CLEAR_ON_MANAGER_START | CLEAR_ON_IGNITION_ON, BOOL}},
    {"DriverLockoutCount", {CLEAR_ON_MANAGER_START | CLEAR_ON_IGNITION_ON, INT, "0"}},
    {"AlphaLongitudinalEnabled", {PERSISTENT | DEVELOPMENT_ONLY | BACKUP, BOOL}},
    {"ExperimentalMode", {PERSISTENT | BACKUP, BOOL}},
    {"ExperimentalModeConfirmed", {PERSISTENT | BACKUP, BOOL}},
    {"FirmwareQueryDone", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BOOL}},
    {"ForcePowerDown", {PERSISTENT, BOOL}},
    {"GitBranch", {PERSISTENT, STRING}},
    {"GitCommit", {PERSISTENT, STRING}},
    {"GitCommitDate", {PERSISTENT, STRING}},
    {"GitDiff", {PERSISTENT, STRING}},
    {"GithubSshKeys", {PERSISTENT | BACKUP, STRING}},
    {"GithubUsername", {PERSISTENT | BACKUP, STRING}},
    {"GitRemote", {PERSISTENT, STRING}},
    {"GsmApn", {PERSISTENT | BACKUP, STRING}},
    {"GsmMetered", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"GsmRoaming", {PERSISTENT | BACKUP, BOOL}},
    {"HardwareSerial", {PERSISTENT, STRING}},
    {"HasAcceptedTerms", {PERSISTENT, STRING, "0"}},
    {"InstallDate", {PERSISTENT, TIME}},
    {"IsDriverViewEnabled", {CLEAR_ON_MANAGER_START, BOOL}},
    {"IsEngaged", {PERSISTENT, BOOL}},
    {"IsLdwEnabled", {PERSISTENT | BACKUP, BOOL}},
    {"IsLiveStreaming", {CLEAR_ON_MANAGER_START | CLEAR_ON_IGNITION_ON, BOOL}},
    {"IsMetric", {PERSISTENT | BACKUP, BOOL}},
    {"IsOffroad", {CLEAR_ON_MANAGER_START, BOOL}},
    {"IsRhdDetected", {PERSISTENT, BOOL}},
    {"IsReleaseBranch", {CLEAR_ON_MANAGER_START, BOOL}},
    {"IsTestedBranch", {CLEAR_ON_MANAGER_START, BOOL}},
    {"JoystickDebugMode", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, BOOL}},
    {"LanguageSetting", {PERSISTENT | BACKUP, STRING, "en"}},
    {"LastAthenaPingTime", {CLEAR_ON_MANAGER_START, INT}},
    {"LastGPSPosition", {PERSISTENT, STRING}},
    {"LastManagerExitReason", {CLEAR_ON_MANAGER_START, STRING}},
    {"LastOffroadStatusPacket", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, JSON}},
    {"LastAgnosPowerMonitorShutdown", {CLEAR_ON_MANAGER_START, STRING}},
    {"LastPowerDropDetected", {CLEAR_ON_MANAGER_START, STRING}},
    {"LastUpdateException", {CLEAR_ON_MANAGER_START, STRING}},
    {"LastUpdateRouteCount", {PERSISTENT, INT, "0"}},
    {"LastUpdateTime", {PERSISTENT, TIME}},
    {"LastUpdateUptimeOnroad", {PERSISTENT, FLOAT, "0.0"}},
    {"LiveDelay", {PERSISTENT | BACKUP, BYTES}},
    {"LiveParameters", {PERSISTENT, JSON}},
    {"LiveParametersV2", {PERSISTENT, BYTES}},
    {"LivestreamEncoderBitrate", {CLEAR_ON_MANAGER_START | DONT_LOG, INT}},
    {"LivestreamRequestKeyframe", {CLEAR_ON_MANAGER_START | DONT_LOG, BOOL}},
    {"LiveTorqueParameters", {PERSISTENT | DONT_LOG, BYTES}},
    {"LocationFilterInitialState", {PERSISTENT, BYTES}},
    {"LateralManeuverMode", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, BOOL}},
    {"LongitudinalManeuverMode", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, BOOL}},
    {"LongitudinalPersonality", {PERSISTENT | BACKUP, INT, std::to_string(static_cast<int>(cereal::LongitudinalPersonality::STANDARD))}},
    {"NetworkMetered", {PERSISTENT | BACKUP, BOOL}},
    {"ObdMultiplexingChanged", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BOOL}},
    {"ObdMultiplexingEnabled", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BOOL}},
    {"Offroad_CarUnrecognized", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_ChestnutBranch", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_ChestnutNotDetected", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_ChestnutOverheated", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_ChestnutPcieUnavailable", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_ChestnutUncompiled", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_ChestnutUpdateFailed", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_ChestnutUsbSlow", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_ConnectivityNeeded", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_ConnectivityNeededPrompt", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_ExcessiveActuation", {PERSISTENT, JSON}},
    {"Offroad_NoFirmware", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_Recalibration", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_TemperatureTooHigh", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_UnregisteredHardware", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_UpdateFailed", {CLEAR_ON_MANAGER_START, JSON}},
    {"Offroad_DriverMonitoringUncertain", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"OnroadCycleRequested", {CLEAR_ON_MANAGER_START, BOOL}},
    {"OpenpilotEnabledToggle", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"PandaHeartbeatLost", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, BOOL}},
    {"PrimeType", {PERSISTENT, INT}},
    {"RecordAudio", {PERSISTENT | BACKUP, BOOL}},
    {"RecordFront", {PERSISTENT | BACKUP, BOOL}},
    {"RecordFrontLock", {PERSISTENT, BOOL}},  // for the internal fleet
    {"SecOCKey", {PERSISTENT | DONT_LOG | BACKUP, STRING}},
    {"ShowDebugInfo", {PERSISTENT, BOOL}},
    {"RouteCount", {PERSISTENT, INT, "0"}},
    {"SnoozeUpdate", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, BOOL}},
    {"SshEnabled", {PERSISTENT | BACKUP, BOOL}},
    {"TermsVersion", {PERSISTENT, STRING}},
    {"TorqueBar", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"TrainingVersion", {PERSISTENT, STRING}},
    {"UbloxAvailable", {PERSISTENT, BOOL}},
    {"UpdateAvailable", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BOOL}},
    {"UpdateFailedCount", {CLEAR_ON_MANAGER_START, INT}},
    {"UpdaterAvailableBranches", {PERSISTENT, STRING}},
    {"UpdaterCurrentDescription", {CLEAR_ON_MANAGER_START, STRING}},
    {"UpdaterCurrentReleaseNotes", {CLEAR_ON_MANAGER_START, BYTES}},
    {"UpdaterFetchAvailable", {CLEAR_ON_MANAGER_START, BOOL}},
    {"UpdaterNewDescription", {CLEAR_ON_MANAGER_START, STRING}},
    {"UpdaterNewReleaseNotes", {CLEAR_ON_MANAGER_START, BYTES}},
    {"UpdaterState", {CLEAR_ON_MANAGER_START, STRING}},
    {"UpdaterTargetBranch", {CLEAR_ON_MANAGER_START, STRING}},
    {"UpdaterLastFetchTime", {PERSISTENT, TIME}},
    {"UptimeOffroad", {PERSISTENT, FLOAT, "0.0"}},
    {"UptimeOnroad", {PERSISTENT, FLOAT, "0.0"}},
    {"ChestnutActive", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON, BOOL}},
    {"ChestnutLoading", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON, BOOL}},
    {"ChestnutModelError", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON, BOOL}},
    {"Version", {PERSISTENT, STRING}},

    // --- sunnypilot params --- //
    {"ApiCache_DriveStats", {PERSISTENT, JSON}},
    {"AutoLaneChangeBsmDelay", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"AutoLaneChangeTimer", {PERSISTENT | BACKUP, INT, "0"}},
    {"BlinkerLateralReengageDelay", {PERSISTENT | BACKUP, INT, "0"}},  // seconds
    {"BlinkerMinLateralControlSpeed", {PERSISTENT | BACKUP, INT, "20"}},  // MPH or km/h
    {"BlinkerPauseLateralControl", {PERSISTENT | BACKUP, INT, "0"}},
    {"Brightness", {PERSISTENT | BACKUP, INT, "0"}},
    {"CarList", {PERSISTENT, JSON}},
    {"CarParamsSP", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, BYTES}},
    {"CarParamsSPCache", {CLEAR_ON_MANAGER_START, BYTES}},
    {"CarParamsSPPersistent", {PERSISTENT, BYTES}},
    {"CarPlatformBundle", {PERSISTENT | BACKUP, JSON}},
    {"ChevronInfo", {PERSISTENT | BACKUP, INT, "4"}},
    {"CompletedSunnylinkConsentVersion", {PERSISTENT, STRING, "0"}},
    {"CustomAccIncrementsEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"CustomAccLongPressIncrement", {PERSISTENT | BACKUP, INT, "5"}},
    {"CustomAccShortPressIncrement", {PERSISTENT | BACKUP, INT, "1"}},
    {"DeviceBootMode", {PERSISTENT | BACKUP, INT, "0"}},
    {"DevUIInfo", {PERSISTENT | BACKUP, INT, "0"}},
    {"EnableCopyparty", {PERSISTENT | BACKUP, BOOL}},
    {"EnableGithubRunner", {PERSISTENT | BACKUP, BOOL}},
    {"GreenLightAlert", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"GithubRunnerSufficientVoltage", {CLEAR_ON_MANAGER_START , BOOL}},
    {"HasAcceptedTermsSP", {PERSISTENT, STRING, "0"}},
    {"HideVEgoUI", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"IntelligentCruiseButtonManagement", {PERSISTENT | BACKUP , BOOL}},
    {"InteractivityTimeout", {PERSISTENT | BACKUP, INT, "0"}},
    {"IsDevelopmentBranch", {CLEAR_ON_MANAGER_START, BOOL}},
    {"IsReleaseSpBranch", {CLEAR_ON_MANAGER_START, BOOL}},
    {"LastGPSPositionLLK", {PERSISTENT, STRING}},
    {"LeadDepartAlert", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"MaxTimeOffroad", {PERSISTENT | BACKUP, INT, "1800"}},
    {"ModelRunnerTypeCache", {CLEAR_ON_ONROAD_TRANSITION, INT}},
    {"OffroadMode", {CLEAR_ON_MANAGER_START, BOOL}},
    {"Offroad_TiciSupport", {CLEAR_ON_MANAGER_START, JSON}},
    {"OnroadScreenOffBrightness", {PERSISTENT | BACKUP, INT, "0"}},
    {"OnroadScreenOffBrightnessMigrated", {PERSISTENT | BACKUP, STRING, "0.0"}},
    {"OnroadScreenOffTimer", {PERSISTENT | BACKUP, INT, "15"}},
    {"OnroadScreenOffTimerMigrated", {PERSISTENT | BACKUP, STRING, "0.0"}},
    {"OnroadUploads", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"QuickBootToggle", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"QuietMode", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"RainbowMode", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"RoadEdgeLaneChangeEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"RocketFuel", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ScreenSaverEnabled", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"ScreenSaverTimeout", {PERSISTENT | BACKUP, INT, "300"}},
    {"ShowAdvancedControls", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ShowTurnSignals", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"StandstillTimer", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"TrueVEgoUI", {PERSISTENT | BACKUP, BOOL, "0"}},

    // toyota specific params
    {"ToyotaAutoHold", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ToyotaEnhancedBsm", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ToyotaTSS2Long", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ToyotaDriveMode", {PERSISTENT | BACKUP, BOOL, "0"}},

    // MADS params
    {"Mads", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"MadsMainCruiseAllowed", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"MadsSteeringMode", {PERSISTENT | BACKUP, INT, "0"}},
    {"MadsUnifiedEngagementMode", {PERSISTENT | BACKUP, BOOL, "1"}},

    // Model Manager params
    {"ModelManager_ActiveBundle", {PERSISTENT, JSON}},
    {"ModelManager_ActiveBundleUSBGPU", {PERSISTENT, JSON}}, //TODO-SP: kept for migration, remove on next sync?
    {"ModelManager_ActiveBundleChestnut", {PERSISTENT, JSON}},
    {"ModelManager_ActiveJson", {CLEAR_ON_MANAGER_START, JSON}},
    {"ModelManager_ClearCache", {CLEAR_ON_MANAGER_START, BOOL}},
    {"ModelManager_DownloadRef", {CLEAR_ON_MANAGER_START | CLEAR_ON_ONROAD_TRANSITION, STRING}},
    {"ModelManager_Favs", {PERSISTENT | BACKUP, STRING}},
    {"ModelManager_LastSyncTime", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, INT, "0"}},
    {"ModelManager_LastSyncTime_Chestnut", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, INT, "0"}},
    {"ModelManager_ModelsCache", {PERSISTENT | BACKUP, JSON}},
    {"ModelManager_ModelsCache_Chestnut", {PERSISTENT | BACKUP, JSON}},

    // Neural Network Lateral Control
    {"NeuralNetworkLateralControl", {PERSISTENT | BACKUP, BOOL, "0"}},

    // sunnylink params
    {"EnableSunnylinkUploader", {PERSISTENT | BACKUP, BOOL}},
    {"LastSunnylinkPingTime", {CLEAR_ON_MANAGER_START, INT}},
    {"ParamsVersion", {PERSISTENT, INT}},
    {"SunnylinkCache_Roles", {PERSISTENT, STRING}},
    {"SunnylinkCache_Users", {PERSISTENT, STRING}},
    {"SunnylinkDongleId", {PERSISTENT, STRING}},
    {"SunnylinkdPid", {PERSISTENT, INT}},
    {"SunnylinkEnabled", {PERSISTENT, BOOL, "1"}},
    {"SunnylinkTempFault", {CLEAR_ON_MANAGER_START | CLEAR_ON_OFFROAD_TRANSITION, BOOL, "0"}},

    {"SunnylinkLocalApps", {PERSISTENT, JSON}},
    {"SunnylinkLocalPairingCode", {CLEAR_ON_MANAGER_START, JSON}},
    {"SunnylinkLocalDiscoveredApp", {CLEAR_ON_MANAGER_START, JSON}},
    {"SunnylinkLocalPairingRequest", {CLEAR_ON_MANAGER_START, BOOL}},

    // Backup Manager params
    {"BackupManager_CreateBackup", {PERSISTENT, BOOL}},
    {"BackupManager_RestoreVersion", {PERSISTENT, STRING}},

    // sunnypilot car specific params
    {"HyundaiLongitudinalTuning", {PERSISTENT | BACKUP, INT, "0"}},
    {"SubaruStopAndGo", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"SubaruStopAndGoManualParkingBrake", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"TeslaCoopSteering", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"TeslaMadsScreenButton", {PERSISTENT | BACKUP, INT, "0"}},
    {"ToyotaEnforceStockLongitudinal", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ToyotaStopAndGoHack", {PERSISTENT | BACKUP, BOOL, "0"}},

    {"DynamicExperimentalControl", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"BlindSpot", {PERSISTENT | BACKUP, BOOL, "0"}},

    // Accel Controller profiles (Eco / Normal / Sport)
    {"AccelPersonalityEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"AccelPersonality", {PERSISTENT | BACKUP, INT, "1"}},

    // sunnypilot model params
    {"CameraOffset", {PERSISTENT | BACKUP, FLOAT, "0.0"}},
    {"LagdToggle", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"LagdToggleDelay", {PERSISTENT | BACKUP, FLOAT, "0.2"}},
    {"LagdValueCache", {PERSISTENT, FLOAT, "0.2"}},
    {"LaneTurnDesire", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"LaneTurnValue", {PERSISTENT | BACKUP, FLOAT, "19.0"}},
    {"PlanplusControl", {PERSISTENT | BACKUP, FLOAT, "1.0"}},

    // mapd
    {"MapAdvisorySpeedLimit", {CLEAR_ON_ONROAD_TRANSITION, FLOAT}},
    {"Mapd_ClearCache", {CLEAR_ON_MANAGER_START, BOOL}},
    {"MapdVersion", {PERSISTENT, STRING}},
    {"MapSpeedLimit", {CLEAR_ON_ONROAD_TRANSITION, FLOAT, "0.0"}},
    {"NextMapSpeedLimit", {CLEAR_ON_ONROAD_TRANSITION, JSON}},
    {"Offroad_OSMUpdateRequired", {CLEAR_ON_MANAGER_START, JSON}},
    {"OsmDbUpdatesCheck", {CLEAR_ON_MANAGER_START, BOOL}},  // mapd database update happens with device ON, reset on boot
    {"OSMDownloadBounds", {PERSISTENT, STRING}},
    {"OsmDownloadedDate", {PERSISTENT, STRING, "0.0"}},
    {"OSMDownloadLocations", {PERSISTENT, JSON}},
    {"OSMDownloadProgress", {CLEAR_ON_MANAGER_START, JSON}},
    {"OsmLocal", {PERSISTENT, BOOL}},
    {"OsmLocationName", {PERSISTENT, STRING}},
    {"OsmLocationTitle", {PERSISTENT, STRING}},
    {"OsmLocationUrl", {PERSISTENT, STRING}},
    {"OsmStateName", {PERSISTENT, STRING, "All"}},
    {"OsmStateTitle", {PERSISTENT, STRING}},
    {"OsmWayTest", {PERSISTENT, STRING}},
    {"RoadName", {CLEAR_ON_ONROAD_TRANSITION, STRING}},
    {"RoadNameToggle", {PERSISTENT | BACKUP, BOOL, "0"}},

    // Speed Limit
    {"SpeedLimitMode", {PERSISTENT | BACKUP, INT, "1"}},
    {"SpeedLimitOffsetType", {PERSISTENT | BACKUP, INT, "0"}},
    // 4 = combined: take the LOWER of the car and map limits. Default is 4 so a
    // stricter limit from either source wins - the previous default of 3
    // (map_data_priority) ignored the car limit entirely whenever map had one.
    {"SpeedLimitPolicy", {PERSISTENT | BACKUP, INT, "4"}},  // 0=car only, 1=map only, 2=car first, 3=map first, 4=combined (min)
    {"SpeedLimitValueOffset", {PERSISTENT | BACKUP, INT, "0"}},

    // Smart Cruise Control
    {"MapTargetVelocities", {CLEAR_ON_ONROAD_TRANSITION, STRING}},
    {"SmartCruiseControlMap", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"SmartCruiseControlVision", {PERSISTENT | BACKUP, BOOL, "0"}},

    // Torque lateral control custom params
    {"CustomTorqueParams", {PERSISTENT | BACKUP , BOOL}},
    {"EnforceTorqueControl", {PERSISTENT | BACKUP, BOOL}},
    {"LateralJerkTorqueController", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"LiveTorqueParamsToggle", {PERSISTENT | BACKUP , BOOL}},
    {"LiveTorqueParamsRelaxedToggle", {PERSISTENT | BACKUP , BOOL}},
    {"TorqueControlTune", {PERSISTENT | BACKUP, FLOAT, "0.0"}},
    {"TorqueParamsOverrideEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"TorqueParamsOverrideFriction", {PERSISTENT | BACKUP, FLOAT, "0.1"}},
    {"TorqueParamsOverrideLatAccelFactor", {PERSISTENT | BACKUP, FLOAT, "2.5"}},

    {"DistractionDetectionLevel", {PERSISTENT | BACKUP, INT, "1"}},
    {"DisableDM", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"LivestreamActiveCamera", {CLEAR_ON_MANAGER_START | DONT_LOG, STRING}},
    {"LivestreamEncoderLagging", {CLEAR_ON_MANAGER_START | DONT_LOG, BOOL}},
    {"LocalDriveStats", {PERSISTENT, JSON}},
    {"TripsDataSource", {PERSISTENT | BACKUP, STRING, "local"}},
    {"SpDevBeep", {PERSISTENT, BOOL, "0"}},
    {"WebuiHeadlessMode", {PERSISTENT | BACKUP, STRING, "auto"}},
    {"IsOnroadPreview", {CLEAR_ON_MANAGER_START, BOOL}},
    {"IsOnroad", {PERSISTENT, BOOL, "0"}},  // onroad state mirror written for carrot phone-app broadcast
    {"CarName", {PERSISTENT, STRING}},  // user-set car name, sent via carrot FTP export

    {"ImuCalibrationEnabled", {PERSISTENT, BOOL}},
    {"ImuCalibrationMatrix", {PERSISTENT, BYTES}},
    {"ImuCalibrationRequested", {CLEAR_ON_MANAGER_START, BOOL}},
    {"ImuCalibrationStatus", {PERSISTENT, STRING}},
    {"HideFirehosePrompt", {PERSISTENT | BACKUP, BOOL, "0"}},
    // Longitudinal MPC tuning
    {"LongitudinalMpcTuningComfortBrake", {PERSISTENT | BACKUP, FLOAT, "2.5"}},
    {"LongitudinalMpcTuningStopDistance", {PERSISTENT | BACKUP, FLOAT, "6.0"}},
    {"LongitudinalMpcTuningTFollowRelaxed", {PERSISTENT | BACKUP, FLOAT, "1.75"}},
    {"LongitudinalMpcTuningTFollowStandard", {PERSISTENT | BACKUP, FLOAT, "1.45"}},
    {"LongitudinalMpcTuningTFollowAggressive", {PERSISTENT | BACKUP, FLOAT, "1.25"}},
    {"LongitudinalMpcTuningXEgoObstacleCost", {PERSISTENT | BACKUP, FLOAT, "3.0"}},
    {"LongitudinalMpcTuningJEgoCost", {PERSISTENT | BACKUP, FLOAT, "5.0"}},
    {"LongitudinalMpcTuningAChangeCost", {PERSISTENT | BACKUP, FLOAT, "200.0"}},
    {"LongitudinalMpcTuningDangerZoneCost", {PERSISTENT | BACKUP, FLOAT, "100.0"}},
    {"LongitudinalMpcTuningLeadDangerFactor", {PERSISTENT | BACKUP, FLOAT, "0.75"}},

    // Amap / Carrot (phone projection & navigation)
    // AmapEnabled is deprecated: it historically controlled both Amap Web map
    // data and the 7706 blind-spot parser. It is kept here only for one-time
    // migration to AmapMapDataEnabled / CarrotAmapBlindSpotEnabled.
    {"AmapEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"AmapApiKey", {PERSISTENT | DONT_LOG, STRING}},
    // Use Amap (Gaode) online Web API for speed limits / road names.
    {"AmapMapDataEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    // OSM offline map data. Off means "do not use the offline map for speed limits
    // or road names", so a user who relies on Amap or carrot can silence the
    // offline fallback. Default 1 keeps existing behaviour.
    {"OsmMapDataEnabled", {PERSISTENT | BACKUP, BOOL, "1"}},
    // Set once the legacy AmapEnabled switch has been migrated, so the migration
    // cannot run again and silently re-enable Amap after the user disabled it.
    {"AmapLegacyMigrated", {PERSISTENT, BOOL, "0"}},
    // Parse 7706 UDP blind-spot / LiDAR / extBlinker fields (AmapNaviServ).
    {"CarrotAmapBlindSpotEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"CarrotEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    // 7714 WebSocket v2 navi link killswitch. Default off so the new
    // carrotNavi process never starts unless explicitly enabled. Requires
    // CarrotEnabled as the master switch (see process_config.py).
    {"CarrotNaviV2Enabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    // Opt-in system time sync from the phone's 7706/7714 epochTime/timezone.
    // Default OFF: modifying the system clock on a running car is dangerous and
    // sunnypilot already keeps time via NTP. Only when explicitly enabled does
    // carrot_serv nudge the clock/timezone, and only within a limited drift.
    {"CarrotNtpTimeSync", {PERSISTENT | BACKUP, BOOL, "0"}},
    // Retired. The listen port is the CARROT_MAN_UDP_PORT constant in carrot_man.py:/n    // the phone app hard-codes 7706 as its fallback in three paths and offers no way
    // to change it, so a configurable value could only cause silent packet loss. Kept
    // registered so params_migration can clear a stale value; not exposed in any UI.
    {"CarrotManUdpPort", {PERSISTENT | BACKUP, INT, "7706"}},
    {"CarrotPanelSide", {PERSISTENT | BACKUP, INT, "0"}},  // carrot nav HUD panel side: 0=left, 1=right
    {"CarrotPanelOpacity", {PERSISTENT | BACKUP, INT, "100"}},  // carrot nav HUD panel opacity percent 0-100
    {"LiDARUdpPort", {PERSISTENT | BACKUP, INT, "4211"}},  // LiDAR/camera direct-UDP listen port; dormant until start_navi_comm() is wired (C3 decision)
    // DrivingMode enum (carrot_functions.py): 1=Eco, 2=Safe, 3=Normal, 4=High.
    // The comment here used to read "0=eco,1=normal,2=sport,3=safe", which matches
    // nothing in the enum, and the default was "1" on that mistaken reading - so the
    // running mode was Eco while config.py, nav_params.json and both UIs said Normal.
    {"MyDrivingMode", {PERSISTENT | BACKUP, INT, "3"}},  // 1=Eco, 2=Safe, 3=Normal, 4=High
    // TFollowGap/CruiseMaxVals use the CarrotPilot int*100 representation so
    // that carrot_functions.py can keep dividing by 100.0 (matching cp).
    {"TFollowGap1", {PERSISTENT | BACKUP, INT, "110"}},
    {"TFollowGap2", {PERSISTENT | BACKUP, INT, "120"}},
    {"TFollowGap3", {PERSISTENT | BACKUP, INT, "140"}},
    {"TFollowGap4", {PERSISTENT | BACKUP, INT, "160"}},
    // cp tuning alignment: params present in CarrotPilot settings but newly
    // registered here so webui read/reset works and defaults match cp.
    {"CruiseGapLevels", {PERSISTENT | BACKUP, INT, "4"}},
    // How many follow-gap levels the vehicle exposes (3 or 4). Read by
    // sunnypilot CruiseHelper when the distance button cycles the gap; spans the
    // cluster personality range. Same default as cp.
    {"LongitudinalPersonalityMax", {PERSISTENT | BACKUP, INT, "3"}},
    // Restored with the VCruiseCarrot port (cp L7). These were removed in the dead-key
    // cleanup because nothing read them; VCruiseCarrot is their reader.
    {"AutoCruiseControl", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoGasCancelSpeed", {PERSISTENT | BACKUP, INT, "30"}},
    {"AutoGasTokSpeed", {PERSISTENT | BACKUP, INT, "0"}},
    {"PaddleMode", {PERSISTENT | BACKUP, INT, "0"}},
    {"SoftHoldOnCancel", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"UseLaneLineSpeed", {PERSISTENT | BACKUP, INT, "0"}},
    // New with L7.
    {"ActivateCruiseAfterBrake", {CLEAR_ON_MANAGER_START, INT, "0"}},
    {"AutoRoadSpeedAdjust", {PERSISTENT | BACKUP, INT, "50"}},
    {"AutoSpeedUptoRoadSpeedLimit", {PERSISTENT | BACKUP, INT, "0"}},
    {"LeadAccelResponseTF1", {PERSISTENT | BACKUP, INT, "-1"}},
    {"LeadAccelResponseTF2", {PERSISTENT | BACKUP, INT, "-1"}},
    {"LeadAccelResponseTF3", {PERSISTENT | BACKUP, INT, "-1"}},
    {"LeadAccelResponseTF4", {PERSISTENT | BACKUP, INT, "-1"}},
    {"AutoNaviRearCameraHoldDistance", {PERSISTENT | BACKUP, INT, "100"}},
    // Removed: carrot keys for opendbc-layer features this fork has not ported.
    // They were registered (and some drawn in a UI) but no code in this tree read them,
    // so the knob advertised a feature that did not exist. See artifacts/carrot_control_audit/
    // cp_sp_opendbc_integration_gaps_2026-09-23.md for what each one would need.
    {"CruiseMaxVals0", {PERSISTENT | BACKUP, INT, "160"}},
    {"CruiseMaxVals1", {PERSISTENT | BACKUP, INT, "160"}},
    {"CruiseMaxVals2", {PERSISTENT | BACKUP, INT, "120"}},
    {"CruiseMaxVals3", {PERSISTENT | BACKUP, INT, "100"}},
    {"CruiseMaxVals4", {PERSISTENT | BACKUP, INT, "80"}},
    {"CruiseMaxVals5", {PERSISTENT | BACKUP, INT, "70"}},
    {"CruiseMaxVals6", {PERSISTENT | BACKUP, INT, "60"}},
    {"TrafficLight", {CLEAR_ON_MANAGER_START, JSON, "{}"}},  // fused/carrot navi traffic-light state
    {"CarrotNaviCrossroad", {CLEAR_ON_MANAGER_START, JSON, "{}"}},  // visible complex-crossroad hint from 7714 v2
    {"CarrotNaviImage", {CLEAR_ON_MANAGER_START, JSON, "{}"}},  // 7714 v2 complex-crossroad base64 image for HUD overlay
    {"CarrotNaviDebug", {CLEAR_ON_MANAGER_START, JSON, "{}"}},  // carrot navi debug state for UI viewer
    {"CarrotNaviWebBootstrapRequest", {CLEAR_ON_MANAGER_START, STRING, ""}},  // web bootstrap request payload from webui
    {"CarrotNaviAppStatus", {CLEAR_ON_MANAGER_START, STRING, ""}},  // 7714 v2 app foreground/focus/map/capture status
    {"CarrotNaviCameraState", {CLEAR_ON_MANAGER_START, STRING, ""}},  // 7714 v2 camera mode/level/tilt/bearing
    {"CarrotNaviCompositionState", {CLEAR_ON_MANAGER_START, STRING, ""}},  // 7714 v2 UI composition active panels
    {"TrafficLightDetectMode", {PERSISTENT | BACKUP, INT, "2"}},  // 0=off, 1=red-stop-only, 2=stop&go (cp default)  // 0=off,1=red stop,2=red stop + green go
    {"CarrotCurveSpeedEnabled", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"CarrotNavCruiseSpeedEnabled", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"CarrotHudInfoEnabled", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"CarrotWebEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    // Unified control killswitches (carrot > Amap > OSM arbitration). Default off/safe.
    {"CarrotLongitudinalSourceEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},  // enable CarrotPlanner as a LongitudinalPlanSP source
    {"CarrotTrafficLightFusionEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},  // fuse carrot / Amap / vision traffic lights
    {"TrafficLightNavCautionOnly", {PERSISTENT | BACKUP, BOOL, "1"}},       // fused red light only warns; set 0 to allow stop assist
    {"DesireArbiterEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},             // lateral lane-change/fork desire from nav
    // Let carrot ATC (auto turn control) synthesise a turn signal from the phone's
    // navigation intent. OFF by default. When on, an ATC/atcType/forkLeft-style packet
    // makes desire_helper treat a blinker as pressed, which reaches the vehicle: the
    // synthetic blinker drives LaneChangeState.preLaneChange -> modelV2 laneChangeState
    // -> controlsd CC.left/rightBlinker -> the car's own turn-signal CAN message. That is
    // a navigation intent becoming a vehicle actuation, so it has to be an explicit
    // choice rather than the default.
    {"CarrotAtcBlinkerEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"CarrotSourceTimeoutMs", {PERSISTENT | BACKUP, INT, "2000"}},          // carrot packet timeout [ms]
    {"CarrotTrafficCongestionEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},   // fold phone TMC congestion into SmartCruiseControlMap (only lowers the target)
    // Carrot navigation deceleration for a point ahead: ATC turn speed, the curve
    // speed table, and the route-curvature speed. Folds into SmartCruiseControlMap
    // (which must ALSO be on for it to actuate, same as the congestion cap).
    {"CarrotMapDecelEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},
    // One-shot: the first time Carrot navigation is enabled, its map-deceleration
    // sub-features (congestion / map-decel / Amap curve) are seeded ON so the user
    // does not have to find three more switches. Each stays independently offable
    // afterwards - they are killswitches, not prerequisites.
    {"CarrotNavFeaturesSeeded", {PERSISTENT, BOOL, "0"}},
    {"HapticFeedbackWhenSpeedCamera", {PERSISTENT, INT, "0"}},
    // Published by networkd; the Carrot web dialog reads it for the QR link.
    {"NetworkAddress", {CLEAR_ON_MANAGER_START, STRING}},
    // Destination pushed by the phone (sunnylink athena RPC setNavDestination,
    // and carrot_man's external-navi path). Both wrote it through
    // Params.put() while it was unregistered, so check_key() raised
    // UnknownKeyName: the athena RPC call had no guard around it at all, and
    // carrot's copy only survived because of a broad except.
    // JSON type: writers must pass a dict, not a json.dumps() string.
    {"NavDestination", {PERSISTENT, JSON, "{}"}},
    // Timezone the phone pushed, plus who set it. carrot_serv writes them after
    // syncing the clock from the app so timed.py does not immediately overwrite
    // the app's value with the device's own guess.
    {"TimezoneName", {PERSISTENT, STRING}},
    {"TimezoneSource", {PERSISTENT, STRING}},
    // Registered after the unregistered-reads audit: these BYD-platform and lateral
    // tuning reads were live code with no registration, so no UI or whitelist could
    // ever reach them. Defaults are 0 - the carcontroller's own per-platform
    // fallbacks keep governing exactly as before; nothing changes until a value is
    // actually written.
    {"BydBsdType2", {PERSISTENT, BOOL, "0"}},
    {"BydLatUseSiglin", {PERSISTENT, BOOL, "0"}},
    {"BydLowSpdLong", {PERSISTENT, BOOL, "0"}},
    {"BydModifiedStockLong", {PERSISTENT, BOOL, "0"}},
    {"BydMpcTsr", {PERSISTENT, BOOL, "0"}},
    {"EnableExtRadar", {PERSISTENT, BOOL, "0"}},
    {"UseRedPanda", {PERSISTENT, BOOL, "0"}},
    {"LateralAngleSpdBp1", {PERSISTENT, INT, "0"}},
    {"LateralAngleSpdBp2", {PERSISTENT, INT, "0"}},
    {"LateralAngleSpdDn0", {PERSISTENT, INT, "0"}},
    {"LateralAngleSpdDn1", {PERSISTENT, INT, "0"}},
    {"LateralAngleSpdDn2", {PERSISTENT, INT, "0"}},
    {"LateralAngleSpdUp0", {PERSISTENT, INT, "0"}},
    {"LateralAngleSpdUp1", {PERSISTENT, INT, "0"}},
    {"LateralAngleSpdUp2", {PERSISTENT, INT, "0"}},
    {"LateralAngleTorqCut", {PERSISTENT, INT, "0"}},
    {"LateralAngleTorqMax", {PERSISTENT, INT, "0"}},
    {"SpeedCorrect120", {PERSISTENT, INT, "0"}},
    {"SpeedCorrect30", {PERSISTENT, INT, "0"}},
    {"SpeedCorrect60", {PERSISTENT, INT, "0"}},
    {"SpeedCorrect90", {PERSISTENT, INT, "0"}},
    {"CarrotNavLaneGuideBlockEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},   // let 7706 navLaneGuide block non-guided adjacent lanes
    {"AmapCurveSpeedEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},            // use Amap Web polyline for curve speed
    {"AmapTrafficLightHintEnabled", {PERSISTENT | BACKUP, BOOL, "0"}},      // use Amap Web traffic-light hints
    // Carrot speed/turn/navi tuning surface. Defaults mirror cp/fp behavior where applicable;
    // keys are registered so UnifiedParams writes land in the cross-process Params store.
    {"AutoCurveSpeedLowerLimit", {PERSISTENT | BACKUP, INT, "30"}},
    {"AutoCurveSpeedFactor", {PERSISTENT | BACKUP, INT, "100"}},
    {"AutoCurveSpeedAggressiveness", {PERSISTENT | BACKUP, INT, "100"}},
    {"AutoTurnControl", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoTurnControlSpeedTurn", {PERSISTENT | BACKUP, INT, "20"}},
    {"AutoTurnControlTurnEnd", {PERSISTENT | BACKUP, INT, "6"}},
    {"AutoTurnMapChange", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"AutoNaviSpeedCtrlEnd", {PERSISTENT | BACKUP, INT, "6"}},
    {"VehicleNaviCanControl", {PERSISTENT | BACKUP, INT, "0"}},
    {"VehicleNaviSchoolZoneControl", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"VehicleSpeedCameraControlMode", {PERSISTENT | BACKUP, INT, "1"}},
    {"VehicleSpeedCameraDistanceTime", {PERSISTENT | BACKUP, INT, "60"}},
    {"AutoRoadSpeedLimitOffset", {PERSISTENT | BACKUP, INT, "-1"}},
    {"AutoNaviSpeedBumpTime", {PERSISTENT | BACKUP, INT, "1"}},
    {"AutoNaviSpeedBumpSpeed", {PERSISTENT | BACKUP, INT, "35"}},
    {"AutoNaviSpeedBumpEndDistance", {PERSISTENT | BACKUP, INT, "200"}},
    {"LatSuspendAngleDeg", {PERSISTENT | BACKUP, INT, "300"}},
    {"ClusterNaviMapTheme", {PERSISTENT | BACKUP, INT, "1"}},
    {"ClusterNaviMapType", {PERSISTENT | BACKUP, INT, "0"}},
    {"ClusterNaviMapFps", {PERSISTENT | BACKUP, INT, "1"}},
    {"CarrotNaviHudMapProfile", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoNaviCountDownMode", {PERSISTENT | BACKUP, INT, "2"}},
    {"TurnSpeedControlMode", {PERSISTENT | BACKUP, INT, "1"}},
    {"MapTurnSpeedFactor", {PERSISTENT | BACKUP, INT, "100"}},
    // Carrot tuning surface (mirrors _DEFAULT_NAV_PARAMS in sunnypilot/carrot/config.py).
    // Registered so UnifiedParams writes land in the cross-process Params store;
    // nav_params.json remains a read fallback for values tuned before registration.
    {"AutoTurnDistOffset", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoForkDistOffset", {PERSISTENT | BACKUP, INT, "30"}},
    {"AutoDoForkBlinkerDist", {PERSISTENT | BACKUP, INT, "15"}},
    {"AutoDoForkNavDist", {PERSISTENT | BACKUP, INT, "15"}},
    {"AutoForkDistOffsetH", {PERSISTENT | BACKUP, INT, "1000"}},
    {"AutoDoForkDecalDistH", {PERSISTENT | BACKUP, INT, "50"}},
    {"AutoDoForkDecalDist", {PERSISTENT | BACKUP, INT, "20"}},
    {"AutoDoForkBlinkerDistH", {PERSISTENT | BACKUP, INT, "30"}},
    {"AutoDoForkNavDistH", {PERSISTENT | BACKUP, INT, "50"}},
    {"AutoUpRoadLimit", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoUpRoadLimit40KMH", {PERSISTENT | BACKUP, INT, "15"}},
    {"AutoUpHighwayRoadLimit", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoUpHighwayRoadLimit40KMH", {PERSISTENT | BACKUP, INT, "15"}},
    {"RoadType", {PERSISTENT | BACKUP, INT, "-1"}},
    {"AutoForkDecalRateH", {PERSISTENT | BACKUP, INT, "80"}},
    {"AutoForkSpeedMinH", {PERSISTENT | BACKUP, INT, "60"}},
    {"AutoKeepForkSpeedH", {PERSISTENT | BACKUP, INT, "5"}},
    {"AutoForkDecalRate", {PERSISTENT | BACKUP, INT, "80"}},
    {"AutoForkSpeedMin", {PERSISTENT | BACKUP, INT, "45"}},
    {"AutoKeepForkSpeed", {PERSISTENT | BACKUP, INT, "5"}},
    {"ShowDebugLog", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"AutoCurveSpeedFactorH", {PERSISTENT | BACKUP, INT, "100"}},
    {"AutoCurveSpeedAggressivenessH", {PERSISTENT | BACKUP, INT, "100"}},
    {"SameSpiCamFilter", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"StockBlinkerCtrl", {PERSISTENT | BACKUP, INT, "0"}},
    {"DynamicBlindRange", {PERSISTENT | BACKUP, INT, "0"}},
    {"DynamicBlindDistance", {PERSISTENT | BACKUP, INT, "0"}},
    {"DisableBlindSpot", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"BsdDelayTime", {PERSISTENT | BACKUP, INT, "20"}},
    {"SideBsdDelayTime", {PERSISTENT | BACKUP, INT, "20"}},
    {"SideRelDistTime", {PERSISTENT | BACKUP, INT, "10"}},
    {"SidevRelDistTime", {PERSISTENT | BACKUP, INT, "10"}},
    {"SideRadarMinDist", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoTurnInNotRoadEdge", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"ContinuousLaneChange", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"NewLaneWidthDiff", {PERSISTENT | BACKUP, INT, "8"}},
    {"StopDistanceCarrot", {PERSISTENT | BACKUP, INT, "600"}},
    // One-shot marker for the StopDistanceCarrot -> LongitudinalMpcTuningStopDistance
    // merge. It must be registered: reading an unregistered key raises
    // UnknownKeyName, which the migration's except-block swallows, so the merge
    // would silently never run and the marker would be re-evaluated forever.
    {"CarrotStopDistanceMigrated", {PERSISTENT, STRING}},
    {"CarrotUdpPortMigrated", {PERSISTENT, STRING}},
    {"AutoNaviSpeedCtrlMode", {PERSISTENT | BACKUP, INT, "2"}},
    {"AutoNaviSpeedDecelRate", {PERSISTENT | BACKUP, INT, "120"}},  // 1.2 m/s^2 (cp default)
    {"AutoNaviSpeedSafetyFactor", {PERSISTENT | BACKUP, INT, "105"}},
    {"SoundVolumeAdjust", {PERSISTENT | BACKUP, INT, "100"}},
    {"SoundVolumeAdjustEngage", {PERSISTENT | BACKUP, INT, "100"}},
    {"CarrotException", {PERSISTENT | BACKUP, STRING, ""}},
    {"JLeadFactor3", {PERSISTENT | BACKUP, FLOAT, "0"}},
    {"CruiseEcoControl", {PERSISTENT | BACKUP, INT, "2"}},
    {"MyDrivingModeAuto", {PERSISTENT | BACKUP, INT, "0"}},
    {"DynamicTFollowLC", {PERSISTENT | BACKUP, FLOAT, "100.0"}},
    // Carrot longitudinal / t_follow tuning surface (webui exposure, mirrors config.py).
    {"LeadAccelResponse", {PERSISTENT | BACKUP, INT, "0"}},
    {"LongActuatorDelay", {PERSISTENT | BACKUP, INT, "20"}},
    {"LongTuningKf", {PERSISTENT | BACKUP, INT, "100"}},
    {"LongTuningKiV", {PERSISTENT | BACKUP, INT, "0"}},
    {"LongTuningKpV", {PERSISTENT | BACKUP, INT, "100"}},
    {"TFollowDecelBoost", {PERSISTENT | BACKUP, INT, "0"}},
    // Carrot cruise / acceleration tuning surface.
    {"CruiseButtonLongDelay", {PERSISTENT | BACKUP, INT, "40"}},
    {"CruiseButtonMode", {PERSISTENT | BACKUP, INT, "0"}},
    {"CruiseOnDist", {PERSISTENT | BACKUP, INT, "0"}},
    {"CruiseSpeed1", {PERSISTENT | BACKUP, INT, "10"}},
    {"CruiseSpeed2", {PERSISTENT | BACKUP, INT, "10"}},
    {"CruiseSpeed3", {PERSISTENT | BACKUP, INT, "10"}},
    {"CruiseSpeed4", {PERSISTENT | BACKUP, INT, "10"}},
    {"CruiseSpeed5", {PERSISTENT | BACKUP, INT, "10"}},
    {"CruiseSpeedUnit", {PERSISTENT | BACKUP, INT, "10"}},
    {"CruiseSpeedUnitBasic", {PERSISTENT | BACKUP, INT, "10"}},
    // Carrot speed limits / road speed tuning surface.
    {"SpeedFromPCM", {PERSISTENT | BACKUP, INT, "0"}},
    // Carrot traffic stop / lights tuning surface.
    {"TrafficStopDistanceAdjust", {PERSISTENT | BACKUP, INT, "-150"}},
    // Carrot lane change / blinker / lane-line tuning surface.
    {"LaneChangeDelay", {PERSISTENT | BACKUP, INT, "0"}},
    {"LaneChangeNeedTorque", {PERSISTENT | BACKUP, INT, "0"}},
    {"LaneLineCheck", {PERSISTENT | BACKUP, INT, "0"}},
    {"OnnxBsdIntervalMs", {PERSISTENT | BACKUP, INT, "250"}},
    {"OnnxBsdSmoothingMs", {PERSISTENT | BACKUP, INT, "200"}},
    {"OnnxBsdThreshold", {PERSISTENT | BACKUP, INT, "45"}},
    {"UseLaneLineCurveSpeed", {PERSISTENT | BACKUP, INT, "0"}},
    // Carrot steering / lateral tuning surface.
    {"AlwaysLateral", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"CustomSR", {PERSISTENT | BACKUP, INT, "0"}},
    {"LatMpcAccelCost", {PERSISTENT | BACKUP, INT, "100"}},
    {"LatMpcJerkCost", {PERSISTENT | BACKUP, INT, "1"}},
    {"LatMpcMotionCost", {PERSISTENT | BACKUP, INT, "7"}},
    {"LatMpcPathCost", {PERSISTENT | BACKUP, INT, "200"}},
    {"LatMpcSteeringRateCost", {PERSISTENT | BACKUP, INT, "7"}},
    {"LateralTorqueCustom", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"LateralTorqueFriction", {PERSISTENT | BACKUP, INT, "100"}},
    {"LateralTorqueKd", {PERSISTENT | BACKUP, INT, "0"}},
    {"LateralTorqueKf", {PERSISTENT | BACKUP, INT, "100"}},
    {"LateralTorqueKiV", {PERSISTENT | BACKUP, INT, "10"}},
    {"LateralTorqueKpV", {PERSISTENT | BACKUP, INT, "100"}},
    {"PathOffset", {PERSISTENT | BACKUP, INT, "0"}},
    {"SteerActuatorDelay", {PERSISTENT | BACKUP, INT, "30"}},
    {"SteerRatioRate", {PERSISTENT | BACKUP, INT, "100"}},
    // Carrot vehicle / CAN / buttons tuning surface.
    {"AutoGasSyncSpeed", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"CancelButtonMode", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"LfaButtonMode", {PERSISTENT | BACKUP, INT, "0"}},
    // Carrot misc driving tuning surface.
    {"ApplyModelSpeed", {PERSISTENT | BACKUP, INT, "0"}},
    {"AutoEngage", {PERSISTENT | BACKUP, INT, "0"}},
    // Carrot tuning surface: parameters present in config.py but previously
    // unregistered in params_keys.h. Registering them lets UnifiedParams write
    // directly to the cross-process Params store instead of nav_params.json.
    {"CameraYawTrimDeg", {PERSISTENT | BACKUP, INT, "0"}},
    {"CarrotYouTubeLive", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"CarrotYouTubeQuality", {PERSISTENT | BACKUP, INT, "0"}},
    {"CarrotYouTubeTimestamp", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHud", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudBrightness", {PERSISTENT | BACKUP, INT, "0"}},
    {"ClusterHudCameraViewMode", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudCoreMode", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudDebug", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudEncoder", {PERSISTENT | BACKUP, INT, "0"}},
    {"ClusterHudLiveFps", {PERSISTENT | BACKUP, INT, "1"}},
    {"ClusterHudMirror", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudOrientation", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudPanelLayout", {PERSISTENT | BACKUP, INT, "0"}},
    {"ClusterHudPriority", {PERSISTENT | BACKUP, INT, "10"}},
    {"ClusterHudRadarDisplay", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudRadarInfo", {PERSISTENT | BACKUP, INT, "4"}},
    {"ClusterHudRadarSourceColor", {PERSISTENT | BACKUP, INT, "0"}},
    {"ClusterHudScreenMode", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ClusterHudTheme", {PERSISTENT | BACKUP, INT, "0"}},
    {"EnableRadarTracks", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"EnableSpeedTF", {PERSISTENT | BACKUP, INT, "0"}},
    {"HotspotOnBoot", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"LatMpcInputOffset", {PERSISTENT | BACKUP, INT, "4"}},
    {"LatSmoothSec", {PERSISTENT | BACKUP, INT, "13"}},
    {"LateralTorqueAccelFactor", {PERSISTENT | BACKUP, INT, "2500"}},
    {"MapboxStyle", {PERSISTENT | BACKUP, INT, "0"}},
    {"MuteDoor", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"MuteSeatbelt", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"OnnxLaneIntervalMs", {PERSISTENT | BACKUP, INT, "400"}},
    {"OnnxLaneThreshold", {PERSISTENT | BACKUP, INT, "25"}},
    {"RecordRoadCam", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ShareData", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ShowCameraWithCluster", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ShowCustomBrightness", {PERSISTENT | BACKUP, INT, "100"}},
    {"ShowDateTime", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"ShowDebugUI", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"ShowDeviceState", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"ShowLaneInfo", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"ShowModelView", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ShowPathColor", {PERSISTENT | BACKUP, INT, "12"}},
    {"ShowPathColorCruiseOff", {PERSISTENT | BACKUP, INT, "1"}},
    {"ShowPathColorLane", {PERSISTENT | BACKUP, INT, "3"}},
    {"ShowPathEnd", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"ShowPathMode", {PERSISTENT | BACKUP, INT, "9"}},
    {"ShowPathModeLane", {PERSISTENT | BACKUP, INT, "11"}},
    {"ShowPlotMode", {PERSISTENT | BACKUP, INT, "0"}},
    {"ShowRadarInfo", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ShowRouteInfo", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"ShowTpms", {PERSISTENT | BACKUP, BOOL, "1"}},
    {"SoftwareMenu", {PERSISTENT | BACKUP, BOOL, "0"}},
    {"SoundLanguageSetting", {PERSISTENT | BACKUP, STRING, "auto"}},
    {"UseWideCamera", {PERSISTENT | BACKUP, BOOL, "1"}},
};
