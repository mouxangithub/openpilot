"""HTTP handlers for P2 skill lifecycle routes.

Provides endpoints for disposing, diagnosing and registering skills at both
global and session scopes.
"""

from __future__ import annotations

from typing import Any

from aiohttp import web


def _skill_registry():
  from ai.skill.registry import get_skill_registry, set_skill_base_dir
  from ai.system.paths import workspace_path
  set_skill_base_dir(workspace_path("ai_skills", mkdir=True))
  return get_skill_registry()


async def api_skill_dispose(request: web.Request) -> web.Response:
  """POST /api/ai/skills/{id}/dispose"""
  from ai.server.deps import json_response
  skill_id = request.match_info.get("id", "")
  if not skill_id:
    return json_response({"ok": False, "error": "skill id required"}, status=400)

  registry = _skill_registry()
  result = registry.dispose(skill_id)
  return json_response(result, status=200 if result.get("ok") else 404)


async def api_skill_diagnose(request: web.Request) -> web.Response:
  """GET /api/ai/skills/{id}/diagnose"""
  from ai.server.deps import json_response
  skill_id = request.match_info.get("id", "")
  if not skill_id:
    return json_response({"ok": False, "error": "skill id required"}, status=400)

  registry = _skill_registry()
  report = registry.diagnose(skill_id)
  return json_response({"ok": report.ok, "skill_id": skill_id, "report": report.to_dict()})


async def api_skill_diagnose_all(request: web.Request) -> web.Response:
  """POST /api/ai/skills/diagnose-all"""
  from ai.server.deps import json_response
  registry = _skill_registry()

  conflicts = registry.check_conflicts()
  reports: dict[str, dict[str, Any]] = {}
  for skill in registry.list_skills():
    reports[skill.id] = registry.diagnose(skill.id).to_dict()

  return json_response({
    "ok": conflicts.ok and all(r.get("ok") for r in reports.values()),
    "conflicts": conflicts.to_dict(),
    "reports": reports,
  })


async def api_skill_session_register(request: web.Request) -> web.Response:
  """POST /api/ai/skills/session/register"""
  from ai.server.deps import json_response
  from ai.skill.models import Skill

  try:
    body = await request.json()
  except Exception:
    return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
  if not isinstance(body, dict):
    body = {}

  session_id = str(body.get("session_id") or body.get("sessionId") or "").strip()
  skill_data = body.get("skill") or {}
  if not session_id:
    return json_response({"ok": False, "error": "session_id required"}, status=400)
  if not isinstance(skill_data, dict) or not skill_data.get("id"):
    return json_response({"ok": False, "error": "skill object with id required"}, status=400)

  registry = _skill_registry()
  skill = Skill.from_dict(skill_data)
  session_registry = registry.for_session(session_id)
  session_registry.register(skill)
  return json_response({"ok": True, "session_id": session_id, "skill": skill.to_dict()})
