"""Built-in RAG documents (SecOC / engage / adaptation / CP migration / comma docs)."""

from __future__ import annotations

import time
from typing import Any

from openpilot.common.params import Params

from ai.system.paths import rel_source
from ai.services.rag.builtin_loader import load_json_builtin_docs
from ai.tools.domains.core.comma_docs_rag import COMMA_DOCS_RAG
from ai.tools.domains.core.secoc_rag import SECOC_RAG
from ai.tools.domains.core.wiki_rag import WIKI_RAG
from ai.common.rag_config import rag_max_docs
from ai.tools.domains.core.rag_store import (
  _MAX_DOC_CHARS,
  _load_docs,
  _save_docs,
)

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
部分 fork 在设置/Web UI（如 Dashy）提供 SecOCKey 安装入口，用户自行填入 32 位 hex；AI 禁止代写 SecOCKey。""",
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
    "id": "builtin_mads_lateral_triage",
    "title": "MADS 横向 / LKAS 故障分诊",
    "tags": ["mads", "lateral", "lkas", "toyota", "faq", "steer"],
    "refresh": True,
    "text": """用户报「控制不匹配：横向」「LKAS故障」「MAIN+MADS 不控横向」时：

工具：diagnose_mads_lateral → get_mads_settings → read_onroad_events / trip_review → grep_log mads|lateral|LKAS

两种报错勿混：
- controlsMismatchLateral：Python mads.data_sample vs Panda controlsAllowedLateral。修 """ + rel_source("sunnypilot", "mads", "mads.py") + """（禁 data_sample）+ pandad process_mads_heartbeat。不必刷 Panda。
- steerTempUnavailable / steerUnavailable（UI: LKAS故障）：丰田 EPS LKA_STATE；MADS active 但 Panda 拦截 STEERING_LKA。修 opendbc mads.h mads_acc_main_lateral_latch（MAIN 电平保持，学 dp ALKA）并刷 Panda：python """ + rel_source("selfdrive", "pandad", "pandad.py") + """

故障链：MAIN 上升沿放行横向 → heartbeat 滞后撤权 → MAIN 仍亮无法再次请求 → 软件仍发 LKA → EPS 故障。

丰田操作：巡航 MAIN（非 LDA）+ MADS 开 + MadsMainCruiseAllowed 开。默认 MadsSteeringMode=0 Remain Active。

部分 fork 用 dp_lat_alka（lkas_on=acc_main_on），无 MADS heartbeat；带 MADS 的安装树用 MADS + mads.h，勿混为同一开关。

技能：mads-lateral-troubleshoot""",
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
    "title": "横向调优：旧 fork (CP) → openpilot",
    "tags": ["carrot", "cp", "lateral", "tuning", "migration", "faq"],
    "refresh": True,
    "text": """从 CarrotPilot/OpenPilotCP 等旧 fork 迁移到 openpilot 时，横向 Param 对照（本机若无 CP 专有名则跳过）：

| CP 参数/说法 | openpilot (常见) | 说明 |
| AdjustLaneOffset / PathOffset | dp_lat_offset_cm | 车道偏移厘米 |
| LaneChangeDelay / LaneChangeBsd | dp_lat_lca_auto_sec, dp_lat_lca_speed | lca_speed=0 关闭 |
| MADS / 全速域横向 | dp_lat_alka | 品牌相关 |
| SteerActuatorDelay, LatSmoothSec, LateralTorque*, LatMpc* | 无同名 | 勿写入；用 list_dp_settings、dp-brand-* |
| CustomSteerMax | CarParams 级 | 非用户 Param |

工具：search_knowledge_base, list_dp_settings, snapshot_tune_state, diff_params。""",
  },
  {
    "id": "builtin_cp_lon_mapping",
    "title": "纵向调优：旧 fork (CP) → openpilot",
    "tags": ["carrot", "cp", "longitudinal", "tuning", "migration", "faq"],
    "refresh": True,
    "text": """CP 纵向迁移对照：

| CP | openpilot (常见) |
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
    "text": """旧 fork 的 Carrot 面板项在本机可能对应 Web 设置 UI（如 Dashy :5088）与 dp_ui_*：

| CP UI | openpilot (常见) |
| ShowPathColor/Mode、彩虹路径 | dp_ui_rainbow, dp_ui_display_mode |
| Carrot 面板开关 | fetch_dashy_settings + list_dp_settings |
| dp_dev_model | dp_dev_model_selected |
| IsMetric | IsMetric |

用户口述 CP 界面项：先 fetch_dashy_settings，再映射 dp_*，勿假设 CP Param 存在。""",
  },
  {
    "id": "builtin_github_runner",
    "title": "GitHub Runner / C3 prebuilt CI",
    "tags": ["github", "runner", "ci", "prebuilt", "tici", "c3", "faq"],
    "refresh": True,
    "text": """C3 自建 GitHub Actions Runner 为 fork 编译 master-c3 → 发布 master-c3-prebuilt。

安装：GitHub Actions → Runners → token → release/ci/install_github_runner.sh --token --repo
标签须含 tici。数据目录 /data/github/runner；服务名在 runner/.service。

GUI：开发者 → 显示高级控制项 → GitHub Runner Service（Param EnableGithubRunner）。
manager 离路且电压>9V、非计量网络时 systemctl 启停；github_runner.sh 读 .service 服务名。

工具：github_runner_status, github_runner_recovery_hint, install_github_runner。
文档：ai/docs/GITHUB_RUNNER.md；技能 github-runner。""",
  },
  {
    "id": "builtin_panda_f4_c3_porting",
    "title": "C3 / DOS / 黑熊 / 多 Panda 移植（三层参考提交）",
    "tags": ["panda", "f4", "dos", "black-panda", "c3", "tici", "porting", "opendbc", "dual-panda", "faq"],
    "refresh": True,
    "text": """当 openpilot fork 不适配 C3 内置 DOS（F4）、外接黑熊（F4）或双 Panda 时，按三层合入：

重要：panda.bin.signed 不内置在 ai/ 中。它是 panda 子模块 scons 产物（panda/board/obj/），随 panda 迭代更新；panda 子模块 bump 后须 build_panda_firmware 再刷写。

参考提交（本 fork master-c3）：
- panda@7d703710 — F4 构建、dos.h、python F4_DEVICES/get_mcu_type；scons 产出 panda.bin.signed
- sp@43d4f56f — launch_chffrplus set_tici_hw/TICI_DOS/set_aux_panda；pandad panda_comms.cc USB 双 Panda bus_offset；card.py num_pandas
- opendbc@3244efe — fw_versions/car_helpers num_pandas 跳过无效 bus；Toyota CanBus offset；safety.h #ifdef CANFD（F4 无 CANFD）

完整步骤：ai/docs/PANDA_C3_F4_PORTING.md；技能 c3-dos-panda。

流程：三层 cherry-pick 或手工合入 → build_panda_firmware（scons panda/board）→ offroad flash_panda_firmware → 重启 manager。

禁忌：勿把 panda.bin.signed 放进 ai。勿用 panda_tici/H7 固件刷 F4。外接红熊 H7 由 pandad 自动刷 panda_h7.bin.signed。""",
  },
  {
    "id": "builtin_git_lfs_fork",
    "title": "Git LFS：fork 拉取与不推送",
    "tags": ["git", "lfs", "push", "fork", "faq"],
    "refresh": True,
    "text": """本 fork LFS 策略：
- 拉取：.lfsconfig → GitLab sunnypilot-new-lfs（git lfs pull）
- 推送：不向 LFS 上传；git push 时 GIT_LFS_SKIP_PUSH=1
- op助手 git_push / git_publish_pull_request 已自动设置 GIT_LFS_SKIP_PUSH=1
- OpFont/training 图片在 .gitattributes 排除 LFS，走普通 Git

推送前：git lfs push --dry-run origin HEAD 应为 0 对象。
失败 Unprocessable entity → 设 GIT_LFS_SKIP_PUSH=1 或 git config lfs.allowincompletepush true

文档 ai/docs/GIT_LFS.md；技能 git-lfs-fork。""",
  },
  {
    "id": "builtin_headless_webui",
    "title": "无屏模式与 WebUI 操作",
    "tags": ["headless", "webui", "c3", "agnos", "wifi", "faq"],
    "refresh": True,
    "text": """无屏 C3：原生 ui 不启动，WebUI :5080 为主界面，op助手 :5090。

检测：OPENPILOT_HEADLESS=1；或 launch 脚本无触摸中断；Param WebuiHeadlessMode auto|on|off；API GET /api/opui/headless-mode。

无屏必知：AGNOS 升级走 WebUI Software→AGNOS 或 SSH agnos.py；manager 错误在 /tmp/manager_last_error.txt。

WebUI 15 设置面板：device network sunnylink toggles software models steering cruise visuals display osm trips vehicle firehose developer。

实时：WebSocket ws://IP:5080/ws/opui（state/home/panel/put_param）。

op助手工具：webui_health_check webui_headless_status webui_service_status；技能 headless-webui。
完整 API：ai/docs/HEADLESS_WEBUI.md""",
  },
  *load_json_builtin_docs(),
  *COMMA_DOCS_RAG,
  *SECOC_RAG,
  *WIKI_RAG,
]


def ensure_builtin_rag_docs(params: Params | None = None) -> dict[str, Any]:
  """Insert or refresh built-in FAQ docs (single load/save batch)."""
  params = params or Params()
  docs = _load_docs(params)
  by_id: dict[str, dict[str, Any]] = {str(d.get("id", "")): d for d in docs if d.get("id")}

  removed = 0
  for old_id in _DEPRECATED_BUILTIN_IDS:
    if old_id in by_id:
      by_id.pop(old_id, None)
      removed += 1

  seeded = 0
  refreshed = 0
  skipped = 0
  now = int(time.time())
  for doc in _BUILTIN_DOCS:
    doc_id = str(doc["id"])
    should_write = doc_id not in by_id or doc.get("refresh")
    if not should_write:
      skipped += 1
      continue
    text = str(doc.get("text") or "").strip()
    if not text:
      continue
    if len(text) > _MAX_DOC_CHARS:
      text = text[:_MAX_DOC_CHARS]
    prev = by_id.get(doc_id)
    by_id[doc_id] = {
      "id": doc_id,
      "title": str(doc.get("title") or "Untitled").strip(),
      "text": text,
      "tags": doc.get("tags") or [],
      "at": now,
      "embedded": bool(prev.get("embedded")) if prev else False,
      "chunk_count": int(prev.get("chunk_count") or 0) if prev else 0,
    }
    if prev:
      refreshed += 1
    else:
      seeded += 1

  _save_docs(params, list(by_id.values()))
  return {
    "ok": True,
    "seeded": seeded,
    "refreshed": refreshed,
    "removed": removed,
    "skipped": skipped,
    "total": len(_BUILTIN_DOCS),
    "stored": min(len(by_id), rag_max_docs()),
    "errors": [],
    "at": now,
  }
