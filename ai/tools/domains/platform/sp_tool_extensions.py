"""openpilot grouped settings + device/sunnylink tools (merged via extensions.py)."""

from __future__ import annotations

from typing import Any, Callable

SP_EXTENSION_TOOL_META: dict[str, dict[str, Any]] = {
  "get_torque_settings": {"label": "扭矩设置", "group": "read", "default_enabled": True, "driving": True},
  "set_torque_settings": {"label": "写入扭矩", "group": "write", "default_enabled": True, "driving": True},
  "get_lane_change_settings": {"label": "变道设置", "group": "read", "default_enabled": True, "driving": True},
  "set_lane_change_settings": {"label": "写入变道", "group": "write", "default_enabled": True, "driving": True},
  "get_speed_limit_settings": {"label": "限速设置", "group": "read", "default_enabled": True, "driving": True},
  "set_speed_limit_settings": {"label": "写入限速", "group": "write", "default_enabled": True, "driving": True},
  "list_visuals_settings": {"label": "视觉 HUD", "group": "read", "default_enabled": True, "driving": True},
  "set_visuals_settings": {"label": "写入视觉", "group": "write", "default_enabled": True, "driving": True},
  "get_sunnylink_status": {"label": "Sunnylink 状态", "group": "read", "default_enabled": True, "driving": True},
  "trigger_sunnylink_backup": {"label": "Sunnylink 备份", "group": "write", "default_enabled": True, "driving": False},
  "trigger_sunnylink_restore": {"label": "Sunnylink 恢复", "group": "write", "default_enabled": True, "driving": False},
  "get_sp_device_hw": {"label": "设备硬件", "group": "read", "default_enabled": True, "driving": True},
  "set_sp_dev_beep": {"label": "Lite 蜂鸣", "group": "write", "default_enabled": True, "driving": True},
  "get_model_tune_settings": {"label": "模型调参", "group": "read", "default_enabled": True, "driving": True},
  "set_model_tune_settings": {"label": "写入模型调参", "group": "write", "default_enabled": True, "driving": True},
  "get_display_settings": {"label": "显示设置", "group": "read", "default_enabled": True, "driving": True},
  "set_display_settings": {"label": "写入显示", "group": "write", "default_enabled": True, "driving": True},
  "get_device_settings": {"label": "设备设置", "group": "read", "default_enabled": True, "driving": True},
  "set_device_settings": {"label": "写入设备", "group": "write", "default_enabled": True, "driving": True},
  "list_sunnylink_backups": {"label": "Sunnylink 备份列表", "group": "read", "default_enabled": True, "driving": True},
  "get_backup_manager_status": {"label": "备份进程状态", "group": "read", "default_enabled": True, "driving": True},
  "list_f4_pandas": {"label": "F4 Panda 列表", "group": "read", "default_enabled": True, "driving": True},
  "list_all_pandas": {"label": "全部 Panda 列表", "group": "read", "default_enabled": True, "driving": True},
  "panda_firmware_status": {"label": "Panda 固件签名", "group": "read", "default_enabled": True, "driving": True},
  "recover_dos_panda": {"label": "刷 DOS/黑熊固件", "group": "write", "default_enabled": True, "driving": False},
  "flash_panda_firmware": {"label": "刷 Panda 固件", "group": "write", "default_enabled": True, "driving": False},
  "rebuild_pandad": {"label": "重编 pandad", "group": "write", "default_enabled": True, "driving": False},
  "rebuild_pandad_tici": {"label": "重编 pandad（旧名）", "group": "write", "default_enabled": True, "driving": False},
  "panda_recovery_hint": {"label": "Panda 恢复建议", "group": "read", "default_enabled": True, "driving": True},
  "build_panda_firmware": {"label": "编译 panda 固件", "group": "write", "default_enabled": True, "driving": False, "pc_only": False},
  "build_panda_h7_firmware": {"label": "编译 H7 固件", "group": "write", "default_enabled": True, "driving": False, "pc_only": False},
  "build_panda_tici_firmware": {"label": "编译 H7 固件（旧名）", "group": "write", "default_enabled": True, "driving": False, "pc_only": False},
  "github_runner_status": {"label": "GitHub Runner 状态", "group": "read", "default_enabled": True, "driving": True},
  "github_runner_recovery_hint": {"label": "Runner 排查建议", "group": "read", "default_enabled": True, "driving": True},
  "install_github_runner": {"label": "安装 GitHub Runner", "group": "write", "default_enabled": True, "driving": False},
  "github_actions_auth_status": {"label": "GitHub PAT 状态", "group": "read", "default_enabled": True, "driving": True},
  "set_github_actions_pat": {"label": "配置 GitHub PAT", "group": "write", "default_enabled": True, "driving": False},
  "list_github_workflow_runs": {"label": "Workflow 运行列表", "group": "read", "default_enabled": True, "driving": True},
  "get_github_workflow_run": {"label": "Workflow 运行详情", "group": "read", "default_enabled": True, "driving": True},
  "cancel_github_workflow_run": {"label": "取消 Workflow", "group": "write", "default_enabled": True, "driving": False},
  "list_github_runners": {"label": "GitHub Runners 列表", "group": "read", "default_enabled": True, "driving": True},
  "stop_github_runner_service": {"label": "停止 Runner 服务", "group": "write", "default_enabled": True, "driving": False},
  "translation_status": {"label": "翻译更新可用性", "group": "read", "default_enabled": True, "driving": True},
  "update_zh_translations": {"label": "更新中文翻译", "group": "write", "default_enabled": True, "driving": False, "pc_only": False},
}

SP_EXTENSION_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "get_torque_settings", "description": "Read LiveTorque / torque override params.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_torque_settings", "description": "Write torque-related params while stationary.", "parameters": {"type": "object", "properties": {"params": {"type": "object"}, "confirm": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
  {"type": "function", "function": {"name": "get_lane_change_settings", "description": "Read AutoLaneChange timer and BSM delay.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_lane_change_settings", "description": "Write lane change params while stationary.", "parameters": {"type": "object", "properties": {"params": {"type": "object"}, "confirm": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
  {"type": "function", "function": {"name": "get_speed_limit_settings", "description": "Read SpeedLimit* params.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_speed_limit_settings", "description": "Write speed limit params while stationary.", "parameters": {"type": "object", "properties": {"params": {"type": "object"}, "confirm": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
  {"type": "function", "function": {"name": "list_visuals_settings", "description": "Read visuals/HUD toggle params.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_visuals_settings", "description": "Write visuals/HUD params while stationary.", "parameters": {"type": "object", "properties": {"params": {"type": "object"}, "confirm": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
  {"type": "function", "function": {"name": "get_sunnylink_status", "description": "Sunnylink registration, backup/restore pending flags.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "trigger_sunnylink_backup", "description": "Queue Sunnylink cloud backup (offroad).", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": ["confirm"]}}},
  {"type": "function", "function": {"name": "trigger_sunnylink_restore", "description": "Queue Sunnylink restore from version (offroad).", "parameters": {"type": "object", "properties": {"version": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["confirm"]}}},
  {"type": "function", "function": {"name": "get_sp_device_hw", "description": "Lite variant, SpDevBeep, Panda count, board hints.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_sp_dev_beep", "description": "Enable SpDevBeep on Lite hardware (GPIO beepd).", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}}, "required": ["enabled", "confirm"]}}},
  {"type": "function", "function": {"name": "get_model_tune_settings", "description": "Read CameraOffset and PlanplusControl (modeld_v2).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_model_tune_settings", "description": "Write CameraOffset / PlanplusControl while stationary.", "parameters": {"type": "object", "properties": {"params": {"type": "object"}, "confirm": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
  {"type": "function", "function": {"name": "get_display_settings", "description": "Read display params (brightness, onroad screen off, interactivity).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_display_settings", "description": "Write display params while stationary.", "parameters": {"type": "object", "properties": {"params": {"type": "object"}, "confirm": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
  {"type": "function", "function": {"name": "get_device_settings", "description": "Read device params (max offroad, boot mode, quiet, developer toggles).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "set_device_settings", "description": "Write device/developer service params while stationary.", "parameters": {"type": "object", "properties": {"params": {"type": "object"}, "confirm": {"type": "boolean"}}, "required": ["params", "confirm"]}}},
  {"type": "function", "function": {"name": "list_sunnylink_backups", "description": "List Sunnylink cloud backups for this device.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "get_backup_manager_status", "description": "backupManagerSP progress and pending backup/restore flags.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "list_f4_pandas", "description": "List USB pandas; highlight F4 (black/DOS) and internal vs external. Read-only.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "list_all_pandas", "description": "List all USB pandas with hw_type/MCU, multi-panda scenario (e.g. F4+H7), and pandad process snapshot. Read-only.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "panda_firmware_status", "description": "List pandas with firmware signature match vs repo build (read-only). Use before/after flash_panda_firmware.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "panda_recovery_hint", "description": "When sidebar NO PANDA or pandaStates empty: recommended tool sequence and doc links.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "build_panda_firmware", "description": "Offroad: run scons in openpilot/panda/board to generate panda.bin.signed (and optionally panda_h7.bin.signed). Firmware is NOT bundled in ai — always built from the panda submodule. target=auto picks F4 and/or H7 from connected pandas; single internal F4 C3 DOS → F4 only.", "parameters": {"type": "object", "properties": {"jobs": {"type": "integer"}, "target": {"type": "string", "enum": ["auto", "f4", "h7", "all"], "description": "auto=from USB layout; f4/h7/all → panda/board (same scons)"}}, "required": []}}},
  {"type": "function", "function": {"name": "build_panda_h7_firmware", "description": "Offroad: scons panda/board → panda_h7.bin.signed (external red panda / H7).", "parameters": {"type": "object", "properties": {"jobs": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "build_panda_tici_firmware", "description": "Deprecated alias for build_panda_h7_firmware.", "parameters": {"type": "object", "properties": {"jobs": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "recover_dos_panda", "description": "Offroad: flash F4 panda (C3 DOS internal or aux black panda) with panda.bin.signed. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "serial": {"type": "string"}, "external": {"type": "boolean", "description": "Flash first external F4 (aux black panda)"}, "internal": {"type": "boolean", "description": "Flash internal F4 (C3 DOS)"}, "build_firmware": {"type": "boolean", "description": "Run scons first if firmware missing"}}, "required": []}}},
  {"type": "function", "function": {"name": "flash_panda_firmware", "description": "Offroad: flash all connected pandas with repo firmware (H7/red panda via pandad, F4/DOS/black via panda/). Prefer this over recover_dos_panda when user asks to flash panda generally. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "serial": {"type": "string", "description": "Flash one serial only"}, "all_pandas": {"type": "boolean", "description": "Flash every connected panda (default true)"}, "external": {"type": "boolean"}, "internal": {"type": "boolean"}, "build_firmware": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "rebuild_pandad", "description": "Offroad: run ai/scripts/rebuild_pandad.sh after git reset deleted pandad binary. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "rebuild_pandad_tici", "description": "Deprecated alias for rebuild_pandad.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "github_runner_status", "description": "Read C3 GitHub Actions self-hosted runner: install paths, EnableGithubRunner gates, systemd service name/state. See ai/docs/GITHUB_RUNNER.md.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "github_runner_recovery_hint", "description": "When CI build is Pending or runner offline: recommended steps (params, systemd, install).", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "install_github_runner", "description": "Offroad: run release/ci/install_github_runner.sh on C3. User provides GitHub Actions registration token (Settings→Actions→Runners→New self-hosted runner — NOT a PAT). When user pastes token and asks to install, call with token=... and confirm=true after they approve. Token never logged or returned.", "parameters": {"type": "object", "properties": {"token": {"type": "string", "description": "One-time runner registration token from GitHub"}, "repo_url": {"type": "string"}, "restore": {"type": "boolean", "description": "Restore existing .credentials/.service with new token"}, "start_at_boot": {"type": "boolean"}, "confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "github_actions_auth_status", "description": "Check ai_github_actions_pat in config.json: configured/valid. Never returns token. See ai/docs/GITHUB_RUNNER.md.", "parameters": {"type": "object", "properties": {"repo_url": {"type": "string"}}, "required": []}}},
  {"type": "function", "function": {"name": "set_github_actions_pat", "description": "Store or clear ai_github_actions_pat in config.json (classic/fine-grained PAT with repo+actions). confirm=true required. Empty token clears. Token never logged.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "list_github_workflow_runs", "description": "List GitHub Actions workflow runs (default build.yaml). Requires ai_github_actions_pat.", "parameters": {"type": "object", "properties": {"repo_url": {"type": "string"}, "workflow": {"type": "string"}, "status": {"type": "string", "description": "e.g. in_progress, queued, completed"}, "branch": {"type": "string"}, "per_page": {"type": "integer"}}, "required": []}}},
  {"type": "function", "function": {"name": "get_github_workflow_run", "description": "Workflow run details and jobs by run_id. Requires ai_github_actions_pat.", "parameters": {"type": "object", "properties": {"run_id": {"type": "integer"}, "repo_url": {"type": "string"}}, "required": ["run_id"]}}},
  {"type": "function", "function": {"name": "cancel_github_workflow_run", "description": "Cancel a workflow run on GitHub. confirm=true required. Requires ai_github_actions_pat with actions write.", "parameters": {"type": "object", "properties": {"run_id": {"type": "integer"}, "repo_url": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["run_id"]}}},
  {"type": "function", "function": {"name": "list_github_runners", "description": "List self-hosted runners from GitHub API (online/busy/labels) plus local install summary.", "parameters": {"type": "object", "properties": {"repo_url": {"type": "string"}}, "required": []}}},
  {"type": "function", "function": {"name": "stop_github_runner_service", "description": "Offroad: sudo systemctl stop local runner service. Does not uninstall. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
  {"type": "function", "function": {"name": "translation_status", "description": "Check whether this branch can regenerate UI translation files (SConstruct, source UI files, scripts present). Read-only.", "parameters": {"type": "object", "properties": {}, "required": []}}},
  {"type": "function", "function": {"name": "update_zh_translations", "description": "Run merge_zh_translations.py then supplement_zh_translations.py to regenerate app_zh-CHS.po and app_zh-CHT.po. Only works on source branches with SConstruct and UI Python sources; fails safely on prebuilt branches. confirm=true required.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}, "skip_merge": {"type": "boolean", "description": "Skip string extraction and only apply supplement"}, "skip_supplement": {"type": "boolean", "description": "Skip supplement and only run merge"}}, "required": []}}},
]


def make_sp_extension_handlers(
  p,
  *,
  stationary_check: Callable[[str], dict[str, Any] | None],
  needs_confirm: Callable[[], bool],
  get_state_reader: Callable[[], Any] | None = None,
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
  from ai.tools.domains.platform.write_pending import create_pending

  def _group_set(action: str, group: str, apply_fn):
    def handler(args):
      err = stationary_check("write_param")
      if err:
        return err
      writes = args.get("params") or {}
      if not isinstance(writes, dict):
        return {"ok": False, "error": "params must be an object"}
      if not args.get("confirm") and needs_confirm():
        from ai.tools.domains.tune.sp_tune_groups import preview_group_writes
        preview = preview_group_writes(p, writes, group)
        if not preview.get("ok", True):
          return preview
        return create_pending(p, action=action, payload={"params": writes}, preview=preview.get("changes", preview))
      return apply_fn(p, writes)
    return handler

  def _device_group_set(action: str, group: str, apply_fn):
    def handler(args):
      err = stationary_check("write_param")
      if err:
        return err
      writes = args.get("params") or {}
      if not isinstance(writes, dict):
        return {"ok": False, "error": "params must be an object"}
      if not args.get("confirm") and needs_confirm():
        from ai.tools.domains.platform.display_device_tools import preview_group_writes as dev_preview
        preview = dev_preview(p, writes, group)
        if not preview.get("ok", True):
          return preview
        return create_pending(p, action=action, payload={"params": writes}, preview=preview.get("changes", preview))
      return apply_fn(p, writes)
    return handler

  def _model_tune_set(args):
    err = stationary_check("write_param")
    if err:
      return err
    writes = args.get("params") or {}
    if not args.get("confirm") and needs_confirm():
      from ai.tools.domains.tune.model_tune_tools import preview_model_tune_writes
      preview = preview_model_tune_writes(p, writes)
      if not preview.get("ok", True):
        return preview
      return create_pending(p, action="set_model_tune_settings", payload={"params": writes}, preview=preview.get("changes", preview))
    from ai.tools.domains.tune.model_tune_tools import apply_model_tune_writes
    return apply_model_tune_writes(p, writes)

  def h_get_model_tune_settings(_a):
    from ai.tools.domains.tune.model_tune_tools import get_model_tune_settings
    return get_model_tune_settings(p)

  def h_get_display_settings(_a):
    from ai.tools.domains.platform.display_device_tools import get_display_settings
    return get_display_settings(p)

  def h_get_device_settings(_a):
    from ai.tools.domains.platform.display_device_tools import get_device_settings
    return get_device_settings(p)

  def h_list_sunnylink_backups(_a):
    from ai.tools.domains.cloud.sunnylink_tools import list_sunnylink_backups
    return list_sunnylink_backups(p)

  def h_get_backup_manager_status(_a):
    from ai.tools.domains.cloud.sunnylink_tools import get_backup_manager_status
    return get_backup_manager_status(get_state_reader=get_state_reader)

  def h_list_f4_pandas(_a):
    from ai.tools.domains.platform.panda_flash_tools import list_f4_pandas
    return list_f4_pandas()

  def h_list_all_pandas(_a):
    from ai.tools.domains.platform.panda_flash_tools import list_all_pandas
    return list_all_pandas()

  def h_panda_firmware_status(_a):
    from ai.tools.domains.platform.panda_flash_tools import panda_firmware_status
    return panda_firmware_status()

  def h_panda_recovery_hint(_a):
    from ai.tools.domains.platform.panda_flash_tools import panda_recovery_hint
    return panda_recovery_hint(get_state_reader=get_state_reader)

  def h_build_panda_firmware(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.platform.panda_flash_tools import build_panda_firmware
    target = str(args.get("target") or "auto")
    return build_panda_firmware(jobs=int(args.get("jobs", 4) or 4), target=target)

  def h_build_panda_h7_firmware(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.platform.panda_flash_tools import build_panda_h7_firmware
    return build_panda_h7_firmware(jobs=int(args.get("jobs", 4) or 4))

  def h_build_panda_tici_firmware(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.platform.panda_flash_tools import build_panda_tici_firmware
    return build_panda_tici_firmware(jobs=int(args.get("jobs", 4) or 4))

  def h_recover_dos_panda(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.platform.panda_flash_tools import recover_dos_panda
    return recover_dos_panda(
      confirm=bool(args.get("confirm")),
      serial=str(args.get("serial", "") or ""),
      external=bool(args.get("external")),
      internal=bool(args.get("internal")),
      build_firmware=bool(args.get("build_firmware")),
    )

  def h_flash_panda_firmware(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.platform.panda_flash_tools import flash_panda_firmware
    all_pandas = args.get("all_pandas")
    if all_pandas is None:
      all_pandas = not bool(args.get("serial") or args.get("external") or args.get("internal"))
    return flash_panda_firmware(
      confirm=bool(args.get("confirm")),
      serial=str(args.get("serial", "") or ""),
      all_pandas=bool(all_pandas),
      external=bool(args.get("external")),
      internal=bool(args.get("internal")),
      build_firmware=bool(args.get("build_firmware")),
    )

  def h_rebuild_pandad(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.platform.panda_flash_tools import rebuild_pandad
    return rebuild_pandad(confirm=bool(args.get("confirm")))

  def h_rebuild_pandad_tici(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.platform.panda_flash_tools import rebuild_pandad_tici
    return rebuild_pandad_tici(confirm=bool(args.get("confirm")))

  def h_github_runner_status(_a):
    from ai.tools.domains.devops.github_runner_tools import github_runner_status
    return github_runner_status(p)

  def h_github_runner_recovery_hint(_a):
    from ai.tools.domains.devops.github_runner_tools import github_runner_recovery_hint
    return github_runner_recovery_hint(p, get_state_reader=get_state_reader)

  def h_install_github_runner(args):
    err = stationary_check("run_shell")
    if err:
      return err
    from ai.tools.domains.devops.github_runner_tools import install_github_runner_preview

    token = str(args.get("token", "") or "").strip()
    repo_url = str(args.get("repo_url", "") or "")
    start_at_boot = bool(args.get("start_at_boot"))
    restore = bool(args.get("restore"))
    confirm = bool(args.get("confirm"))

    if confirm:
      return install_github_runner_preview(
        token=token,
        repo_url=repo_url,
        start_at_boot=start_at_boot,
        restore=restore,
        confirm=True,
        params=p,
      )

    preview = install_github_runner_preview(
      token=token,
      repo_url=repo_url,
      start_at_boot=start_at_boot,
      restore=restore,
      confirm=False,
      params=p,
    )
    if token and needs_confirm():
      return create_pending(
        p,
        action="install_github_runner",
        payload={
          "token": token,
          "repo_url": repo_url,
          "start_at_boot": start_at_boot,
          "restore": restore,
        },
        preview=preview.get("preview", preview),
      )
    return preview

  def h_github_actions_auth_status(args):
    from ai.tools.domains.devops.github_actions_tools import github_actions_auth_status
    return github_actions_auth_status(p, repo_url=str(args.get("repo_url", "") or ""))

  def h_set_github_actions_pat(args):
    err = stationary_check("write_param")
    if err:
      return err
    from ai.tools.domains.devops.github_actions_tools import set_github_actions_pat
    return set_github_actions_pat(
      token=str(args.get("token", "") or ""),
      confirm=bool(args.get("confirm")),
      params=p,
    )

  def h_list_github_workflow_runs(args):
    from ai.tools.domains.devops.github_actions_tools import list_github_workflow_runs
    return list_github_workflow_runs(
      repo_url=str(args.get("repo_url", "") or ""),
      workflow=str(args.get("workflow", "") or "build.yaml"),
      status=str(args.get("status", "") or "") or None,
      branch=str(args.get("branch", "") or "") or None,
      per_page=int(args.get("per_page", 10) or 10),
      params=p,
    )

  def h_get_github_workflow_run(args):
    from ai.tools.domains.devops.github_actions_tools import get_github_workflow_run
    return get_github_workflow_run(
      run_id=int(args.get("run_id") or 0),
      repo_url=str(args.get("repo_url", "") or ""),
      params=p,
    )

  def h_cancel_github_workflow_run(args):
    from ai.tools.domains.devops.github_actions_tools import cancel_github_workflow_run
    return cancel_github_workflow_run(
      run_id=int(args.get("run_id") or 0),
      repo_url=str(args.get("repo_url", "") or ""),
      confirm=bool(args.get("confirm")),
      params=p,
    )

  def h_list_github_runners(args):
    from ai.tools.domains.devops.github_actions_tools import list_github_runners
    return list_github_runners(repo_url=str(args.get("repo_url", "") or ""), params=p)

  def h_stop_github_runner_service(args):
    err = stationary_check("run_shell")
    if err:
      return err

  def h_translation_status(_a):
    from ai.tools.domains.platform.translation_tools import translation_status
    return translation_status()

  def h_update_zh_translations(args):
    from ai.tools.domains.platform.translation_tools import merge_zh_translations, supplement_zh_translations, can_update_translations
    status = can_update_translations()
    if not status["can_update"]:
      return {"ok": False, "error": "Translation update not available on this branch", "details": status}
    if not args.get("confirm") and needs_confirm():
      return {"ok": True, "needs_confirmation": True, "hint": "Set confirm=true to regenerate zh-CHS/zh-CHT po files."}
    skip_merge = bool(args.get("skip_merge"))
    skip_supplement = bool(args.get("skip_supplement"))
    results = {}
    if not skip_merge:
      results["merge"] = merge_zh_translations()
      if not results["merge"]["ok"]:
        return {"ok": False, "error": "merge_zh_translations failed", "results": results}
    if not skip_supplement:
      results["supplement"] = supplement_zh_translations()
      if not results["supplement"]["ok"]:
        return {"ok": False, "error": "supplement_zh_translations failed", "results": results}
    return {"ok": True, "results": results}
    from ai.tools.domains.devops.github_actions_tools import stop_github_runner_service
    return stop_github_runner_service(confirm=bool(args.get("confirm")), params=p)

  def h_get_torque_settings(_a):
    from ai.tools.domains.tune.sp_tune_groups import get_torque_settings
    return get_torque_settings(p)

  def h_get_lane_change_settings(_a):
    from ai.tools.domains.tune.sp_tune_groups import get_lane_change_settings
    return get_lane_change_settings(p)

  def h_get_speed_limit_settings(_a):
    from ai.tools.domains.tune.sp_tune_groups import get_speed_limit_settings
    return get_speed_limit_settings(p)

  def h_list_visuals_settings(_a):
    from ai.tools.domains.tune.sp_tune_groups import list_visuals_settings
    return list_visuals_settings(p)

  def h_get_sunnylink_status(_a):
    from ai.tools.domains.cloud.sunnylink_tools import get_sunnylink_status
    return get_sunnylink_status(p)

  def h_get_sp_device_hw(_a):
    from ai.tools.domains.platform.device_hw_tools import get_sp_device_hw
    return get_sp_device_hw(p, get_state_reader=get_state_reader)

  def h_trigger_sunnylink_backup(args):
    err = stationary_check("write_param")
    if err:
      return err
    if not args.get("confirm") and needs_confirm():
      return {"ok": True, "needs_confirmation": True, "hint": "Set confirm=true to queue backup."}
    from ai.tools.domains.cloud.sunnylink_tools import trigger_sunnylink_backup
    return trigger_sunnylink_backup(p)

  def h_trigger_sunnylink_restore(args):
    err = stationary_check("write_param")
    if err:
      return err
    version = str(args.get("version", "latest") or "latest")
    if not args.get("confirm") and needs_confirm():
      return {"ok": True, "needs_confirmation": True, "version": version, "hint": "Set confirm=true to queue restore."}
    from ai.tools.domains.cloud.sunnylink_tools import trigger_sunnylink_restore
    return trigger_sunnylink_restore(p, version)

  def h_set_sp_dev_beep(args):
    err = stationary_check("write_param")
    if err:
      return err
    enabled = bool(args.get("enabled"))
    if not args.get("confirm") and needs_confirm():
      return {"ok": True, "needs_confirmation": True, "SpDevBeep": enabled}
    from ai.tools.domains.platform.device_hw_tools import set_sp_dev_beep
    return set_sp_dev_beep(p, enabled)

  from ai.tools.domains.tune.sp_tune_groups import (
    apply_lane_change_writes,
    apply_speed_limit_writes,
    apply_torque_writes,
    apply_visuals_writes,
  )

  from ai.tools.domains.platform.display_device_tools import apply_device_writes, apply_display_writes

  return {
    "get_torque_settings": h_get_torque_settings,
    "set_torque_settings": _group_set("set_torque_settings", "torque", apply_torque_writes),
    "get_lane_change_settings": h_get_lane_change_settings,
    "set_lane_change_settings": _group_set("set_lane_change_settings", "lane_change", apply_lane_change_writes),
    "get_speed_limit_settings": h_get_speed_limit_settings,
    "set_speed_limit_settings": _group_set("set_speed_limit_settings", "speed_limit", apply_speed_limit_writes),
    "list_visuals_settings": h_list_visuals_settings,
    "set_visuals_settings": _group_set("set_visuals_settings", "visuals", apply_visuals_writes),
    "get_sunnylink_status": h_get_sunnylink_status,
    "trigger_sunnylink_backup": h_trigger_sunnylink_backup,
    "trigger_sunnylink_restore": h_trigger_sunnylink_restore,
    "get_sp_device_hw": h_get_sp_device_hw,
    "set_sp_dev_beep": h_set_sp_dev_beep,
    "get_model_tune_settings": h_get_model_tune_settings,
    "set_model_tune_settings": _model_tune_set,
    "get_display_settings": h_get_display_settings,
    "set_display_settings": _device_group_set("set_display_settings", "display", apply_display_writes),
    "get_device_settings": h_get_device_settings,
    "set_device_settings": _device_group_set("set_device_settings", "device", apply_device_writes),
    "list_sunnylink_backups": h_list_sunnylink_backups,
    "get_backup_manager_status": h_get_backup_manager_status,
    "list_f4_pandas": h_list_f4_pandas,
    "list_all_pandas": h_list_all_pandas,
    "panda_firmware_status": h_panda_firmware_status,
    "panda_recovery_hint": h_panda_recovery_hint,
    "build_panda_firmware": h_build_panda_firmware,
    "build_panda_h7_firmware": h_build_panda_h7_firmware,
    "build_panda_tici_firmware": h_build_panda_tici_firmware,
    "recover_dos_panda": h_recover_dos_panda,
    "flash_panda_firmware": h_flash_panda_firmware,
    "rebuild_pandad": h_rebuild_pandad,
    "rebuild_pandad_tici": h_rebuild_pandad_tici,
    "github_runner_status": h_github_runner_status,
    "github_runner_recovery_hint": h_github_runner_recovery_hint,
    "install_github_runner": h_install_github_runner,
    "github_actions_auth_status": h_github_actions_auth_status,
    "set_github_actions_pat": h_set_github_actions_pat,
    "list_github_workflow_runs": h_list_github_workflow_runs,
    "get_github_workflow_run": h_get_github_workflow_run,
    "cancel_github_workflow_run": h_cancel_github_workflow_run,
    "list_github_runners": h_list_github_runners,
    "stop_github_runner_service": h_stop_github_runner_service,
    "translation_status": h_translation_status,
    "update_zh_translations": h_update_zh_translations,
  }
