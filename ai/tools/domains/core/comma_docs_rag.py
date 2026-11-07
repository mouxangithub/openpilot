"""Built-in RAG summaries from upstream docs (docs.comma.ai / docs/)."""

from __future__ import annotations

from typing import Any

# All ids use builtin_op_* prefix; refresh=True so text tracks upstream doc changes on restart.
COMMA_DOCS_RAG: list[dict[str, Any]] = [
  {
    "id": "builtin_op_overview",
    "title": "openpilot 官方概述",
    "tags": ["openpilot", "comma", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/index.md（https://docs.comma.ai）

openpilot 是开源驾驶辅助系统，运行于 comma four 设备。
功能：ACC 自适应巡航、ALC 自动车道居中、FCW 前向碰撞预警、LDW 车道偏离预警；
Engage 时还有基于摄像头的驾驶员监控（DM）。
原理：通过车辆原厂 ADAS 接口（转向/油门/制动 CAN），提供比原厂更优的加减速与转向输入。
支持车型见 CARS.md（builtin_op_cars_support）；集成行为见 builtin_op_integration；限制见 builtin_op_limitations。""",
  },
  {
    "id": "builtin_op_glossary",
    "title": "openpilot 术语表",
    "tags": ["openpilot", "glossary", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/concepts/glossary.md

onroad — 点火开启时 openpilot 的运行状态（IsOnroad=true）。
offroad — 点火关闭时的状态。
route — 一次 onroad 行程的完整录制。
segment — route 按 1 分钟切分的片段；日志以 segment 为单位存储。
comma connect — 路线 Web 查看器 connect.comma.ai；qcamera 视频在此展示。
panda — 设备上的安全协处理器，经 CAN 直接与车辆通信；实现 functional safety。
comma four — comma 官方硬件，运行 openpilot 的推荐设备。

车机助手：read_params(IsOnroad) 判断 on/offroad；list_routes / trip_review 查 route。""",
  },
  {
    "id": "builtin_op_cars_support",
    "title": "官方支持车型表解读（CARS.md）",
    "tags": ["cars", "support", "dashcam", "engage", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/CARS.md（约 334 款上游支持车；美规为主）

支持车定义：安装 comma 设备后「即插即用」，体验优于原厂 ADAS。

ACC 列含义（决定能否 Engage / 是否 dashcam）：
- openpilot — 横向+纵向均由 openpilot 控制（完整 OP）。
- openpilot available — 默认可用 stock ACC；openpilot 纵向为 Alpha，须在非 release 分支（如 nightly-dev）打开开关后才替换 stock ACC。
- Stock — 仅 stock ACC/LKA，openpilot 不接管纵向或部分控制 → 常表现为 dashcam 或受限 engage。
- dashcam — 仅行车记录仪，无横向/纵向控制（未收录指纹或 SecOC 等）。

其他列：No ACC accel below / No ALC below 为最低生效车速；Steering Torque / Resume from stop 为能力星级。

重要脚注（分诊常用）：
¹ 纵向 Alpha 仅 nightly-dev 等分支可开；开纵向会禁用部分原厂 AEB/FCW（本田 CMBS、斯巴鲁 EyeSight 等）。
⁹ 特斯拉 HW3/HW4 需在车机 Software→Additional Vehicle Information 查看 Autopilot computer。
¹² VAG J533 harness 接 CAN 网关（方向盘柱上方）。
¹⁶ 仅 J533 网关 harness 可开 openpilot 纵向；camera harness 车型限 stock ACC。
丰田 SecOC 新平台（RAV4 Prime 2021+、Sienna 2021+、Tundra 2022+ 等）上游尚未支持，需社区 SecOCKey。

无法 engage 时：search_knowledge_base(builtin_op_cars_support) + read_params(CarParams) 对照 ACC 列与 footprint。
社区扩展车型见 wiki.comma.ai，非上游 CARS 表。""",
  },
  {
    "id": "builtin_op_integration",
    "title": "openpilot 与原厂功能集成",
    "tags": ["integration", "stock", "acc", "lka", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/INTEGRATION.md

所有支持车：
- 原厂 LKA/ALC → 由 openpilot ALC 替代，仅 Engage 时生效。
- 原厂 LDW → 由 openpilot LDW 替代。

部分支持车（CARS.md ACC 列为 openpilot / openpilot available）：
- stock ACC → openpilot ACC（available 需 Alpha 开关）。
- openpilot FCW 在 stock FCW 之外额外工作。

应保留的其他原厂功能：FCW、AEB、自动远光、盲点、侧向碰撞预警等（因车而异）。
分诊：用户抱怨「ACC 没了」→ 查 CARS ACC 列是否为 Stock / 是否未开纵向 Alpha。""",
  },
  {
    "id": "builtin_op_limitations",
    "title": "openpilot 使用限制（官方）",
    "tags": ["limitations", "safety", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/LIMITATIONS.md

总则：openpilot 不自动驾驶；驾驶员须全程握方向盘、随时接管。

ALC/LDW 限制：不查盲点；变道须驾驶员确认安全。恶劣天气、摄像头遮挡/损坏、错误安装、急弯匝道、施工区、横风、陡坡窄弯、强光等会降低或失效。

ACC/FCW 限制：不识别红绿灯/停车标志/限速牌；静止前车、急刹、旁车加塞、收费站桥梁金属板等场景可能异常；加减速幅度有限。

DM 限制：非精确疲劳度量；夜间、强光、人脸出框、驾驶员摄像头遮挡时不可靠。

助手话术：遇上述场景提醒用户接管，勿承诺全场景可用。""",
  },
  {
    "id": "builtin_op_safety",
    "title": "openpilot 安全模型要点",
    "tags": ["safety", "panda", "fork", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/SAFETY.md

定位：L2 ACC+ALC 辅助系统；驾驶员警觉必要但不充分；无适销性担保。
开发遵循 FMVSS、ISO26262 思路、MISRA C（安全相关代码）、SIL/HIL/实车测试。

两大安全要求：
1. 驾驶员可随时踩刹车或按 Cancel 立即接管。
2. Engage 时执行器扭矩/加速度受限，轨迹变化不得快于驾驶员安全反应（横向约 ISO11270/ISO15622：1m 偏离最多约 0.9s 执行）。

实现参考：panda safety model；车型细节 opendbc/safety/safety。

Fork 合规（违反可被 comma 封禁）：
- 不得削弱驾驶员监控（selfdrive/monitoring）。
- 不得削弱过度执行检查（selfdrived/helpers.py）。
- 修改 opendbc/safety/ 时：不得使用 openpilot 商标；须保留并通过完整 safety 测试套件。

向用户说明安全边界时引用本文档即可，勿鼓励关闭 DM。""",
  },
  {
    "id": "builtin_op_car_port",
    "title": "车型移植（Car Port）官方结构",
    "tags": ["car-port", "opendbc", "adaptation", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/how-to/car-port.md

car port = 让某车型支持 openpilot 的代码集合。复杂度取决于同品牌已有支持、车辆 ADAS 架构。

opendbc/car/[brand]/ 标准文件：
- interface.py — CarInterface
- carstate.py — CAN → CarState
- carcontroller.py — CarControl → 车辆执行
- [brand]can.py — CAN 组帧
- values.py — 扭矩/加速度限值、车型常量
- radar_interface.py — 雷达（如有）

安全：opendbc/safety/modes/[brand].h + tests/test_[brand].py

openpilot 残留：selfdrive/car/car_specific.py（品牌事件逻辑），将逐步迁出。

Brand port（新品牌/平台）vs Model port（同品牌新车款，较易）。
视频概述：https://www.youtube.com/watch?v=XxPS5TpTUnI

车机助手闭环见 builtin_vehicle_adaptation_guide；勿直接改 opendbc，用 save_adaptation_draft。""",
  },
  {
    "id": "builtin_op_logs",
    "title": "openpilot 日志与路线结构",
    "tags": ["logs", "route", "segment", "rlog", "qlog", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/concepts/logs.md

route：点火上升沿开始，下降沿结束；按 1 分钟切为 segment。

每 segment 主要文件：
- rlog.zst — 全量进程间 cereal 消息（Cap'n Proto + zstd）；见 cereal/services.py。
- fcamera.hevc / ecamera.hevc / dcamera.hevc — 前路/广焦/驾驶员 H.265 视频。
- qlog.zst — rlog 降采样子集，便于上传。
- qcamera.ts — 低分辨率前路 H.264；comma connect 播放源。

工具：tools/lib/logreader.py、tools/replay；车机用 grep_log、trip_review、list_routes。
助手分析路线：extract_can_ids_from_route、cabana_analyze（需 route 路径）。""",
  },
  {
    "id": "builtin_op_contributing_fork",
    "title": "上游贡献与 Fork 训练数据兼容",
    "tags": ["contributing", "fork", "cereal", "official", "faq"],
    "refresh": True,
    "text": """来源：docs/CONTRIBUTING.md

上游优先级：安全 > 稳定 > 质量 > 功能。PR 对 master，需明确目的、验证、过 CI。
难合并：纯风格、500+ 行、无目标 PR、UI  redesign、多数新功能 PR。

Fork 训练数据若要被 comma 采纳，须满足：
1. cereal 消息结构兼容（见 cereal#custom-forks）。
2. 不得改动任何 stock 消息字段语义（如 selfdriveState.enabled、carState.steeringAngleDeg）；自定义结构另建。
3. 不得包含上游 platforms 未支持的车；新车型用新 opendbc platform。

非代码贡献：报 bug、Discord #driving-feedback、Wi-Fi 上传、跑 nightly、comma10k 标注。

调参可走 dp_* 等扩展键（若本机存在）；改安全/控车逻辑需知 fork 合规与 comma 封禁风险。""",
  },
  {
    "id": "builtin_op_safety_full",
    "title": "openpilot 安全边界（全文）",
    "tags": ["safety", "official", "faq"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/SAFETY.md
适用范围：openpilot 安全设计与 fork 合规要求的英文原文全文。

# Safety

openpilot is an Adaptive Cruise Control (ACC) and Automated Lane Centering (ALC) system.
Like other ACC and ALC systems, openpilot is a failsafe passive system and it requires the
driver to be alert and to pay attention at all times.

To assist the driver in maintaining alertness, openpilot includes a driver monitoring feature
that alerts when it detects driver distraction.

However, even with an attentive driver, we must make further efforts for the system to be
safe. We repeat, **driver alertness is necessary, but not sufficient, for openpilot to be
used safely** and openpilot is provided with no warranty of fitness for any purpose.

openpilot is developed in good faith to be compliant with FMVSS requirements and to follow
industry standards of safety for Level 2 Driver Assistance Systems. In particular, we observe
ISO26262 guidelines, including those from pertinent documents released by NHTSA. In addition,
we impose strict coding guidelines (like MISRA C : 2012) on parts of openpilot that are
safety relevant. We also perform software-in-the-loop, hardware-in-the-loop, and in-vehicle
tests before each software release.

Following Hazard and Risk Analysis and FMEA, at a very high level, we have designed openpilot
ensuring two main safety requirements.

1. The driver must always be capable to immediately retake manual control of the vehicle,
   by stepping on the brake pedal or by pressing the cancel button.
2. The vehicle must not alter its trajectory too quickly for the driver to safely
   react. This means that while the system is engaged, the actuators are constrained
   to operate within reasonable limits.

For these actuator limits we observe ISO11270 and ISO15622. Lateral limits described there
translate to 0.9 seconds of maximum actuation to achieve a 1m lateral deviation.

For additional safety implementation details, refer to the panda safety model
(github.com/commaai/panda#safety-model). For vehicle specific implementation of the safety
concept, refer to opendbc/safety/safety.

### Forks of openpilot

* Do not disable or nerf driver monitoring (openpilot/selfdrive/monitoring)
* Do not disable or nerf excessive actuation checks (openpilot/selfdrive/selfdrived/helpers.py)
* If your fork modifies any of the code in opendbc/safety/:
   * your fork cannot use the openpilot trademark
   * your fork must preserve the full safety test suite and all tests must pass, including
     any new coverage required by the fork's changes

Failure to comply with these standards will get you and your users banned from comma.ai servers.

comma.ai strongly discourages the use of openpilot forks with safety code either missing or
not fully meeting the above requirements.""",
  },
  {
    "id": "builtin_op_limitations_full",
    "title": "openpilot 功能局限（全文）",
    "tags": ["safety", "official", "faq"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/LIMITATIONS.md
适用范围：openpilot ALC/LDW、ACC/FCW、DM 官方限制清单的英文原文全文。

## Limitations of openpilot ALC and LDW

openpilot ALC and openpilot LDW do not automatically drive the vehicle or reduce the amount
of attention that must be paid to operate your vehicle. The driver must always keep control
of the steering wheel and be ready to correct the openpilot ALC action at all times.

While changing lanes, openpilot is not capable of looking next to you or checking your blind
spot. Only nudge the wheel to initiate a lane change after you have confirmed it's safe to
do so.

Many factors can impact the performance of openpilot ALC and openpilot LDW, causing them to
be unable to function as intended. These include, but are not limited to:

* Poor visibility (heavy rain, snow, fog, etc.) or weather conditions that may interfere
  with sensor operation.
* The road facing camera is obstructed, covered or damaged by mud, ice, snow, etc.
* Obstruction caused by applying excessive paint or adhesive products (such as wraps,
  stickers, rubber coating, etc.) onto the vehicle.
* The device is mounted incorrectly.
* When in sharp curves, like on-off ramps, intersections etc...; openpilot is designed to
  be limited in the amount of steering torque it can produce.
* In the presence of restricted lanes or construction zones.
* When driving on highly banked roads or in presence of strong cross-wind.
* Extremely hot or cold temperatures.
* Bright light (due to oncoming headlights, direct sunlight, etc.).
* Driving on hills, narrow, or winding roads.

The list above does not represent an exhaustive list of situations that may interfere with
proper operation of openpilot components. It is the driver's responsibility to be in control
of the vehicle at all times.

## Limitations of openpilot ACC and FCW

openpilot ACC and openpilot FCW are not systems that allow careless or inattentive driving.
It is still necessary for the driver to pay close attention to the vehicle's surroundings
and to be ready to re-take control of the gas and the brake at all times.

Many factors can impact the performance of openpilot ACC and openpilot FCW, causing them to
be unable to function as intended. These include, but are not limited to:

* Poor visibility (heavy rain, snow, fog, etc.) or weather conditions that may interfere
  with sensor operation.
* The road facing camera or radar are obstructed, covered, or damaged by mud, ice, snow, etc.
* Obstruction caused by applying excessive paint or adhesive products (such as wraps,
  stickers, rubber coating, etc.) onto the vehicle.
* The device is mounted incorrectly.
* Approaching a toll booth, a bridge or a large metal plate.
* When driving on roads with pedestrians, cyclists, etc...
* In presence of traffic signs or stop lights, which are not detected by openpilot at this
  time.
* When the posted speed limit is below the user selected set speed. openpilot does not
  detect speed limits at this time.
* In presence of vehicles in the same lane that are not moving.
* When abrupt braking maneuvers are required. openpilot is designed to be limited in the
  amount of deceleration and acceleration that it can produce.
* When surrounding vehicles perform close cut-ins from neighbor lanes.
* Driving on hills, narrow, or winding roads.
* Extremely hot or cold temperatures.
* Bright light (due to oncoming headlights, direct sunlight, etc.).
* Interference from other equipment that generates radar waves.

The list above does not represent an exhaustive list of situations that may interfere with
proper operation of openpilot components. It is the driver's responsibility to be in control
of the vehicle at all times.

## Limitations of openpilot DM

openpilot DM should not be considered an exact measurement of the alertness of the driver.

Many factors can impact the performance of openpilot DM, causing it to be unable to function
as intended. These include, but are not limited to:

* Low light conditions, such as driving at night or in dark tunnels.
* Bright light (due to oncoming headlights, direct sunlight, etc.).
* The driver's face is partially or completely outside field of view of the cabin camera.
* The cabin camera is obstructed, covered, or damaged.

The list above does not represent an exhaustive list of situations that may interfere with
proper operation of openpilot components. A driver should not rely on openpilot DM to assess
their level of attention.""",
  },
  {
    "id": "builtin_op_cars_index_guide",
    "title": "车型支持查询指引（CARS_INDEX 数据模块）",
    "tags": ["cars", "support", "faq", "lookup"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/CARS.md（约 334 款上游支持车的结构化索引）

查询「某车型是否支持 / 支持包要求 / ACC 语义」时，不要把整篇 CARS.md 当文档检索，
直接使用车型索引数据模块 ai/tools/domains/vehicle/cars_index.py 的 lookup_cars(make, model)：
- 大小写不敏感、部分匹配；返回 make/model/years/package/acc/acc_min_mph/alc_min_mph/
  steer_torque_stars/resume_stars/hardware_summary 字段。
- ACC 列语义：openpilot — 完整横向+纵向控制；openpilot available — 默认用 stock ACC，
  OP 纵向为 Alpha 须非 release 分支开开关；Stock — 仅原厂 ACC/LKA；dashcam — 仅行车记录仪。
- acc_min_mph / alc_min_mph 为该功能最低生效车速（mph，0 表示全速域）。
- steer_torque_stars / resume_stars 为能力星级（0-5，5=满星）。
- hardware_summary 为所需硬件清单摘要（None 表示无需额外硬件）。
脚注细节（如纵向 Alpha 副作用、SecOC 平台限制）参考 builtin_op_cars_support 与 builtin_op_integration。""",
  },
]
