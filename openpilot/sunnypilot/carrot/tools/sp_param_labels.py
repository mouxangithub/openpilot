#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Labels for the settings this fork adds to the 7000 catalog.

CarrotPilot's catalog carries four label slots per param and three per menu node:
`title/descr` are Korean, `etitle/edescr` English, `ctitle/cdescr` Chinese, and menu
nodes hold `ko/en/zh` directly. This fork's added params (the `carrot/config.py` surface
plus the on-device settings pages) have no upstream labels, so this module is the single
source for them - the generator consumes it, never the JSON by hand.

Descriptions follow what the code actually does with each key (`carrot_serv.py`,
`sunnypilot` lateral/longitudinal), not what the name suggests.
"""

# ---------------------------------------------------------------------------
# fork-only params: name -> (en_title, en_descr, zh_title, zh_descr)
# The ko slot keeps the humanized key name from the generator.
# ---------------------------------------------------------------------------

PARAM_LABELS: dict[str, tuple[str, str, str, str]] = {
  # ---- carrot fork surface: AUTO_FORK family ------------------------------
  # NOTE on the two curve-speed families. These names come from CarrotPilot, and the two
  # families are consumed by DIFFERENT controllers with OPPOSITE polarity:
  #   * Factor            -> the Carrot envelope (carrot_functions.carrot_curve_speed_params
  #                          -> curve_speed.py). There `lateral_budget = TARGET_LAT_ACCEL /
  #                          sensitivity`, so a HIGHER factor means a LOWER speed budget and
  #                          a SLOWER curve. Upstream's own Factor labels say exactly this;
  #                          they already live in carrot_settings.json, so only the H
  #                          variant is added here for consistency.
  #   * Aggressiveness    -> SmartCruiseControlVision (vision_controller._load_curve_tuning),
  #                          where `th_scale = 1 / aggressiveness`: a LOWER value arms the
  #                          turn cycle on gentler curves, i.e. slows earlier.
  # The labels below follow the code, not the CarrotPilot name.
  "AutoCurveSpeedAggressiveness": ("Curve speed aggression (SCC-V)", "Smart Cruise Control Vision only: how early it reacts to a curve on ordinary roads. Lower slows earlier for gentler curves; 100 = neutral.", "弯道减速积极度（SCC-V）", "仅作用于视觉智能巡航（SCC-V）：普通道路上的弯道反应早晚。数值越低，越早对缓弯减速；100 为中性。"),
  "AutoCurveSpeedAggressivenessH": ("Curve speed aggression (SCC-V, highway)", "Highway variant of the SCC-V curve reaction threshold. Lower slows earlier; 100 = neutral.", "弯道减速积极度（SCC-V，高速）", "SCC-V 弯道反应阈值的高速档。数值越低减速越早；100 为中性。"),
  "AutoCurveSpeedFactor": ("Curve speed factor", "Higher values lower the lateral-acceleration budget and the curve target speed, so the car slows more. Slowing starts according to the distance to the curve; 100 = Carrot default.", "弯道速度系数", "数值越高，允许的横向加速度和弯道目标速度越低，减速越明显。根据距弯道的距离提前减速；100 为 Carrot 默认值。"),
  "AutoCurveSpeedFactorH": ("Curve speed factor (highway)", "Highway variant of the Carrot curve-speed factor. Higher lowers the curve target speed (slower); 100 = Carrot default.", "弯道速度系数（高速）", "Carrot 弯道速度系数的高速档。数值越高弯道目标速度越低（更慢）；100 为 Carrot 默认值。"),
  "AutoDoForkBlinkerDist": ("Fork auto-blinker distance", "Distance before a fork at which the auto turn signal fires.", "岔路自动转向灯距离", "到达岔路前多远自动打转向灯。"),
  "AutoDoForkBlinkerDistH": ("Fork auto-blinker distance (highway)", "Highway variant of the fork auto-blinker distance.", "岔路自动转向灯距离（高速）", "高速公路岔路自动转向灯的触发距离。"),
  "AutoDoForkDecalDist": ("Fork decal braking distance", "Distance before deceleration markings (decal) where fork braking begins.", "岔路导流线减速距离", "距导流线（减速标线）多远开始岔路制动。"),
  "AutoDoForkDecalDistH": ("Fork decal braking distance (highway)", "Highway variant of the decal braking distance.", "岔路导流线减速距离（高速）", "高速公路导流线制动的触发距离。"),
  "AutoDoForkNavDist": ("Fork nav action distance", "Distance before a navigation fork at which fork handling engages.", "导航岔路动作距离", "距导航岔路（出口）多远开始执行岔路动作。"),
  "AutoDoForkNavDistH": ("Fork nav action distance (highway)", "Highway variant of the nav fork action distance.", "导航岔路动作距离（高速）", "高速公路导航岔路的动作距离。"),
  "AutoForkDecalRate": ("Fork decal braking rate", "Braking strength while crossing deceleration markings (percent).", "导流线减速强度", "通过导流线时的制动强度（百分比）。"),
  "AutoForkDecalRateH": ("Fork decal braking rate (highway)", "Highway variant of the decal braking rate.", "导流线减速强度（高速）", "高速公路导流线减速强度。"),
  "AutoForkDistOffset": ("Fork action distance offset", "Extra distance added to every fork action trigger.", "岔路动作距离偏移", "所有岔路动作触发距离上的附加偏移。"),
  "AutoForkDistOffsetH": ("Fork action distance offset (highway)", "Highway variant of the fork distance offset.", "岔路动作距离偏移（高速）", "高速公路岔路动作距离偏移。"),
  "AutoForkSpeedMin": ("Fork minimum speed", "Fork handling will not brake below this speed (km/h).", "岔路减速最低速度", "岔路制动不会降到该速度以下（km/h）。"),
  "AutoForkSpeedMinH": ("Fork minimum speed (highway)", "Highway variant of the fork minimum speed.", "岔路减速最低速度（高速）", "高速公路岔路减速下限（km/h）。"),
  "AutoKeepForkSpeed": ("Keep fork speed time", "Seconds the fork speed target is held after the fork.", "岔路后保持车速时间", "通过岔路后保持岔路目标速度的秒数。"),
  "AutoKeepForkSpeedH": ("Keep fork speed time (highway)", "Highway variant of the keep-fork-speed time.", "岔路后保持车速时间（高速）", "高速公路岔路后保持车速的秒数。"),
  "AutoTurnDistOffset": ("Auto turn distance offset", "Distance offset for auto-turn (intersection) triggers.", "自动转向距离偏移", "自动转向（路口）触发距离的偏移。"),
  "AutoTurnInNotRoadEdge": ("Auto turn without road edge", "Allow auto-turn triggers when the map has no road-edge data (0 = off).", "无路缘自动转向", "地图缺少路缘数据时也允许自动转向（0 = 关）。"),
  "AutoUpHighwayRoadLimit": ("Highway low-limit boost", "Boost highway speed limits below 60 km/h toward 60 (0 = off).", "高速限速上调开关", "高速上低于 60 km/h 的限速自动上调（0 = 关）。"),
  "AutoUpHighwayRoadLimit40KMH": ("Highway low-limit boost amount", "Boost amount (km/h) applied to highway limits at or below 40 km/h.", "高速限速上调幅度", "高速 ≤40 km/h 限速的上调幅度（km/h）。"),
  "AutoUpRoadLimit": ("Road low-limit boost", "Boost ordinary-road speed limits below 60 km/h toward 60 (0 = off).", "道路限速上调开关", "普通道路低于 60 km/h 的限速自动上调（0 = 关）。"),
  "AutoUpRoadLimit40KMH": ("Road low-limit boost amount", "Boost amount (km/h) applied to ordinary-road limits at or below 40 km/h.", "道路限速上调幅度", "普通道路 ≤40 km/h 限速的上调幅度（km/h）。"),

  # ---- carrot fork surface: LATERAL ---------------------------------------
  "BsdDelayTime": ("BSD alert delay", "Delay before the front blind-spot warning fires (ms).", "盲点报警延迟", "前向盲点报警的触发延迟（毫秒）。"),

  # ---- carrot fork surface: MISC ------------------------------------------
  "CarrotException": ("Exception report buffer", "Last exception captured by the carrot services (read-only).", "异常上报缓存", "carrot 服务最近捕获的异常信息（只读）。"),
  "CarrotNaviHudMapProfile": ("Navi HUD map profile", "Map rendering profile for the navigation HUD.", "导航 HUD 地图风格", "导航 HUD 的地图渲染风格。"),
  "CarrotYouTubeLive": ("YouTube live source", "Offline-screen YouTube live stream selection (0 = off).", "YouTube 直播源", "熄屏播放的 YouTube 直播流选择（0 = 关）。"),
  "CarrotYouTubeQuality": ("YouTube quality", "Preferred YouTube stream quality.", "YouTube 画质", "YouTube 播放的画质档位。"),
  "CarrotYouTubeTimestamp": ("YouTube timestamp", "Show the stream timestamp overlay.", "YouTube 时间戳", "显示 YouTube 播放时间戳悬浮层。"),
  "ClusterHudCoreMode": ("Cluster HUD core mode", "CPU core affinity mode for the cluster HUD renderer.", "仪表 HUD 核心模式", "仪表 HUD 渲染的 CPU 核心绑定模式。"),
  "ClusterHudLiveFps": ("Cluster HUD live FPS", "Frame rate mode of the cluster HUD while onroad.", "仪表 HUD 实时帧率", "行车中仪表 HUD 的帧率档位。"),
  "ClusterHudPriority": ("Cluster HUD priority", "Scheduling priority of the cluster HUD thread.", "仪表 HUD 优先级", "仪表 HUD 线程的调度优先级。"),
  "ContinuousLaneChange": ("Continuous lane change", "Allow one blinker gesture to chain multiple lane changes.", "连续变道", "允许一次转向灯手势连续完成多次变道。"),
  "DisableBlindSpot": ("Disable blind spot", "Disable the blind-spot monitor entirely.", "禁用盲点监测", "完全关闭盲点监测功能。"),
  "DynamicBlindDistance": ("Dynamic blind distance", "Scale blind-spot warning distance with speed.", "动态盲区距离", "盲区报警距离随车速动态调整。"),
  "DynamicBlindRange": ("Dynamic blind range", "Extended detection range used by the dynamic blind distance.", "动态盲区范围", "动态盲区使用的扩展探测范围。"),
  "EnableSpeedTF": ("Enable speed T-follow", "Use the speed-dependent following-distance table.", "启用速度跟随时距", "启用随速度变化的跟车时距表。"),
  "NewLaneWidthDiff": ("Lane width difference", "Lane-width delta threshold used by lane keeping.", "车道宽度差异阈值", "车道保持所用车道宽度差的判定阈值。"),
  "SameSpiCamFilter": ("Same-source wide-cam filter", "Ignore wide-camera detections that duplicate the main camera.", "同源广角相机过滤", "过滤与主相机重复的广角相机检测。"),
  "SideBsdDelayTime": ("Side BSD delay", "Delay before the side blind-spot warning fires (ms).", "侧向盲点延迟", "侧向盲点报警的触发延迟（毫秒）。"),
  "SideRadarMinDist": ("Side radar minimum distance", "Ignore side-radar returns closer than this (m).", "侧向雷达最小距离", "忽略近于该值的侧向雷达回波（米）。"),
  "SideRelDistTime": ("Side relative distance time", "Time window for the side relative-distance warning.", "侧向相对距离时间", "侧向相对距离报警的时间窗。"),
  "SidevRelDistTime": ("Side relative distance time (v)", "Speed-scaled variant of the side relative-distance window.", "侧向相对距离时间（速度档）", "侧向相对距离报警随速度分档的时间窗。"),
  "StockBlinkerCtrl": ("Stock blinker control", "Let the stock car body controller own the turn signals.", "原厂转向灯控制", "转向灯交由原厂车身控制器管理。"),

  # ---- carrot fork surface: SPEED -----------------------------------------
  "RoadType": ("Road type", "Manual road-category override for speed logic (-1 = auto).", "道路类型", "速度逻辑的道路类型手动指定（-1 = 自动）。"),

  # ---- carrot fork surface: DISPLAY ---------------------------------------
  "ShowDebugLog": ("Show debug log", "Show the carrot debug log on the onroad UI (0 = off).", "显示调试日志", "在行车界面显示 carrot 调试日志（0 = 关）。"),

  # ---- on-device pages: alpha_longitudinal_toggles ------------------------
  "AlphaLongitudinalEnabled": ("Alpha longitudinal", "End-to-end longitudinal control for supported vehicles.", "Alpha 纵向控制", "受支持车型启用端到端纵向控制。"),
  "DynamicExperimentalControl": ("Dynamic experimental control", "Switch between calm and experimental profiles from live driving behavior.", "动态实验模式", "根据实时驾驶表现自动切换 静音/实验 模式。"),
  "ExperimentalMode": ("Experimental mode", "Enable the experimental (end-to-end) driving profile.", "实验模式", "启用实验（端到端）驾驶模式。"),
  "ExperimentalModeConfirmed": ("Experimental mode confirmed", "Set once the experimental-mode risk notice has been acknowledged.", "实验模式已确认", "实验模式风险提示已确认过的标记。"),
  "ExperimentalModeLeadGap": ("Experimental mode lead gap", "Activate experimental mode when following closely.", "实验模式跟车条件", "近距跟车时自动进入实验模式。"),
  "ExperimentalModeSetSpeed": ("Experimental mode set speed", "Activate experimental mode below a set speed.", "实验模式速度条件", "低于设定速度时自动进入实验模式。"),

  # ---- on-device pages: carrot_tuning -------------------------------------
  "CarrotWebEnabled": ("Carrot web panel", "Serve the 7000 web panel.", "Carrot Web 面板", "启用 7000 端口的 Web 设置面板。"),

  # ---- on-device pages: cruise --------------------------------------------
  "CustomAccIncrementsEnabled": ("Custom ACC increments", "Use custom short/long-press speed steps instead of the stock ones.", "自定义 ACC 增量", "用自定义的短按/长按速度步进替代原厂步进。"),
  "CustomAccLongPressIncrement": ("ACC long-press increment", "Speed step applied by a long ACC press (km/h).", "ACC 长按增量", "ACC 长按一次变化的速度（km/h）。"),
  "CustomAccShortPressIncrement": ("ACC short-press increment", "Speed step applied by a short ACC press (km/h).", "ACC 短按增量", "ACC 短按一次变化的速度（km/h）。"),
  "IntelligentCruiseButtonManagement": ("Intelligent cruise button management", "Synthesize stock ACC button presses to reach the desired set speed (ICBM).", "智能巡航按键管理", "自动模拟原厂 ACC 按键将设定速度调到目标值（ICBM）。"),
  "LongitudinalMpcTuningAChangeCost": ("MPC accel-change cost", "Longitudinal MPC cost on changing acceleration.", "MPC 加速度变化代价", "纵向 MPC 对加速度变化的惩罚权重。"),
  "LongitudinalMpcTuningComfortBrake": ("MPC comfort brake", "Braking deceleration treated as comfort limit (m/s²).", "MPC 舒适制动减速度", "MPC 视为舒适上限的制动减速度（m/s²）。"),
  "LongitudinalMpcTuningDangerZoneCost": ("MPC danger zone cost", "MPC cost inside the danger zone around the lead.", "MPC 危险区代价", "纵向 MPC 对前车危险区内的惩罚权重。"),
  "LongitudinalMpcTuningJEgoCost": ("MPC jerk cost", "MPC cost on jerk (rate of acceleration change).", "MPC 加加速度代价", "纵向 MPC 对加加速度的惩罚权重。"),
  "LongitudinalMpcTuningLeadDangerFactor": ("MPC lead danger factor", "How strongly the lead's danger zone shapes the plan.", "MPC 前车危险系数", "前车危险区对规划的影响强度。"),
  "LongitudinalMpcTuningStopDistance": ("MPC stop distance", "Distance kept when stopping behind a lead (m).", "MPC 停车距离", "跟停时与前车保持的距离（米）。"),
  "LongitudinalMpcTuningTFollowAggressive": ("Following gap - aggressive", "Time-headway used by the aggressive profile (s).", "跟车时距 - 激进", "激进档使用的跟车时距（秒）。"),
  "LongitudinalMpcTuningTFollowRelaxed": ("Following gap - relaxed", "Time-headway used by the relaxed profile (s).", "跟车时距 - 宽松", "宽松档使用的跟车时距（秒）。"),
  "LongitudinalMpcTuningTFollowStandard": ("Following gap - standard", "Time-headway used by the standard profile (s).", "跟车时距 - 标准", "标准档使用的跟车时距（秒）。"),
  "LongitudinalMpcTuningXEgoObstacleCost": ("MPC ego-obstacle cost", "MPC cost between ego and the obstacle reference.", "MPC 自车-障碍物代价", "纵向 MPC 对自车贴近障碍物的惩罚权重。"),
  "SmartCruiseControlMap": ("Smart cruise control (map)", "Use map data (limits and curvature) to shape the cruise target.", "地图智能巡航", "结合地图限速与曲率修正巡航目标（SCC-M）。"),
  "SmartCruiseControlVision": ("Smart cruise control (vision)", "Use vision curvature to slow before curves (SCC-V).", "视觉智能巡航", "利用视觉曲率在弯道前自动减速（SCC-V）。"),
  "SpeedLimitMode": ("Speed limit mode", "What to do at a limit: display only, ask, or apply.", "限速模式", "遇到限速时的动作：仅显示 / 询问 / 自动调整。"),
  "SpeedLimitOffsetType": ("Speed limit offset type", "Offset is a percentage or a fixed value.", "限速偏移类型", "限速偏移按百分比还是固定值。"),
  "SpeedLimitPolicy": ("Speed limit source policy", "Which speed-limit sources are trusted and how they combine.", "限速数据源策略", "限速来源（车辆/地图）的取舍与合并策略。"),
  "SpeedLimitValueOffset": ("Speed limit offset", "Offset applied to detected speed limits.", "限速偏移值", "在识别到的限速上叠加的偏移量。"),

  # ---- on-device pages: developer / software ------------------------------
  "DisableUpdates": ("Disable updates", "Block the updater from fetching new builds.", "禁用更新", "禁止更新器拉取新版本。"),
  "DoReboot": ("Reboot device", "Reboot the comma device (action).", "重启设备", "重启设备（执行动作）。"),
  "EnableCopyparty": ("Enable copyparty", "Run the copyparty file server.", "启用 Copyparty", "运行 copyparty 文件服务。"),
  "EnableGithubRunner": ("Enable GitHub runner", "Upload dashcam clips to the GitHub runner pipeline.", "启用 GitHub Runner", "将行车记录片段上传到 GitHub Runner 流水线。"),
  "IsDevelopmentBranch": ("Development branch", "This build tracks a development branch (read-only).", "开发分支", "当前构建为开发分支（只读）。"),
  "IsReleaseSpBranch": ("Release branch", "This build tracks a release branch (read-only).", "发布分支", "当前构建为发布分支（只读）。"),
  "IsTestedBranch": ("Tested branch", "This build tracks the tested branch (read-only).", "已测试分支", "当前构建为已测试分支（只读）。"),
  "QuickBootToggle": ("Quick boot", "Skip some offroad initialization for a faster boot.", "快速启动", "跳过部分离路初始化以加快开机。"),
  "ShowAdvancedControls": ("Show advanced controls", "Reveal advanced controls across the settings UI.", "显示高级控件", "在设置界面中显示高级控件。"),

  # ---- on-device pages: device --------------------------------------------
  "DeviceBootMode": ("Boot mode", "What the device does at power on.", "开机模式", "设备上电后的启动行为。"),
  "DongleId": ("Dongle ID", "Device identifier used by the services (read-only).", "设备 ID", "服务使用的设备标识（只读）。"),
  "HardwareSerial": ("Hardware serial", "Factory serial number (read-only).", "硬件序列号", "出厂序列号（只读）。"),
  "IsOnroadPreview": ("Onroad preview", "Render the onroad UI while offroad.", "行车界面预览", "离路时渲染行车界面用于预览。"),
  "MaxTimeOffroad": ("Max time offroad", "Seconds offroad before the device suspends.", "离线休眠时限", "离路多少秒后设备休眠。"),
  "OffroadMode": ("Offroad mode", "Force the device to stay offroad (screen off, no onroad).", "离路模式", "强制设备保持离路（熄屏、不进入行车）。"),
  "OnroadUploads": ("Onroad uploads", "Allow uploads while driving.", "行车中上传", "允许在行车过程中上传数据。"),
  "QuietMode": ("Quiet mode", "Silence prompts and alerts.", "静音模式", "静音提示与警告。"),

  # ---- on-device pages: display -------------------------------------------
  "Brightness": ("Brightness", "Screen brightness (0 = auto).", "屏幕亮度", "屏幕亮度（0 = 自动）。"),
  "HideFirehosePrompt": ("Hide firehose prompt", "Hide the training-data collection prompt.", "隐藏数据采集提示", "隐藏数据采集（firehose）提示。"),
  "InteractivityTimeout": ("Interactivity timeout", "Seconds of inactivity before controls lock.", "交互超时", "多少秒无操作后锁定交互（0 = 不锁）。"),
  "OnroadScreenOffBrightness": ("Onroad screen-off brightness", "Brightness while the screen is dimmed onroad.", "行车熄屏亮度", "行车中屏幕熄灭时的背光亮度。"),
  "OnroadScreenOffTimer": ("Onroad screen-off timer", "Seconds onroad before the screen turns off.", "行车熄屏计时", "行车中多少秒后熄屏。"),
  "ScreenSaverEnabled": ("Screen saver", "Enable the offroad screen saver.", "屏保开关", "离路时启用屏保。"),
  "ScreenSaverTimeout": ("Screen saver timeout", "Seconds offroad before the screen saver starts.", "屏保超时", "离路多少秒后启动屏保。"),

  # ---- on-device pages: models --------------------------------------------
  "CameraOffset": ("Camera offset", "Lateral offset applied to the model's lane center.", "相机偏移", "对模型车道中心施加的横向偏移。"),
  "LagdToggle": ("LaGD", "Enable the lane-line guided decoder model output.", "LaGD 开关", "启用车道线引导解码（LaGD）的模型输出。"),
  "LagdToggleDelay": ("LaGD delay", "Blend time when switching into the LaGD output (s).", "LaGD 延迟", "切入 LaGD 输出时的混合过渡时间（秒）。"),
  "LaneTurnDesire": ("Lane turn desire", "Let the model's turn desire steer through wide lanes.", "车道转弯意图", "允许模型转弯意图在大宽度车道内转向。"),
  "LaneTurnValue": ("Lane turn threshold", "Desire threshold above which lane-turn steering engages.", "车道转弯阈值", "触发车道转弯转向的意图阈值。"),
  "ModelManager_ClearCache": ("Clear model cache", "Delete downloaded model artifacts (action).", "清除模型缓存", "删除已下载的模型文件（执行动作）。"),
  "ModelManager_DownloadRef": ("Model download reference", "Favorite/download reference used by the model manager.", "模型下载引用", "模型管理器使用的收藏/下载引用。"),
  "ModelManager_Favs": ("Model favorites", "Saved favorite models (read-only).", "模型收藏", "已收藏的模型列表（只读）。"),

  # ---- on-device pages: navigation ----------------------------------------
  "CarrotAtcBlinkerEnabled": ("Navi ATC blinker", "Fire the turn signal from navigation turn commands (ATC).", "导航 ATC 转向灯", "由导航转向指令自动打转向灯（ATC）。"),
  "CarrotAmapBlindSpotEnabled": ("Amap blind-spot data", "Use Amap lane-level data for blind-spot checks.", "高德盲区数据", "使用高德车道级数据辅助盲区判断。"),
  "CarrotEnabled": ("Carrot navi link", "Enable the Carrot navigation link service.", "Carrot 导航联动", "启用 Carrot 导航联动服务。"),
  "CarrotNavCruiseSpeedEnabled": ("Navi cruise speed link", "Let navigation set the cruise target speed.", "导航联动巡航速度", "允许导航修改巡航目标速度。"),
  "CarrotNaviDebug": ("Navi debug state", "Navigation debug state for the UI viewer (read-only).", "导航调试状态", "导航调试状态（UI 查看用，只读）。"),
  "CarrotNaviV2Enabled": ("Carrot navi V2", "Enable the 7714 navigation V2 channel.", "Carrot 导航 V2", "启用 7714 导航 V2 通道。"),
  "OsmMapDataEnabled": ("OSM map data", "Feed OSM map data to mapd.", "OSM 地图数据", "向 mapd 提供 OSM 地图数据。"),

  # ---- on-device pages: osm (mostly read-only state) ----------------------
  "Mapd_ClearCache": ("Clear mapd cache", "Drop mapd's compiled map cache (action).", "清除 mapd 缓存", "清空 mapd 编译缓存（执行动作）。"),
  "MapdVersion": ("mapd version", "Version of the installed map daemon (read-only).", "mapd 版本", "已安装地图守护进程版本（只读）。"),
  "OSMDownloadBounds": ("OSM download bounds", "Bounding box of the current map download (read-only).", "地图下载范围", "当前地图下载的边界范围（只读）。"),
  "OSMDownloadLocations": ("OSM download locations", "Region list of the current download (read-only).", "地图下载区域", "当前下载的区域列表（只读）。"),
  "OSMDownloadProgress": ("OSM download progress", "Progress of the running map download (read-only).", "地图下载进度", "正在进行的地图下载进度（只读）。"),
  "OsmDbUpdatesCheck": ("Check map DB updates", "Check for map database updates.", "检查地图库更新", "检查地图数据库是否有更新。"),
  "OsmDownloadedDate": ("Map downloaded date", "When the current map set was downloaded (read-only).", "地图下载日期", "当前地图的下载时间（只读）。"),
  "OsmLocal": ("Use local maps", "Use locally sideloaded map files instead of downloading.", "使用本地地图", "使用本地导入的地图文件而非在线下载。"),
  "OsmLocationName": ("Current location name", "Resolved location name from the map (read-only).", "当前位置名称", "地图解析出的当前位置名（只读）。"),
  "OsmLocationTitle": ("Current location title", "Display title of the current location (read-only).", "当前位置标题", "当前位置的显示标题（只读）。"),
  "OsmStateName": ("Region filter", "Country/state filter for map downloads.", "国家/省份筛选", "地图下载的国家/省份筛选。"),
  "OsmStateTitle": ("Region title", "Display title of the selected region (read-only).", "区域标题", "所选区域的显示标题（只读）。"),

  # ---- on-device pages: steering ------------------------------------------
  "AutoLaneChangeBsmDelay": ("Auto lane change wait for BSM", "Hold the lane change until blind-spot monitoring clears it.", "自动变道等待盲点", "盲点监测未报警时才执行自动变道。"),
  "AutoLaneChangeTimer": ("Auto lane change timer", "Delay before an auto lane change completes (0 = stock timing).", "自动变道计时", "自动变道完成的延迟（0 = 原厂时序）。"),
  "BlinkerLateralReengageDelay": ("Blinker re-engage delay", "Delay after a blinker before lateral control re-engages.", "转向灯后重新接管延时", "转向灯结束后横向控制重新接管的延迟。"),
  "BlinkerMinLateralControlSpeed": ("Blinker pause min speed", "Below this speed a blinker does not pause lateral control.", "转向灯暂停最低速度", "低于该速度时转向灯不再暂停横向控制。"),
  "BlinkerPauseLateralControl": ("Blinker pauses lateral", "Whether a blinker pauses lateral control.", "转向灯暂停横向控制", "打转向灯时是否暂停横向控制。"),
  "CarPlatformBundle": ("Car platform bundle", "Active vehicle platform bundle (read-only).", "车型平台绑定包", "当前生效的车型平台绑定包（只读）。"),
  "CustomTorqueParams": ("Custom torque params", "Use hand-set torque params instead of learned ones.", "自定义扭矩参数", "使用手动设置的扭矩参数而非学习值。"),
  "EnforceTorqueControl": ("Enforce torque control", "Force torque-based lateral on cars without stock support.", "强制扭矩控制", "在原厂不支持的车上强制使用扭矩横向控制。"),
  "LateralJerkTorqueController": ("Lateral jerk torque controller", "Limit lateral jerk in the torque controller.", "横向加加速度控制器", "扭矩控制器中限制横向加加速度。"),
  "LiveTorqueParamsRelaxedToggle": ("Live torque (relaxed)", "Use the relaxed tolerance variant of live torque learning.", "实时扭矩宽松模式", "实时扭矩学习使用宽松容差。"),
  "LiveTorqueParamsToggle": ("Live torque params", "Learn lateral torque params live from steering data.", "实时扭矩参数学习", "从转向数据实时学习横向扭矩参数。"),
  "Mads": ("MADS", "Modded ACC/Steering: independent steering engagement.", "MADS 开关", "改装巡航/转向（MADS）：转向独立接管。"),
  "MadsMainCruiseAllowed": ("MADS main cruise allowed", "Allow MADS to manage the main cruise button.", "MADS 主巡航允许", "允许 MADS 接管主巡航按键。"),
  "MadsSteeringMode": ("MADS steering mode", "Steering engagement mode used by MADS.", "MADS 转向模式", "MADS 使用的转向接管模式。"),
  "MadsUnifiedEngagementMode": ("MADS unified engagement", "One control engages both cruise and steering.", "MADS 统一接管模式", "单一操作同时接管巡航与转向。"),
  "NeuralNetworkLateralControl": ("Neural network lateral control", "Blend a neural lateral path into the controller (NNLC).", "神经网络横向控制", "在控制器中融合神经网络横向路径（NNLC）。"),
  "RoadEdgeLaneChangeEnabled": ("Road edge lane change", "Block lane changes that would cross a detected road edge.", "路缘变道检测", "检测到路缘时阻止越界变道。"),
  "TeslaMadsScreenButton": ("Tesla MADS screen button", "Show the MADS toggle on the Tesla screen.", "特斯拉 MADS 屏幕按钮", "在特斯拉屏幕上显示 MADS 开关。"),
  "TorqueControlTune": ("Torque control tune", "Fine adjustment applied to torque control output.", "扭矩控制微调", "对扭矩控制输出的精细调整。"),
  "TorqueParamsOverrideEnabled": ("Torque params override", "Apply the manual torque param override below.", "扭矩参数覆盖开关", "启用下方手动扭矩参数覆盖。"),
  "TorqueParamsOverrideFriction": ("Torque friction", "Manual friction coefficient for the torque model.", "扭矩摩擦系数", "扭矩模型的手动摩擦系数。"),
  "TorqueParamsOverrideLatAccelFactor": ("Torque lat-accel factor", "Manual lateral-acceleration gain for the torque model.", "扭矩横向加速度系数", "扭矩模型的手动横向加速度增益。"),

  # ---- on-device pages: sunnylink -----------------------------------------
  "BackupManager_CreateBackup": ("Create backup", "Create a sunnylink configuration backup (action).", "创建备份", "创建 sunnylink 配置备份（执行动作）。"),
  "BackupManager_RestoreVersion": ("Restore backup version", "Backup version selected for restore.", "恢复备份版本", "选择要恢复的备份版本。"),
  "CompletedSunnylinkConsentVersion": ("Sunnylink consent version", "Consent text version already accepted (read-only).", "sunnylink 同意版本", "已同意的 sunnylink 条款版本（只读）。"),
  "EnableSunnylinkUploader": ("Enable sunnylink uploader", "Upload logs through sunnylink.", "启用 sunnylink 上传器", "通过 sunnylink 上传日志。"),
  "SunnylinkDongleId": ("Sunnylink dongle ID", "Sunnylink device identifier (read-only).", "sunnylink 设备 ID", "sunnylink 设备标识（只读）。"),
  "SunnylinkEnabled": ("Sunnylink", "Enable the sunnylink service.", "sunnylink 开关", "启用 sunnylink 服务。"),

  # ---- on-device pages: toggles (ExperimentalMode is labelled above) ------

  # ---- on-device pages: trips ---------------------------------------------
  "IsMetric": ("Metric units", "Show distances and speeds in metric units.", "公制单位", "距离与速度使用公制单位。"),
  "LocalDriveStats": ("Local drive stats", "Aggregated local drive statistics (read-only).", "本地驾驶统计", "本地累计驾驶统计（只读）。"),
  "TripsDataSource": ("Trips data source", "Where the trips page reads its data: local, cloud, or both.", "行程数据来源", "行程页读取数据的来源：本地 / 云端 / 全部。"),

  # ---- on-device pages: vehicle -------------------------------------------
  "HyundaiLongitudinalTuning": ("Hyundai longitudinal tuning", "Longitudinal tuning variant for Hyundai/E-guides (default/EV/gas).", "现代纵向调校", "现代/起亚车型的纵向调校变体（默认/纯电/燃油）。"),
  "OnroadCycleRequested": ("Restart onroad processes", "Request the onroad processes to cycle (action).", "重启行车进程", "请求行车相关进程重启（执行动作）。"),
  "SubaruStopAndGo": ("Subaru stop and go", "Allow full stops for Subaru without brake press.", "斯巴鲁跟停", "斯巴鲁车型无需踩刹车即可跟停再起步。"),
  "SubaruStopAndGoManualParkingBrake": ("Subaru stop and go (manual brake)", "Stop-and-go variant for cars with a manual parking brake.", "斯巴鲁跟停（手刹）", "机械手刹车型的跟停变体。"),
  "TeslaCoopSteering": ("Tesla cooperative steering", "Enable cooperative steering on Tesla vehicles.", "特斯拉协同转向", "在特斯拉车型上启用协同转向。"),
  "ToyotaAutoHold": ("Toyota auto hold", "Integrate with the Toyota auto-hold brake.", "丰田 Auto Hold", "与丰田自动驻车（Auto Hold）联动。"),
  "ToyotaDriveMode": ("Toyota drive mode", "Respect the Toyota drive-mode selector.", "丰田驾驶模式", "跟随丰田驾驶模式选择器调整行为。"),
  "ToyotaEnhancedBsm": ("Toyota enhanced BSM", "Use the enhanced Toyota blind-spot monitor data.", "丰田增强盲点", "使用丰田增强型盲点监测数据。"),
  "ToyotaEnforceStockLongitudinal": ("Toyota stock longitudinal", "Force stock Toyota longitudinal control.", "丰田强制原厂纵向", "强制使用丰田原厂纵向控制。"),
  "ToyotaStopAndGoHack": ("Toyota stop and go", "Allow full stops on Toyota without brake press.", "丰田跟停", "丰田车型无需踩刹车即可跟停再起步。"),
  "ToyotaTSS2Long": ("Toyota TSS2.5/3.0 longitudinal", "Use TSS2.5/3.0 longitudinal messages.", "丰田 TSS2.5/3.0 纵向", "使用 TSS2.5/3.0 的纵向控制报文。"),

  # ---- on-device pages: visuals -------------------------------------------
  "BlindSpot": ("Blind spot UI", "Draw blind-spot indicators on the onroad UI.", "盲点警示", "行车界面绘制盲点指示。"),
  "ChevronInfo": ("Chevron info", "What the lead-car chevron shows (distance/time/speed).", "车距信息", "前车箭头（chevron）显示的内容。"),
  "DevUIInfo": ("Developer UI info", "Show developer info overlays onroad.", "开发者信息", "行车界面显示开发者信息。"),
  "GreenLightAlert": ("Green light alert", "Alert when the lead departs on a green light.", "绿灯提醒", "绿灯放行时提醒前车已起步。"),
  "HideVEgoUI": ("Hide speed", "Hide the speed readout on the onroad UI.", "隐藏车速", "行车界面隐藏车速读数。"),
  "LeadDepartAlert": ("Lead depart alert", "Alert when the lead starts moving.", "前车起步提醒", "前车起步时发出提醒。"),
  "RainbowMode": ("Rainbow mode", "Rainbow-colored lane lines.", "彩虹模式", "车道线使用彩虹配色。"),
  "RoadNameToggle": ("Show road name", "Display the current road name onroad.", "显示路名", "行车界面显示当前道路名。"),
  "RocketFuel": ("Rocket fuel", "Acceleration easing effect while speeding up.", "火箭加速特效", "急加速时显示火箭推进动画。"),
  "ShowTurnSignals": ("Show turn signals", "Show the model's turn-signal intent onroad.", "显示转向灯", "行车界面显示模型转向灯意图。"),
  "StandstillTimer": ("Standstill timer", "Show how long the car has been stopped.", "停车计时", "显示停车等待时长。"),
  "TorqueBar": ("Torque bar", "Show the steering torque bar.", "扭矩条", "显示转向扭矩条。"),
  "TrueVEgoUI": ("True speed", "Use the true (uncorrected) speed on the UI.", "真实车速", "界面显示未经修正的真实车速。"),

  # ---- IMU calibration (this fork's locationd IMU work) -------------------
  "ImuCalibrationEnabled": ("IMU calibration", "Use the mounted-IMU calibration matrix.", "IMU 校准", "启用支架 IMU 校准矩阵。"),
  "ImuCalibrationMatrix": ("IMU calibration matrix", "Computed 3x3 rotation matrix (read-only).", "IMU 校准矩阵", "计算得到的 3x3 旋转矩阵（只读）。"),
  "ImuCalibrationRequested": ("Request IMU calibration", "Re-run IMU calibration on next boot (action).", "请求 IMU 校准", "下次启动时重新进行 IMU 校准（执行动作）。"),
  "ImuCalibrationStatus": ("IMU calibration status", "Current IMU calibration state (read-only).", "IMU 校准状态", "当前 IMU 校准状态（只读）。"),

  # ---- model download mirrors (this fork's models/mirror.py) --------------
  "ModelManager_GithubProxy": ("Model list source", "How the model list JSON is fetched: direct, jsDelivr fallback, or a proxy prefix.", "模型列表源", "模型目录 JSON 的获取方式：直连 / jsDelivr 兜底 / 代理前缀。"),
  "ModelManager_MirrorUrl": ("Model download mirror", "Prefix for big/small model artifact downloads (hf-mirror.com default; off = direct).", "模型下载镜像", "大/小模型 artifact 下载前缀（默认 hf-mirror.com；off = 直连）。"),

  # ---- map decel (carrot) -------------------------------------------------
  "CarrotMapDecelEnabled": ("Map-data decel", "Use map data to decelerate for curves and intersections ahead.", "地图数据减速", "利用地图数据对前方弯道/路口提前减速。"),
}

# ---------------------------------------------------------------------------
# carrot (sp) family menu labels
# ---------------------------------------------------------------------------

FAMILY_LABELS: dict[str, tuple[str, str, str]] = {
  "AUTO_FORK": ("오토 포크/분기", "Auto fork & ramps", "岔路自动驾驶"),
  "LATERAL": ("횡방향", "Lateral extras", "横向扩展"),
  "SPEED": ("속도", "Speed extras", "速度扩展"),
  "DISPLAY": ("표시", "Display extras", "显示扩展"),
  "MISC": ("기타", "Miscellaneous", "杂项"),
}

# ---------------------------------------------------------------------------
# on-device settings page menu labels
# ---------------------------------------------------------------------------

PAGE_LABELS: dict[str, tuple[str, str, str]] = {
  "alpha_longitudinal_toggles": ("알파 롱 토글", "Alpha longitudinal", "Alpha 纵向控制"),
  "carrot_tuning": ("당근 튜닝", "Carrot tuning", "Carrot 调校"),
  "cruise": ("크루즈", "Cruise", "巡航"),
  "developer": ("개발자", "Developer", "开发者"),
  "device": ("장치", "Device", "设备"),
  "display": ("화면", "Display", "显示"),
  "models": ("모델 선택", "Model selection", "模型选择"),
  "navigation": ("내비게이션", "Navigation", "导航"),
  "network": ("네트워크", "Network", "网络"),
  "osm": ("OSM 지도", "OSM maps", "OSM 地图"),
  "software": ("소프트웨어", "Software", "软件"),
  "steering": ("조향", "Steering", "转向"),
  "sunnylink": ("sunnylink", "Sunnylink", "Sunnylink"),
  "toggles": ("토글", "Toggles", "开关"),
  "trips": ("주행 기록", "Trips", "行程"),
  "vehicle": ("차량", "Vehicle", "车辆"),
  "visuals": ("시각 효과", "Visuals", "视觉"),
  # not on-device pages, but added params use them as their group
  "maps": ("지도", "Maps", "地图"),
  "imu": ("IMU", "IMU calibration", "IMU 惯性测量"),
}

# ---------------------------------------------------------------------------
# extra menu sections this fork adds (params referenced by name; the IMU ones
# also gain param entries since no upstream entry or on-device page has them)
# ---------------------------------------------------------------------------

IMU_PARAMS: tuple[str, ...] = (
  "ImuCalibrationEnabled", "ImuCalibrationRequested", "ImuCalibrationStatus", "ImuCalibrationMatrix",
)

# Maps section: display/limit parameters that read map data (a param may appear
# in cp's tree as well - menu references are by name and the panel dedupes).
MAPS_PARAMS: tuple[str, ...] = (
  "OsmMapDataEnabled",      # mapd feed (also in navigation page group)
  "OsmLocal",               # local sideload switch (also in osm page group)
  "MapboxStyle",            # panel map style (cp: SYSTEM/SYS_NET)
  "MapTurnSpeedFactor",     # turn slowdown factor (cp: DRIVING/SPEED)
  "CarrotMapDecelEnabled",  # map-data based decel
  "CarrotNaviHudMapProfile",
  "ClusterNaviMapTheme", "ClusterNaviMapType", "ClusterNaviMapFps",
)

# Model download mirror keys live in the MISC family; surface them on the
# models page group too, where a user looks for them.
MODEL_MIRROR_PARAMS: tuple[str, ...] = ("ModelManager_MirrorUrl", "ModelManager_GithubProxy")


def apply_param_labels(entry: dict) -> dict:
  """Fill an added param entry's label slots from `PARAM_LABELS`.

  ko slots keep whatever the generator put there (humanized key); the en/zh
  slots fall back to the humanized key when this module has no entry.
  """
  labels = PARAM_LABELS.get(entry["name"])
  if labels is None:
    return entry
  etitle, edescr, ctitle, cdescr = labels
  if etitle:
    entry["etitle"] = etitle
  if edescr:
    entry["edescr"] = edescr
  if ctitle:
    entry["ctitle"] = ctitle
  if cdescr:
    entry["cdescr"] = cdescr
  return entry
