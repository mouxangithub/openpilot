"""Model tier routing — WorkBuddy-style lite / default / craft."""

from __future__ import annotations

import re
from typing import Any

from ai.common.storage import read_param

_TIERS = ("auto", "lite", "default", "craft")
_TIER_PATTERNS: dict[str, re.Pattern[str]] = {
  "lite": re.compile(
    r"(flash|mini|lite|haiku|nano|fast|turbo|8b|small|instant)",
    re.IGNORECASE,
  ),
  "craft": re.compile(
    r"(pro|opus|sonnet|reason|think|max|ultra|craft|deep|70b|72b|large)",
    re.IGNORECASE,
  ),
}


def normalize_tier(raw: str | None) -> str:
  t = str(raw or "auto").strip().lower()
  return t if t in _TIERS else "auto"


def tier_from_body(body: dict[str, Any] | None, params: Any = None) -> str:
  if isinstance(body, dict):
    for key in ("modelTier", "model_tier", "tier"):
      if body.get(key):
        return normalize_tier(str(body[key]))
  return normalize_tier(str(read_param(params, "ai_model_tier", "auto") or "auto"))


def score_model_for_tier(model: str, tier: str) -> int:
  """Higher score = better match for tier."""
  if tier in ("auto", "default"):
    return 50
  m = model or ""
  pat = _TIER_PATTERNS.get(tier)
  if not pat:
    return 50
  if pat.search(m):
    return 100
  if tier == "lite":
    return 10 if _TIER_PATTERNS["craft"].search(m) else 40
  if tier == "craft":
    return 10 if _TIER_PATTERNS["lite"].search(m) else 40
  return 50


def reorder_chain_for_tier(chain: list[Any], tier: str) -> list[Any]:
  """Reorder model config chain to prefer tier-matching models."""
  tier = normalize_tier(tier)
  if tier in ("auto", "default") or not chain:
    return chain
  scored = [(score_model_for_tier(getattr(c, "model", "") or "", tier), i, c) for i, c in enumerate(chain)]
  scored.sort(key=lambda x: (-x[0], x[1]))
  return [c for _, _, c in scored]
