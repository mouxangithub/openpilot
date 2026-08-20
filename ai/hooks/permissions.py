"""Permission hooks — evaluate tool risk before execution."""

from __future__ import annotations

from typing import Any

# Tools that require vehicle stopped (unless admin).
_WRITE_TOOLS = frozenset({
  "write_params", "write_file", "apply_tune_preset", "apply_sp_tune_preset",
  "select_model_bundle", "set_mads_settings", "git_commit", "git_pull",
  "restart_service", "restart_ui", "apply_adaptation", "confirm_write",
})

# High-risk — log prominently; block while driving.
_HIGH_RISK = frozenset({
  "reboot_device", "shutdown_device", "git_push", "manager_control",
  "ota_apply", "install_github_runner",
})


async def evaluate_tool_permission(ctx: dict[str, Any]) -> dict[str, Any] | None:
  name = str(ctx.get("name") or "")
  if not name or name in ("search_tools", "load_tool"):
    return None

  body = ctx.get("body") or {}
  get_reader = body.get("_get_state_reader")
  driving = False
  if callable(get_reader):
    try:
      driving = bool(get_reader().update(timeout=0).is_driving)
    except Exception:
      pass

  from ai.system.admin import is_admin_mode
  from openpilot.common.params import Params
  params = body.get("_params") or Params()
  admin = is_admin_mode(params)

  if name in _HIGH_RISK and driving and not admin:
    return {
      "block": True,
      "reason": f"Tool '{name}' is blocked while driving. Stop the vehicle first.",
      "permission": "high_risk_driving",
    }

  if name in _WRITE_TOOLS and driving and not admin:
    return {
      "block": True,
      "reason": f"Tool '{name}' requires vehicle stopped.",
      "permission": "write_while_driving",
    }

  # Soft warn — do not block
  if name in _HIGH_RISK:
    return {"permission": "high_risk", "permission_warn": True}

  return {"permission": "allow"}
