"""Regression guard before param writes."""

from __future__ import annotations

from typing import Any

from ai.tools.route_scoring_tools import score_tune_session


def check_tune_regression(
  route_before: str,
  route_after: str,
  *,
  min_score_delta: float = -5.0,
  block_on_regression: bool = True,
) -> dict[str, Any]:
  """Return regression check; block_on_regression sets ok=False when score drops too much."""
  if not route_before or not route_after:
    return {"ok": True, "skipped": True, "reason": "routes not provided"}

  res = score_tune_session(route_before, route_after, min_score_delta=min_score_delta)
  if not res.get("ok"):
    return res

  if block_on_regression and not res.get("passed"):
    return {
      **res,
      "ok": False,
      "blocked": True,
      "error": res.get("recommendation", "Tune regression detected"),
    }
  return {**res, "blocked": False}
