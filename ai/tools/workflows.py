"""Structured workflow prompts for plan/execute modes."""

from __future__ import annotations

from typing import Any

WORKFLOWS: dict[str, dict[str, Any]] = {
  "konik_connect": {
    "name": "Konik 云配对",
    "mode": "execute",
    "steps": [
      "konik_connect_status",
      "konik_generate_device_keys if keys missing or cloned device",
      "konik_reset_dongle_id",
      "konik_register_device",
      "Remind user: open https://stable.konik.ai to scan QR",
    ],
    "prompt": (
      "执行 Konik Connect 一条龙（替代 comma connect）：先 konik_connect_status，"
      "offroad 下按需 konik_generate_device_keys(confirm=true)、konik_reset_dongle_id(confirm=true)、"
      "konik_register_device(confirm=true)；或直接用 konik_connect_pipeline(confirm=true)。"
      "勿输出完整私钥。完成后提示用户在 stable.konik.ai 扫码配对。"
    ),
  },
  "engage_triage": {
    "name": "无法 Engage 分诊",
    "mode": "execute",
    "steps": [
      "get_vehicle_state + read_onroad_events",
      "lookup_secoc_tier if Toyota/Lexus",
      "trip_review",
      "If carUnrecognized: extract_can_ids_from_route or cabana → compare_fingerprint",
      "Output numbered checklist with next human action",
    ],
    "prompt": (
      "执行「无法 Engage」工作流：按 engage-troubleshooting 技能顺序调用工具，"
      "先 SecOC → 指纹 → dashcam → LKAS，每步引用工具结果，最后给出检查表。"
    ),
  },
  "secoc_tsk": {
    "name": "丰田 SecOC 密钥",
    "mode": "execute",
    "steps": [
      "get_tsk_manager_status + lookup_secoc_tier",
      "If RAV4 Prime/Sienna: tsk_extract_key(confirm=true)",
      "Else if user has key: tsk_install_secoc_key or guide /?settings=secoc",
      "Else: tsk_run_pipeline(confirm=true) or tsk_start_can_collect → tsk_wait_for_job → tsk_start_dataflash_dump → tsk_wait_for_job → tsk_find_and_install_key",
      "reboot_device reminder; read_onroad_events verify",
    ],
    "prompt": (
      "执行丰田 SecOC 工作流（secoc-toyota 技能）：先 get_tsk_manager_status 与 lookup_secoc_tier，"
      "按 install_options 选一键提取、手动安装或 tsk_run_pipeline / CAN+DataFlash 查找；写操作 confirm=true 且 offroad；"
      "勿输出完整密钥；成功后提醒重启并 read_onroad_events。"
    ),
  },
  "vehicle_adaptation": {
    "name": "新车适配",
    "mode": "plan",
    "steps": [
      "list_dbcs + read_dbc_file",
      "Cabana 抓 CAN 或 extract_can_ids_from_route",
      "analyze_can_id_pattern + compare_fingerprint",
      "suggest_signals_for_adaptation",
      "get_adaptation_template → save_adaptation_draft 预览",
      "car_porting_auto_fingerprint / test_route / test_interfaces",
      "car_porting_steering_accuracy",
      "search_local_routes_for_can / search_car_segments",
    ],
    "prompt": (
      "执行「新车适配」工作流：从指纹五类 CAN 开始，对照 opendbc，"
      "生成草稿模板并说明封闭场地验证步骤。禁止直接改 opendbc。"
    ),
  },
  "cp_migration": {
    "name": "CP 迁移调优",
    "mode": "plan",
    "steps": [
      "search_knowledge_base(CP 参数名)",
      "list_dp_settings + snapshot_tune_state",
      "diff_params 预览映射",
      "静止后 write_params 或 apply_tune_preset",
    ],
    "prompt": (
      "用户从 Carrot/OpenPilotCP 迁移：启用 carrot-legacy 对照，"
      "将口述的 CP 参数映射到 dp_* / Dashy，禁止写 CP 专有 Param。"
    ),
  },
  "tune_session": {
    "name": "调优会话",
    "mode": "execute",
    "steps": [
      "snapshot_tune_state（自动保存快照）",
      "list_dp_settings + read_params",
      "提出 1–3 项改动并 diff_params",
      "静止确认后 write_params；失败则 restore_tune_snapshot",
    ],
    "prompt": (
      "执行调优会话：先快照，再读当前 dp_*，给出最小改动建议；"
      "写入前 diff；用户不满意可 rollback_last_tune。"
    ),
  },
  "tune_maneuver": {
    "name": "纵横向 Maneuver 报告",
    "mode": "plan",
    "steps": [
      "maneuver_mode_status（只读）",
      "long_maneuver_report / lat_maneuver_report",
      "plotjuggler_data_summary",
      "car_porting_steering_accuracy",
    ],
    "prompt": (
      "封闭场地 maneuver 路线分析：生成纵/横向 HTML 报告摘要，"
      "配合 plotjuggler_data_summary；禁止 AI 自动开启 ManeuverMode Param。"
    ),
  },
  "post_drive_review": {
    "name": "行程复盘",
    "mode": "execute",
    "steps": [
      "trip_review + suggest_tune_from_route",
      "post_drive_voice_summary",
      "update_agent_memory 摘要",
    ],
    "prompt": (
      "停车后复盘：trip_review 与路线调优建议，post_drive_voice_summary 简报，写入记忆。"
    ),
  },
  "compare_routes_tune": {
    "name": "调参前后路线对比",
    "mode": "plan",
    "steps": [
      "score_tune_session(route_before, route_after)",
      "compare_tune_ab(route_a, route_b)",
      "route_event_timeline on both routes if disengage issues",
      "list_tune_passport recent entries",
      "给出纵向/横向差异解读与下一步调参建议",
    ],
    "prompt": (
      "对比调参前后两条路线：先 score_tune_session，再 compare_tune_ab；"
      "若评分下降则建议 restore_tune_snapshot；禁止自动 write_params。"
    ),
  },
  "post_tune_validation": {
    "name": "调参后验证闭环",
    "mode": "execute",
    "steps": [
      "save_tune_snapshot(label=before)",
      "write_params or apply_tune_from_route with route_before/route_after",
      "score_tune_session",
      "compare_tune_ab",
      "list_tune_passport + list_audit_trail",
    ],
    "prompt": (
      "执行调参后验证闭环：快照→改参→量化评分→A/B 对比→审计。"
      "评分未通过则 restore_tune_snapshot。"
    ),
  },
  "batch_route_review": {
    "name": "近期路线批量复盘",
    "mode": "execute",
    "steps": [
      "batch_route_summary",
      "对异常路线 analyze_route_summary + plotjuggler_data_summary",
    ],
    "prompt": "列出最近路线摘要，对 vEgo 或信号异常的路线深入分析。",
  },
}


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
  return WORKFLOWS.get(workflow_id)


def list_workflows() -> list[dict[str, Any]]:
  return [
    {"id": wid, "name": w["name"], "mode": w.get("mode", "execute"), "steps": w.get("steps", [])}
    for wid, w in WORKFLOWS.items()
  ]


def workflow_system_prompt(workflow_id: str) -> str:
  w = WORKFLOWS.get(workflow_id)
  if not w:
    return ""
  steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(w.get("steps", [])))
  return (
    f"# Active workflow: {w['name']}\n"
    f"Follow these steps in order (use tools where noted):\n{steps}\n\n"
    f"{w.get('prompt', '')}"
  )
