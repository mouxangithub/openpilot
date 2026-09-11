using Cxx = import "/include/c++.capnp";
$Cxx.namespace("cereal");

@0xb526ba661d550a59;

# custom.capnp: a home for empty structs reserved for custom forks
# These structs are guaranteed to remain reserved and empty in mainline
# cereal, so use these if you want custom events in your fork.

# DO rename the structs
# DON'T change the identifier (e.g. @0x81c2f05a394cf4af)

struct ModularAssistiveDrivingSystem {
  state @0 :ModularAssistiveDrivingSystemState;
  enabled @1 :Bool;
  active @2 :Bool;
  available @3 :Bool;

  enum ModularAssistiveDrivingSystemState {
    disabled @0;
    paused @1;
    enabled @2;
    softDisabling @3;
    overriding @4;
  }
}

struct IntelligentCruiseButtonManagement {
  state @0 :IntelligentCruiseButtonManagementState;
  sendButton @1 :SendButtonState;
  vTarget @2 :Float32;

  enum IntelligentCruiseButtonManagementState {
    inactive @0;      # No button press or default state
    preActive @1;     # Pre-active state before transitioning to increasing or decreasing
    increasing @2;    # Increasing speed
    decreasing @3;    # Decreasing speed
    holding @4;       # Holding steady speed
  }

  enum SendButtonState {
    none @0;
    increase @1;
    decrease @2;
  }
}

# Same struct as Log.RadarState.LeadData
struct LeadData {
  dRel @0 :Float32;
  yRel @1 :Float32;
  vRel @2 :Float32;
  aRel @3 :Float32;
  vLead @4 :Float32;
  dPath @6 :Float32;
  vLat @7 :Float32;
  vLeadK @8 :Float32;
  aLeadK @9 :Float32;
  fcw @10 :Bool;
  status @11 :Bool;
  aLeadTau @12 :Float32;
  modelProb @13 :Float32;
  radar @14 :Bool;
  radarTrackId @15 :Int32 = -1;

  aLeadDEPRECATED @5 :Float32;
}

struct SelfdriveStateSP @0x81c2f05a394cf4af {
  mads @0 :ModularAssistiveDrivingSystem;
  intelligentCruiseButtonManagement @1 :IntelligentCruiseButtonManagement;
  buttonsPressed @2 :UInt16;
  buttonsReleaseToggle @3 :UInt16;

  enum AudibleAlert {
    none @0;

    engage @1;
    disengage @2;
    refuse @3;

    warningSoft @4;
    warningImmediate @5;

    prompt @6;
    promptRepeat @7;
    promptDistracted @8;

    # unused, these are reserved for upstream events so we don't collide
    reserved9 @9;
    reserved10 @10;
    reserved11 @11;
    reserved12 @12;
    reserved13 @13;
    reserved14 @14;
    reserved15 @15;
    reserved16 @16;
    reserved17 @17;
    reserved18 @18;
    reserved19 @19;
    reserved20 @20;
    reserved21 @21;
    reserved22 @22;
    reserved23 @23;
    reserved24 @24;
    reserved25 @25;
    reserved26 @26;
    reserved27 @27;
    reserved28 @28;
    reserved29 @29;
    reserved30 @30;

    promptSingleLow @31;
    promptSingleHigh @32;

    # carrot (phone projection & navigation)
    audioTurn @33;
    longEngaged @34;
    longDisengaged @35;
    trafficSignGreen @36;
    trafficSignChanged @37;
    laneChangeCarrot @38;
    stopping @39;
    autoHold @40;
    engage2 @41;
    disengage2 @42;
    trafficError @43;
    bsdWarning @44;
    speedDown @45;
    stopStop @46;
    reverseGear2 @47;
    audio1 @48;
    audio2 @49;
    audio3 @50;
    audio4 @51;
    audio5 @52;
    audio6 @53;
    audio7 @54;
    audio8 @55;
    audio9 @56;
    audio10 @57;
    nnff @58;
    preLaneChangeCarrot @59;
    atcCancel @60;
    atcResume @61;
    preLaneChangeLeft2 @62;
    preLaneChangeRight2 @63;
    laneChangeOk @64;
    lastLane @65;
    newLane @66;
    laneChangeEnd @67;
  }
}

struct ModelManagerSP @0xaedffd8f31e7b55d {
  activeBundle @0 :ModelBundle;
  selectedBundle @1 :ModelBundle;
  availableBundles @2 :List(ModelBundle);

  struct DownloadUri {
    uri @0 :Text;
    sha256 @1 :Text;
  }

  enum DownloadStatus {
    notDownloading @0;
    downloading @1;
    downloaded @2;
    cached @3;
    failed @4;
    verifying @5;
  }

  struct DownloadProgress {
    status @0 :DownloadStatus;
    progress @1 :Float32;
    eta @2 :UInt32;
  }

  struct Chunk {
    fileName @0 :Text;
    sha256 @1 :Text;
  }

  struct Artifact {
    fileName @0 :Text;
    downloadUri @1 :DownloadUri;
    downloadProgress @2 :DownloadProgress;
    chunks @3 :List(Chunk);
  }

  struct Model {
    type @0 :Type;
    artifact @1 :Artifact;  # Main artifact
    metadata @2 :Artifact;  # Metadata artifact

    enum Type {
      supercombo @0;
      navigation @1;
      vision @2;
      policy @3;
      offPolicy @4;
      onPolicy @5;
      chunked @6;
    }
  }

  enum Runner {
    snpe @0;
    tinygrad @1;
    stock @2;
  }

  struct Override {
    key @0 :Text;
    value @1 :Text;
  }

  struct ModelBundle {
    index @0 :UInt32;
    internalName @1 :Text;
    displayName @2 :Text;
    models @3 :List(Model);
    status @4 :DownloadStatus;
    generation @5 :UInt32;
    environment @6 :Text;
    runner @7 :Runner;
    is20hz @8 :Bool;
    ref @9 :Text;
    minimumSelectorVersion @10 :UInt32;
    overrides @11 :List(Override);
  }
}

struct LongitudinalPlanSP @0xf35cc4560bbf6ec2 {
  dec @0 :DynamicExperimentalControl;
  longitudinalPlanSource @1 :LongitudinalPlanSource;
  smartCruiseControl @2 :SmartCruiseControl;
  speedLimit @3 :SpeedLimit;
  vTarget @4 :Float32;
  aTarget @5 :Float32;
  events @6 :List(OnroadEventSP.Event);
  e2eAlerts @7 :E2eAlerts;
  accelController @8 :AccelController;

  struct DynamicExperimentalControl {
    state @0 :DynamicExperimentalControlState;
    enabled @1 :Bool;
    active @2 :Bool;
    decelIntent @3 :Float32;
    curveDetected @4 :Bool;
    wantBlended @5 :Bool;
    leadVeto @6 :Bool;

    enum DynamicExperimentalControlState {
      acc @0;
      blended @1;
    }
  }

  struct SmartCruiseControl {
    vision @0 :Vision;
    map @1 :Map;

    struct Vision {
      state @0 :VisionState;
      vTarget @1 :Float32;
      aTarget @2 :Float32;
      currentLateralAccel @3 :Float32;
      maxPredictedLateralAccel @4 :Float32;
      enabled @5 :Bool;
      active @6 :Bool;
    }

    struct Map {
      state @0 :MapState;
      vTarget @1 :Float32;
      aTarget @2 :Float32;
      enabled @3 :Bool;
      active @4 :Bool;
    }

    enum VisionState {
      disabled @0; # System disabled or inactive.
      enabled @1; # No predicted substantial turn on vision range.
      entering @2; # A substantial turn is predicted ahead, adapting speed to turn comfort levels.
      turning @3; # Actively turning. Managing acceleration to provide a roll on turn feeling.
      leaving @4; # Road ahead straightens. Start to allow positive acceleration.
      overriding @5; # System overriding with manual control.
    }

    enum MapState {
      disabled @0; # System disabled or inactive.
      enabled @1; # No predicted substantial turn on map range.
      turning @2; # Actively turning. Managing acceleration to provide a roll on turn feeling.
      overriding @3; # System overriding with manual control.
    }
  }

  struct SpeedLimit {
    resolver @0 :Resolver;
    assist @1 :Assist;

    struct Resolver {
      speedLimit @0 :Float32;
      distToSpeedLimit @1 :Float32;
      source @2 :Source;
      speedLimitOffset @3 :Float32;
      speedLimitLast @4 :Float32;
      speedLimitFinal @5 :Float32;
      speedLimitFinalLast @6 :Float32;
      speedLimitValid @7 :Bool;
      speedLimitLastValid @8 :Bool;
    }

    struct Assist {
      state @0 :AssistState;
      enabled @1 :Bool;
      active @2 :Bool;
      vTarget @3 :Float32;
      aTarget @4 :Float32;
    }

    enum Source {
      none @0;
      car @1;
      map @2;
    }

    enum AssistState {
      disabled @0;
      inactive @1; # No speed limit set or not enabled by parameter.
      preActive @2;
      pending @3; # Awaiting new speed limit.
      adapting @4; # Reducing speed to match new speed limit.
      active @5; # Cruising at speed limit.
    }
  }

  enum LongitudinalPlanSource {
    cruise @0;
    sccVision @1;
    sccMap @2;
    speedLimitAssist @3;
    carrot @4;
  }

  struct TrafficLightState {
    lightState @0 :State;
    source @1 :Source;
    confidence @2 :Float32;
    distance @3 :Float32;

    enum State {
      unknown @0;
      red @1;
      green @2;
      redConfirmed @3;
      greenConfirmed @4;
    }

    enum Source {
      none @0;
      carrot @1;
      amap @2;
      vision @3;
      fused @4;
    }
  }

  struct CarrotPlan {
    xState @0 :Text;
    drivingMode @1 :Text;
    vTarget @2 :Float32;
    aTarget @3 :Float32;
    stopDist @4 :Float32;
    active @5 :Bool;
  }

  struct E2eAlerts {
    greenLightAlert @0 :Bool;
    leadDepartAlert @1 :Bool;
  }

  struct AccelController {
    enabled @0 :Bool;
    active @1 :Bool;
    profile @2 :Profile;
    enum Profile {
      eco @0;
      normal @1;
      sport @2;
    }
  }

  trafficLight @9 :TrafficLightState;
  carrot @10 :CarrotPlan;
}

struct OnroadEventSP @0xda96579883444c35 {
  events @0 :List(Event);

  struct Event {
    name @0 :EventName;

    # event types
    enable @1 :Bool;
    noEntry @2 :Bool;
    warning @3 :Bool;   # alerts presented only when  enabled or soft disabling
    userDisable @4 :Bool;
    softDisable @5 :Bool;
    immediateDisable @6 :Bool;
    preEnable @7 :Bool;
    permanent @8 :Bool; # alerts presented regardless of openpilot state
    overrideLateral @10 :Bool;
    overrideLongitudinal @9 :Bool;
  }

  enum EventName {
    lkasEnable @0;
    lkasDisable @1;
    manualSteeringRequired @2;
    manualLongitudinalRequired @3;
    silentLkasEnable @4;
    silentLkasDisable @5;
    silentBrakeHold @6;
    silentWrongGear @7;
    silentReverseGear @8;
    silentDoorOpen @9;
    silentSeatbeltNotLatched @10;
    silentParkBrake @11;
    controlsMismatchLateral @12;
    hyundaiRadarTracksConfirmed @13;
    experimentalModeSwitched @14;
    wrongCarModeAlertOnly @15;
    pedalPressedAlertOnly @16;
    laneTurnLeft @17;
    laneTurnRight @18;
    speedLimitPreActive @19;
    speedLimitActive @20;
    speedLimitChanged @21;
    speedLimitPending @22;
    e2eChime @23;
    laneChangeRoadEdge @24;
    bigModelReady @25;

    # carrot (phone projection & navigation)
    trafficSignGreen @26;
    trafficSignChanged @27;
    trafficStopping @28;
  }
}

struct CarParamsSP @0x80ae746ee2596b11 {
  flags @0 :UInt32;        # flags for car specific quirks in sunnypilot
  safetyParam @1 : Int16;  # flags for sunnypilot's custom safety flags
  pcmCruiseSpeed @3 :Bool;
  intelligentCruiseButtonManagementAvailable @4 :Bool;
  enableGasInterceptor @5 :Bool;

  neuralNetworkLateralControl @2 :NeuralNetworkLateralControl;

  struct NeuralNetworkLateralControl {
    model @0 :Model;
    fuzzyFingerprint @1 :Bool;

    struct Model {
      path @0 :Text;
      name @1 :Text;
    }
  }
}

struct CarControlSP @0xa5cd762cd951a455 {
  mads @0 :ModularAssistiveDrivingSystem;
  params @1 :List(Param);
  leadOne @2 :LeadData;
  leadTwo @3 :LeadData;
  intelligentCruiseButtonManagement @4 :IntelligentCruiseButtonManagement;

  struct Param {
    key @0 :Text;
    type @2 :ParamType;
    value @3 :Data;

    valueDEPRECATED @1 :Text; # The data type change may cause issues with backwards compatibility.
  }

  enum ParamType {
    string @0;
    bool @1;
    int @2;
    float @3;
    time @4;
    json @5;
    bytes @6;
  }
}

struct BackupManagerSP @0xf98d843bfd7004a3 {
  backupStatus @0 :Status;
  restoreStatus @1 :Status;
  backupProgress @2 :Float32;
  restoreProgress @3 :Float32;
  lastError @4 :Text;
  currentBackup @5 :BackupInfo;
  backupHistory @6 :List(BackupInfo);

  enum Status {
    idle @0;
    inProgress @1;
    completed @2;
    failed @3;
  }

  struct Version {
    major @0 :UInt16;
    minor @1 :UInt16;
    patch @2 :UInt16;
    build @3 :UInt16;
    branch @4 :Text;
  }

  struct MetadataEntry {
    key @0 :Text;
    value @1 :Text;
    tags @2 :List(Text);
  }

  struct BackupInfo {
    deviceId @0 :Text;
    version @1 :UInt32;
    config @2 :Text;
    isEncrypted @3 :Bool;
    createdAt @4 :Text;  # ISO timestamp
    updatedAt @5 :Text;  # ISO timestamp
    sunnypilotVersion @6 :Version;
    backupMetadata @7 :List(MetadataEntry);
  }
}

struct CarStateSP @0xb86e6369214c01c8 {
  speedLimit @0 :Float32;
  amapLineValid @1 :Bool;
  amapLeftLineType @2 :Int32;
  amapRightLineType @3 :Int32;
  amapLeftLineBlocked @4 :Bool;
  amapRightLineBlocked @5 :Bool;
}

struct LiveMapDataSP @0xf416ec09499d9d19 {
  speedLimitValid @0 :Bool;
  speedLimit @1 :Float32;
  speedLimitAheadValid @2 :Bool;
  speedLimitAhead @3 :Float32;
  speedLimitAheadDistance @4 :Float32;
  roadName @5 :Text;
  curveSpeedAheadValid @6 :Bool;
  curveSpeedAhead @7 :Float32;
  curveSpeedAheadDistance @8 :Float32;
  trafficLightAheadValid @9 :Bool;
  trafficLightAheadDistance @10 :Float32;
}

struct ModelDataV2SP @0xa1680744031fdb2d {
  laneTurnDirection @0 :TurnDirection;
  leftLaneChangeEdgeBlock @1 :Bool;
  rightLaneChangeEdgeBlock @2 :Bool;

  enum TurnDirection {
    none @0;
    turnLeft @1;
    turnRight @2;
  }
}

struct LongitudinalMpcTuningSP @0xcb9fd56c7057593a {
  comfortBrake @0 :Float32;
  stopDistance @1 :Float32;
  tFollowRelaxed @2 :Float32;
  tFollowStandard @3 :Float32;
  tFollowAggressive @4 :Float32;
  xEgoObstacleCost @5 :Float32;
  jEgoCost @6 :Float32;
  aChangeCost @7 :Float32;
  dangerZoneCost @8 :Float32;
  leadDangerFactor @9 :Float32;
}

struct AmapNaviSP @0xc2243c65e0340384 {
  leftBlind @0 :Int32;
  rightBlind @1 :Int32;
  lineValid @2 :Bool;
  leftLine @3 :Int32;
  rightLine @4 :Int32;
}

struct NavInstructionCarrotSP @0x9ccdc8676701b412 {
  maneuverPrimaryText @0 :Text;
  maneuverSecondaryText @1 :Text;
  maneuverDistance @2 :Float32;
  maneuverType @3 :Text;
  maneuverModifier @4 :Text;
  distanceRemaining @5 :Float32;
  timeRemaining @6 :Float32;
  timeRemainingTypical @7 :Float32;
  speedLimit @8 :Float32;
  allManeuvers @9 :List(Maneuver);

  struct Maneuver {
    distance @0 :Float32;
    type @1 :Text;
    modifier @2 :Text;
  }
}

struct CarrotManSP @0xcd96dafb67a082d0 {
  activeCarrot @0 :Int32;
  nRoadLimitSpeed @1 :Int32;
  remote @2 :Text;
  xSpdType @3 :Int32;
  xSpdLimit @4 :Int32;
  xSpdDist @5 :Int32;
  xSpdCountDown @6 :Int32;
  xTurnInfo @7 :Int32;
  xDistToTurn @8 :Int32;
  xTurnCountDown @9 :Int32;
  atcType @10 :Text;
  vTurnSpeed @11 :Int32;
  szPosRoadName @12 :Text;
  szTBTMainText @13 :Text;
  desiredSpeed @14 :Int32;
  desiredSource @15 :Text;
  carrotCmdIndex @16 :Int32;
  carrotCmd @17 :Text;
  carrotArg @18 :Text;
  xPosLat @19 :Float32;
  xPosLon @20 :Float32;
  xPosAngle @21 :Float32;
  xPosSpeed @22 :Float32;
  trafficState @23 :Int32;
  nGoPosDist @24 :Int32;
  nGoPosTime @25 :Int32;
  szSdiDescr @26 :Text;
  naviPaths @27 :Text;
  leftSec @28 :Int32;
  xDistToTurnNav @29 :Int32;
  xDistToTurnNavLast @30 :Int32;
  xDistToTurnMax @31 :Int32;
  xDistToTurnMaxCnt @32 :Int32;
  xLeftTurnSec @33 :Int32;
  roadCate @34 :Int32;
  extBlinker @35 :Int32;
  extState @36 :Int32;
  leftBlind @37 :Int32;
  rightBlind @38 :Int32;
  trafficCountdown @39 :Int32;
  szGoalName @40 :Text;
  szTBTMainTextNext @41 :Text;
  szNearDirName @42 :Text;
  nSdiSection @43 :Int32 = -1;
  gpsSpeed @44 :Float32 = 0.0;
  epochTime @45 :Int64 = 0;
  timezone @46 :Text = "Asia/Seoul";
  nTBTNextRoadWidth @47 :Int32 = 0;
}

struct ImuCalibrationSP @0xb057204d7deadf3f {
  status @0 :Status;
  progress @1 :Int8;
  error @2 :Error;
  rpyCalib @3 :List(Float32);
  imuCalibMatrix @4 :List(Float32);
  yawStd @5 :Float32;
  validRatio @6 :Float32;

  enum Status {
    idle @0;
    staticCollecting @1;
    dynamicCollecting @2;
    computing @3;
    completed @4;
    failed @5;
    cancelled @6;
  }

  enum Error {
    none @0;
    notStationary @1;
    slopeTooSteep @2;
    notEnoughStaticSamples @3;
    noStraightRoad @4;
    timeout @5;
    cameraOdometryUnreliable @6;
    computationFailed @7;
    matrixInvalid @8;
  }
}

struct CarrotNaviStateSP @0xbd443b539493bc68 {
  schemaVersion @0 :UInt16;
  generation @1 :UInt64;
  sessionId @2 :Text;
  publishMonoTimeNanos @3 :UInt64;
  connected @4 :Bool;
  vehicle @5 :Vehicle;
  guidanceCurrent @6 :Guidance;
  guidanceNext @7 :Guidance;
  laneCurrent @8 :Lane;
  laneAhead @9 :List(Lane);
  speed @10 :Speed;
  trafficSignal @11 :TrafficSignal;
  crossroad @12 :Crossroad;
  route @13 :Route;
  navigationStatus @14 :NavigationStatus;

  struct ItemMeta {
    present @0 :Bool;
    sequence @1 :UInt64;
    sourceTimestampMillis @2 :UInt64;
    receivedMonoTimeNanos @3 :UInt64;
  }

  struct Vehicle {
    meta @0 :ItemMeta;
    latitude @1 :Float64;
    longitude @2 :Float64;
    headingDeg @3 :Float32;
    speedKph @4 :Float32;
    roadName @5 :Text;
    virtualGps @6 :Bool;
  }

  struct Guidance {
    meta @0 :ItemMeta;
    distanceM @1 :Int32;
    timeSec @2 :Int32;
    turnType @3 :Int32;
    roadName @4 :Text;
    mainText @5 :Text;
    nearDirection @6 :Text;
    midDirection @7 :Text;
    farDirection @8 :Text;
    pointValid @9 :Bool;
    latitude @10 :Float64;
    longitude @11 :Float64;
  }

  struct Lane {
    meta @0 :ItemMeta;
    count @1 :Int16;
    distanceM @2 :Int32;
    visible @3 :Bool;
    lanePlay @4 :Bool;
    currentLane @5 :Int16;
    turnCode @6 :Int32;
    turnInfo @7 :List(Int16);
    etcInfo @8 :List(Int16);
    available @9 :List(Int16);
    guideLineColor @10 :Int16;
    roadCategory @11 :Int16;
    voiceCode @12 :Int16;
  }

  struct Speed {
    meta @0 :ItemMeta;
    currentKph @1 :Float32;
    roadLimitValid @2 :Bool;
    roadLimitKph @3 :Int16;
    sdiPresent @4 :Bool;
    sdiType @5 :Int32;
    sdiDistanceM @6 :Int32;
    sdiSpeedLimitKph @7 :Int16;
    sectionPresent @8 :Bool;
    sectionActive @9 :Bool;
    sectionSpeedLimitKph @10 :Int16;
    sectionAverageKph @11 :Float32;
    sectionOverallAverageKph @12 :Float32;
    sectionRemainingDistanceM @13 :Float32;
    sectionRemainingTimeSec @14 :Int32;
    sectionProgress @15 :Float32;
    sectionSuspended @16 :Bool;
    sectionOffRoute @17 :Bool;
    sdiSectionType @18 :Int32;
    sdiBlockType @19 :Int32;
    sdiBlockSpeedKph @20 :Int16;
    sdiBlockDistanceM @21 :Int32;
    secondarySdiPresent @22 :Bool;
    secondarySdiType @23 :Int32;
    secondarySdiDistanceM @24 :Int32;
    secondarySdiSpeedLimitKph @25 :Int16;
    secondarySdiSectionType @26 :Int32;
    secondarySdiBlockType @27 :Int32;
    secondarySdiBlockSpeedKph @28 :Int16;
    secondarySdiBlockDistanceM @29 :Int32;
  }

  struct TrafficSignal {
    meta @0 :ItemMeta;
    visible @1 :Bool;
    distanceM @2 :Int32;
    source @3 :Text;
    redValid @4 :Bool;
    redOn @5 :Bool;
    redRemainSec @6 :Int16;
    leftValid @7 :Bool;
    leftOn @8 :Bool;
    leftRemainSec @9 :Int16;
    greenValid @10 :Bool;
    greenOn @11 :Bool;
    greenRemainSec @12 :Int16;
    rightValid @13 :Bool;
    rightOn @14 :Bool;
    rightRemainSec @15 :Int16;
    uturnValid @16 :Bool;
    uturnOn @17 :Bool;
    uturnRemainSec @18 :Int16;
    uiCounterValid @19 :Bool;
    uiCounterRemainSec @20 :Int16;
  }

  struct Crossroad {
    meta @0 :ItemMeta;
    visible @1 :Bool;
    distanceM @2 :Int32;
    imageCode @3 :Int32;
    imageUrl @4 :Text;
  }

  struct Coordinate {
    latitude @0 :Float64;
    longitude @1 :Float64;
  }

  struct Route {
    meta @0 :ItemMeta;
    remainingDistanceM @1 :Int32;
    remainingTimeSec @2 :Int32;
    movedDistanceM @3 :Int32;
    movedTimeSec @4 :Int32;
    totalDistanceM @5 :Int32;
    polyline @6 :List(Coordinate);
  }

  struct NavigationStatus {
    meta @0 :ItemMeta;
    mode @1 :Text;
    guidanceActive @2 :Bool;
    offRoute @3 :Bool;
    routePresent @4 :Bool;
  }
}

struct CarrotNaviMediaSP @0xfc6241ed8877b611 {
  schemaVersion @0 :UInt16;
  sessionId @1 :Text;
  kind @2 :Text;
  name @3 :Text;
  sequence @4 :UInt64;
  sourceTimestampMillis @5 :UInt64;
  receivedMonoTimeNanos @6 :UInt64;
  present @7 :Bool;
  messageType @8 :UInt8;
  formatOrReason @9 :UInt8;
  flags @10 :UInt16;
  width @11 :UInt16;
  height @12 :UInt16;
  reason @13 :Text;
  payload @14 :Data;
}

struct CustomReserved17 @0xa30662f84033036c {
}

struct CustomReserved18 @0xc86a3d38d13eb3ef {
}

struct CustomReserved19 @0xa4f1eb3323f5f582 {
}
