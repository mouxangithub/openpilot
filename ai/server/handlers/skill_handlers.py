"""HTTP handlers for skill registry and invocation."""

from __future__ import annotations

from typing import Any

from aiohttp import web


def _skill_registry():
  from ai.skill.registry import get_skill_registry, set_skill_base_dir
  from ai.system.paths import workspace_path
  set_skill_base_dir(workspace_path("ai_skills", mkdir=True))
  return get_skill_registry()


async def api_skill_registry(request: web.Request) -> web.Response:
  from ai.server.deps import json_response
  registry = _skill_registry()

  if request.method == "GET":
    skill_id = str(request.query.get("skillId") or request.query.get("skill_id") or "").strip()
    if skill_id:
      try:
        skill = registry.get(skill_id)
        return json_response({"ok": True, "skill": skill.to_dict()})
      except Exception as e:
        if hasattr(e, "to_dict"):
          return json_response(e.to_dict(), status=404)
        return json_response({"ok": False, "error": str(e)}, status=404)
    from ai.skills.unified import list_unified_skills
    return json_response({"ok": True, "skills": list_unified_skills()})

  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    body = {}

  op = str(body.get("operation", "register")).strip()
  try:
    if op == "register":
      skill = registry.register_from_dict(body.get("skill", {}))
      return json_response({"ok": True, "skill": skill.to_dict()})
    if op == "unregister":
      ok = registry.unregister(str(body.get("skillId") or body.get("skill_id") or ""))
      return json_response({"ok": ok})
    if op == "invoke":
      invocation = registry.request_invocation(
        str(body.get("skillId") or body.get("skill_id") or ""),
        dict(body.get("args") or {}),
        request_id=str(body.get("requestId") or body.get("request_id") or ""),
        auto_confirm=bool(body.get("autoConfirm") or body.get("auto_confirm")),
      )
      return json_response({"ok": invocation.status == "success", "invocation": invocation.to_dict()})
    if op == "tools":
      return json_response({"ok": True, "tools": registry.build_tool_definitions()})
    return json_response({"ok": False, "error": f"unknown operation {op}"}, status=400)
  except Exception as e:
    if hasattr(e, "to_dict"):
      return json_response(e.to_dict(), status=409)
    return json_response({"ok": False, "error": str(e)}, status=500)
