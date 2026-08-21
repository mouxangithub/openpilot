"""Constraint gates for evolved artifacts (Hermes guardrails, OP-adapted)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Hermes guardrail defaults (PLAN.md) — keep local to avoid Params import chain in tests
MAX_SKILL_CHARS = 15_000
MAX_TOOL_DESC_CHARS = 500
MAX_GROWTH_RATIO = 0.35

_SECTION_RE = re.compile(r"^##\s+", re.M)


@dataclass
class ConstraintResult:
  passed: bool
  constraint_name: str
  message: str


def validate_artifact(
  text: str,
  *,
  artifact_type: str = "skill",
  baseline_text: str = "",
) -> list[ConstraintResult]:
  results: list[ConstraintResult] = []
  body = (text or "").strip()
  limit = MAX_SKILL_CHARS if artifact_type == "skill" else MAX_TOOL_DESC_CHARS
  size = len(body)

  results.append(ConstraintResult(
    passed=bool(body),
    constraint_name="non_empty",
    message="non-empty" if body else "empty artifact",
  ))
  results.append(ConstraintResult(
    passed=size <= limit,
    constraint_name="size_limit",
    message=f"{size}/{limit} chars",
  ))

  if baseline_text:
    growth = (size - len(baseline_text)) / max(1, len(baseline_text))
    results.append(ConstraintResult(
      passed=growth <= MAX_GROWTH_RATIO,
      constraint_name="growth_limit",
      message=f"growth {growth:+.1%} (max {MAX_GROWTH_RATIO:+.0%})",
    ))

  if artifact_type == "skill":
    sections = len(_SECTION_RE.findall(body))
    results.append(ConstraintResult(
      passed=sections >= 1 or len(body) < 400,
      constraint_name="skill_structure",
      message=f"{sections} markdown sections",
    ))
    # OP safety: no actuator language in evolved skills
    bad = re.search(r"\b(steer|brake|throttle|转向|制动|油门)\b.*\b(command|指令|发送)\b", body, re.I)
    results.append(ConstraintResult(
      passed=bad is None,
      constraint_name="safety_semantic",
      message="no actuator command patterns" if bad is None else "actuator command pattern detected",
    ))

  return results


def all_passed(results: list[ConstraintResult]) -> bool:
  return all(r.passed for r in results)
