"""
LLM tool schemas and handlers for op助手.

Imported by ai.aid — keeps aid.py focused on HTTP/SSE.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime
from typing import Any, Callable

from openpilot.common.params import Params

from ai.system.safety import is_action_allowed
from ai.system.admin import is_admin_mode
from ai.system.shell import ALLOWED_COMMANDS, run_command, run_shell_command
from ai.tools.dp_settings import list_dp_settings
from ai.tools.memory_store import append_note, delete_note, get_memory, update_vehicle_profile
from ai.tools.param_write import put_param
from ai.tools.params_policy import (
  catalog_summary,
  validate_write_batch,
)
from ai.tools.presets import TUNE_PRESETS, get_preset, list_presets
from ai.tools.diagnostics_tools import (
  analyze_route_summary,
  diff_params,
  fetch_dashy_settings,
  grep_log,
  read_manager_log,
  read_onroad_events,
  read_qlog_segment,
  snapshot_tune_state,
  trip_review,
)
from ai.tools.rag_store import list_documents, remove_document, search_documents, upsert_document, reindex_all
from ai.tools.write_pending import create_pending
from ai.tools.scheduler import list_tasks, remove_task, upsert_task
from ai.embedding import load_embedding_config
from ai.client import load_config_from_params

# Tool metadata for Web UI (enabled + driving flags)
TOOL_META: dict[str, dict[str, Any]] = {
  "get_vehicle_state": {"label": "车辆状态", "group": "read", "default_enabled": True, "driving": True},
  "read_params": {"label": "读取参数", "group": "read", "default_enabled": True, "driving": True},
  "list_dp_settings": {"label": "Dragonpilot 设置", "group": "read", "default_enabled": True, "driving": True},
  "get_params_catalog": {"label": "参数目录", "group": "read", "default_enabled": True, "driving": True},
  "get_agent_memory": {"label": "读取记忆", "group": "read", "default_enabled": True, "driving": True},
  "read_onroad_events": {"label": "onroad 事件", "group": "read", "default_enabled": True, "driving": True},
  "snapshot_tune_state": {"label": "调优快照", "group": "read", "default_enabled": True, "driving": True},
  "diff_params": {"label": "参数对比", "group": "read", "default_enabled": True, "driving": True},
  "fetch_dashy_settings": {"label": "Dashy 设置", "group": "read", "default_enabled": True, "driving": True},
  "read_manager_log": {"label": "Manager 日志", "group": "read", "default_enabled": True, "driving": True},
  "grep_log": {"label": "日志搜索", "group": "read", "default_enabled": True, "driving": True},
  "search_knowledge_base": {"label": "知识库检索", "group": "read", "default_enabled": True, "driving": True},
  "get_full_vehicle_state": {"label": "完整状态 JSON", "group": "read", "default_enabled": True, "driving": True},
  "list_drive_routes": {"label": "行车路线列表", "group": "read", "default_enabled": True, "driving": True},
  "analyze_route_summary": {"label": "路线摘要", "group": "read", "default_enabled": True, "driving": True},
  "read_qlog_segment": {"label": "路线日志片段", "group": "read", "default_enabled": True, "driving": True},
  "trip_review": {"label": "行程复盘", "group": "read", "default_enabled": True, "driving": True},
  "list_tune_presets": {"label": "调优预设列表", "group": "read", "default_enabled": True, "driving": True},
  "list_scheduled_tasks": {"label": "定时任务列表", "group": "read", "default_enabled": True, "driving": True},
  "list_knowledge_docs": {"label": "知识库列表", "group": "read", "default_enabled": True, "driving": True},
  "cabana_explain_signal": {"label": "CAN 信号解释", "group": "read", "default_enabled": True, "driving": True},
  "cabana_analyze": {"label": "CAN AI 分析", "group": "read", "default_enabled": True, "driving": True},
  "list_dbcs": {"label": "DBC 列表", "group": "read", "default_enabled": True, "driving": True},
  "read_dbc_file": {"label": "读取 DBC", "group": "read", "default_enabled": True, "driving": True},
  "list_adaptation_projects": {"label": "适配草稿列表", "group": "read", "default_enabled": True, "driving": True},
  "export_adaptation_bundle": {"label": "导出适配包", "group": "read", "default_enabled": True, "driving": True},
  "analyze_can_id_pattern": {"label": "CAN ID 分析", "group": "read", "default_enabled": True, "driving": True},
  "compare_fingerprint": {"label": "指纹对照", "group": "read", "default_enabled": True, "driving": True},
  "suggest_signals_for_adaptation": {"label": "适配信号推荐", "group": "read", "default_enabled": True, "driving": True},
  "get_adaptation_template": {"label": "适配代码模板", "group": "read", "default_enabled": True, "driving": True},
  "extract_can_ids_from_route": {"label": "路线 CAN 指纹", "group": "read", "default_enabled": True, "driving": True},
  "car_porting_auto_fingerprint": {"label": "car_porting 固件指纹", "group": "read", "default_enabled": True, "driving": True},
  "car_porting_test_route": {"label": "car_porting 车型测试", "group": "read", "default_enabled": True, "driving": False},
  "car_porting_fingerprint_to_draft": {"label": "固件指纹存草稿", "group": "write", "default_enabled": True, "driving": False},
  "car_porting_test_interfaces": {"label": "car_porting 接口测试", "group": "read", "default_enabled": True, "driving": False},
  "car_porting_steering_accuracy": {"label": "转向精度分析", "group": "read", "default_enabled": True, "driving": True},
  "car_porting_search_segments_by_can": {"label": "公有库 CAN 搜段", "group": "read", "default_enabled": True, "driving": False},
  "long_maneuver_report": {"label": "纵向 maneuver 报告", "group": "read", "default_enabled": True, "driving": False},
  "mpc_longitudinal_tuning_report": {"label": "MPC 纵向仿真报告", "group": "read", "default_enabled": True, "driving": False},
  "lat_maneuver_report": {"label": "横向 maneuver 报告", "group": "read", "default_enabled": True, "driving": False},
  "maneuver_mode_status": {"label": "Maneuver 模式状态", "group": "read", "default_enabled": True, "driving": True},
  "route_time_series": {"label": "路线时序数据", "group": "read", "default_enabled": True, "driving": True},
  "route_fetch_frame": {"label": "路线抽帧", "group": "read", "default_enabled": True, "driving": True},
  "route_video_info": {"label": "路线视频信息", "group": "read", "default_enabled": True, "driving": True},
  "search_local_routes_for_can": {"label": "本地路线搜 CAN", "group": "read", "default_enabled": True, "driving": True},
  "comma_auth_status": {"label": "Comma 登录状态", "group": "read", "default_enabled": True, "driving": True},
  "search_car_segments": {"label": "公有 segment 库", "group": "read", "default_enabled": True, "driving": False},
  "read_bootlog": {"label": "Bootlog 列表", "group": "read", "default_enabled": True, "driving": True},
  "plotjuggler_data_summary": {"label": "PlotJuggler 摘要", "group": "read", "default_enabled": True, "driving": True},
  "read_dbc_platform_map": {"label": "平台 DBC 映射", "group": "read", "default_enabled": True, "driving": True},
  "get_host_environment": {"label": "运行环境", "group": "read", "default_enabled": True, "driving": True},
  "pc_launch_plotjuggler": {"label": "PC PlotJuggler", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_replay": {"label": "PC Replay", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_cabana": {"label": "PC Cabana", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_sim_bridge": {"label": "PC 仿真桥", "group": "read", "default_enabled": False, "driving": False, "pc_only": True},
  "pc_auth_login_hint": {"label": "PC Comma 登录", "group": "read", "default_enabled": True, "driving": True, "pc_only": True},
  "pc_capture_route_context": {"label": "PC 路线数据快照", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_list_tool_sessions": {"label": "PC 工具会话列表", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_get_tool_session": {"label": "PC 工具会话详情", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_jotpluggler": {"label": "PC JotPluggler", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_replay_stream": {"label": "PC Replay ZMQ", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_plotjuggler_stream": {"label": "PC PlotJuggler 流", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_jotpluggler_stream": {"label": "PC JotPluggler 流", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_replay_viz_stream": {"label": "PC Replay+可视化流", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_replay_ui": {"label": "PC Replay UI", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "pc_launch_camerastream": {"label": "PC 摄像头流", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "route_export_clip": {"label": "导出路线视频", "group": "read", "default_enabled": True, "driving": False},
  "route_extract_audio": {"label": "导出路线音频", "group": "read", "default_enabled": True, "driving": False},
  "route_ublox_summary": {"label": "Ublox 摘要", "group": "read", "default_enabled": True, "driving": True},
  "route_can_stats": {"label": "路线 CAN 统计", "group": "read", "default_enabled": True, "driving": True},
  "compare_route_signals": {"label": "路线信号对比", "group": "read", "default_enabled": True, "driving": False},
  "batch_route_summary": {"label": "批量路线摘要", "group": "read", "default_enabled": True, "driving": True},
  "search_route_messages": {"label": "路线消息搜索", "group": "read", "default_enabled": True, "driving": True},
  "list_plotjuggler_layouts": {"label": "PlotJuggler 布局", "group": "read", "default_enabled": True, "driving": True},
  "list_jotpluggler_layouts": {"label": "JotPluggler 布局", "group": "read", "default_enabled": True, "driving": True},
  "get_build_info": {"label": "构建信息", "group": "read", "default_enabled": True, "driving": True},
  "list_managed_processes": {"label": "进程列表", "group": "read", "default_enabled": True, "driving": True},
  "maneuversd_status": {"label": "Maneuver 守护进程", "group": "read", "default_enabled": True, "driving": True},
  "get_webcam_dev_setup": {"label": "Webcam 开发指引", "group": "read", "default_enabled": True, "driving": True, "pc_only": True},
  "get_devsync_hint": {"label": "Devsync 同步指引", "group": "read", "default_enabled": True, "driving": True, "pc_only": True},
  "pc_devsync_status": {"label": "Devsync 同步体检", "group": "read", "default_enabled": True, "driving": True, "pc_only": True},
  "openpilotci_segment_url": {"label": "OpenpilotCI URL", "group": "read", "default_enabled": True, "driving": True},
  "live_cereal_summary": {"label": "实时 cereal 摘要", "group": "read", "default_enabled": True, "driving": False},
  "lookup_secoc_tier": {"label": "SecOC 档位", "group": "read", "default_enabled": True, "driving": True},
  "suggest_tune_from_route": {"label": "路线调优建议", "group": "read", "default_enabled": True, "driving": True},
  "save_tune_snapshot": {"label": "保存调优快照", "group": "write", "default_enabled": True, "driving": False},
  "restore_tune_snapshot": {"label": "恢复调优快照", "group": "write", "default_enabled": True, "driving": True},
  "list_tune_snapshots": {"label": "调优快照列表", "group": "read", "default_enabled": True, "driving": True},
  "reindex_knowledge_base": {"label": "重建向量索引", "group": "config", "default_enabled": True, "driving": True},
  "write_params": {"label": "写入参数", "group": "write", "default_enabled": True, "driving": True},
  "apply_tune_preset": {"label": "应用调优预设", "group": "write", "default_enabled": True, "driving": True},
  "select_driving_model": {"label": "切换驾驶模型", "group": "write", "default_enabled": True, "driving": True},
  "update_agent_memory": {"label": "更新记忆", "group": "memory", "default_enabled": True, "driving": True},
  "manage_knowledge_doc": {"label": "管理知识库", "group": "memory", "default_enabled": True, "driving": True},
  "manage_scheduled_task": {"label": "管理定时任务", "group": "config", "default_enabled": True, "driving": True},
  "save_adaptation_draft": {"label": "保存适配草稿", "group": "write", "default_enabled": True, "driving": True},
  "run_shell": {"label": "终端诊断", "group": "shell", "default_enabled": True, "driving": True},
  "run_shell_command": {"label": "任意 Shell", "group": "shell", "default_enabled": True, "driving": True},
  "read_file": {"label": "读文件", "group": "fs", "default_enabled": True, "driving": True},
  "write_file": {"label": "写文件", "group": "fs", "default_enabled": True, "driving": True},
  "list_directory": {"label": "列目录", "group": "fs", "default_enabled": True, "driving": True},
  "restart_service": {"label": "重启服务", "group": "shell", "default_enabled": True, "driving": True},
  "restart_ui": {"label": "重启 UI", "group": "shell", "default_enabled": True, "driving": True},
}

from ai.tools.extensions import EXTENSION_TOOL_META  # noqa: E402

TOOL_META.update(EXTENSION_TOOL_META)

READ_ONLY_TOOLS = frozenset(
  n for n, m in TOOL_META.items() if m.get("group") == "read"
)


def tool_meta_for_host() -> dict[str, dict[str, Any]]:
  try:
    from ai.system.host_env import is_pc_dev
    pc_dev = is_pc_dev()
  except Exception:
    pc_dev = os.name == "nt" or not os.path.isfile("/TICI")
  filtered = {
    name: meta
    for name, meta in TOOL_META.items()
    if not meta.get("pc_only") or pc_dev
  }
  from ai.tools.tool_ui_meta import enrich_tool_meta_for_ui
  return enrich_tool_meta_for_ui(filtered)


_RESTARTABLE_SERVICES = frozenset({"aid", "ui", "manager", "selfdrive/ui"})

from ai.tools.op_run import ROUTES_DIR as _ROUTES_DIR  # noqa: E402


def build_tool_schemas() -> list[dict[str, Any]]:
  shell_cmds = ", ".join(sorted(ALLOWED_COMMANDS.keys()))
  schemas = [
    {"type": "function", "function": {"name": "get_vehicle_state", "description": "Read current vehicle/openpilot snapshot (speed, engage, alerts, faults, events, device health).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_full_vehicle_state", "description": "Read detailed cereal JSON: carState, carParams, selfdriveState, controlsState, deviceState, pandaStates, processes, events.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "read_params", "description": "Read comma-separated Params keys.", "parameters": {"type": "object", "properties": {"keys": {"type": "string"}}, "required": ["keys"]}}},
    {"type": "function", "function": {"name": "list_dp_settings", "description": "List Dragonpilot tunable settings with titles, descriptions, and current values for this vehicle brand.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_params_catalog", "description": "Get AI param safety catalog (tier, section, summary).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "list_tune_presets", "description": "List Dragonpilot tune presets (comfort_follow, alka_enable, etc.).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "write_params", "description": "Write Params while stationary. JSON object key->value. Optional regression guard via route_before/route_after.", "parameters": {"type": "object", "properties": {"params": {"type": "object", "additionalProperties": True}, "confirm": {"type": "boolean", "description": "Must be true to apply."}, "route_before": {"type": "string"}, "route_after": {"type": "string"}, "skip_regression_check": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
    {"type": "function", "function": {"name": "apply_tune_preset", "description": "Apply a named tune preset while stationary.", "parameters": {"type": "object", "properties": {"preset_id": {"type": "string"}, "confirm": {"type": "boolean"}, "route_before": {"type": "string"}, "route_after": {"type": "string"}, "skip_regression_check": {"type": "boolean"}}, "required": ["preset_id", "confirm"]}}},
    {"type": "function", "function": {"name": "select_driving_model", "description": "Set dp_dev_model_selected (empty string = AUTO). Stationary only.", "parameters": {"type": "object", "properties": {"model": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["model", "confirm"]}}},
    {"type": "function", "function": {"name": "get_agent_memory", "description": "Read long-term notes and vehicle profile stored on device.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "update_agent_memory", "description": "Append a note and/or update vehicle profile fields.", "parameters": {"type": "object", "properties": {"note": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "vehicle_profile": {"type": "object"}}, "required": []}}},
    {"type": "function", "function": {"name": "list_scheduled_tasks", "description": "List scheduled agent tasks.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "manage_scheduled_task", "description": "Create/update/remove a scheduled task.", "parameters": {"type": "object", "properties": {"operation": {"type": "string", "enum": ["upsert", "remove"]}, "task_id": {"type": "string"}, "name": {"type": "string"}, "action": {"type": "string"}, "trigger": {"type": "string", "enum": ["interval", "on_offroad", "on_ignition", "on_wifi", "daily_at"]}, "interval_minutes": {"type": "integer"}, "enabled": {"type": "boolean"}, "payload": {"type": "object", "description": "For daily_at: {hour, minute}"}}, "required": ["operation"]}}},
    {"type": "function", "function": {"name": "list_drive_routes", "description": "List recent drive log route folders under /data/media/0/realdata.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "analyze_route_summary", "description": "Summarize a drive route (date, qlog/rlog segments, file counts).", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}}, "required": ["route_name"]}}},
    {"type": "function", "function": {"name": "read_qlog_segment", "description": "Read CAN frames and car/controls state from a route time window (qlog or rlog). Use after Cabana or analyze_route_summary.", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}, "start_sec": {"type": "number", "description": "Seconds from route start"}, "end_sec": {"type": "number"}, "topics": {"type": "array", "items": {"type": "string"}, "description": "can, carState, controlsState, selfdriveState, onroadEvents"}, "max_messages": {"type": "integer"}}, "required": ["route_name"]}}},
    {"type": "function", "function": {"name": "trip_review", "description": "Structured trip/engage review: events, SecOC hints, tune snapshot, route, log matches, recommendations.", "parameters": {"type": "object", "properties": {"route_name": {"type": "string", "description": "Optional route folder name; latest route if omitted."}}, "required": []}}},
    {"type": "function", "function": {"name": "read_onroad_events", "description": "Read current onroad events with severity flags.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "snapshot_tune_state", "description": "Export tune-related dp_* params; set save_snapshot=true to persist for rollback.", "parameters": {"type": "object", "properties": {"save_snapshot": {"type": "boolean"}, "label": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "diff_params", "description": "Compare proposed param writes vs current values (no write).", "parameters": {"type": "object", "properties": {"params": {"type": "object"}}, "required": ["params"]}}},
    {"type": "function", "function": {"name": "fetch_dashy_settings", "description": "Fetch Dashy Web UI settings from localhost:5088.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "read_manager_log", "description": "Read recent manager / device error log.", "parameters": {"type": "object", "properties": {"lines": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "grep_log", "description": "Regex search in recent manager log.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "lines": {"type": "integer"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "search_knowledge_base", "description": "Semantic (vector) or keyword search in user knowledge base.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}, "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by doc tags e.g. dragonpilot, toyota"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "reindex_knowledge_base", "description": "Rebuild cloud embedding index for all knowledge docs (stationary, needs WiFi).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "list_knowledge_docs", "description": "List knowledge base document titles.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "manage_knowledge_doc", "description": "Add/update/remove a knowledge document.", "parameters": {"type": "object", "properties": {"operation": {"type": "string", "enum": ["upsert", "remove"]}, "doc_id": {"type": "string"}, "title": {"type": "string"}, "text": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["operation"]}}},
    {"type": "function", "function": {"name": "cabana_explain_signal", "description": "Explain a CAN signal in plain language (read-only).", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "signal": {"type": "string"}, "address": {"type": "string"}, "value": {"type": "string"}, "dbc": {"type": "string"}, "decoded": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "cabana_analyze", "description": "Analyze CAN frames with AI. Pass user question and optional frame text.", "parameters": {"type": "object", "properties": {"question": {"type": "string"}, "frames_text": {"type": "string"}}, "required": ["question"]}}},
    {"type": "function", "function": {"name": "list_dbcs", "description": "List available DBC files in opendbc (read-only).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "read_dbc_file", "description": "Read a DBC file content and signal preview (read-only).", "parameters": {"type": "object", "properties": {"dbc_name": {"type": "string"}}, "required": ["dbc_name"]}}},
    {"type": "function", "function": {"name": "list_adaptation_projects", "description": "List vehicle adaptation draft projects on device.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "save_adaptation_draft", "description": "Save DBC/CarState/CarController snippets to adaptation_drafts/ (NOT opendbc). Stationary; confirm=true to apply.", "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}, "fingerprint": {"type": "string"}, "files": {"type": "object", "additionalProperties": {"type": "string"}}, "notes": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["project_id", "files", "confirm"]}}},
    {"type": "function", "function": {"name": "export_adaptation_bundle", "description": "Export adaptation draft files + PR checklist for dev machine merge.", "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}}},
    {"type": "function", "function": {"name": "analyze_can_id_pattern", "description": "Summarize CAN IDs for fingerprint brainstorming.", "parameters": {"type": "object", "properties": {"hex_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["hex_ids"]}}},
    {"type": "function", "function": {"name": "compare_fingerprint", "description": "Compare observed CAN IDs against opendbc fingerprints.", "parameters": {"type": "object", "properties": {"hex_ids": {"type": "array", "items": {"type": "string"}}, "brand": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "suggest_signals_for_adaptation", "description": "Suggest DBC signals for speed/steer/brake/gas/gear classes.", "parameters": {"type": "object", "properties": {"dbc_name": {"type": "string"}}, "required": ["dbc_name"]}}},
    {"type": "function", "function": {"name": "get_adaptation_template", "description": "Get CarState/CarController/fingerprint draft templates.", "parameters": {"type": "object", "properties": {"brand": {"type": "string"}, "model_name": {"type": "string"}, "fingerprint": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "extract_can_ids_from_route", "description": "Extract unique CAN IDs from route qlog/rlog + fingerprint compare.", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}}, "required": ["route_name"]}}},
    {"type": "function", "function": {"name": "car_porting_auto_fingerprint", "description": "Run tools/car_porting/auto_fingerprint.py on a route: extract FW versions from carParams (read-only, for opendbc merge on PC).", "parameters": {"type": "object", "properties": {"route": {"type": "string", "description": "Route folder name or LogReader segment (e.g. dongle|date--time/0)"}, "platform": {"type": "string", "description": "Optional car platform override (e.g. TOYOTA_COROLLA)"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "car_porting_test_route", "description": "Run tools/car_porting/test_car_model.py (TestCarModel unittest) on a route. Stationary; may take several minutes.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "car_model": {"type": "string", "description": "Car platform for test route (--car)"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "car_porting_fingerprint_to_draft", "description": "auto_fingerprint output saved to adaptation_drafts/ (NOT opendbc). Stationary; confirm=true to apply.", "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}, "route": {"type": "string"}, "platform": {"type": "string"}, "notes": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["project_id", "route", "confirm"]}}},
    {"type": "function", "function": {"name": "car_porting_test_interfaces", "description": "Run pytest selfdrive/car/tests/test_car_interfaces.py (optional -k brand). Stationary.", "parameters": {"type": "object", "properties": {"brand": {"type": "string", "description": "pytest -k filter, e.g. toyota, subaru"}}, "required": []}}},
    {"type": "function", "function": {"name": "car_porting_steering_accuracy", "description": "Steering tracking accuracy stats from route (tools/car_porting/measure_steering_accuracy.py).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "group": {"type": "string", "description": "crawl|slow|medium|fast|veryfast|germany|all"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "car_porting_search_segments_by_can", "description": "Search commaCarSegments public DB for segments containing all CAN IDs. Needs network.", "parameters": {"type": "object", "properties": {"hex_ids": {"type": "array", "items": {"type": "string"}}, "platform": {"type": "string"}, "segment_limit": {"type": "integer"}}, "required": ["hex_ids", "platform"]}}},
    {"type": "function", "function": {"name": "long_maneuver_report", "description": "Generate longitudinal maneuver HTML report (tools/longitudinal_maneuvers/generate_report.py). Stationary.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "description": {"type": "string"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "mpc_longitudinal_tuning_report", "description": "Generate MPC longitudinal simulation HTML report (no route). Stationary; may take minutes.", "parameters": {"type": "object", "properties": {"output_path": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "lat_maneuver_report", "description": "Generate lateral maneuver HTML report (tools/lateral_maneuvers/generate_report.py). Stationary.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "description": {"type": "string"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "maneuver_mode_status", "description": "Read LongitudinalManeuverMode / LateralManeuverMode params (read-only).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "route_time_series", "description": "Extract downsampled time series from route logs (tools/lib/log_time_series).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "topics": {"type": "array", "items": {"type": "string"}}, "max_messages": {"type": "integer"}, "max_points": {"type": "integer"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "route_fetch_frame", "description": "Extract JPEG frame from route video (local or comma API).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "segment": {"type": "integer"}, "frame": {"type": "integer"}, "camera": {"type": "string", "enum": ["front", "wide", "driver"]}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "route_video_info", "description": "List video files and frame counts for a local route.", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}}, "required": ["route_name"]}}},
    {"type": "function", "function": {"name": "search_local_routes_for_can", "description": "Find recent local routes containing all given CAN IDs.", "parameters": {"type": "object", "properties": {"hex_ids": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer"}}, "required": ["hex_ids"]}}},
    {"type": "function", "function": {"name": "comma_auth_status", "description": "Check comma API auth token status (tools/lib/auth.py).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "search_car_segments", "description": "List commaCarSegments public segments for a platform or all platforms.", "parameters": {"type": "object", "properties": {"platform": {"type": "string"}, "limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "read_bootlog", "description": "List device bootlogs from comma API (tools/lib/bootlog.py).", "parameters": {"type": "object", "properties": {"dongle_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "plotjuggler_data_summary", "description": "Signal min/max/mean summary without PlotJuggler GUI.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "topics": {"type": "array", "items": {"type": "string"}}, "max_messages": {"type": "integer"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "read_dbc_platform_map", "description": "Platform to DBC name mapping (tools/cabana/dbc/generate_dbc_json.py).", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_host_environment", "description": "Detect host: comma C3/C3X/C4 or PC dev; hardware_profile includes Panda MCU (PC probes via panda_tici), manager/pandad status, and pc_tools inventory.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_plotjuggler", "description": "PC only: launch tools/plotjuggler/juggle.py GUI for a route (Ubuntu 24.04 dev).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "layout": {"type": "string"}, "parse_can": {"type": "boolean"}, "demo": {"type": "boolean"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_replay", "description": "PC only: launch tools/replay/replay (requires scons build). Stationary.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "demo": {"type": "boolean"}, "data_dir": {"type": "string"}, "speed": {"type": "number"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_cabana", "description": "PC only: launch desktop tools/cabana/cabana (requires scons build).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "demo": {"type": "boolean"}, "data_dir": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_sim_bridge", "description": "PC only: launch MetaDrive sim bridge (tools/sim/run_bridge.py). Dev only, not with real car.", "parameters": {"type": "object", "properties": {"joystick": {"type": "boolean"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_capture_route_context", "description": "PC only: capture route carParams, topics, signal stats — same data PlotJuggler/Replay/Cabana load (no GUI).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "include_signal_summary": {"type": "boolean"}, "include_topics": {"type": "boolean"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "pc_list_tool_sessions", "description": "PC only: list recent pc_launch_* sessions with launch params and whether process is still alive.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_get_tool_session", "description": "PC only: get session launch params, pid status, and captured route data snapshot.", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "refresh_process": {"type": "boolean"}, "refresh_data": {"type": "boolean"}}, "required": ["session_id"]}}},
    {"type": "function", "function": {"name": "pc_launch_jotpluggler", "description": "PC only: launch tools/jotpluggler/jotpluggler for a route (requires scons build).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "layout": {"type": "string"}, "demo": {"type": "boolean"}, "data_dir": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_replay_stream", "description": "PC only: replay route with ZMQ=1 in background (publisher for stream viz).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "demo": {"type": "boolean"}, "data_dir": {"type": "string"}, "speed": {"type": "number"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_plotjuggler_stream", "description": "PC only: PlotJuggler --stream (ZMQ subscriber). Start replay stream or device bridge first.", "parameters": {"type": "object", "properties": {"layout": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_jotpluggler_stream", "description": "PC only: JotPluggler --stream --show (ZMQ). Start replay stream or device bridge first.", "parameters": {"type": "object", "properties": {"address": {"type": "string"}, "buffer_seconds": {"type": "number"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_replay_viz_stream", "description": "PC only: start ZMQ replay + plotjuggler or jotpluggler stream viz together.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "demo": {"type": "boolean"}, "viz": {"type": "string", "description": "plotjuggler or jotpluggler"}, "layout": {"type": "string"}, "speed": {"type": "number"}, "data_dir": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_replay_ui", "description": "PC only: launch tools/replay/ui.py debug UI (ZMQ).", "parameters": {"type": "object", "properties": {"address": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_launch_camerastream", "description": "PC only: tools/camerastream/compressed_vipc.py decode remote cameras.", "parameters": {"type": "object", "properties": {"device_addr": {"type": "string"}, "cams": {"type": "string"}, "nvidia": {"type": "boolean"}}, "required": ["device_addr"]}}},
    {"type": "function", "function": {"name": "route_export_clip", "description": "Export route video clip MP4 (tools/clip/run.py). Stationary.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "start_sec": {"type": "integer"}, "end_sec": {"type": "integer"}, "demo": {"type": "boolean"}, "output": {"type": "string"}, "data_dir": {"type": "string"}, "title": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "route_extract_audio", "description": "Extract rawAudioData to WAV from route.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "output": {"type": "string"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "route_ublox_summary", "description": "Summarize ubloxRaw messages in route.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "max_messages": {"type": "integer"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "route_can_stats", "description": "Read-only CAN ID stats from route (no hardware replay).", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "max_batches": {"type": "integer"}}, "required": ["route"]}}},
    {"type": "function", "function": {"name": "compare_route_signals", "description": "Compare signal stats between two routes.", "parameters": {"type": "object", "properties": {"route_a": {"type": "string"}, "route_b": {"type": "string"}, "topics": {"type": "array", "items": {"type": "string"}}}, "required": ["route_a", "route_b"]}}},
    {"type": "function", "function": {"name": "batch_route_summary", "description": "Summarize N most recent local routes.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "search_route_messages", "description": "Count/search cereal message type in a route.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "message_type": {"type": "string"}, "max_hits": {"type": "integer"}}, "required": ["route", "message_type"]}}},
    {"type": "function", "function": {"name": "list_plotjuggler_layouts", "description": "List tools/plotjuggler/layouts XML files.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "list_jotpluggler_layouts", "description": "List tools/jotpluggler/layouts JSON files.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_build_info", "description": "Git commit, models, CarParams version info.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "list_managed_processes", "description": "List managerState processes and health.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "maneuversd_status", "description": "Maneuver mode params + maneuversd process status.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_webcam_dev_setup", "description": "PC webcam openpilot dev setup instructions.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_devsync_hint", "description": "PC to device devsync.rsyn instructions (manual).", "parameters": {"type": "object", "properties": {"device_ip": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_devsync_status", "description": "PC only: read-only devsync preflight (rsync/git/ssh, optional SSH probe to comma device). Does not sync.", "parameters": {"type": "object", "properties": {"device_ip": {"type": "string"}, "remote_path": {"type": "string"}, "identity": {"type": "string"}, "probe_ssh": {"type": "boolean"}}, "required": []}}},
    {"type": "function", "function": {"name": "openpilotci_segment_url", "description": "Build openpilotci blob URL for a segment file.", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}, "segment": {"type": "integer"}, "filename": {"type": "string"}}, "required": ["route_name", "segment", "filename"]}}},
    {"type": "function", "function": {"name": "live_cereal_summary", "description": "Short live ZMQ cereal sample (read-only).", "parameters": {"type": "object", "properties": {"services": {"type": "array", "items": {"type": "string"}}, "addr": {"type": "string"}, "duration_sec": {"type": "number"}, "max_messages": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "pc_auth_login_hint", "description": "PC only: how to run tools/lib/auth.py for comma connect login.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "lookup_secoc_tier", "description": "Lookup Toyota/Lexus SecOC support tier (read-only).", "parameters": {"type": "object", "properties": {"car_fingerprint": {"type": "string"}, "brand": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "suggest_tune_from_route", "description": "Route-based tune suggestions (read-only).", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "save_tune_snapshot", "description": "Save current dp_* tune params for rollback.", "parameters": {"type": "object", "properties": {"label": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "restore_tune_snapshot", "description": "Restore tune params from snapshot (stationary).", "parameters": {"type": "object", "properties": {"snapshot_id": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["confirm"]}}},
    {"type": "function", "function": {"name": "list_tune_snapshots", "description": "List saved tune snapshots.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "run_shell", "description": f"Run whitelisted diagnostic command: {shell_cmds}.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "enum": sorted(ALLOWED_COMMANDS.keys())}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "run_shell_command", "description": "Admin: run arbitrary shell command on openpilot/AGNOS host (cwd=openpilot root).", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Admin: read a text file under openpilot repo or /data (AGNOS).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Admin: write a text file under openpilot repo or /data (AGNOS).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "Admin: list directory under openpilot repo or /data (AGNOS).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "restart_service", "description": "Restart aid/ui/manager (stationary).", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "restart_ui", "description": "Restart openpilot UI (stationary).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  ]
  from ai.tools.extensions import EXTENSION_SCHEMAS
  return schemas + EXTENSION_SCHEMAS


AVAILABLE_TOOLS = build_tool_schemas()


def filter_tools(
  enabled: bool,
  tool_prefs: dict[str, Any],
  *,
  driving: bool,
  admin: bool = False,
) -> list[dict[str, Any]] | None:
  if not enabled:
    return None
  try:
    from ai.system.host_env import is_pc_dev
    pc_dev = is_pc_dev()
  except Exception:
    pc_dev = os.name == "nt" or not os.path.isfile("/TICI")

  out: list[dict[str, Any]] = []
  for tool in AVAILABLE_TOOLS:
    name = tool.get("function", {}).get("name", "")
    meta = TOOL_META.get(name, {})
    if tool_prefs and name in tool_prefs:
      pref = tool_prefs.get(name)
      if pref is False or pref == "off" or pref == 0:
        continue
    if meta.get("pc_only") and not pc_dev:
      continue
    if driving and not admin:
      allow = name in READ_ONLY_TOOLS or meta.get("driving") is True
      if not allow:
        continue
    out.append(tool)
  return out or None


def make_handlers(
  *,
  get_state_reader,
  params: Params | None = None,
) -> dict[str, Callable[[dict[str, Any]], Any]]:
  """Factory — inject state accessors from aid."""
  p = params or Params()
  admin = is_admin_mode(p)

  def _embedding_cfg():
    chat = load_config_from_params(p)
    return load_embedding_config(p, chat)

  def _stationary_check(action: str):
    state = get_state_reader().update(timeout=0)
    allowed, reason = is_action_allowed(action, state, admin=admin)
    if not allowed:
      return {"ok": False, "error": reason}
    return None

  def _needs_confirm() -> bool:
    return not admin

  def h_get_vehicle_state(_a):
    reader = get_state_reader()
    reader.update(timeout=0)
    return reader.latest().get("vehicle", reader.snapshot().to_dict())

  def h_get_full_vehicle_state(_a):
    reader = get_state_reader()
    reader.update(timeout=0)
    return reader.latest()

  def h_read_params(args):
    keys = [k.strip() for k in args.get("keys", "").split(",") if k.strip()]
    values = {}
    for key in keys:
      try:
        val = p.get(key)
      except Exception:
        values[key] = None
        continue
      if isinstance(val, bytes):
        val = val.decode(errors="replace")
      values[key] = val
    return {"keys": values}

  def h_list_dp_settings(_a):
    state = get_state_reader().update(timeout=0)
    brand = getattr(state, "brand", "") or ""
    return list_dp_settings(p, brand=brand)

  def h_get_params_catalog(_a):
    return {"ok": True, "params": catalog_summary()}

  def h_list_tune_presets(_a):
    return {"ok": True, "presets": list_presets()}

  def h_write_params(args):
    err = _stationary_check("write_param")
    if err:
      return err
    writes = args.get("params") or {}
    if not isinstance(writes, dict):
      return {"ok": False, "error": "params must be an object"}
    if not args.get("confirm"):
      if not _needs_confirm():
        pass
      else:
        preview = diff_params(p, writes).get("changes", {})
        state = get_state_reader().update(timeout=0)
        return create_pending(
          p,
          action="write_params",
          payload={
            "params": writes,
            "route_before": str(args.get("route_before", "") or ""),
            "route_after": str(args.get("route_after", "") or ""),
            "skip_regression_check": bool(args.get("skip_regression_check")),
            "brand": getattr(state, "brand", "") or "",
          },
          preview=preview,
        )
    from ai.tools.tune_write_pipeline import apply_param_writes
    state = get_state_reader().update(timeout=0)
    return apply_param_writes(
      p,
      writes,
      action="write_params",
      brand=getattr(state, "brand", "") or "",
      route_before=str(args.get("route_before", "") or ""),
      route_after=str(args.get("route_after", "") or ""),
      skip_regression_check=bool(args.get("skip_regression_check")),
      snapshot_label="auto_before_write",
      admin=admin,
    )

  def h_apply_tune_preset(args):
    err = _stationary_check("write_param")
    if err:
      return err
    preset_id = str(args.get("preset_id", ""))
    preset = get_preset(preset_id)
    if not preset:
      return {"ok": False, "error": "Unknown preset_id"}
    if preset.get("rollback"):
      if not args.get("confirm") and _needs_confirm():
        from ai.tools.tune_snapshot_store import list_tune_snapshots
        return create_pending(
          p,
          action="restore_tune_snapshot",
          payload={"snapshot_id": ""},
          preview={"rollback": True, "snapshots": list_tune_snapshots().get("snapshots", [])[:3]},
        )
      from ai.tools.tune_snapshot_store import restore_tune_snapshot
      return restore_tune_snapshot(p)
    if not args.get("confirm"):
      if _needs_confirm():
        preview = diff_params(p, preset["params"]).get("changes", {})
        state = get_state_reader().update(timeout=0)
        return create_pending(
          p,
          action="apply_tune_preset",
          payload={
            "preset_id": preset_id,
            "brand": getattr(state, "brand", "") or "",
            "route_before": str(args.get("route_before", "") or ""),
            "route_after": str(args.get("route_after", "") or ""),
            "skip_regression_check": bool(args.get("skip_regression_check")),
          },
          preview=preview,
        )
    from ai.tools.tune_write_pipeline import apply_param_writes
    state = get_state_reader().update(timeout=0)
    return apply_param_writes(
      p,
      preset["params"],
      action="apply_tune_preset",
      brand=getattr(state, "brand", "") or "",
      route_before=str(args.get("route_before", "") or ""),
      route_after=str(args.get("route_after", "") or ""),
      skip_regression_check=bool(args.get("skip_regression_check")),
      snapshot_label=f"auto_before_{preset_id}",
      preset_id=preset_id,
      admin=admin,
    )

  def h_select_driving_model(args):
    err = _stationary_check("write_param")
    if err:
      return err
    model = str(args.get("model", ""))
    if not args.get("confirm"):
      if _needs_confirm():
        preview = diff_params(p, {"dp_dev_model_selected": model}).get("changes", {})
        return create_pending(p, action="select_driving_model", payload={"model": model}, preview=preview)
    put_param(p, "dp_dev_model_selected", model)
    return {"ok": True, "model": model, "hint": "Re-engage or restart UI if model does not switch."}

  def h_get_agent_memory(_a):
    return get_memory(p)

  def h_update_agent_memory(args):
    out: dict[str, Any] = {"ok": True}
    if args.get("note"):
      out["note"] = append_note(p, args["note"], args.get("tags"))
    if args.get("vehicle_profile"):
      out["profile"] = update_vehicle_profile(p, args["vehicle_profile"])
    return out

  def h_list_scheduled_tasks(_a):
    return list_tasks(p)

  def h_manage_scheduled_task(args):
    op = args.get("operation")
    if op == "remove":
      return remove_task(p, str(args.get("task_id", "")))
    if op == "upsert":
      return upsert_task(
        p,
        task_id=args.get("task_id"),
        name=str(args.get("name", "")),
        action=str(args.get("action", "read_last_log")),
        interval_minutes=int(args.get("interval_minutes", 60)),
        enabled=bool(args.get("enabled", True)),
        trigger=str(args.get("trigger", "interval")),
        payload=args.get("payload"),
      )
    return {"ok": False, "error": "operation must be upsert or remove"}

  def h_list_drive_routes(args):
    limit = int(args.get("limit", 15))
    base = _ROUTES_DIR
    if not os.path.isdir(base):
      return {"ok": True, "routes": [], "hint": "Routes directory not found on this host."}
    entries = []
    for name in os.listdir(base):
      full = os.path.join(base, name)
      if not os.path.isdir(full):
        continue
      try:
        mtime = os.path.getmtime(full)
        entries.append({"name": name, "mtime": datetime.fromtimestamp(mtime).isoformat(timespec="seconds")})
      except OSError:
        continue
    entries.sort(key=lambda x: x["mtime"], reverse=True)
    return {"ok": True, "routes": entries[:limit]}

  def h_analyze_route_summary(args):
    return analyze_route_summary(str(args.get("route_name", "")))

  def h_read_qlog_segment(args):
    topics = args.get("topics")
    if topics is not None and not isinstance(topics, list):
      topics = None
    return read_qlog_segment(
      str(args.get("route_name", "")),
      start_sec=float(args.get("start_sec", 0.0)),
      end_sec=float(args.get("end_sec", 120.0)),
      topics=topics,
      max_messages=int(args.get("max_messages", 400)),
    )

  def h_trip_review(args):
    state = get_state_reader().update(timeout=0)
    brand = getattr(state, "brand", "") or ""
    return trip_review(
      p,
      get_state_reader,
      brand=brand,
      route_name=str(args.get("route_name", "")),
    )

  def h_read_onroad_events(_a):
    return read_onroad_events(get_state_reader)

  def h_snapshot_tune_state(args):
    state = get_state_reader().update(timeout=0)
    brand = getattr(state, "brand", "") or ""
    snap = snapshot_tune_state(p, brand=brand)
    if args.get("save_snapshot"):
      from ai.tools.tune_snapshot_store import save_tune_snapshot
      saved = save_tune_snapshot(p, label=str(args.get("label", "manual")), brand=brand)
      snap["saved_snapshot"] = saved.get("snapshot")
    return snap

  def h_diff_params(args):
    return diff_params(p, args.get("params") or {})

  async def h_fetch_dashy_settings(_a):
    return await fetch_dashy_settings()

  def h_read_manager_log(args):
    return read_manager_log(p, lines=int(args.get("lines", 80)))

  def h_grep_log(args):
    return grep_log(p, str(args.get("pattern", "")), lines=int(args.get("lines", 200)))

  async def h_search_knowledge_base(args):
    tags = args.get("tags")
    tag_list = [str(t) for t in tags] if isinstance(tags, list) else None
    return await search_documents(
      p,
      str(args.get("query", "")),
      limit=int(args.get("limit", 5)),
      embed_config=_embedding_cfg(),
      tags=tag_list,
    )

  async def h_reindex_knowledge_base(_a):
    err = _stationary_check("write_param")
    if err:
      return err
    return await reindex_all(p, _embedding_cfg())

  def h_list_knowledge_docs(_a):
    return list_documents(p)

  async def h_manage_knowledge_doc(args):
    op = args.get("operation")
    if op == "remove":
      return remove_document(p, str(args.get("doc_id", "")))
    if op == "upsert":
      return await upsert_document(
        p,
        title=str(args.get("title", "")),
        text=str(args.get("text", "")),
        tags=args.get("tags"),
        doc_id=args.get("doc_id"),
        embed_config=_embedding_cfg(),
      )
    return {"ok": False, "error": "operation must be upsert or remove"}

  def h_list_dbcs(_a):
    from ai.tools.adaptation import list_dbcs
    return list_dbcs()

  def h_read_dbc_file(args):
    from ai.tools.adaptation import read_dbc_file
    return read_dbc_file(str(args.get("dbc_name", "")))

  def h_list_adaptation_projects(_a):
    from ai.tools.adaptation import list_adaptation_projects
    return list_adaptation_projects()

  def h_export_adaptation_bundle(args):
    from ai.tools.adaptation import export_adaptation_bundle
    return export_adaptation_bundle(str(args.get("project_id", "")))

  def h_analyze_can_id_pattern(args):
    from ai.tools.adaptation import analyze_can_id_pattern
    return analyze_can_id_pattern(args.get("hex_ids") or [])

  def h_compare_fingerprint(args):
    from ai.tools.fingerprint_lib import compare_fingerprint
    state = get_state_reader().update(timeout=0)
    brand = str(args.get("brand", "")) or getattr(state, "brand", "") or ""
    return compare_fingerprint(hex_ids=args.get("hex_ids") or [], brand=brand)

  def h_suggest_signals_for_adaptation(args):
    from ai.tools.adaptation import suggest_signals_for_adaptation
    return suggest_signals_for_adaptation(str(args.get("dbc_name", "")))

  def h_get_adaptation_template(args):
    from ai.tools.adaptation_templates import get_adaptation_template
    state = get_state_reader().update(timeout=0)
    brand = str(args.get("brand", "")) or getattr(state, "brand", "") or ""
    return get_adaptation_template(
      brand=brand,
      model_name=str(args.get("model_name", "NEW_MODEL")),
      fingerprint=str(args.get("fingerprint", "")),
    )

  def h_extract_can_ids_from_route(args):
    from ai.tools.fingerprint_lib import extract_can_ids_from_route
    route = str(args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route_name required"}
    return extract_can_ids_from_route(route)

  def h_car_porting_auto_fingerprint(args):
    from ai.tools.car_porting_tools import car_porting_auto_fingerprint
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    platform = str(args.get("platform", "")).strip() or None
    return car_porting_auto_fingerprint(route, platform=platform)

  def h_car_porting_test_route(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.car_porting_tools import car_porting_test_route
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    car_model = str(args.get("car_model", "")).strip() or None
    return car_porting_test_route(route, car_model=car_model)

  def h_car_porting_fingerprint_to_draft(args):
    err = _stationary_check("write_param")
    if err:
      return err
    from ai.tools.car_porting_tools import car_porting_fingerprint_to_draft
    project_id = str(args.get("project_id", ""))
    route = str(args.get("route", ""))
    if not project_id or not route:
      return {"ok": False, "error": "project_id and route required"}
    platform = str(args.get("platform", "")).strip() or None
    notes = str(args.get("notes", ""))
    payload = {"project_id": project_id, "route": route, "platform": platform, "notes": notes}
    if not args.get("confirm"):
      return create_pending(
        p,
        action="car_porting_fingerprint_to_draft",
        payload={**payload, "confirm": True},
        preview={"project_id": project_id, "route": route, "platform": platform, "note": "Saves FW output to adaptation_drafts only"},
      )
    return car_porting_fingerprint_to_draft(**payload)

  def h_car_porting_test_interfaces(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.car_porting_tools import car_porting_test_interfaces
    brand = str(args.get("brand", "")).strip() or None
    return car_porting_test_interfaces(brand=brand)

  def h_car_porting_steering_accuracy(args):
    from ai.tools.car_porting_tools import car_porting_steering_accuracy
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    return car_porting_steering_accuracy(route, group=str(args.get("group", "all")))

  def h_car_porting_search_segments_by_can(args):
    from ai.tools.comma_cloud_tools import car_porting_search_segments_by_can
    hex_ids = args.get("hex_ids") or []
    platform = str(args.get("platform", ""))
    if not hex_ids or not platform:
      return {"ok": False, "error": "hex_ids and platform required"}
    return car_porting_search_segments_by_can(
      hex_ids,
      platform,
      segment_limit=int(args.get("segment_limit", 8)),
    )

  def h_long_maneuver_report(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.maneuver_tools import long_maneuver_report
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    desc = str(args.get("description", "")).strip() or None
    return long_maneuver_report(route, desc)

  def h_mpc_longitudinal_tuning_report(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.maneuver_tools import mpc_longitudinal_tuning_report
    out = str(args.get("output_path", "")).strip() or None
    return mpc_longitudinal_tuning_report(out)

  def h_lat_maneuver_report(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.maneuver_tools import lat_maneuver_report
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    desc = str(args.get("description", "")).strip() or None
    return lat_maneuver_report(route, desc)

  def h_maneuver_mode_status(_a):
    from ai.tools.maneuver_tools import maneuver_mode_status
    return maneuver_mode_status()

  def h_route_time_series(args):
    from ai.tools.route_tools import route_time_series
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    topics = args.get("topics")
    if topics is not None and not isinstance(topics, list):
      topics = None
    return route_time_series(
      route,
      topics=topics,
      max_messages=int(args.get("max_messages", 8000)),
      max_points=int(args.get("max_points", 200)),
    )

  def h_route_fetch_frame(args):
    from ai.tools.route_tools import route_fetch_frame
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    return route_fetch_frame(
      route,
      segment=int(args.get("segment", 0)),
      frame=int(args.get("frame", 0)),
      camera=str(args.get("camera", "front")),
    )

  def h_route_video_info(args):
    from ai.tools.route_tools import route_video_info
    route_name = str(args.get("route_name", "") or args.get("route", ""))
    if not route_name:
      return {"ok": False, "error": "route_name required"}
    return route_video_info(route_name)

  def h_search_local_routes_for_can(args):
    from ai.tools.route_tools import search_local_routes_for_can
    hex_ids = args.get("hex_ids") or []
    if not hex_ids:
      return {"ok": False, "error": "hex_ids required"}
    return search_local_routes_for_can(hex_ids, limit=int(args.get("limit", 15)))

  def h_comma_auth_status(_a):
    from ai.tools.comma_cloud_tools import comma_auth_status
    return comma_auth_status()

  def h_search_car_segments(args):
    from ai.tools.comma_cloud_tools import search_car_segments
    platform = str(args.get("platform", "")).strip() or None
    return search_car_segments(platform, limit=int(args.get("limit", 40)))

  def h_read_bootlog(args):
    from ai.tools.comma_cloud_tools import read_bootlog
    dongle_id = str(args.get("dongle_id", "")).strip() or None
    return read_bootlog(dongle_id, limit=int(args.get("limit", 20)))

  def h_plotjuggler_data_summary(args):
    from ai.tools.plotjuggler_tools import plotjuggler_data_summary
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    topics = args.get("topics")
    if topics is not None and not isinstance(topics, list):
      topics = None
    return plotjuggler_data_summary(route, topics=topics, max_messages=int(args.get("max_messages", 10000)))

  def h_read_dbc_platform_map(args):
    from ai.tools.plotjuggler_tools import read_dbc_platform_map
    return read_dbc_platform_map(limit=int(args.get("limit", 80)))

  def h_get_host_environment(_a):
    from ai.system.host_env import get_host_environment
    return get_host_environment()

  def h_pc_launch_plotjuggler(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_plotjuggler
    return pc_launch_plotjuggler(
      str(args.get("route", "")).strip() or None,
      layout=str(args.get("layout", "")).strip() or None,
      parse_can=bool(args.get("parse_can")),
      demo=bool(args.get("demo")),
    )

  def h_pc_launch_replay(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_replay
    route = str(args.get("route", "")).strip() or None
    data_dir = str(args.get("data_dir", "")).strip() or None
    speed = args.get("speed")
    return pc_launch_replay(
      route,
      demo=bool(args.get("demo")),
      data_dir=data_dir,
      speed=float(speed) if speed is not None else None,
    )

  def h_pc_launch_cabana(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_cabana
    route = str(args.get("route", "")).strip() or None
    data_dir = str(args.get("data_dir", "")).strip() or None
    return pc_launch_cabana(route, demo=bool(args.get("demo")), data_dir=data_dir)

  def h_pc_launch_sim_bridge(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_sim_bridge
    return pc_launch_sim_bridge(joystick=bool(args.get("joystick")))

  def h_pc_auth_login_hint(_a):
    from ai.tools.pc_dev_tools import pc_auth_login_hint
    return pc_auth_login_hint()

  def h_pc_capture_route_context(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_capture_route_context
    route = str(args.get("route", "") or args.get("route_name", "")).strip()
    if not route:
      return {"ok": False, "error": "route required"}
    return pc_capture_route_context(
      route,
      include_signal_summary=bool(args.get("include_signal_summary", True)),
      include_topics=bool(args.get("include_topics", True)),
    )

  def h_pc_list_tool_sessions(args):
    from ai.tools.pc_dev_tools import pc_list_tool_sessions
    return pc_list_tool_sessions(limit=int(args.get("limit", 20)))

  def h_pc_get_tool_session(args):
    from ai.tools.pc_dev_tools import pc_get_tool_session
    return pc_get_tool_session(
      str(args.get("session_id", "")).strip(),
      refresh_process=bool(args.get("refresh_process", True)),
      refresh_data=bool(args.get("refresh_data", False)),
    )

  def h_pc_launch_jotpluggler(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_jotpluggler
    route = str(args.get("route", "")).strip() or None
    data_dir = str(args.get("data_dir", "")).strip() or None
    return pc_launch_jotpluggler(
      route,
      layout=str(args.get("layout", "")).strip() or None,
      demo=bool(args.get("demo")),
      data_dir=data_dir,
    )

  def h_pc_launch_replay_stream(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_replay_stream
    route = str(args.get("route", "")).strip() or None
    data_dir = str(args.get("data_dir", "")).strip() or None
    speed = args.get("speed")
    return pc_launch_replay_stream(
      route,
      demo=bool(args.get("demo")),
      data_dir=data_dir,
      speed=float(speed) if speed is not None else None,
    )

  def h_pc_launch_plotjuggler_stream(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_plotjuggler_stream
    return pc_launch_plotjuggler_stream(layout=str(args.get("layout", "")).strip() or None)

  def h_pc_launch_jotpluggler_stream(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_jotpluggler_stream
    buf = args.get("buffer_seconds")
    return pc_launch_jotpluggler_stream(
      address=str(args.get("address", "")).strip() or None,
      buffer_seconds=float(buf) if buf is not None else None,
    )

  def h_pc_launch_replay_viz_stream(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_replay_viz_stream
    route = str(args.get("route", "")).strip() or None
    data_dir = str(args.get("data_dir", "")).strip() or None
    speed = args.get("speed")
    return pc_launch_replay_viz_stream(
      route,
      demo=bool(args.get("demo")),
      viz=str(args.get("viz", "plotjuggler")),
      layout=str(args.get("layout", "")).strip() or None,
      speed=float(speed) if speed is not None else None,
      data_dir=data_dir,
    )

  def h_pc_launch_replay_ui(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_replay_ui
    return pc_launch_replay_ui(address=str(args.get("address", "127.0.0.1")).strip() or "127.0.0.1")

  def h_pc_launch_camerastream(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.pc_dev_tools import pc_launch_camerastream
    return pc_launch_camerastream(
      str(args.get("device_addr", "")).strip(),
      cams=str(args.get("cams", "0,1,2")),
      nvidia=bool(args.get("nvidia")),
    )

  def h_route_export_clip(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.route_media_tools import route_export_clip
    route = str(args.get("route", "")).strip() or None
    return route_export_clip(
      route or "",
      start_sec=args.get("start_sec"),
      end_sec=args.get("end_sec"),
      demo=bool(args.get("demo")),
      output=str(args.get("output", "")).strip() or None,
      data_dir=str(args.get("data_dir", "")).strip() or None,
      title=str(args.get("title", "")).strip() or None,
    )

  def h_route_extract_audio(args):
    from ai.tools.route_media_tools import route_extract_audio
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    return route_extract_audio(route, output=str(args.get("output", "")).strip() or None)

  def h_route_ublox_summary(args):
    from ai.tools.route_media_tools import route_ublox_summary
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    return route_ublox_summary(route, max_messages=int(args.get("max_messages", 5000)))

  def h_route_can_stats(args):
    from ai.tools.route_analysis_tools import route_can_stats
    route = str(args.get("route", "") or args.get("route_name", ""))
    if not route:
      return {"ok": False, "error": "route required"}
    return route_can_stats(route, max_batches=int(args.get("max_batches", 2000)))

  def h_compare_route_signals(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.route_analysis_tools import compare_route_signals
    ra = str(args.get("route_a", "")).strip()
    rb = str(args.get("route_b", "")).strip()
    if not ra or not rb:
      return {"ok": False, "error": "route_a and route_b required"}
    topics = args.get("topics")
    if topics is not None and not isinstance(topics, list):
      topics = None
    return compare_route_signals(ra, rb, topics=topics)

  def h_batch_route_summary(args):
    from ai.tools.route_analysis_tools import batch_route_summary
    return batch_route_summary(limit=int(args.get("limit", 5)))

  def h_search_route_messages(args):
    from ai.tools.route_analysis_tools import search_route_messages
    route = str(args.get("route", "") or args.get("route_name", ""))
    msg_type = str(args.get("message_type", "")).strip()
    if not route:
      return {"ok": False, "error": "route required"}
    return search_route_messages(route, msg_type, max_hits=int(args.get("max_hits", 20)))

  def h_list_plotjuggler_layouts(_a):
    from ai.tools.viz_layout_tools import list_plotjuggler_layouts
    return list_plotjuggler_layouts()

  def h_list_jotpluggler_layouts(_a):
    from ai.tools.viz_layout_tools import list_jotpluggler_layouts
    return list_jotpluggler_layouts()

  def h_get_build_info(_a):
    from ai.tools.system_info_tools import get_build_info
    return get_build_info()

  def h_list_managed_processes(_a):
    from ai.tools.system_info_tools import list_managed_processes
    return list_managed_processes(get_state_reader)

  def h_maneuversd_status(_a):
    from ai.tools.maneuver_tools import maneuversd_status
    return maneuversd_status(get_state_reader)

  def h_get_webcam_dev_setup(_a):
    from ai.tools.devops_tools import get_webcam_dev_setup
    return get_webcam_dev_setup()

  def h_get_devsync_hint(args):
    from ai.tools.devops_tools import get_devsync_hint
    ip = str(args.get("device_ip", "")).strip() or None
    return get_devsync_hint(device_ip=ip)

  def h_pc_devsync_status(args):
    from ai.tools.devops_tools import pc_devsync_status
    return pc_devsync_status(
      device_ip=str(args.get("device_ip", "")).strip() or None,
      remote_path=args.get("remote_path") or "/data/openpilot",
      identity=str(args.get("identity", "")).strip() or None,
      probe_ssh=bool(args.get("probe_ssh", True)),
    )

  def h_openpilotci_segment_url(args):
    from ai.tools.devops_tools import openpilotci_segment_url
    return openpilotci_segment_url(
      str(args.get("route_name", "")).strip(),
      int(args.get("segment", 0)),
      str(args.get("filename", "")).strip(),
    )

  def h_live_cereal_summary(args):
    err = _stationary_check("run_shell")
    if err:
      return err
    from ai.tools.live_tools import live_cereal_summary
    services = args.get("services")
    if services is not None and not isinstance(services, list):
      services = None
    return live_cereal_summary(
      services=services,
      addr=str(args.get("addr", "127.0.0.1")).strip() or "127.0.0.1",
      duration_sec=float(args.get("duration_sec", 3.0)),
      max_messages=int(args.get("max_messages", 500)),
    )

  def h_lookup_secoc_tier(args):
    from ai.tools.secoc_lookup import lookup_secoc_tier
    state = get_state_reader().update(timeout=0)
    fp = str(args.get("car_fingerprint", "")) or getattr(state, "car_fingerprint", "") or ""
    brand = str(args.get("brand", "")) or getattr(state, "brand", "") or ""
    return lookup_secoc_tier(fp, brand)

  def h_suggest_tune_from_route(args):
    from ai.tools.diagnostics_tools import suggest_tune_from_route
    state = get_state_reader().update(timeout=0)
    brand = getattr(state, "brand", "") or ""
    return suggest_tune_from_route(p, str(args.get("route_name", "")), brand=brand)

  def h_save_tune_snapshot(args):
    err = _stationary_check("write_param")
    if err:
      return err
    from ai.tools.tune_snapshot_store import save_tune_snapshot
    state = get_state_reader().update(timeout=0)
    return save_tune_snapshot(p, label=str(args.get("label", "manual")), brand=getattr(state, "brand", "") or "")

  def h_restore_tune_snapshot(args):
    err = _stationary_check("write_param")
    if err:
      return err
    snapshot_id = str(args.get("snapshot_id", ""))
    if not args.get("confirm"):
      from ai.tools.tune_snapshot_store import list_tune_snapshots
      return create_pending(
        p,
        action="restore_tune_snapshot",
        payload={"snapshot_id": snapshot_id},
        preview={"snapshot_id": snapshot_id or "latest", "available": list_tune_snapshots().get("snapshots", [])[:5]},
      )
    from ai.tools.tune_snapshot_store import restore_tune_snapshot
    return restore_tune_snapshot(p, snapshot_id)

  def h_list_tune_snapshots(_a):
    from ai.tools.tune_snapshot_store import list_tune_snapshots
    return list_tune_snapshots()

  def h_save_adaptation_draft(args):
    err = _stationary_check("write_param")
    if err:
      return err
    from ai.tools.adaptation import save_adaptation_draft
    files = args.get("files") or {}
    if not isinstance(files, dict) or not files:
      return {"ok": False, "error": "files object is required"}
    payload = {
      "project_id": str(args.get("project_id", "")),
      "fingerprint": str(args.get("fingerprint", "")),
      "files": files,
      "notes": str(args.get("notes", "")),
      "metadata": args.get("metadata"),
    }
    if not args.get("confirm") and _needs_confirm():
      preview = {
        "project_id": payload["project_id"],
        "fingerprint": payload["fingerprint"],
        "file_names": list(files.keys()),
        "note": "Draft only — not written to opendbc",
      }
      return create_pending(p, action="save_adaptation_draft", payload=payload, preview=preview)
    return save_adaptation_draft(**payload)

  async def h_cabana_explain_signal(args):
    from ai.cabana import cabana_explain_signal_tool
    return await cabana_explain_signal_tool(args)

  async def h_cabana_analyze(args):
    from ai.cabana import cabana_analyze_tool
    from ai.tools.fingerprint_lib import compare_fingerprint, extract_hex_ids_from_text, extract_observed_fingerprint
    question = args.get("question", "")
    frames = args.get("frames_text", "")
    result = await cabana_analyze_tool(question, frames)
    if frames:
      hex_ids = extract_hex_ids_from_text(frames)
      observed = extract_observed_fingerprint(frames)
      state = get_state_reader().update(timeout=0)
      brand = getattr(state, "brand", "") or ""
      fp_analysis = compare_fingerprint(hex_ids=hex_ids, observed=observed, brand=brand, limit=5)
      pattern = None
      if hex_ids:
        from ai.tools.adaptation import analyze_can_id_pattern
        pattern = analyze_can_id_pattern(hex_ids)
      if isinstance(result, dict):
        result["hex_ids"] = hex_ids[:80]
        result["fingerprint_compare"] = fp_analysis
        result["pattern_analysis"] = pattern
    return result

  def h_run_shell(args):
    err = _stationary_check("shell")
    if err:
      return err
    return run_command(args.get("command", ""))

  def h_run_shell_command(args):
    err = _stationary_check("shell")
    if err:
      return err
    timeout = int(args.get("timeout", 60) or 60)
    return run_shell_command(str(args.get("command", "")), timeout=min(timeout, 300))

  def h_read_file(args):
    from ai.tools.fs_tools import read_file
    return read_file(str(args.get("path", "")))

  def h_write_file(args):
    err = _stationary_check("write_param")
    if err:
      return err
    from ai.tools.fs_tools import write_file
    return write_file(str(args.get("path", "")), str(args.get("content", "")))

  def h_list_directory(args):
    from ai.tools.fs_tools import list_directory
    return list_directory(str(args.get("path", ".") or "."))

  def h_restart_service(args):
    err = _stationary_check("restart_service")
    if err:
      return err
    name = str(args.get("name", "")).strip()
    if not name:
      return {"ok": False, "error": "name required"}
    if not admin and name not in _RESTARTABLE_SERVICES:
      return {"ok": False, "error": f"Service '{name}' not whitelisted."}
    subprocess.run(["pkill", "-f", name], check=False)
    return {"ok": True, "message": f"Sent restart to {name}"}

  def h_restart_ui(_a):
    err = _stationary_check("restart_ui")
    if err:
      return err
    subprocess.run(["pkill", "-f", "selfdrive/ui"], check=False)
    return {"ok": True, "message": "UI restart signal sent"}

  handlers = {
    "get_vehicle_state": h_get_vehicle_state,
    "get_full_vehicle_state": h_get_full_vehicle_state,
    "read_params": h_read_params,
    "list_dp_settings": h_list_dp_settings,
    "get_params_catalog": h_get_params_catalog,
    "list_tune_presets": h_list_tune_presets,
    "write_params": h_write_params,
    "apply_tune_preset": h_apply_tune_preset,
    "select_driving_model": h_select_driving_model,
    "get_agent_memory": h_get_agent_memory,
    "update_agent_memory": h_update_agent_memory,
    "list_scheduled_tasks": h_list_scheduled_tasks,
    "manage_scheduled_task": h_manage_scheduled_task,
    "list_drive_routes": h_list_drive_routes,
    "analyze_route_summary": h_analyze_route_summary,
    "read_qlog_segment": h_read_qlog_segment,
    "trip_review": h_trip_review,
    "read_onroad_events": h_read_onroad_events,
    "snapshot_tune_state": h_snapshot_tune_state,
    "diff_params": h_diff_params,
    "fetch_dashy_settings": h_fetch_dashy_settings,
    "read_manager_log": h_read_manager_log,
    "grep_log": h_grep_log,
    "search_knowledge_base": h_search_knowledge_base,
    "reindex_knowledge_base": h_reindex_knowledge_base,
    "list_knowledge_docs": h_list_knowledge_docs,
    "manage_knowledge_doc": h_manage_knowledge_doc,
    "list_dbcs": h_list_dbcs,
    "read_dbc_file": h_read_dbc_file,
    "list_adaptation_projects": h_list_adaptation_projects,
    "save_adaptation_draft": h_save_adaptation_draft,
    "export_adaptation_bundle": h_export_adaptation_bundle,
    "analyze_can_id_pattern": h_analyze_can_id_pattern,
    "compare_fingerprint": h_compare_fingerprint,
    "suggest_signals_for_adaptation": h_suggest_signals_for_adaptation,
    "get_adaptation_template": h_get_adaptation_template,
    "extract_can_ids_from_route": h_extract_can_ids_from_route,
    "car_porting_auto_fingerprint": h_car_porting_auto_fingerprint,
    "car_porting_test_route": h_car_porting_test_route,
    "car_porting_fingerprint_to_draft": h_car_porting_fingerprint_to_draft,
    "car_porting_test_interfaces": h_car_porting_test_interfaces,
    "car_porting_steering_accuracy": h_car_porting_steering_accuracy,
    "car_porting_search_segments_by_can": h_car_porting_search_segments_by_can,
    "long_maneuver_report": h_long_maneuver_report,
    "mpc_longitudinal_tuning_report": h_mpc_longitudinal_tuning_report,
    "lat_maneuver_report": h_lat_maneuver_report,
    "maneuver_mode_status": h_maneuver_mode_status,
    "route_time_series": h_route_time_series,
    "route_fetch_frame": h_route_fetch_frame,
    "route_video_info": h_route_video_info,
    "search_local_routes_for_can": h_search_local_routes_for_can,
    "comma_auth_status": h_comma_auth_status,
    "search_car_segments": h_search_car_segments,
    "read_bootlog": h_read_bootlog,
    "plotjuggler_data_summary": h_plotjuggler_data_summary,
    "read_dbc_platform_map": h_read_dbc_platform_map,
    "get_host_environment": h_get_host_environment,
    "pc_launch_plotjuggler": h_pc_launch_plotjuggler,
    "pc_launch_replay": h_pc_launch_replay,
    "pc_launch_cabana": h_pc_launch_cabana,
    "pc_launch_sim_bridge": h_pc_launch_sim_bridge,
    "pc_auth_login_hint": h_pc_auth_login_hint,
    "pc_capture_route_context": h_pc_capture_route_context,
    "pc_list_tool_sessions": h_pc_list_tool_sessions,
    "pc_get_tool_session": h_pc_get_tool_session,
    "pc_launch_jotpluggler": h_pc_launch_jotpluggler,
    "pc_launch_replay_stream": h_pc_launch_replay_stream,
    "pc_launch_plotjuggler_stream": h_pc_launch_plotjuggler_stream,
    "pc_launch_jotpluggler_stream": h_pc_launch_jotpluggler_stream,
    "pc_launch_replay_viz_stream": h_pc_launch_replay_viz_stream,
    "pc_launch_replay_ui": h_pc_launch_replay_ui,
    "pc_launch_camerastream": h_pc_launch_camerastream,
    "route_export_clip": h_route_export_clip,
    "route_extract_audio": h_route_extract_audio,
    "route_ublox_summary": h_route_ublox_summary,
    "route_can_stats": h_route_can_stats,
    "compare_route_signals": h_compare_route_signals,
    "batch_route_summary": h_batch_route_summary,
    "search_route_messages": h_search_route_messages,
    "list_plotjuggler_layouts": h_list_plotjuggler_layouts,
    "list_jotpluggler_layouts": h_list_jotpluggler_layouts,
    "get_build_info": h_get_build_info,
    "list_managed_processes": h_list_managed_processes,
    "maneuversd_status": h_maneuversd_status,
    "get_webcam_dev_setup": h_get_webcam_dev_setup,
    "get_devsync_hint": h_get_devsync_hint,
    "pc_devsync_status": h_pc_devsync_status,
    "openpilotci_segment_url": h_openpilotci_segment_url,
    "live_cereal_summary": h_live_cereal_summary,
    "lookup_secoc_tier": h_lookup_secoc_tier,
    "suggest_tune_from_route": h_suggest_tune_from_route,
    "save_tune_snapshot": h_save_tune_snapshot,
    "restore_tune_snapshot": h_restore_tune_snapshot,
    "list_tune_snapshots": h_list_tune_snapshots,
    "cabana_explain_signal": h_cabana_explain_signal,
    "cabana_analyze": h_cabana_analyze,
    "run_shell": h_run_shell,
    "run_shell_command": h_run_shell_command,
    "read_file": h_read_file,
    "write_file": h_write_file,
    "list_directory": h_list_directory,
    "restart_service": h_restart_service,
    "restart_ui": h_restart_ui,
  }
  from ai.tools.extensions import make_extension_handlers
  handlers.update(
    make_extension_handlers(
      params=p,
      get_state_reader=get_state_reader,
      stationary_check=_stationary_check,
      needs_confirm=_needs_confirm,
    )
  )
  return handlers


def execute_tool(handlers: dict[str, Any], name: str, arguments: str) -> Any:
  handler = handlers.get(name)
  if handler is None:
    return {"ok": False, "error": f"Tool '{name}' not implemented"}
  try:
    args = json.loads(arguments) if arguments else {}
  except json.JSONDecodeError:
    return {"ok": False, "error": "Invalid tool arguments JSON"}
  try:
    result = handler(args)
    try:
      from ai.tools.audit_store import record_audit
      ok = True
      if isinstance(result, dict) and result.get("ok") is False:
        ok = False
      record_audit(action="tool_call", tool=name, detail={"args": args, "ok": ok}, ok=ok)
    except Exception:
      pass
    return result
  except Exception as e:
    return {"ok": False, "error": f"Tool execution failed: {e}"}


async def execute_tool_async(handlers: dict[str, Any], name: str, arguments: str) -> Any:
  import asyncio
  handler = handlers.get(name)
  if handler is None:
    return {"ok": False, "error": f"Tool '{name}' not implemented"}
  try:
    args = json.loads(arguments) if arguments else {}
  except json.JSONDecodeError:
    return {"ok": False, "error": "Invalid tool arguments JSON"}
  try:
    result = handler(args)
    if asyncio.iscoroutine(result):
      result = await result
    try:
      from ai.tools.audit_store import record_audit
      ok = True
      if isinstance(result, dict) and result.get("ok") is False:
        ok = False
      record_audit(action="tool_call", tool=name, detail={"args": args, "ok": ok}, ok=ok)
    except Exception:
      pass
    return result
  except Exception as e:
    return {"ok": False, "error": f"Tool execution failed: {e}"}
