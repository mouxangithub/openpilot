"""OpenClaw-style heartbeat — periodic checklist from HEARTBEAT.md + LLM triage."""

from __future__ import annotations

import json
import re
from typing import Any

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

from ai.core.wspace.store import heartbeat_checklist


def _parse_llm_decision(content: str) -> dict[str, Any]:
  text = (content or "").strip()
  if not text:
    return {}
  try:
    return json.loads(text)
  except Exception:
    pass
  match = re.search(r"\{[\s\S]*\}", text)
  if match:
    try:
      return json.loads(match.group(0))
    except Exception:
      return {}
  return {}


async def run_heartbeat(params: Params, *, get_state_reader) -> dict[str, Any]:
  """Evaluate HEARTBEAT.md checklist; notify only when LLM finds actionable items."""
  checklist = heartbeat_checklist()
  if not checklist:
    return {"ok": True, "skipped": True, "reason": "empty checklist"}

  state = get_state_reader().update(timeout=0)
  actions: list[str] = []
  notified = False

  try:
    from ai.tools.notifications import list_notifications, push_notification
    unread = list_notifications(unread_only=True).get("notifications", [])
    if unread:
      actions.append(f"unread_notifications={len(unread)}")
  except Exception as e:
    cloudlog.debug(f"aid: heartbeat notifications: {e}")
    unread = []

  if not state.is_driving:
    actions.append("vehicle_stopped")
  else:
    actions.append("vehicle_driving")

  llm_decision: dict[str, Any] = {}
  try:
    from ai.server.deps import read_ai_config
    from ai.core.llm.model_router import chat_completion_collect_with_failover
    config = read_ai_config(params)
    if config.is_configured:
      unread_hint = f"{len(unread)} unread notifications" if unread else "no unread notifications"
      prompt = (
        "You are a heartbeat monitor for an openpilot in-car assistant. "
        "Given the checklist and vehicle state, decide if a user notification is warranted. "
        "Reply with JSON only: "
        '{"notify": boolean, "title": string, "body": string, "actions": string[]}. '
        "If nothing needs attention, set notify=false and actions=[].\n\n"
        f"Checklist:\n{checklist}\n\n"
        f"State: driving={state.is_driving}, {unread_hint}"
      )
      content, _, _, err = await chat_completion_collect_with_failover(
        config,
        params,
        [
          {"role": "system", "content": "Respond with compact JSON only."},
          {"role": "user", "content": prompt},
        ],
        max_tokens=400,
        timeout_total=45,
      )
      if not err and content:
        llm_decision = _parse_llm_decision(content)
        llm_actions = llm_decision.get("actions") or []
        if isinstance(llm_actions, list):
          actions.extend(str(a) for a in llm_actions[:6])
        if llm_decision.get("notify"):
          from ai.tools.notifications import push_notification
          title = str(llm_decision.get("title") or "Heartbeat")
          body = str(llm_decision.get("body") or "").strip()
          if body:
            push_notification(title, body[:500], level="info")
            notified = True
  except Exception as e:
    cloudlog.debug(f"aid: heartbeat llm skipped: {e}")

  if not notified and len(unread) >= 3:
    try:
      from ai.tools.notifications import push_notification
      push_notification(
        "Heartbeat",
        f"有 {len(unread)} 条未读通知待处理",
        level="info",
      )
      notified = True
    except Exception:
      pass

  cloudlog.info(f"aid: heartbeat tick driving={state.is_driving} actions={actions} notified={notified}")
  return {
    "ok": True,
    "driving": state.is_driving,
    "checklistChars": len(checklist),
    "actions": actions,
    "notified": notified,
    "llm": bool(llm_decision),
  }
