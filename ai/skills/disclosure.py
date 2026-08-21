"""Progressive skill disclosure — rank and load skills by query relevance (Hermes-style)."""

from __future__ import annotations

import re
from typing import Any

_PINNED_IDS = frozenset({"safety-policy", "memory-protocol"})
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
  return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def rank_skills(
  entries: list[dict[str, Any]],
  *,
  query: str = "",
  brand: str = "",
  max_skills: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  """Return (selected_entries, deferred_manifest_entries)."""
  if not entries:
    return [], []

  q_tokens = _tokens(query)
  scored: list[tuple[float, dict[str, Any]]] = []

  for entry in entries:
    sid = str(entry.get("id") or "")
    if not sid:
      continue
    score = 0.0
    if sid in _PINNED_IDS:
      score += 10_000.0
    name = str(entry.get("name") or "")
    desc = str(entry.get("description") or "")
    hay = _tokens(f"{sid} {name} {desc}".replace("-", " "))
    if q_tokens:
      overlap = len(q_tokens & hay)
      score += overlap * 12.0
      for qt in q_tokens:
        if qt in sid.replace("-", ""):
          score += 8.0
    brands = entry.get("brands") or []
    if brand and brands:
      if brand.lower() in {b.lower() for b in brands}:
        score += 25.0
      else:
        score -= 5.0
    if entry.get("default_enabled", True):
      score += 1.0
    scored.append((score, entry))

  scored.sort(key=lambda x: x[0], reverse=True)

  selected: list[dict[str, Any]] = []
  selected_ids: set[str] = set()
  for score, entry in scored:
    sid = entry.get("id")
    if sid in _PINNED_IDS and sid not in selected_ids:
      selected.append(entry)
      selected_ids.add(sid)

  for score, entry in scored:
    if len(selected) >= max_skills:
      break
    sid = entry.get("id")
    if sid in selected_ids:
      continue
    if score <= 0 and q_tokens:
      continue
    selected.append(entry)
    selected_ids.add(sid)

  if not q_tokens and len(selected) < min(max_skills, len(entries)):
    for _, entry in scored:
      sid = entry.get("id")
      if sid in selected_ids:
        continue
      selected.append(entry)
      selected_ids.add(sid)
      if len(selected) >= max_skills:
        break

  deferred = [e for e in entries if e.get("id") not in selected_ids]
  return selected, deferred


def skill_manifest_lines(entries: list[dict[str, Any]], *, limit: int = 40) -> list[str]:
  lines: list[str] = []
  for entry in entries[:limit]:
    sid = entry.get("id", "")
    name = entry.get("name", sid)
    desc = (entry.get("description") or "")[:120]
    lines.append(f"- `{sid}` — {name}: {desc}")
  if len(entries) > limit:
    lines.append(f"- ... and {len(entries) - limit} more (use load_skill tool)")
  return lines
