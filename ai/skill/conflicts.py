"""Skill conflict and cycle detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ai.skill.models import Skill, SkillError


@dataclass
class SkillConflictReport:
  """Aggregated conflict report for the whole registry."""

  ok: bool = True
  conflicts: list[dict[str, Any]] = field(default_factory=list)
  cycles: list[list[str]] = field(default_factory=list)
  missing_deps: list[dict[str, Any]] = field(default_factory=list)
  duplicate_ids: list[dict[str, Any]] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "ok": self.ok,
      "conflicts": list(self.conflicts),
      "cycles": [list(c) for c in self.cycles],
      "missing_deps": list(self.missing_deps),
      "duplicate_ids": list(self.duplicate_ids),
    }


def check_conflicts(
  skills: list[Skill],
  resolve_dependency: Callable[[str], Skill],
) -> SkillConflictReport:
  """Detect duplicate skill ids, cyclic dependencies and missing dependencies.

  ``resolve_dependency`` must raise ``SkillError`` when a dependency cannot be
  resolved. The list ``skills`` is the authoritative snapshot of the registry
  under inspection.
  """
  conflicts: list[dict[str, Any]] = []
  duplicate_ids: list[dict[str, Any]] = []
  missing_deps: list[dict[str, Any]] = []
  cycles: list[list[str]] = []

  seen: dict[str, list[str]] = {}
  for skill in skills:
    seen.setdefault(skill.id, []).append(skill.version or "0.0.0")
  for sid, versions in seen.items():
    if len(versions) > 1:
      entry = {"skill_id": sid, "versions": versions}
      conflicts.append(entry)
      duplicate_ids.append(entry)

  def _walk(skill_id: str, path: list[str], visited_in_path: set[str]) -> None:
    if skill_id in visited_in_path:
      start = path.index(skill_id)
      cycles.append(path[start:] + [skill_id])
      return
    try:
      skill = resolve_dependency(skill_id)
    except SkillError:
      return
    deps = skill.dependencies or []
    if not isinstance(deps, list):
      return
    new_path = path + [skill_id]
    new_visited = visited_in_path | {skill_id}
    for dep in deps:
      dep_name = dep.name if isinstance(dep, object) and hasattr(dep, "name") else str(dep)
      try:
        resolve_dependency(dep_name)
      except SkillError:
        missing_deps.append({"skill_id": skill_id, "missing": dep_name})
        continue
      _walk(dep_name, new_path, new_visited)

  visited_roots: set[str] = set()
  for skill in skills:
    if skill.id not in visited_roots:
      _walk(skill.id, [], set())
      visited_roots.add(skill.id)

  ok = not conflicts and not cycles and not missing_deps
  return SkillConflictReport(
    ok=ok,
    conflicts=conflicts,
    cycles=cycles,
    missing_deps=missing_deps,
    duplicate_ids=duplicate_ids,
  )
