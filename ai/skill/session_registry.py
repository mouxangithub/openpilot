"""Session-scoped skill overlay registry for P2 lifecycle."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from ai.skill.models import Skill, SkillError

if TYPE_CHECKING:
  from ai.skill.registry import SkillRegistry


class SessionSkillRegistry:
  """Overlay view on top of the global ``SkillRegistry``.

  Allows a session to register private skill instances, shadow global skills,
  and dispose session-local resources without affecting other sessions.
  """

  def __init__(self, session_id: str, global_registry: SkillRegistry) -> None:
    self.session_id = str(session_id)
    self.global_registry = global_registry
    self._lock = threading.RLock()
    self._session_skills: dict[str, Skill] = {}

  def register(self, skill: Skill) -> Skill:
    """Register a session-local skill (shadows global skills with the same id)."""
    with self._lock:
      self._session_skills[skill.id] = skill
    return skill

  def get(self, skill_id: str) -> Skill:
    """Return session-local skill if present, otherwise fall back to global."""
    with self._lock:
      skill = self._session_skills.get(skill_id)
    if skill is not None:
      return skill
    return self.global_registry.get(skill_id)

  def list_skills(self) -> list[Skill]:
    """Return the union of global and session-local skills; session overrides win."""
    global_skills = {s.id: s for s in self.global_registry.list_skills()}
    with self._lock:
      local_skills = dict(self._session_skills)
    global_skills.update(local_skills)
    return list(global_skills.values())

  def dispose(self, skill_id: str) -> dict[str, Any]:
    """Call a skill's dispose handler if present, then remove it from session scope."""
    with self._lock:
      skill = self._session_skills.pop(skill_id, None)
    if skill is None:
      try:
        skill = self.global_registry.get(skill_id)
      except SkillError:
        return {"ok": False, "skill_id": skill_id, "error": "skill not found"}

    error = ""
    try:
      if skill.handler is not None and hasattr(skill.handler, "dispose"):
        dispose_fn = getattr(skill.handler, "dispose")
        if callable(dispose_fn):
          dispose_fn()
    except Exception as e:
      error = str(e)

    return {"ok": True, "skill_id": skill_id, "error": error or None}

  def dispose_all(self) -> list[dict[str, Any]]:
    """Dispose all session-local skills."""
    with self._lock:
      ids = list(self._session_skills.keys())
    return [self.dispose(sid) for sid in ids]

  def diagnose(self, skill_id: str) -> dict[str, Any]:
    """Return a diagnostics report for a skill visible in this session."""
    from ai.skill.diagnostics import diagnose_skill
    try:
      skill = self.get(skill_id)
    except SkillError as e:
      return {"ok": False, "skill_id": skill_id, "error": e.message}
    return diagnose_skill(skill, resolve_dependency=self.get).to_dict()

  def check_conflicts(self) -> dict[str, Any]:
    """Return a conflict report for the session overlay view."""
    from ai.skill.conflicts import check_conflicts
    return check_conflicts(self.list_skills(), resolve_dependency=self.get).to_dict()
