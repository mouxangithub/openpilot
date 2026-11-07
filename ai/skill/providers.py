"""Skill provider abstraction and scope-aware merge (D-P1.3).

A ``SkillProvider`` is any source that can enumerate and resolve skills. We ship
two concrete providers:

* :class:`RegistrySkillProvider` — wraps an existing :class:`~ai.skill.registry.SkillRegistry`.
* :class:`DirectorySkillProvider` — loads ``skill.json`` manifests from a directory tree.

:class:`CompositeSkillProvider` merges several providers into one view, resolving
duplicate ids by (``rank`` asc, scope priority, ``id``) so a lower-rank skill
overrides a higher-rank one. Helpers :func:`merge_skills` and
:func:`filter_by_invocation` expose the same semantics to callers that already
hold plain :class:`~ai.skill.models.Skill` lists.

This module is intentionally additive: it imports only from ``ai.skill.models``
and never mutates the registry, so it cannot disturb existing skill behaviour.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable, Literal

from ai.skill.models import Skill

Actor = Literal["model", "user"]

# Lower value = higher priority when two skills share the same id and rank.
_SCOPE_PRIORITY: dict[str, int] = {"session": 0, "project": 1, "global": 2}


def _scope_priority(scope: str) -> int:
  """Return the merge priority for a skill scope (lower wins)."""
  return _SCOPE_PRIORITY.get(str(scope), 3)


def _merge_key(skill: Skill):
  """Sort/merge key: lower rank wins, then narrower scope, then stable id."""
  return (int(getattr(skill, "rank", 600)), _scope_priority(getattr(skill, "scope", "global")), skill.id)


def merge_skills(
  skills: Iterable[Skill],
  *,
  provider_order: dict[str, int] | None = None,
) -> list[Skill]:
  """Deduplicate skills by id, keeping the highest-priority definition.

  ``provider_order`` optionally maps a skill ``source`` or provider name to a
  tie-break index (lower = earlier) used only when rank and scope both tie.
  """
  order = provider_order or {}

  def key(skill: Skill):
    rank, scope_pri, sid = _merge_key(skill)
    tie = order.get(str(getattr(skill, "source", "") or ""), 999)
    return (rank, scope_pri, tie, sid)

  best: dict[str, Skill] = {}
  for skill in sorted(skills, key=key):
    if skill.id not in best:
      best[skill.id] = skill
  # Deterministic output: ordered by the same priority key.
  return sorted(best.values(), key=key)


def filter_by_invocation(skills: Iterable[Skill], *, actor: Actor) -> list[Skill]:
  """Keep only skills whose invocation policy allows ``actor``.

  ``actor="model"`` keeps skills with ``model_invocable``; ``actor="user"`` keeps
  skills with ``user_invocable``. Unknown actors raise ``ValueError``.
  """
  if actor not in ("model", "user"):
    raise ValueError(f"unknown actor: {actor!r}")
  out: list[Skill] = []
  for skill in skills:
    policy = getattr(skill, "invocation_policy", None)
    allowed = True
    if policy is not None:
      allowed = policy.model_invocable if actor == "model" else policy.user_invocable
    if allowed:
      out.append(skill)
  return out


class SkillProvider(ABC):
  """Abstract source of skills."""

  @property
  @abstractmethod
  def name(self) -> str:
    """Human-readable provider name used for diagnostics."""

  @abstractmethod
  def list_skills(self) -> list[Skill]:
    """Return every skill this provider knows about."""

  @abstractmethod
  def get(self, skill_id: str) -> Skill | None:
    """Resolve a single skill by id, or ``None`` if absent."""


class RegistrySkillProvider(SkillProvider):
  """Adapt an existing :class:`SkillRegistry` to the provider interface."""

  def __init__(self, registry: Any, *, name: str = "registry") -> None:
    self._registry = registry
    self._name = name

  @property
  def name(self) -> str:
    return self._name

  def list_skills(self) -> list[Skill]:
    lister = getattr(self._registry, "list_skills", None)
    if not callable(lister):
      return []
    return list(lister())

  def get(self, skill_id: str) -> Skill | None:
    try:
      return self._registry.get(skill_id)
    except Exception:  # noqa: BLE001 - registry raises SkillError for missing ids
      return None


class DirectorySkillProvider(SkillProvider):
  """Load skills from ``skill.json`` manifests under a directory tree.

  Supports two layouts:

  * one manifest per skill directory: ``<root>/<skill>/skill.json``
  * a single aggregate manifest: ``<root>/manifest.json`` with ``{"skills": [...]}</skill>``
  """

  MANIFEST_NAME = "skill.json"

  def __init__(self, root: str | Path, *, name: str = "directory") -> None:
    self.root = Path(root)
    self._name = name
    self._cache: list[Skill] | None = None

  @property
  def name(self) -> str:
    return self._name

  def _load_manifest_file(self, path: Path) -> list[Skill]:
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
      return []
    if isinstance(data, dict) and isinstance(data.get("skills"), list):
      items = data["skills"]
    elif isinstance(data, dict):
      items = [data]
    elif isinstance(data, list):
      items = data
    else:
      return []
    skills: list[Skill] = []
    for item in items:
      if not isinstance(item, dict) or not item.get("id"):
        continue
      # Default source to the manifest path so merge tie-breaks stay stable.
      item = {**item}
      item.setdefault("source", f"file://{path.as_posix()}")
      skills.append(Skill.from_dict(item))
    return skills

  def list_skills(self) -> list[Skill]:
    if self._cache is not None:
      return list(self._cache)
    skills: list[Skill] = []
    if self.root.is_dir():
      # Aggregate manifest first, then per-skill manifests.
      aggregate = self.root / "manifest.json"
      if aggregate.is_file():
        skills.extend(self._load_manifest_file(aggregate))
      for child in sorted(self.root.iterdir()):
        if child.is_dir():
          manifest = child / self.MANIFEST_NAME
          if manifest.is_file():
            skills.extend(self._load_manifest_file(manifest))
        elif child.name == self.MANIFEST_NAME and child.is_file():
          skills.extend(self._load_manifest_file(child))
    self._cache = merge_skills(skills)
    return list(self._cache)

  def get(self, skill_id: str) -> Skill | None:
    for skill in self.list_skills():
      if skill.id == skill_id:
        return skill
    return None

  def invalidate(self) -> None:
    """Drop the cached manifest view so the next access re-reads disk."""
    self._cache = None


class CompositeSkillProvider(SkillProvider):
  """Merge several providers into a single scope-aware view."""

  def __init__(self, providers: Iterable[SkillProvider] | None = None, *, name: str = "composite") -> None:
    self._providers: list[SkillProvider] = list(providers or [])
    self._name = name

  @property
  def name(self) -> str:
    return self._name

  @property
  def providers(self) -> list[SkillProvider]:
    return list(self._providers)

  def add(self, provider: SkillProvider) -> None:
    self._providers.append(provider)

  def list_skills(self) -> list[Skill]:
    merged: list[Skill] = []
    provider_order: dict[str, int] = {}
    for index, provider in enumerate(self._providers):
      provider_order[provider.name] = index
      for skill in provider.list_skills():
        # Tag the provider name so merge tie-breaks honour registration order.
        if not str(getattr(skill, "source", "") or ""):
          skill.source = provider.name
        merged.append(skill)
    return merge_skills(merged, provider_order=provider_order)

  def get(self, skill_id: str) -> Skill | None:
    for skill in self.list_skills():
      if skill.id == skill_id:
        return skill
    return None
