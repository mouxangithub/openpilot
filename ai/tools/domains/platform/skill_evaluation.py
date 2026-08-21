"""Pareto-style skill candidate scoring (accuracy proxy, token cost, clarity)."""

from __future__ import annotations

import re
from typing import Any

_SECTION_RE = re.compile(r"^##\s+", re.M)


def score_skill_candidate(
  body: str,
  *,
  hotspot: dict[str, Any] | None = None,
) -> dict[str, Any]:
  text = (body or "").strip()
  tokens = max(1, len(text) // 4)
  sections = len(_SECTION_RE.findall(text))
  steps = len(re.findall(r"^\s*\d+[\.\)]\s+", text, re.M))

  error_terms: set[str] = set()
  if hotspot:
    for err in hotspot.get("toolErrors") or []:
      error_terms.update(re.findall(r"[\w\u4e00-\u9fff]{3,}", str(err).lower()))
    for sig in hotspot.get("signals") or []:
      if str(sig).startswith("tool:"):
        error_terms.add(str(sig).split(":", 1)[-1].lower())

  coverage = 0
  lower = text.lower()
  for term in error_terms:
    if term in lower:
      coverage += 1
  accuracy = min(1.0, (coverage / max(1, len(error_terms))) if error_terms else (0.5 + min(0.5, sections / 6)))

  token_efficiency = max(0.0, 1.0 - min(1.0, tokens / 2500))
  clarity = min(1.0, (sections * 0.15) + (steps * 0.08) + (0.2 if "##" in text else 0))

  return {
    "accuracy": round(accuracy, 3),
    "tokenEfficiency": round(token_efficiency, 3),
    "clarity": round(clarity, 3),
    "tokens": tokens,
    "sections": sections,
  }


def pareto_frontier(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Return non-dominated candidates on (accuracy, tokenEfficiency, clarity)."""
  if not candidates:
    return []

  def dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = ("accuracy", "tokenEfficiency", "clarity")
    better_or_equal = all(a.get("scores", {}).get(k, 0) >= b.get("scores", {}).get(k, 0) for k in keys)
    strictly_better = any(a.get("scores", {}).get(k, 0) > b.get("scores", {}).get(k, 0) for k in keys)
    return better_or_equal and strictly_better

  frontier: list[dict[str, Any]] = []
  for cand in candidates:
    if any(dominates(other, cand) for other in candidates if other is not cand):
      continue
    frontier.append(cand)
  frontier.sort(
    key=lambda c: (
      c.get("scores", {}).get("accuracy", 0),
      c.get("scores", {}).get("clarity", 0),
      c.get("scores", {}).get("tokenEfficiency", 0),
    ),
    reverse=True,
  )
  return frontier


def pick_best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
  if not candidates:
    return None
  for c in candidates:
    c["scores"] = score_skill_candidate(c.get("body", ""), hotspot=c.get("hotspot"))
  frontier = pareto_frontier(candidates)
  return frontier[0] if frontier else max(candidates, key=lambda c: sum(c.get("scores", {}).values()))
