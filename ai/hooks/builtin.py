"""Built-in plugin hooks — driving safety, canvas, audit, sidecar."""

from __future__ import annotations

from typing import Any

from ai.hooks.registry import register_hook

# Writes / service restarts still require stationary (legacy mode).
_WRITE_WHILE_PARKED = frozenset({
  "write_file", "write_param", "write_params", "git_commit",
  "apply_tune_preset", "apply_sp_tune_preset", "restore_tune_snapshot",
  "restart_service", "restart_ui", "confirm_write", "apply_adaptation",
})

# Never allowed — direct vehicle control tools (if added).
_VEHICLE_CONTROL_TOOLS = frozenset({
  "control_actuator", "send_can", "set_steering", "set_throttle", "set_brake",
})


async def _hook_driving_tool_guard(ctx: dict[str, Any]) -> dict[str, Any] | None:
  name = str(ctx.get("name") or "")
  if name in ("run_shell", "run_shell_command"):
    return None
  if name in _VEHICLE_CONTROL_TOOLS:
    return {"block": True, "reason": "Direct vehicle control is permanently forbidden."}

  body = ctx.get("body") or {}
  get_reader = body.get("_get_state_reader")
  if not callable(get_reader):
    return None
  try:
    state = get_reader().update(timeout=0)
    if not state.is_driving:
      return None
  except Exception:
    return None

  from ai.system.admin import is_admin_mode
  from openpilot.common.params import Params
  params = body.get("_params") or Params()
  if is_admin_mode(params):
    if name in _VEHICLE_CONTROL_TOOLS:
      return {"block": True, "reason": "Direct vehicle control is permanently forbidden."}
    return None

  if name in _WRITE_WHILE_PARKED:
    return {
      "block": True,
      "reason": f"Tool '{name}' requires vehicle stopped (writes disabled while driving).",
    }
  return None


async def _hook_audit_tool(ctx: dict[str, Any]) -> dict[str, Any] | None:
  from openpilot.common.swaglog import cloudlog
  name = ctx.get("name", "")
  agent = ctx.get("agent_id", "")
  session_id = str(ctx.get("session_id") or "")
  result = ctx.get("result")
  ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
  cloudlog.info(f"aid: tool {name} agent={agent} ok={ok}")
  try:
    from ai.tools.domains.platform.audit_store import record_audit
    record_audit(
      action="tool_call",
      tool=name,
      ok=ok,
      detail={"agent_id": agent},
      session_id=session_id,
      agent_id=agent,
    )
  except Exception:
    pass
  try:
    from ai.core.runtime.sidecar_hub import publish_tool_event
    await publish_tool_event({
      "type": "tool_done",
      "name": name,
      "agentId": agent,
      "ok": ok,
      "sessionId": session_id,
    })
  except Exception:
    pass
  return None


async def _hook_tool_start_sidecar(ctx: dict[str, Any]) -> dict[str, Any] | None:
  try:
    from ai.core.runtime.sidecar_hub import publish_tool_event
    await publish_tool_event({
      "type": "tool_start",
      "name": ctx.get("name", ""),
      "agentId": ctx.get("agent_id", ""),
      "sessionId": ctx.get("session_id", ""),
    })
  except Exception:
    pass
  return None


async def _hook_canvas_from_result(ctx: dict[str, Any]) -> dict[str, Any] | None:
  result = ctx.get("result")
  if not isinstance(result, dict):
    return None
  session_id = str(ctx.get("session_id") or "")
  name = str(ctx.get("name") or "")
  from ai.canvas.store import maybe_capture_tool_artifact, notify_artifact
  artifact = maybe_capture_tool_artifact(session_id, name, result)
  if artifact:
    ctx["canvas_artifact"] = artifact
    try:
      await notify_artifact(session_id, artifact)
    except Exception:
      pass
  return None


async def _hook_permission(ctx: dict[str, Any]) -> dict[str, Any] | None:
  from ai.hooks.permissions import evaluate_tool_permission
  return await evaluate_tool_permission(ctx)


async def _hook_externalize_result(ctx: dict[str, Any]) -> dict[str, Any] | None:
  result = ctx.get("result")
  if result is None:
    return None
  try:
    from ai.tools.result_externalize import externalize_if_needed
    body = ctx.get("body") or {}
    params = body.get("_params")
    compact, artifact = externalize_if_needed(
      result,
      session_id=str(ctx.get("session_id") or ""),
      tool_name=str(ctx.get("name") or ""),
      params=params,
    )
    if compact is not result:
      ctx["result"] = compact
    if artifact:
      ctx["canvas_artifact"] = artifact
  except Exception:
    pass
  return None


def register_builtin_hooks() -> None:
  register_hook("before_tool_call", _hook_driving_tool_guard, priority=100)
  register_hook("before_tool_call", _hook_permission, priority=90)
  register_hook("before_tool_call", _hook_tool_start_sidecar, priority=50)
  register_hook("after_tool_call", _hook_externalize_result, priority=15)
  register_hook("after_tool_call", _hook_audit_tool, priority=10)
  register_hook("after_tool_call", _hook_canvas_from_result, priority=5)
