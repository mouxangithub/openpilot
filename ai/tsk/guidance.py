"""Unified next-step hints for TSK matcher / dump failures."""

from __future__ import annotations

from typing import Any

_SECOC_SETTINGS = "/?settings=secoc"


def matcher_debug_fields(result: dict[str, Any]) -> dict[str, Any]:
  keys = (
    "status", "address", "offset", "windows_scanned", "survivors",
    "matches", "sync", "protected", "malformed", "dump_partial",
  )
  return {k: result[k] for k in keys if result.get(k) is not None}


def matcher_next_steps(result: dict[str, Any]) -> list[str]:
  status = str(result.get("status") or "")
  if status == "found":
    return ["重启设备使密钥生效", "read_onroad_events 确认无 startupNoSecOcKey"]
  if status == "insufficient_oracle":
    return [
      "车辆置于 READY 模式（混动已启动）",
      "tsk_start_can_collect(confirm=true) → tsk_wait_for_job(job=can)",
    ]
  if status == "no_dump":
    return [
      "车辆置于 Not Ready to Drive",
      "tsk_start_dataflash_dump(confirm=true) → tsk_wait_for_job(job=dataflash)",
    ]
  if status == "not_found":
    if result.get("dump_partial"):
      return [
        "熄火并切回 Not Ready to Drive，重新完整导出 DataFlash",
        "或清除缓存后重新 CAN→DF→查找",
        f"RAV4 Prime/Sienna 等可尝试 tsk_extract_key(confirm=true)",
      ]
    return [
      "tsk_clear_cache(confirm=true) 后重新采集 CAN",
      "重新导出 DataFlash 后再 tsk_find_and_install_key",
      f"已有密钥可在 {_SECOC_SETTINGS} 手动安装",
    ]
  if status == "key_missed":
    return [
      "熄火并切回 Not Ready to Drive 后重新导出 DataFlash",
      "RAV4 Prime/Sienna 等可尝试 tsk_extract_key(confirm=true) 跳过 CAN/DF",
    ]
  if status == "partial":
    return [
      "可尝试 tsk_find_and_install_key(confirm=true)",
      "若失败，熄火后重新完整导出 DataFlash",
    ]
  if status == "error":
    return [f"查看 debug 字段；黑屏可 tsk_restart_pandad；设置页 {_SECOC_SETTINGS}"]
  return [f"打开 op 助手设置 → SecOC（{_SECOC_SETTINGS}）查看详情"]


def enrich_failure_response(result: dict[str, Any]) -> dict[str, Any]:
  """Attach debug + next_steps without mutating secrets."""
  out = dict(result)
  out["debug"] = matcher_debug_fields(result)
  steps = matcher_next_steps(result)
  if steps:
    out["next_steps"] = steps
  if not out.get("settings_url"):
    out["settings_url"] = _SECOC_SETTINGS
  return out
