"""Skill diagnostics report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai.skill.models import Skill, SkillDependency, SkillError
from ai.skill.semver import Semver


@dataclass
class SkillDiagnosticsReport:
  """Structured diagnostics for a single skill."""

  skill_id: str
  ok: bool = True
  version: str = "0.0.0"
  scope: str = "global"
  deps_ok: bool = True
  caps_ok: bool = True
  source_trusted: bool = True
  warnings: list[str] = field(default_factory=list)
  dependencies: list[dict[str, Any]] = field(default_factory=list)
  capabilities: list[str] = field(default_factory=list)
  source: str = ""
  error: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "ok": self.ok,
      "skill_id": self.skill_id,
      "version": self.version,
      "scope": self.scope,
      "deps_ok": self.deps_ok,
      "caps_ok": self.caps_ok,
      "source_trusted": self.source_trusted,
      "warnings": list(self.warnings),
      "dependencies": list(self.dependencies),
      "capabilities": list(self.capabilities),
      "source": self.source,
      "error": self.error,
    }


def _skill_version(skill: Skill) -> str:
  return skill.version_from_metadata


def _trusted_source(source: str) -> bool:
  return source.startswith(("builtin:", "https://", "file://")) or not source


def diagnose_skill(
  skill: Skill,
  resolve_dependency: Any,
) -> SkillDiagnosticsReport:
  """Build a diagnostics report for ``skill`` using ``resolve_dependency``.

  ``resolve_dependency`` is any callable that accepts a skill id string and
  returns the registered ``Skill`` instance, or raises ``SkillError`` if the
  dependency is missing.
  """
  warnings: list[str] = []
  deps_ok = True
  dep_reports: list[dict[str, Any]] = []

  for dep in skill.dependencies or []:
    dep_name = dep.name
    constraint = dep.version_constraint
    dep_report: dict[str, Any] = {
      "name": dep_name,
      "version_constraint": constraint,
      "optional": dep.optional,
      "resolved": False,
      "satisfied": False,
      "version": None,
    }
    try:
      dep_skill = resolve_dependency(dep_name)
    except SkillError:
      deps_ok = False if not dep.optional else deps_ok
      if not dep.optional:
        warnings.append(f"missing dependency: {dep_name}")
      dep_reports.append(dep_report)
      continue

    dep_report["resolved"] = True
    dep_version = _skill_version(dep_skill)
    dep_report["version"] = dep_version

    if constraint:
      try:
        if not Semver.parse(dep_version).satisfies(constraint):
          deps_ok = False if not dep.optional else deps_ok
          if not dep.optional:
            warnings.append(f"dependency {dep_name} {dep_version} does not satisfy {constraint}")
          dep_reports.append(dep_report)
          continue
      except Exception as e:
        deps_ok = False if not dep.optional else deps_ok
        if not dep.optional:
          warnings.append(f"dependency {dep_name} version check failed: {e}")
        dep_reports.append(dep_report)
        continue

    dep_report["satisfied"] = True
    dep_reports.append(dep_report)

  capabilities = list(skill.capabilities or [])
  caps_ok = isinstance(capabilities, list)
  source = str(skill.source or "")

  return SkillDiagnosticsReport(
    skill_id=skill.id,
    ok=True,
    version=_skill_version(skill),
    scope=str(skill.scope or "global"),
    deps_ok=deps_ok,
    caps_ok=caps_ok,
    source_trusted=_trusted_source(source),
    warnings=warnings,
    dependencies=dep_reports,
    capabilities=capabilities,
    source=source,
    error=None,
  )
