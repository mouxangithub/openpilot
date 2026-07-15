"""TSK tools for op 助手 — direct calls into ai.tsk.service (no HTTP loopback)."""

from __future__ import annotations

from typing import Any, Callable

from ai.tsk import service as tsk_service


def _attach_ui_card(payload: dict[str, Any]) -> dict[str, Any]:
  summary = tsk_service.get_summary()
  payload["ui_card"] = {
    "type": "tsk",
    "poll": bool(summary.get("poll")),
    "summary": summary,
    "url": summary.get("url"),
  }
  return payload


def _offroad_guard(get_state_reader: Callable[..., Any]) -> dict[str, Any] | None:
  try:
    state = get_state_reader().update(timeout=0)
    if getattr(state, "started", False) and not getattr(state, "force_offroad", False):
      return {"ok": False, "error": "TSK 操作仅能在 offroad 下进行。"}
  except Exception:
    pass
  return None


def _scrub_key_result(result: dict[str, Any]) -> dict[str, Any]:
  if result.get("ok") and result.get("key"):
    result["secoc_key_prefix"] = (result.get("key") or "")[:8] + "…"
    result.pop("key", None)
  return result


def _audit_tsk(tool: str, result: dict[str, Any]) -> dict[str, Any]:
  try:
    from ai.tools.audit_store import record_audit
    record_audit(
      action=f"tsk_{tool}",
      tool=tool,
      detail={"ok": result.get("ok"), "status": result.get("status")},
      ok=bool(result.get("ok")),
    )
  except Exception:
    pass
  return result


def get_tsk_manager_status() -> dict[str, Any]:
  """TSK pipeline snapshot: SecOC key, CAN/DataFlash progress, comma device panda backend."""
  tsk_service.initialize()
  summary = tsk_service.get_summary()
  health = tsk_service.get_health()
  key = summary.get("secoc_key_installed")
  steps = list(summary.get("next_steps") or [])
  return _attach_ui_card({
    "ok": True,
    "running": True,
    "url": summary.get("url"),
    "is_agnos": health.get("is_agnos"),
    "dry_run": health.get("dry_run"),
    "tici": {
      k: health.get(k)
      for k in (
        "device_type", "product_label", "product_name",
        "panda_tici_available", "pandad_tici_available", "use_tici_panda_stack",
        "tici_hw", "tici_dos", "tici_tres",
        "panda_backend", "pandad_process", "pandad_module", "panda_mcu_cache",
      )
      if k in health
    },
    "secoc_key_installed": key,
    "secoc_key_prefix": summary.get("secoc_key_prefix", ""),
    "can": summary.get("can"),
    "dataflash": summary.get("dataflash"),
    "next_steps": steps,
    "busy": summary.get("busy"),
    "install_options": summary.get("install_options"),
    "ai_rule": (
      "offroad 下可用 TSK 工具：一键提取（RAV4 Prime/Sienna）、手动安装、"
      "CAN→DataFlash→查找（或 tsk_run_pipeline 一条龙）、等待作业 tsk_wait_for_job、"
      "取消 tsk_cancel_job、重启本机 pandad（C3→pandad_tici，C3X/C4→pandad）tsk_restart_pandad。"
      "写操作需 confirm=true。勿复述完整密钥。设备对照见 ai/docs/COMMA_DEVICES.md。"
    ),
  })


def tsk_find_and_install_key(*, confirm: bool = False, get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将扫描 DataFlash 并安装 SecOC 密钥。设置 confirm=true 执行。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  result = tsk_service.run_match_and_install()
  return _attach_ui_card(_audit_tsk("find_and_install_key", _scrub_key_result(result)))


def tsk_extract_key(*, confirm: bool = False, get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将通过 UDS 一键提取 SecOC 密钥（RAV4 Prime/Sienna 等）。设置 confirm=true 执行。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  result = tsk_service.run_extract()
  return _attach_ui_card(_audit_tsk("extract_key", _scrub_key_result(result)))


def tsk_install_secoc_key(
  *,
  key: str = "",
  confirm: bool = False,
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将用户提供的 32 位 hex SecOC 密钥写入本机。设置 key=… 且 confirm=true 执行。",
    })
  if not (key or "").strip():
    return {"ok": False, "error": "缺少 key 参数（32 位十六进制）。"}
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  result = tsk_service.run_install_key(key)
  return _attach_ui_card(_audit_tsk("install_secoc_key", _scrub_key_result(result)))


def tsk_uninstall_key(*, confirm: bool = False, get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将移除已安装的 SecOC 密钥文件。设置 confirm=true 执行。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  return _attach_ui_card(_audit_tsk("uninstall_key", tsk_service.run_uninstall()))


def tsk_start_can_collect(*, confirm: bool = False, get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将停止 manager 并采集 CAN（READY 模式）；会终止本机 pandad（C3→pandad_tici，C3X/C4→pandad）。设置 confirm=true 执行。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  return _attach_ui_card(_audit_tsk("start_can_collect", tsk_service.run_can_collect_start()))


def tsk_start_dataflash_dump(*, confirm: bool = False, get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将停止 manager 并导出 DataFlash（会终止本机 pandad）。设置 confirm=true 执行。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  return _attach_ui_card(_audit_tsk("start_dataflash_dump", tsk_service.run_dataflash_dump_start()))


def tsk_clear_cache(*, confirm: bool = False, get_state_reader: Callable[..., Any] | None = None) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将清除 CAN 与 DataFlash 提取缓存（不删除已装密钥）。设置 confirm=true 执行。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  return _attach_ui_card(_audit_tsk("clear_cache", tsk_service.run_clear_cache()))


def tsk_wait_for_job(
  *,
  job: str = "can",
  timeout_seconds: float = 600,
) -> dict[str, Any]:
  """Poll until a CAN/DataFlash/match job finishes or timeout."""
  tsk_service.initialize()
  result = tsk_service.wait_for_job(job=job, timeout_seconds=timeout_seconds)
  return _attach_ui_card(result)


def tsk_cancel_job(
  *,
  job: str = "all",
  confirm: bool = False,
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": "将取消进行中的 CAN 或 DataFlash 采集。设置 job=can|dataflash|all 且 confirm=true。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  result = tsk_service.run_cancel_job(job)
  return _attach_ui_card(_audit_tsk("cancel_job", result))


def tsk_restart_pandad(
  *,
  confirm: bool = False,
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  if not confirm:
    from ai.tsk.lib.panda_connect import pandad_process_name
    proc = pandad_process_name()
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": f"将终止本机 {proc} 进程（黑屏恢复常用；C3 为 pandad_tici，C3X/C4 为 pandad）。设置 confirm=true 执行。",
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  result = tsk_service.run_restart_pandad()
  return _attach_ui_card(_audit_tsk("restart_pandad", result))


def tsk_run_pipeline(
  *,
  confirm: bool = False,
  skip_can: bool = False,
  skip_dataflash: bool = False,
  can_timeout_seconds: float = 120,
  dataflash_timeout_seconds: float = 300,
  get_state_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
  if not confirm:
    return _attach_ui_card({
      "ok": True,
      "needs_confirmation": True,
      "hint": (
        "将按序执行：CAN 采集（若缺）→ DataFlash 导出（若缺）→ 查找安装密钥。"
        "设置 confirm=true 执行；可用 skip_can / skip_dataflash 跳过已有步骤。"
      ),
    })
  if get_state_reader:
    err = _offroad_guard(get_state_reader)
    if err:
      return err
  result = tsk_service.run_secoc_pipeline(
    skip_can=skip_can,
    skip_dataflash=skip_dataflash,
    can_timeout_seconds=can_timeout_seconds,
    dataflash_timeout_seconds=dataflash_timeout_seconds,
  )
  return _attach_ui_card(_audit_tsk("run_pipeline", _scrub_key_result(result)))


def get_tsk_offroad_alert_status() -> dict[str, Any]:
  """Whether Offroad_NoFirmware alert is active and the SecOC settings URL."""
  tsk_service.initialize()
  return tsk_service.get_offroad_alert_status()
