"""Unified skill catalog — merge of the file-backed (legacy) and dynamic skill systems.

deepseek-harness alignment: one catalog with clear source priority, instead of
two parallel skill systems.

Sources (highest priority first):
1. ``ai.skill`` dynamic registry  — runtime-registered skills with invocation.
2. ``ai.skills.loader`` file registry — on-disk skills (``skills/`` dir) used
   for prompt injection.

Both keep their own execution paths (legacy skills run via prompt; dynamic
skills run via the registry); this module only provides a single *view* with
dedup by skill id.
"""

from __future__ import annotations

from typing import Any


def _legacy_entries() -> list[dict[str, Any]]:
  try:
    from ai.skills.loader import list_skills as _file_list
    return list(_file_list())
  except Exception:
    return []


def _dynamic_entries() -> list[dict[str, Any]]:
  try:
    from ai.skill.registry import get_skill_registry
    reg = get_skill_registry()
    return [s.to_dict() for s in reg.list_skills()]
  except Exception:
    return []


def unified_skill_catalog() -> dict[str, dict[str, Any]]:
  """Return id -> skill dict, deduped with dynamic registry taking priority."""
  catalog: dict[str, dict[str, Any]] = {}
  # Lower priority first: legacy file skills.
  try:
    legacy = _legacy_entries()
  except Exception:
    legacy = []
  for entry in legacy:
    sid = str(entry.get("id") or entry.get("skillId") or "").strip()
    if not sid:
      continue
    catalog[sid] = {**entry, "source": "file"}
  # Higher priority: dynamic registry overrides.
  try:
    dynamic = _dynamic_entries()
  except Exception:
    dynamic = []
  for entry in dynamic:
    sid = str(entry.get("id") or entry.get("skillId") or "").strip()
    if not sid:
      continue
    catalog[sid] = {**entry, "source": "dynamic"}
  return catalog


def list_unified_skills() -> list[dict[str, Any]]:
  """List merged skills for the HTTP/registry view (dynamic first)."""
  catalog = unified_skill_catalog()
  entries = list(catalog.values())

  def _sort_key(e: dict[str, Any]) -> tuple[int, str]:
    # dynamic first, then by id
    return (0 if e.get("source") == "dynamic" else 1, str(e.get("id") or e.get("skillId") or ""))

  entries.sort(key=_sort_key)
  return entries
