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

Dragonpilot 为 fork，向用户说明安全边界时引用本文档即可，勿鼓励关闭 DM。""",
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

Dragonpilot 用户：调参走 dp_*；改安全/控车逻辑需知 fork 合规与 comma 封禁风险。""",
  },
]
