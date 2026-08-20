"""Scheduler action implementations (sync); called from aid._scheduler_execute_action."""

from __future__ import annotations

from typing import Any, Callable


async def execute_scheduler_action(
  action: str,
  payload: dict[str, Any],
  *,
  params,
  get_state_reader: Callable,
  notify_push: Callable,
  append_note: Callable,
) -> str:
  if action == "check_runner_health_offroad":
    from ai.tools.domains.devops.github_actions_tools import check_github_runner_health
    res = check_github_runner_health(notify=bool(payload.get("notify", True)))
    if not res.get("healthy"):
      issues = ", ".join(res.get("issues") or [])
      return f"issues: {issues}"
    return "runner/ci healthy"

  if action == "check_device_health_offroad":
    from ai.tools.domains.platform.device_health_tools import device_health
    h = device_health()
    issues = []
    disk = h.get("disk") or {}
    if disk.get("free_gb") is not None and float(disk["free_gb"]) < 3:
      issues.append(f"disk={disk['free_gb']}GB")
    if h.get("max_temp_c") is not None and float(h["max_temp_c"]) > 90:
      issues.append(f"temp={h['max_temp_c']}C")
    if issues:
      await notify_push("设备健康", "; ".join(issues), level="warn")
      return "warn: " + "; ".join(issues)
    return "device health ok"

  if action == "check_github_ci_failed":
    from ai.tools.domains.devops.github_actions_tools import check_github_runner_health
    res = check_github_runner_health(notify=False)
    fails = res.get("recent_failures") or []
    if fails:
      rid = fails[0].get("id")
      await notify_push("CI 编译失败", f"run {rid} failed", level="error")
      return f"ci failure run={rid}"
    return "no recent ci failure"

  if action == "ota_preflight_offroad":
    from ai.tools.domains.devops.branch_tools import ota_preflight_checklist
    res = ota_preflight_checklist(params)
    if not res.get("ready"):
      blockers = ", ".join(res.get("blockers") or [])
      await notify_push("OTA 预检未通过", blockers, level="warn")
      return f"blockers: {blockers}"
    return "ota preflight ok"

  return ""
