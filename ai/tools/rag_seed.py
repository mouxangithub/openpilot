"""Built-in RAG documents (SecOC / engage / adaptation / CP migration / comma docs)."""

from __future__ import annotations

import time
from typing import Any

from openpilot.common.params import Params

from ai.tools.comma_docs_rag import COMMA_DOCS_RAG
from ai.tools.rag_store import list_documents, remove_document, upsert_document_sync

_BUILTIN_PREFIX = "builtin_"

# Retired doc ids (branded titles); removed on seed so knowledge base stays clean.
_DEPRECATED_BUILTIN_IDS = frozenset({
  "builtin_yuluoqc_lat_tune",
  "builtin_yuluoqc_lon_tune",
  "builtin_yuluoqc_ui",
  "builtin_yuluoqc_blog_1054",
  "builtin_yuluoqc_adapt",
})

_BUILTIN_DOCS: list[dict[str, Any]] = [
  {
    "id": "builtin_secoc_overview",
    "title": "SecOC/TSK 概述（丰田系）",
    "tags": ["secoc", "toyota", "optskug", "faq"],
    "text": """丰田部分车型在转向 CAN 报文上使用 SecOC（AUTOSAR Secure Onboard Communication）认证。
没有本车 SecOCKey 时，openpilot 无法发送合法转向指令，常见表现：startupNoSecOcKey、仅行车记录仪模式。
每台车密钥不同，须从本车 EPS 提取，不能共用他人密钥。
权威文档：https://github.com/optskug/docs
密钥提取原理：https://icanhack.nl/blog/secoc-key-extraction/
车型分档：🟢 可按 Setup Guide 提取；🟡 实验路径（如部分 2024 美版 Sienna）；🔴 目前无法破解（2022+ 多数新平台、Tundra HSM 等）。
Dragonpilot：用户在 Dashy Developer → SecOCKey Install 自行填入 32 位 hex；AI 禁止代写 SecOCKey。""",
  },
  {
    "id": "builtin_engage_triage",
    "title": "无法 Engage 快速分诊",
    "tags": ["engage", "dashcam", "faq", "events"],
    "text": """无法开启 openpilot 时分诊顺序：
1) read_onroad_events：若有 startupNoSecOcKey → 先解决 SecOC 密钥，不是调 dp_*。
2) carUnrecognized / startupNoCar → 指纹未收录；SecOC 车须先密钥再适配 DBC。
3) startupNoControl / dashcamMode → 查车型是否在支持表、是否 dashcam 预期行为。
4) steerUnavailable / invalidLkasSetting → 查 LKAS 开关、品牌 EPS 锁止（VAG: dp_vag_avoid_eps_lockout）。
5) 摄像头/模型事件 → grep_log、检查遮挡与校准。
工具：get_vehicle_state, trip_review, read_params(CarParams), grep_log。""",
  },
  {
    "id": "builtin_adaptation_sop",
    "title": "车型适配人机协作 SOP",
    "tags": ["adaptation", "dbc", "fingerprint", "faq"],
    "refresh": True,
    "text": """车机闭环：顶栏 CAN 弹窗 → list_dbcs/read_dbc_file → cabana_analyze → analyze_can_id_pattern（五类 CAN）
→ save_adaptation_draft（静止+confirm）→ export_adaptation_bundle → PC 合入 opendbc → 封闭场地路试。

PC 开发常用：manager 指纹模式、can_printer、cereal dump carState、PlotJuggler — 车机用 Cabana/grep_log/trip_review 替代。
SecOC 车先 Dashy 安装 SecOCKey 再谈 DBC。分步详解：builtin_vehicle_adaptation_guide；完整 ai/docs/VEHICLE_ADAPTATION_GUIDE.md""",
  },
  {
    "id": "builtin_vehicle_adaptation_guide",
    "title": "openpilot 车辆适配与调试纲要",
    "tags": ["adaptation", "fingerprint", "carstate", "carcontroller", "faq"],
    "refresh": True,
    "text": """标准 openpilot 新车适配流程（社区通用方法论）：

1 流程：指纹识别 → CarState/CarController 接口 → CarSpecs/控制参数 → 封闭场地安全验证。
   代码落点：opendbc/car/*/interface.py、carstate.py、carcontroller.py。

2 指纹：抓 CAN，必确认五类信号 ID——车速、转向角、制动、油门、档位。
   格式 FINGERPRINTS={'MODEL':[{0xID:长度,...}]}。车机：Cabana+analyze_can_id_pattern；只写 adaptation_drafts。

3 CarState 最小字段：vEgo, steeringAngleDeg, gas, brake, gasPressed, brakePressed, standstill, gearShifter。
   用 cabana_explain_signal 对照 DBC；get_vehicle_state 验证。

4 CarController：典型 LKAS/SCC 报文；须 apply_driver_steer_torque_limits、MAX_STEER_SPEED 限幅、STEER_DELTA 速率。
   save_adaptation_draft → export_adaptation_bundle。

5 车型参数：CarSpecs(mass,wheelbase,steerRatio)、STEER_MAX、ACCEL_MIN/MAX 写在 values.py，非 Dashy 用户 Param。
   日常行驶调优用本 fork 的 dp_*（list_dp_settings）。

6 调试：carState/carControl → get_vehicle_state/get_full_vehicle_state；日志 → grep_log_errors；Param → read_params。

7 路试清单（封闭场地）：转向反馈/扭矩限制/故障断开；纵向加速度/制动/跟车。

8 性能优化属源码层（降频、批量 CAN），op助手不自动改控车循环。

9 故障：无法识别→指纹/CAN/DBC/SecOC；控制无响应→报文格式、STEER 限幅、状态与 CAN 一致性。
   can_printer→Cabana；DBC 校验→read_dbc_file。""",
  },
  {
    "id": "builtin_op_tuning_wiki",
    "title": "openpilot 调参工具链与路线分析",
    "tags": ["tuning", "plotjuggler", "maneuver", "route", "faq"],
    "refresh": True,
    "text": """调参推荐工具顺序：
1 list_plotjuggler_layouts / list_jotpluggler_layouts 选布局
2 plotjuggler_data_summary 或 route_time_series 看信号
3 调参后 compare_route_signals(route_before, route_after)
4 封闭场地 long_maneuver_report / lat_maneuver_report / car_porting_steering_accuracy
5 MPC 纵向仿真 mpc_longitudinal_tuning_report（无需路线）
6 PR 视频 route_export_clip

PC 可视化：pc_launch_jotpluggler、pc_launch_replay_viz_stream。
批量复盘：batch_route_summary。CAN 只读：route_can_stats（非 can_replay 硬件）。
wiki: https://github.com/commaai/openpilot/wiki/Tuning""",
  },
  {
    "id": "builtin_secoc_sienna_2024",
    "title": "2024 Sienna SecOC 实验路径提示",
    "tags": ["secoc", "sienna", "experimental", "faq"],
    "text": """部分 2024+ 美版 Sienna 不在 optskug 标准 Setup Guide 内，属于 🟡 实验路径。
社区笔记与实验工具见 optskug/docs 与 comma Discord #toyota-security。
关键帧示例：0x2E4 STEERING_LKA、0x131 STEERING_LTA_2；需 EPS 版本、制造年月、产地。
勿在聊天或仓库中公开 SecOCKey。""",
  },
  {
    "id": "builtin_cp_lat_mapping",
    "title": "横向调优：Carrot/CP → Dragonpilot",
    "tags": ["carrot", "cp", "lateral", "tuning", "migration", "faq"],
    "refresh": True,
    "text": """从 CarrotPilot/OpenPilotCP 迁移到 Dragonpilot 时，横向 Param 对照（本 fork 无 CP 专有名）：

| CP 参数/说法 | Dragonpilot | 说明 |
| AdjustLaneOffset / PathOffset | dp_lat_offset_cm | 车道偏移厘米 |
| LaneChangeDelay / LaneChangeBsd | dp_lat_lca_auto_sec, dp_lat_lca_speed | lca_speed=0 关闭 |
| MADS / 全速域横向 | dp_lat_alka | 品牌相关 |
| SteerActuatorDelay, LatSmoothSec, LateralTorque*, LatMpc* | 无同名 | 勿写入；用 list_dp_settings、dp-brand-* |
| CustomSteerMax | CarParams 级 | 非用户 Param |

工具：search_knowledge_base, list_dp_settings, snapshot_tune_state, diff_params。""",
  },
  {
    "id": "builtin_cp_lon_mapping",
    "title": "纵向调优：Carrot/CP → Dragonpilot",
    "tags": ["carrot", "cp", "longitudinal", "tuning", "migration", "faq"],
    "refresh": True,
    "text": """CP 纵向迁移对照：

| CP | Dragonpilot |
| LongitudinalPersonality | 上游 Param，一致 |
| CruiseEcoControl | dp_lon_acm（需 OP 纵向） |
| MyDrivingMode | dp_lon_aem + dp_lon_apm |
| TFollowGap*, CruiseMaxVals*, LongTuning* | 无逐项同名 → Personality + list_tune_presets |
| AutoCruiseControl / SoftHoldMode | dp_toyota_* 等品牌项，list_dp_settings |

写 dp_lon_* 前确认 openpilotLongitudinalControl。工具：read_params, snapshot_tune_state, diff_params。""",
  },
  {
    "id": "builtin_cp_ui_mapping",
    "title": "UI 设置：Carrot 面板 → Dashy",
    "tags": ["carrot", "cp", "ui", "dashy", "migration", "faq"],
    "refresh": True,
    "text": """CP fork 的 Carrot 面板项在 Dragonpilot 对应 Dashy（:5088）与 dp_ui_*：

| CP UI | Dragonpilot |
| ShowPathColor/Mode、彩虹路径 | dp_ui_rainbow, dp_ui_display_mode |
| Carrot 面板开关 | fetch_dashy_settings + list_dp_settings |
| dp_dev_model | dp_dev_model_selected |
| IsMetric | IsMetric |

用户口述 CP 界面项：先 fetch_dashy_settings，再映射 dp_*，勿假设 CP Param 存在。""",
  },
  *COMMA_DOCS_RAG,
]


def ensure_builtin_rag_docs(params: Params | None = None) -> dict[str, Any]:
  """Insert or refresh built-in FAQ docs (idempotent per doc id)."""
  params = params or Params()
  existing = list_documents(params).get("documents") or []
  existing_ids = {str(d.get("id", "")) for d in existing}

  removed = 0
  for old_id in _DEPRECATED_BUILTIN_IDS:
    if old_id in existing_ids:
      try:
        remove_document(params, old_id)
        removed += 1
        existing_ids.discard(old_id)
      except Exception:
        pass

  seeded = 0
  refreshed = 0
  skipped = 0
  errors: list[str] = []
  for doc in _BUILTIN_DOCS:
    doc_id = doc["id"]
    should_write = doc_id not in existing_ids or doc.get("refresh")
    if not should_write:
      skipped += 1
      continue
    try:
      upsert_document_sync(
        params,
        title=doc["title"],
        text=doc["text"],
        tags=doc.get("tags"),
        doc_id=doc_id,
      )
      if doc_id in existing_ids:
        refreshed += 1
      else:
        seeded += 1
    except Exception as e:
      errors.append(f"{doc_id}: {e}")
  return {
    "ok": len(errors) == 0,
    "seeded": seeded,
    "refreshed": refreshed,
    "removed": removed,
    "skipped": skipped,
    "total": len(_BUILTIN_DOCS),
    "errors": errors[:5],
    "at": int(time.time()),
  }
