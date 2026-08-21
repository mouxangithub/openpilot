"""
Load Agent Skills (SKILL.md) into the chat system prompt.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai.skills.disclosure import rank_skills, skill_manifest_lines

log = logging.getLogger("aid.skills")

_SKILLS_ROOT = Path(__file__).resolve().parent
_REGISTRY = _SKILLS_ROOT / "registry.json"
_MAX_CHARS_PER_SKILL = 6000
_MAX_TOTAL_CHARS = 28000


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
  if not _REGISTRY.exists():
    return {"skills": []}
  try:
    with _REGISTRY.open(encoding="utf-8") as f:
      data = json.load(f)
    return data if isinstance(data, dict) else {"skills": []}
  except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
    log.warning("skills registry unreadable: %s", e)
    return {"skills": []}


def list_skills() -> list[dict[str, Any]]:
  return list(_load_registry().get("skills") or [])


def load_enabled_skill_ids(params) -> set[str] | None:
  """Load enabled skill ids from config store; None means all registered skills."""
  from ai.common.storage import read_param
  try:
    raw = read_param(params, "ai_skills_enabled")
    if not raw:
      return None
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    data = json.loads(raw)
    if isinstance(data, list) and data:
      return {str(x) for x in data}
  except Exception:
    pass
  return None


def filter_skills_by_tools(
  entries: list[dict[str, Any]],
  available_tools: set[str] | None,
) -> list[dict[str, Any]]:
  """Drop skills whose requires_tools are not available."""
  if not available_tools:
    return entries
  out = []
  for entry in entries:
    req = entry.get("requires_tools") or []
    if not req:
      out.append(entry)
      continue
    if all(t in available_tools for t in req):
      out.append(entry)
  return out


def save_enabled_skill_ids(params, ids: list[str]) -> None:
  from ai.common.storage import write_param
  write_param(params, "ai_skills_enabled", json.dumps(ids, ensure_ascii=False))


def _read_skill_body(rel_path: str) -> str:
  path = _SKILLS_ROOT / rel_path
  if not path.is_file():
    return ""
  text = path.read_text(encoding="utf-8")
  if len(text) > _MAX_CHARS_PER_SKILL:
    return text[:_MAX_CHARS_PER_SKILL] + "\n\n[... skill truncated ...]"
  return text


def _brand_matches(entry: dict[str, Any], brand: str) -> bool:
  brands = entry.get("brands")
  if not brands:
    return True
  if not brand:
    return False
  return brand.lower() in {b.lower() for b in brands}


def build_skills_prompt(
  enabled_ids: set[str] | None = None,
  *,
  brand: str = "",
  available_tools: set[str] | None = None,
  query: str = "",
  max_skills: int = 10,
) -> str:
  entries = list_skills()
  if available_tools is not None:
    entries = filter_skills_by_tools(entries, available_tools)
  if not entries:
    return ""

  if enabled_ids is None:
    enabled_ids = {e["id"] for e in entries if e.get("id")}

  entries = [e for e in entries if e.get("id") in enabled_ids and _brand_matches(e, brand)]
  selected, deferred = rank_skills(entries, query=query, brand=brand, max_skills=max_skills)

  parts: list[str] = ["# Loaded Agent Skills (progressive disclosure)\n"]
  total = 0
  for entry in selected:
    sid = entry.get("id")
    body = _read_skill_body(entry.get("path", ""))
    if not body:
      continue
    header = f"## Skill: {entry.get('name', sid)}\n"
    chunk = header + body
    if total + len(chunk) > _MAX_TOTAL_CHARS:
      parts.append("\n[... remaining loaded skills truncated ...]")
      break
    parts.append(chunk)
    total += len(chunk)

  if deferred:
    parts.append("## Available skills (not loaded — call `load_skill` to fetch)\n")
    parts.extend(skill_manifest_lines(deferred))

  if len(parts) <= 1:
    return ""
  return "\n\n---\n\n".join(parts)


def load_skill_body_by_id(skill_id: str) -> dict[str, Any]:
  """On-demand skill load for progressive disclosure."""
  sid = (skill_id or "").strip()
  for entry in list_skills():
    if entry.get("id") == sid:
      body = _read_skill_body(entry.get("path", ""))
      if not body:
        return {"ok": False, "error": "skill file empty or missing"}
      return {
        "ok": True,
        "id": sid,
        "name": entry.get("name", sid),
        "body": body,
        "path": entry.get("path"),
      }
  return {"ok": False, "error": f"skill not found: {sid}"}


def clear_cache() -> None:
  _load_registry.cache_clear()
