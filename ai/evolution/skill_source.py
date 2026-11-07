"""Load skill bodies for evolution (registry + learned skills)."""

from __future__ import annotations

from typing import Any

from ai.evolution.config import resolve_skill_entry, skills_root
from ai.skills.loader import load_skill_body_by_id


def load_skill_for_evolution(skill_id: str) -> dict[str, Any]:
  sid = (skill_id or "").strip()
  if not sid:
    return {"ok": False, "error": "skill_id required"}

  loaded = load_skill_body_by_id(sid)
  if loaded.get("ok"):
    entry = resolve_skill_entry(sid) or {}
    return {
      "ok": True,
      "id": sid,
      "name": loaded.get("name") or entry.get("name") or sid,
      "description": entry.get("description") or "",
      "body": loaded.get("body") or "",
      "path": str(skills_root() / (entry.get("path") or "")),
      "source": "registry",
    }

  # Learned / evolved skills
  try:
    from openpilot.common.params import Params
    from ai.tools.skill_learning import list_learned_skills
    learned = list_learned_skills(Params())
    for sk in (learned.get("skills") or []):
      if sk.get("id") == sid or sk.get("title") == sid:
        return {
          "ok": True,
          "id": sid,
          "name": sk.get("title") or sid,
          "description": ", ".join(sk.get("tags") or []),
          "body": sk.get("body") or "",
          "path": "",
          "source": "learned",
        }
  except Exception:
    pass

  return {"ok": False, "error": f"skill not found: {sid}"}
