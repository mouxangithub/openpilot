"""Extension tools registry — merges into agent_tools."""

from __future__ import annotations

from typing import Any, Callable

from ai.plugins.loader import collect_plugin_schemas, collect_plugin_tool_meta, make_plugin_handlers

EXTENSION_TOOL_META: dict[str, dict[str, Any]] = {
  "reboot_device": {"label": "重启设备", "group": "shell", "default_enabled": True, "driving": True},
  "shutdown_device": {"label": "关机", "group": "shell", "default_enabled": True, "driving": True},
  "manager_control": {"label": "Manager 控制", "group": "shell", "default_enabled": True, "driving": False},
  "git_status": {"label": "Git 状态", "group": "read", "default_enabled": True, "driving": True},
  "git_diff": {"label": "Git Diff", "group": "read", "default_enabled": True, "driving": True},
  "git_list_branches": {"label": "Git 分支列表", "group": "read", "default_enabled": True, "driving": True},
  "git_checkout": {"label": "Git 切换分支", "group": "write", "default_enabled": True, "driving": False},
  "git_pull": {"label": "Git Pull", "group": "write", "default_enabled": True, "driving": False},
  "git_fetch": {"label": "Git Fetch", "group": "read", "default_enabled": True, "driving": True},
  "git_stash": {"label": "Git Stash", "group": "write", "default_enabled": True, "driving": False},
  "git_stash_pop": {"label": "Git Stash Pop", "group": "write", "default_enabled": True, "driving": False},
  "git_commit": {"label": "Git Commit", "group": "write", "default_enabled": True, "driving": False},
  "apply_tune_from_route": {"label": "路线调优并应用", "group": "write", "default_enabled": True, "driving": True},
  "compare_tune_ab": {"label": "调优 A/B 对比", "group": "read", "default_enabled": True, "driving": True},
  "score_route_tune": {"label": "路线调参评分", "group": "read", "default_enabled": True, "driving": True},
  "score_tune_session": {"label": "调参前后评分", "group": "read", "default_enabled": True, "driving": True},
  "route_event_timeline": {"label": "路线事件时间线", "group": "read", "default_enabled": True, "driving": True},
  "device_health": {"label": "设备健康", "group": "read", "default_enabled": True, "driving": True},
  "panda_status": {"label": "Panda 状态", "group": "read", "default_enabled": True, "driving": True},
  "list_tune_passport": {"label": "调参护照", "group": "read", "default_enabled": True, "driving": True},
  "manage_param_watchlist": {"label": "参数监视列表", "group": "config", "default_enabled": True, "driving": True},
  "check_param_watchlist": {"label": "参数漂移检查", "group": "read", "default_enabled": True, "driving": True},
  "generate_adaptation_pr_draft": {"label": "适配 PR 草稿", "group": "read", "default_enabled": True, "driving": True},
  "post_drive_voice_summary": {"label": "下车语音简报", "group": "read", "default_enabled": True, "driving": True},
  "sync_knowledge_from_docs": {"label": "同步文档到知识库", "group": "config", "default_enabled": True, "driving": True},
  "pc_devsync_run": {"label": "Devsync 同步执行", "group": "write", "default_enabled": True, "driving": False, "pc_only": True},
  "live_can_capture": {"label": "实时 CAN 采样", "group": "read", "default_enabled": True, "driving": True},
  "network_diagnostics": {"label": "网络诊断", "group": "read", "default_enabled": True, "driving": True},
  "list_audit_trail": {"label": "操作审计日志", "group": "read", "default_enabled": True, "driving": True},
  "list_plugins": {"label": "插件列表", "group": "read", "default_enabled": True, "driving": True},
  "git_push": {"label": "Git Push", "group": "write", "default_enabled": True, "driving": False},
  "ota_status": {"label": "OTA 状态", "group": "read", "default_enabled": True, "driving": True},
  "batch_compare_routes_tune": {"label": "批量路线调参评分", "group": "read", "default_enabled": True, "driving": True},
  "run_pytest": {"label": "运行 Pytest", "group": "read", "default_enabled": True, "driving": False, "pc_only": True},
  "run_scons_build": {"label": "Scons 编译", "group": "write", "default_enabled": True, "driving": False, "pc_only": True},
  "ssh_readonly_exec": {"label": "SSH 只读命令", "group": "read", "default_enabled": True, "driving": True},
  "list_comma_devices": {"label": "Comma 设备列表", "group": "read", "default_enabled": True, "driving": True},
  "list_comma_routes": {"label": "Comma 云路线", "group": "read", "default_enabled": True, "driving": True},
  "analyze_route_vision": {"label": "路线视觉分析", "group": "read", "default_enabled": True, "driving": True},
  "plotjuggler_apply_layout": {"label": "应用 PJ 布局", "group": "read", "default_enabled": True, "driving": True},
  "search_memory_semantic": {"label": "语义搜索记忆", "group": "memory", "default_enabled": True, "driving": True},
  "get_tsk_manager_status": {"label": "TSK 状态", "group": "read", "default_enabled": True, "driving": True},
  "tsk_find_and_install_key": {"label": "TSK 查找安装密钥", "group": "write", "default_enabled": True, "driving": False},
  "tsk_extract_key": {"label": "TSK 一键提取密钥", "group": "write", "default_enabled": True, "driving": False},
  "tsk_install_secoc_key": {"label": "TSK 手动安装密钥", "group": "write", "default_enabled": True, "driving": False},
  "tsk_uninstall_key": {"label": "TSK 卸载密钥", "group": "write", "default_enabled": True, "driving": False},
  "tsk_start_can_collect": {"label": "TSK 采集 CAN", "group": "write", "default_enabled": True, "driving": False},
  "tsk_start_dataflash_dump": {"label": "TSK 导出 DataFlash", "group": "write", "default_enabled": True, "driving": False},
  "tsk_clear_cache": {"label": "TSK 清除提取缓存", "group": "write", "default_enabled": True, "driving": False},
  "tsk_wait_for_job": {"label": "TSK 等待作业", "group": "read", "default_enabled": True, "driving": True},
  "tsk_cancel_job": {"label": "TSK 取消作业", "group": "write", "default_enabled": True, "driving": False},
  "tsk_restart_pandad": {"label": "TSK 重启本机 pandad", "group": "write", "default_enabled": True, "driving": False},
  "tsk_run_pipeline": {"label": "TSK SecOC 一条龙", "group": "write", "default_enabled": True, "driving": False},
  "get_tsk_offroad_alert_status": {"label": "TSK Offroad 提醒", "group": "read", "default_enabled": True, "driving": True},
  "konik_connect_status": {"label": "Konik 配对状态", "group": "read", "default_enabled": True, "driving": True},
  "konik_generate_device_keys": {"label": "Konik 生成设备密钥", "group": "write", "default_enabled": True, "driving": False},
  "konik_reset_dongle_id": {"label": "Konik 清除 DongleId", "group": "write", "default_enabled": True, "driving": False},
  "konik_register_device": {"label": "Konik 注册设备", "group": "write", "default_enabled": True, "driving": False},
  "konik_connect_pipeline": {"label": "Konik 一条龙配对", "group": "write", "default_enabled": True, "driving": False},
}

EXTENSION_TOOL_META.update(collect_plugin_tool_meta())

EXTENSION_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "reboot_device", "description": "Reboot the comma/AGNOS device.", "parameters": {"type": "object", "properties": {"delay_sec": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "shutdown_device", "description": "Shut down the comma/AGNOS device.", "parameters": {"type": "object", "properties": {"delay_sec": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "manager_control", "description": "Start/stop/restart manager, optional scons rebuild, or status.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["status", "start", "stop", "restart", "rebuild"]}, "use_webcam": {"type": "boolean"}, "rebuild": {"type": "boolean"}, "timeout": {"type": "integer"}}, "required": ["action"]}}},
  {"type": "function", "function": {"name": "git_status", "description": "Git status for openpilot repo.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "git_diff", "description": "Git diff for openpilot repo.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "stat": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "git_list_branches", "description": "List local and remote Git branches for openpilot repo.", "parameters": {"type": "object", "properties": {"include_remote": {"type": "boolean"}, "limit": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "git_checkout", "description": "Switch to another Git branch (blocks if working tree is dirty). confirm=true to apply.", "parameters": {"type": "object", "properties": {"branch": {"type": "string"}, "create": {"type": "boolean", "description": "Create branch with checkout -b"}, "start_point": {"type": "string", "description": "Optional base ref when create=true"}, "confirm": {"type": "boolean"}}, "required": ["branch", "confirm"]}}},
  {"type": "function", "function": {"name": "git_pull", "description": "Git pull on openpilot repo.", "parameters": {"type": "object", "properties": {"remote": {"type": "string"}, "branch": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["confirm"]}}},
  {"type": "function", "function": {"name": "git_fetch", "description": "Git fetch from remote (no merge).", "parameters": {"type": "object", "properties": {"remote": {"type": "string"}, "prune": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "git_stash", "description": "Stash uncommitted changes before branch switch.", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "include_untracked": {"type": "boolean"}, "confirm": {"type": "boolean"}}, "required": ["confirm"]}}},
  {"type": "function", "function": {"name": "git_stash_pop", "description": "Pop latest git stash.", "parameters": {"type": "object", "properties": {"index": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": ["confirm"]}}},
  {"type": "function", "function": {"name": "git_commit", "description": "Stage and commit changes in openpilot repo.", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "add_all": {"type": "boolean"}, "paths": {"type": "array", "items": {"type": "string"}}, "confirm": {"type": "boolean"}}, "required": ["message", "confirm"]}}},
  {"type": "function", "function": {"name": "apply_tune_from_route", "description": "Suggest tune from route and apply params (auto snapshot). confirm=true to write.", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}, "confirm": {"type": "boolean"}, "max_params": {"type": "integer"}, "route_before": {"type": "string"}, "route_after": {"type": "string"}, "skip_regression_check": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "compare_tune_ab", "description": "A/B route comparison with tune-focused highlights and recommendations.", "parameters": {"type": "object", "properties": {"route_a": {"type": "string"}, "route_b": {"type": "string"}, "label_a": {"type": "string"}, "label_b": {"type": "string"}}, "required": ["route_a", "route_b"]}}},
  {"type": "function", "function": {"name": "score_route_tune", "description": "Quantitative comfort/engage score for one route.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}}, "required": ["route"]}}},
  {"type": "function", "function": {"name": "score_tune_session", "description": "Compare before/after route scores for tune validation.", "parameters": {"type": "object", "properties": {"route_before": {"type": "string"}, "route_after": {"type": "string"}, "min_score_delta": {"type": "number"}}, "required": ["route_before", "route_after"]}}},
  {"type": "function", "function": {"name": "route_event_timeline", "description": "Chronological engage/disengage and onroad events from route.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "max_events": {"type": "integer"}}, "required": ["route"]}}},
  {"type": "function", "function": {"name": "device_health", "description": "Disk, thermal, AGNOS version, build info.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "panda_status", "description": "Panda USB and live pandaStates.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "list_tune_passport", "description": "List tune change journal entries.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "manage_param_watchlist", "description": "Add/remove/replace watched Param keys.", "parameters": {"type": "object", "properties": {"add": {"type": "array", "items": {"type": "string"}}, "remove": {"type": "array", "items": {"type": "string"}}, "replace": {"type": "array", "items": {"type": "string"}}}, "required": []}}},
  {"type": "function", "function": {"name": "check_param_watchlist", "description": "Detect drift in watched Params vs baseline.", "parameters": {"type": "object", "properties": {"reset_baseline": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "generate_adaptation_pr_draft", "description": "Markdown PR draft from adaptation + git diff.", "parameters": {"type": "object", "properties": {"project_name": {"type": "string"}, "draft_id": {"type": "string"}, "summary": {"type": "string"}}, "required": []}}},
  {"type": "function", "function": {"name": "post_drive_voice_summary", "description": "Post-drive text summary; optional TTS via espeak/say.", "parameters": {"type": "object", "properties": {"route_name": {"type": "string"}, "speak": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "sync_knowledge_from_docs", "description": "Import repo markdown into RAG knowledge base.", "parameters": {"type": "object", "properties": {"max_files": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "pc_devsync_run", "description": "PC only: run one-shot devsync to comma device (requires preflight ready).", "parameters": {"type": "object", "properties": {"device_ip": {"type": "string"}, "remote_path": {"type": "string"}, "identity": {"type": "string"}, "dry_run": {"type": "boolean"}, "confirm": {"type": "boolean"}}, "required": ["device_ip", "confirm"]}}},
  {"type": "function", "function": {"name": "live_can_capture", "description": "Capture live CAN frames from cereal for analysis.", "parameters": {"type": "object", "properties": {"duration_sec": {"type": "number"}, "max_frames": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "network_diagnostics", "description": "WiFi, ping, SSH, comma auth connectivity check.", "parameters": {"type": "object", "properties": {"device_ip": {"type": "string"}, "ping_count": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "list_audit_trail", "description": "List recent AI tool/write audit entries.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "list_plugins", "description": "List loaded op助手 plugins.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "git_push", "description": "Git push to remote (confirm=true).", "parameters": {"type": "object", "properties": {"remote": {"type": "string"}, "branch": {"type": "string"}, "set_upstream": {"type": "boolean"}, "confirm": {"type": "boolean"}}, "required": ["confirm"]}}},
  {"type": "function", "function": {"name": "ota_status", "description": "Read OTA/update availability and version info.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "batch_compare_routes_tune", "description": "Score and rank multiple routes for tune comparison.", "parameters": {"type": "object", "properties": {"routes": {"type": "array", "items": {"type": "string"}}, "baseline": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["routes"]}}},
  {"type": "function", "function": {"name": "run_pytest", "description": "PC only: run pytest (default ai/tests).", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "keyword": {"type": "string"}, "max_fail": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "run_scons_build", "description": "PC only: run scons build in openpilot root.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}, "jobs": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "ssh_readonly_exec", "description": "Run whitelisted read-only SSH command on comma device.", "parameters": {"type": "object", "properties": {"host": {"type": "string"}, "command": {"type": "string"}, "identity": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["host", "command"]}}},
  {"type": "function", "function": {"name": "list_comma_devices", "description": "List comma cloud devices (auth required).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "list_comma_routes", "description": "List cloud routes for dongle.", "parameters": {"type": "object", "properties": {"dongle_id": {"type": "string"}, "limit": {"type": "integer"}, "preserved": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "analyze_route_vision", "description": "Extract route frame + brightness stats for camera review.", "parameters": {"type": "object", "properties": {"route": {"type": "string"}, "segment": {"type": "integer"}, "frame": {"type": "integer"}, "camera": {"type": "string", "enum": ["front", "wide", "driver"]}}, "required": ["route"]}}},
  {"type": "function", "function": {"name": "plotjuggler_apply_layout", "description": "Resolve PlotJuggler layout and return launch command.", "parameters": {"type": "object", "properties": {"layout": {"type": "string"}, "route": {"type": "string"}}, "required": ["layout"]}}},
  {"type": "function", "function": {"name": "search_memory_semantic", "description": "Semantic/keyword search in agent long-term memory.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}}},
  {"type": "function", "function": {"name": "get_tsk_manager_status", "description": "TSK SecOC pipeline status (key, CAN/DataFlash progress, comma device type C3/C3X/C4 and panda_backend/pandad_process from hardware detection).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_find_and_install_key", "description": "Offroad: scan DataFlash with CAN oracle and install SecOC key. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_extract_key", "description": "Offroad: UDS one-shot SecOC key extract (RAV4 Prime/Sienna etc). No CAN/DataFlash prereq. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_install_secoc_key", "description": "Offroad: install user-provided 32-char hex SecOC key. confirm=true and key required.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["key"]}}},
  {"type": "function", "function": {"name": "tsk_uninstall_key", "description": "Offroad: remove installed SecOC key file. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_start_can_collect", "description": "Offroad: start CAN oracle collection (stops manager and this device's pandad: C3→pandad_tici, C3X/C4→pandad). confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_start_dataflash_dump", "description": "Offroad: start DataFlash dump (stops manager and device-specific pandad). confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_clear_cache", "description": "Offroad: clear CAN and DataFlash extraction cache (keeps installed key). confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_wait_for_job", "description": "Wait for TSK background job: can, dataflash, or match idle. Returns when done or timeout.", "parameters": {"type": "object", "properties": {"job": {"type": "string", "enum": ["can", "dataflash", "match"]}, "timeout_seconds": {"type": "number"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_cancel_job", "description": "Offroad: cancel running CAN or DataFlash job. job=can|dataflash|all, confirm=true required.", "parameters": {"type": "object", "properties": {"job": {"type": "string", "enum": ["can", "dataflash", "all"]}, "confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_restart_pandad", "description": "Offroad: kill this device's pandad process (C3/tici→pandad_tici; C3X/tizi and C4/mici→pandad). Black screen recovery. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "tsk_run_pipeline", "description": "Offroad: run CAN collect → wait → DataFlash dump → wait → find/install SecOC key. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "skip_can": {"type": "boolean"}, "skip_dataflash": {"type": "boolean"}, "can_timeout_seconds": {"type": "number"}, "dataflash_timeout_seconds": {"type": "number"}}, "required": []}}},
  {"type": "function", "function": {"name": "get_tsk_offroad_alert_status", "description": "Read Offroad_NoFirmware alert state and SecOC settings URL.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "konik_connect_status", "description": "Konik Connect: SSH/key/dongle pairing progress vs comma connect-killer steps 1-3; pair at stable.konik.ai.", "parameters": {"type": "object", "properties": {"device_ip": {"type": "string", "description": "PC only: comma device IP for SSH step check"}}, "required": []}}},
  {"type": "function", "function": {"name": "konik_generate_device_keys", "description": "Konik Connect step 2: generate /persist/comma RSA keys via 1.sh (cloned devices). Offroad; confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "device_ip": {"type": "string", "description": "PC only: run 1.sh over SSH on device"}}, "required": []}}},
  {"type": "function", "function": {"name": "konik_reset_dongle_id", "description": "Konik Connect step 3: remove DongleId params for re-register on Konik. Offroad; confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "device_ip": {"type": "string"}}, "required": []}}},
  {"type": "function", "function": {"name": "konik_register_device", "description": "Konik Connect step 4: run system/athena/registration.register() against api.konik.ai. Needs keys + cleared DongleId. Offroad; confirm=true.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "device_ip": {"type": "string"}}, "required": []}}},
  {"type": "function", "function": {"name": "konik_connect_pipeline", "description": "Konik one-stop: optional keygen, reset DongleId, register(), return stable.konik.ai pair URL. Offroad; confirm=true.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "device_ip": {"type": "string"}, "regenerate_keys": {"type": "boolean", "description": "Force bash 1.sh even if keys exist (cloned devices)"}}, "required": []}}},
]

EXTENSION_SCHEMAS.extend(collect_plugin_schemas())


def make_extension_handlers(
  *,
  params,
  get_state_reader,
  stationary_check,
  needs_confirm,
) -> dict[str, Callable[..., Any]]:
  ctx = {
    "params": params,
    "get_state_reader": get_state_reader,
    "stationary_check": stationary_check,
    "needs_confirm": needs_confirm,
  }

  def h_reboot_device(args):
    err = stationary_check("reboot_now")
    if err:
      return err
    from ai.tools.system_control_tools import reboot_device
    from ai.tools.audit_store import record_audit
    res = reboot_device(delay_sec=int(args.get("delay_sec", 3) or 3))
    record_audit(action="reboot_device", tool="reboot_device", detail=res, ok=res.get("ok", False))
    return res

  def h_shutdown_device(args):
    err = stationary_check("shutdown_now")
    if err:
      return err
    from ai.tools.system_control_tools import shutdown_device
    from ai.tools.audit_store import record_audit
    res = shutdown_device(delay_sec=int(args.get("delay_sec", 5) or 5))
    record_audit(action="shutdown_device", tool="shutdown_device", detail=res, ok=res.get("ok", False))
    return res

  def h_manager_control(args):
    from ai.tools.system_control_tools import manager_control
    from ai.tools.audit_store import record_audit
    action = str(args.get("action", "status"))
    if action in ("start", "stop", "restart", "rebuild"):
      err = stationary_check("restart_service")
      if err:
        return err
    res = manager_control(
      action,
      use_webcam=bool(args.get("use_webcam")),
      rebuild=bool(args.get("rebuild")),
      timeout=int(args.get("timeout", 600) or 600),
    )
    record_audit(action=f"manager_{action}", tool="manager_control", detail={"action": action}, ok=res.get("ok", False))
    return res

  def h_git_status(_a):
    from ai.tools.git_tools import git_status
    return git_status()

  def h_git_diff(args):
    from ai.tools.git_tools import git_diff
    return git_diff(path=str(args.get("path", "")), stat=bool(args.get("stat")))

  def h_git_list_branches(args):
    from ai.tools.git_tools import git_list_branches
    return git_list_branches(
      include_remote=bool(args.get("include_remote", True)),
      limit=int(args.get("limit", 80) or 80),
    )

  def h_git_checkout(args):
    branch = str(args.get("branch", "")).strip()
    if not branch:
      return {"ok": False, "error": "branch required"}
    if not args.get("confirm"):
      if needs_confirm():
        from ai.tools.git_tools import git_list_branches
        branches = git_list_branches(limit=30)
        return {
          "ok": True,
          "needs_confirmation": True,
          "hint": f"Set confirm=true to checkout '{branch}'.",
          "current": branches.get("current"),
          "local_preview": (branches.get("local") or [])[:15],
        }
    err = stationary_check("write_param")
    if err:
      return err
    from ai.tools.git_tools import git_checkout
    from ai.tools.audit_store import record_audit
    res = git_checkout(
      branch=branch,
      create=bool(args.get("create")),
      start_point=str(args.get("start_point", "")),
    )
    record_audit(
      action="git_checkout",
      tool="git_checkout",
      detail={"branch": branch, "created": bool(args.get("create")), **{k: res.get(k) for k in ("ok", "previous_branch", "branch")}},
      ok=res.get("ok", False),
    )
    return res

  def h_git_pull(args):
    if not args.get("confirm"):
      if needs_confirm():
        return {"ok": True, "needs_confirmation": True, "hint": "Set confirm=true to pull."}
    from ai.tools.git_tools import git_pull
    from ai.tools.audit_store import record_audit
    res = git_pull(remote=str(args.get("remote", "origin")), branch=str(args.get("branch", "")))
    record_audit(action="git_pull", tool="git_pull", detail=res, ok=res.get("ok", False))
    return res

  def _git_write_confirm(args, hint: str):
    if not args.get("confirm") and needs_confirm():
      return {"ok": True, "needs_confirmation": True, "hint": hint}
    err = stationary_check("write_param")
    return err

  def h_git_fetch(args):
    from ai.tools.git_tools import git_fetch
    return git_fetch(remote=str(args.get("remote", "origin")), prune=bool(args.get("prune", True)))

  def h_git_stash(args):
    pending = _git_write_confirm(args, "Set confirm=true to stash.")
    if pending:
      return pending
    from ai.tools.git_tools import git_stash
    from ai.tools.audit_store import record_audit
    res = git_stash(
      message=str(args.get("message", "op助手 stash")),
      include_untracked=bool(args.get("include_untracked")),
    )
    record_audit(action="git_stash", tool="git_stash", detail=res, ok=res.get("ok", False))
    return res

  def h_git_stash_pop(args):
    pending = _git_write_confirm(args, "Set confirm=true to stash pop.")
    if pending:
      return pending
    from ai.tools.git_tools import git_stash_pop
    from ai.tools.audit_store import record_audit
    res = git_stash_pop(index=int(args.get("index", 0) or 0))
    record_audit(action="git_stash_pop", tool="git_stash_pop", detail=res, ok=res.get("ok", False))
    return res

  def h_git_commit(args):
    pending = _git_write_confirm(args, "Set confirm=true to commit.")
    if pending:
      return pending
    from ai.tools.git_tools import git_commit
    from ai.tools.audit_store import record_audit
    paths = args.get("paths")
    path_list = [str(x) for x in paths] if isinstance(paths, list) else None
    res = git_commit(
      message=str(args.get("message", "")),
      add_all=bool(args.get("add_all", True)),
      paths=path_list,
    )
    record_audit(action="git_commit", tool="git_commit", detail=res, ok=res.get("ok", False))
    return res

  def h_apply_tune_from_route(args):
    err = stationary_check("write_param")
    if err:
      return err
    from ai.tools.diagnostics_tools import apply_tune_from_route
    from ai.tools.audit_store import record_audit
    state = get_state_reader().update(timeout=0)
    brand = getattr(state, "brand", "") or ""
    route_before = str(args.get("route_before", "") or "").strip()
    route_after = str(args.get("route_after", "") or "").strip() or str(args.get("route_name", "") or "").strip()
    res = apply_tune_from_route(
      params,
      str(args.get("route_name", "")),
      brand=brand,
      confirm=bool(args.get("confirm")),
      max_params=int(args.get("max_params", 5) or 5),
      route_before=route_before,
      route_after=route_after,
      skip_regression_check=bool(args.get("skip_regression_check")),
      admin=not needs_confirm(),
    )
    if res.get("applied"):
      record_audit(action="apply_tune_from_route", tool="apply_tune_from_route", detail=res, ok=True)
    return res

  def h_compare_tune_ab(args):
    from ai.tools.route_analysis_tools import compare_tune_ab
    return compare_tune_ab(
      str(args.get("route_a", "")),
      str(args.get("route_b", "")),
      label_a=str(args.get("label_a", "before")),
      label_b=str(args.get("label_b", "after")),
    )

  def h_score_route_tune(args):
    from ai.tools.route_scoring_tools import score_route_tune
    return score_route_tune(str(args.get("route", "")))

  def h_score_tune_session(args):
    from ai.tools.route_scoring_tools import score_tune_session
    return score_tune_session(
      str(args.get("route_before", "")),
      str(args.get("route_after", "")),
      min_score_delta=float(args.get("min_score_delta", -5) or -5),
    )

  def h_route_event_timeline(args):
    from ai.tools.route_timeline_tools import route_event_timeline
    return route_event_timeline(
      str(args.get("route", "")),
      max_events=int(args.get("max_events", 80) or 80),
    )

  def h_device_health(_a):
    from ai.tools.device_health_tools import device_health
    return device_health()

  def h_panda_status(_a):
    from ai.tools.device_health_tools import panda_status
    return panda_status(get_state_reader=get_state_reader)

  def h_list_tune_passport(args):
    from ai.tools.tune_passport_store import list_tune_passport
    return list_tune_passport(limit=int(args.get("limit", 30) or 30))

  def h_manage_param_watchlist(args):
    from ai.tools.tune_passport_store import manage_param_watchlist
    return manage_param_watchlist(
      params,
      add=args.get("add") if isinstance(args.get("add"), list) else None,
      remove=args.get("remove") if isinstance(args.get("remove"), list) else None,
      replace=args.get("replace") if isinstance(args.get("replace"), list) else None,
    )

  def h_check_param_watchlist(args):
    from ai.tools.tune_passport_store import check_param_watchlist, get_param_watchlist
    import json as _json
    if args.get("reset_baseline"):
      keys = get_param_watchlist(params)
      baseline = {}
      for k in keys:
        try:
          v = params.get(k)
          baseline[k] = v.decode(errors="replace") if isinstance(v, bytes) else v
        except Exception:
          baseline[k] = None
      params.put("ai_param_watchlist_baseline", _json.dumps(baseline, ensure_ascii=False))
    return check_param_watchlist(params)

  def h_generate_adaptation_pr_draft(args):
    from ai.tools.adaptation_pr_tools import generate_adaptation_pr_draft
    return generate_adaptation_pr_draft(
      project_name=str(args.get("project_name", "")),
      draft_id=str(args.get("draft_id", "")),
      summary=str(args.get("summary", "")),
    )

  def h_post_drive_voice_summary(args):
    from ai.tools.voice_summary_tools import post_drive_voice_summary
    state = get_state_reader().update(timeout=0)
    return post_drive_voice_summary(
      params,
      get_state_reader,
      brand=getattr(state, "brand", "") or "",
      route_name=str(args.get("route_name", "")),
      speak=bool(args.get("speak")),
    )

  def h_sync_knowledge_from_docs(args):
    if args.get("confirm") is False and needs_confirm():
      return {"ok": True, "needs_confirmation": True, "hint": "Set confirm=true to sync docs into RAG."}
    from ai.tools.rag_sync_tools import sync_knowledge_from_docs
    return sync_knowledge_from_docs(params, max_files=int(args.get("max_files", 40) or 40))

  def h_pc_devsync_run(args):
    if not args.get("confirm"):
      if needs_confirm():
        return {"ok": True, "needs_confirmation": True, "hint": "Set confirm=true to sync."}
    from ai.tools.devops_tools import pc_devsync_run
    from ai.tools.audit_store import record_audit
    res = pc_devsync_run(
      device_ip=str(args.get("device_ip", "")),
      remote_path=str(args.get("remote_path", "/data/openpilot")),
      identity=str(args.get("identity", "")) or None,
      dry_run=bool(args.get("dry_run")),
    )
    record_audit(action="pc_devsync_run", tool="pc_devsync_run", detail=res, ok=res.get("ok", False))
    return res

  def h_live_can_capture(args):
    from ai.tools.live_tools import live_can_capture
    return live_can_capture(
      duration_sec=float(args.get("duration_sec", 2) or 2),
      max_frames=int(args.get("max_frames", 300) or 300),
    )

  def h_network_diagnostics(args):
    from ai.tools.network_tools import network_diagnostics
    return network_diagnostics(
      device_ip=str(args.get("device_ip", "")),
      ping_count=int(args.get("ping_count", 3) or 3),
    )

  def h_list_audit_trail(args):
    from ai.tools.audit_store import list_audit_trail
    return list_audit_trail(limit=int(args.get("limit", 50) or 50))

  def h_list_plugins(_a):
    from ai.plugins.loader import list_plugins
    return list_plugins()

  def h_git_push(args):
    pending = _git_write_confirm(args, "Set confirm=true to push.")
    if pending:
      return pending
    from ai.tools.git_tools import git_push
    from ai.tools.audit_store import record_audit
    res = git_push(
      remote=str(args.get("remote", "origin")),
      branch=str(args.get("branch", "")),
      set_upstream=bool(args.get("set_upstream")),
    )
    record_audit(action="git_push", tool="git_push", detail=res, ok=res.get("ok", False))
    return res

  def h_ota_status(_a):
    from ai.tools.ota_tools import ota_status
    return ota_status(params)

  def h_batch_compare_routes_tune(args):
    from ai.tools.route_scoring_tools import batch_compare_routes_tune
    routes = args.get("routes") or []
    if not isinstance(routes, list):
      return {"ok": False, "error": "routes must be an array"}
    return batch_compare_routes_tune(
      [str(x) for x in routes],
      baseline=str(args.get("baseline", "")),
      limit=int(args.get("limit", 8) or 8),
    )

  def h_run_pytest(args):
    from ai.tools.dev_ci_tools import run_pytest
    return run_pytest(
      path=str(args.get("path", "ai/tests")),
      keyword=str(args.get("keyword", "")),
      max_fail=int(args.get("max_fail", 1) or 1),
    )

  def h_run_scons_build(args):
    err = stationary_check("restart_service")
    if err:
      return err
    from ai.tools.dev_ci_tools import run_scons_build
    from ai.tools.audit_store import record_audit
    res = run_scons_build(
      target=str(args.get("target", "")),
      jobs=int(args.get("jobs", 0) or 0) or None,
    )
    record_audit(action="run_scons_build", tool="run_scons_build", detail=res, ok=res.get("ok", False))
    return res

  def h_ssh_readonly_exec(args):
    from ai.tools.ssh_tools import ssh_readonly_exec
    return ssh_readonly_exec(
      host=str(args.get("host", "")),
      command=str(args.get("command", "")),
      identity=str(args.get("identity", "")),
      timeout=int(args.get("timeout", 30) or 30),
    )

  def h_list_comma_devices(_a):
    from ai.tools.comma_cloud_tools import list_comma_devices
    return list_comma_devices()

  def h_list_comma_routes(args):
    from ai.tools.comma_cloud_tools import list_comma_routes
    return list_comma_routes(
      dongle_id=str(args.get("dongle_id", "")),
      limit=int(args.get("limit", 20) or 20),
      preserved=bool(args.get("preserved")),
    )

  def h_analyze_route_vision(args):
    from ai.tools.vision_route_tools import analyze_route_vision
    return analyze_route_vision(
      str(args.get("route", "")),
      segment=int(args.get("segment", 0) or 0),
      frame=int(args.get("frame", 0) or 0),
      camera=str(args.get("camera", "front") or "front"),
    )

  def h_plotjuggler_apply_layout(args):
    from ai.tools.viz_layout_tools import plotjuggler_apply_layout
    return plotjuggler_apply_layout(
      str(args.get("layout", "")),
      route=str(args.get("route", "")),
    )

  async def h_search_memory_semantic(args):
    from ai.tools.memory_vectors import search_memory_semantic
    from ai.embedding import load_embedding_config
    from ai.client import load_config_from_params
    cfg = load_config_from_params(params)
    embed_cfg = load_embedding_config(params, cfg)
    return await search_memory_semantic(
      params,
      str(args.get("query", "")),
      limit=int(args.get("limit", 5) or 5),
      embed_config=embed_cfg,
    )

  def h_get_tsk_manager_status(_a):
    from ai.tools.tsk_tools import get_tsk_manager_status
    return get_tsk_manager_status()

  def h_tsk_find_and_install_key(args):
    from ai.tools.tsk_tools import tsk_find_and_install_key
    return tsk_find_and_install_key(confirm=bool(args.get("confirm")), get_state_reader=get_state_reader)

  def h_tsk_extract_key(args):
    from ai.tools.tsk_tools import tsk_extract_key
    return tsk_extract_key(confirm=bool(args.get("confirm")), get_state_reader=get_state_reader)

  def h_tsk_install_secoc_key(args):
    from ai.tools.tsk_tools import tsk_install_secoc_key
    return tsk_install_secoc_key(
      key=str(args.get("key") or ""),
      confirm=bool(args.get("confirm")),
      get_state_reader=get_state_reader,
    )

  def h_tsk_uninstall_key(args):
    from ai.tools.tsk_tools import tsk_uninstall_key
    return tsk_uninstall_key(confirm=bool(args.get("confirm")), get_state_reader=get_state_reader)

  def h_tsk_start_can_collect(args):
    from ai.tools.tsk_tools import tsk_start_can_collect
    return tsk_start_can_collect(confirm=bool(args.get("confirm")), get_state_reader=get_state_reader)

  def h_tsk_start_dataflash_dump(args):
    from ai.tools.tsk_tools import tsk_start_dataflash_dump
    return tsk_start_dataflash_dump(confirm=bool(args.get("confirm")), get_state_reader=get_state_reader)

  def h_tsk_clear_cache(args):
    from ai.tools.tsk_tools import tsk_clear_cache
    return tsk_clear_cache(confirm=bool(args.get("confirm")), get_state_reader=get_state_reader)

  def h_tsk_wait_for_job(args):
    from ai.tools.tsk_tools import tsk_wait_for_job
    return tsk_wait_for_job(
      job=str(args.get("job") or "can"),
      timeout_seconds=float(args.get("timeout_seconds") or 600),
    )

  def h_tsk_cancel_job(args):
    from ai.tools.tsk_tools import tsk_cancel_job
    return tsk_cancel_job(
      job=str(args.get("job") or "all"),
      confirm=bool(args.get("confirm")),
      get_state_reader=get_state_reader,
    )

  def h_tsk_restart_pandad(args):
    from ai.tools.tsk_tools import tsk_restart_pandad
    return tsk_restart_pandad(confirm=bool(args.get("confirm")), get_state_reader=get_state_reader)

  def h_tsk_run_pipeline(args):
    from ai.tools.tsk_tools import tsk_run_pipeline
    return tsk_run_pipeline(
      confirm=bool(args.get("confirm")),
      skip_can=bool(args.get("skip_can")),
      skip_dataflash=bool(args.get("skip_dataflash")),
      can_timeout_seconds=float(args.get("can_timeout_seconds") or 120),
      dataflash_timeout_seconds=float(args.get("dataflash_timeout_seconds") or 300),
      get_state_reader=get_state_reader,
    )

  def h_get_tsk_offroad_alert_status(_a):
    from ai.tools.tsk_tools import get_tsk_offroad_alert_status
    return get_tsk_offroad_alert_status()

  def h_konik_connect_status(args):
    from ai.tools.konik_connect_tools import konik_connect_status
    return konik_connect_status(device_ip=str(args.get("device_ip") or ""))

  def h_konik_generate_device_keys(args):
    from ai.tools.konik_connect_tools import konik_generate_device_keys
    return konik_generate_device_keys(
      confirm=bool(args.get("confirm")),
      device_ip=str(args.get("device_ip") or ""),
      get_state_reader=get_state_reader,
    )

  def h_konik_reset_dongle_id(args):
    from ai.tools.konik_connect_tools import konik_reset_dongle_id
    return konik_reset_dongle_id(
      confirm=bool(args.get("confirm")),
      device_ip=str(args.get("device_ip") or ""),
      get_state_reader=get_state_reader,
    )

  def h_konik_register_device(args):
    from ai.tools.konik_connect_tools import konik_register_device
    return konik_register_device(
      confirm=bool(args.get("confirm")),
      device_ip=str(args.get("device_ip") or ""),
      get_state_reader=get_state_reader,
    )

  def h_konik_connect_pipeline(args):
    from ai.tools.konik_connect_tools import konik_connect_pipeline
    return konik_connect_pipeline(
      confirm=bool(args.get("confirm")),
      device_ip=str(args.get("device_ip") or ""),
      regenerate_keys=bool(args.get("regenerate_keys")),
      get_state_reader=get_state_reader,
    )

  base = {
    "reboot_device": h_reboot_device,
    "shutdown_device": h_shutdown_device,
    "manager_control": h_manager_control,
    "git_status": h_git_status,
    "git_diff": h_git_diff,
    "git_list_branches": h_git_list_branches,
    "git_checkout": h_git_checkout,
    "git_pull": h_git_pull,
    "git_fetch": h_git_fetch,
    "git_stash": h_git_stash,
    "git_stash_pop": h_git_stash_pop,
    "git_commit": h_git_commit,
    "apply_tune_from_route": h_apply_tune_from_route,
    "compare_tune_ab": h_compare_tune_ab,
    "score_route_tune": h_score_route_tune,
    "score_tune_session": h_score_tune_session,
    "route_event_timeline": h_route_event_timeline,
    "device_health": h_device_health,
    "panda_status": h_panda_status,
    "list_tune_passport": h_list_tune_passport,
    "manage_param_watchlist": h_manage_param_watchlist,
    "check_param_watchlist": h_check_param_watchlist,
    "generate_adaptation_pr_draft": h_generate_adaptation_pr_draft,
    "post_drive_voice_summary": h_post_drive_voice_summary,
    "sync_knowledge_from_docs": h_sync_knowledge_from_docs,
    "pc_devsync_run": h_pc_devsync_run,
    "live_can_capture": h_live_can_capture,
    "network_diagnostics": h_network_diagnostics,
    "list_audit_trail": h_list_audit_trail,
    "list_plugins": h_list_plugins,
    "git_push": h_git_push,
    "ota_status": h_ota_status,
    "batch_compare_routes_tune": h_batch_compare_routes_tune,
    "run_pytest": h_run_pytest,
    "run_scons_build": h_run_scons_build,
    "ssh_readonly_exec": h_ssh_readonly_exec,
    "list_comma_devices": h_list_comma_devices,
    "list_comma_routes": h_list_comma_routes,
    "analyze_route_vision": h_analyze_route_vision,
    "plotjuggler_apply_layout": h_plotjuggler_apply_layout,
    "search_memory_semantic": h_search_memory_semantic,
    "get_tsk_manager_status": h_get_tsk_manager_status,
    "tsk_find_and_install_key": h_tsk_find_and_install_key,
    "tsk_extract_key": h_tsk_extract_key,
    "tsk_install_secoc_key": h_tsk_install_secoc_key,
    "tsk_uninstall_key": h_tsk_uninstall_key,
    "tsk_start_can_collect": h_tsk_start_can_collect,
    "tsk_start_dataflash_dump": h_tsk_start_dataflash_dump,
    "tsk_clear_cache": h_tsk_clear_cache,
    "tsk_wait_for_job": h_tsk_wait_for_job,
    "tsk_cancel_job": h_tsk_cancel_job,
    "tsk_restart_pandad": h_tsk_restart_pandad,
    "tsk_run_pipeline": h_tsk_run_pipeline,
    "get_tsk_offroad_alert_status": h_get_tsk_offroad_alert_status,
    "konik_connect_status": h_konik_connect_status,
    "konik_generate_device_keys": h_konik_generate_device_keys,
    "konik_reset_dongle_id": h_konik_reset_dongle_id,
    "konik_register_device": h_konik_register_device,
    "konik_connect_pipeline": h_konik_connect_pipeline,
  }
  base.update(make_plugin_handlers(ctx))
  return base
