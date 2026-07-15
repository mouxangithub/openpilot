"""
Load Agent Skills (SKILL.md) into the chat system prompt.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger("aid.skills")

_SKILLS_ROOT = Path(__file__).resolve().parent
_REGISTRY = _SKILLS_ROOT / "registry.json"
_MAX_CHARS_PER_SKILL = 6000
_MAX_TOTAL_CHARS = 28000


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
  if not _REGISTRY.exists():
    return {"skills": []}
  with _REGISTRY.open(encoding="utf-8") as f:
    return json.load(f)


def list_skills() -> list[dict[str, Any]]:
  return list(_load_registry().get("skills") or [])


def load_enabled_skill_ids(params) -> set[str] | None:
  """Load enabled skill ids from Params; None means all registered skills."""
  try:
    raw = params.get("ai_skills_enabled")
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
  params.put("ai_skills_enabled", json.dumps(ids, ensure_ascii=False))


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
) -> str:
  entries = list_skills()
  if available_tools is not None:
    entries = filter_skills_by_tools(entries, available_tools)
  if not entries:
    return ""

  if enabled_ids is None:
    enabled_ids = {e["id"] for e in entries if e.get("id")}

  parts: list[str] = ["# Loaded Agent Skills\n"]
  total = 0
  for entry in entries:
    sid = entry.get("id")
    if not sid or sid not in enabled_ids:
      continue
    if not _brand_matches(entry, brand):
      continue
    body = _read_skill_body(entry.get("path", ""))
    if not body:
      continue
    header = f"## Skill: {entry.get('name', sid)}\n"
    chunk = header + body
    if total + len(chunk) > _MAX_TOTAL_CHARS:
      parts.append(f"\n[... remaining skills omitted ({total} chars loaded) ...]")
      break
    parts.append(chunk)
    total += len(chunk)

  if len(parts) <= 1:
    return ""
  return "\n\n---\n\n".join(parts)


def clear_cache() -> None:
  _load_registry.cache_clear()
