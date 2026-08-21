"""Reflective mutate step — GEPA-style without mandatory DSPy."""

from __future__ import annotations

import json
from typing import Any

from ai.core.llm.client import chat_completion_collect
from ai.evolution.dataset import EvalExample
from ai.evolution.fitness import FitnessScore

_MUTATE_SYSTEM = """You improve an openpilot agent SKILL.md using reflective evolution (GEPA).
Given baseline skill, execution trace signals, judge feedback, and a focus area,
output JSON only:
{
  "skill_body": "full improved markdown body (no YAML frontmatter)",
  "changelog": "what changed and why"
}
Preserve safety: never add vehicle actuator commands. Keep under 12k chars. Use ## sections."""


async def reflective_mutate(
  config: Any,
  *,
  baseline_body: str,
  hotspot: dict[str, Any] | None,
  feedback: str = "",
  focus: str = "",
  iteration: int = 0,
) -> dict[str, Any]:
  if not getattr(config, "is_configured", False):
    return {"ok": False, "error": "AI not configured"}

  payload = {
    "iteration": iteration,
    "focus": focus,
    "baseline_excerpt": baseline_body[:8000],
    "hotspot": hotspot or {},
    "judge_feedback": feedback,
  }
  content, _, err = await chat_completion_collect(
    config,
    [
      {"role": "system", "content": _MUTATE_SYSTEM},
      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ],
    max_tokens=3500,
    temperature=0.35,
  )
  if err or not content:
    return {"ok": False, "error": err or "empty mutation"}

  text = content.strip()
  if text.startswith("```"):
    text = text.split("\n", 1)[-1]
    if text.endswith("```"):
      text = text[:-3]
  try:
    data = json.loads(text)
  except json.JSONDecodeError:
    return {"ok": False, "error": "invalid mutation JSON", "raw": text[:500]}

  body = str(data.get("skill_body") or "").strip()
  if not body:
    return {"ok": False, "error": "empty skill_body"}
  return {
    "ok": True,
    "body": body,
    "changelog": str(data.get("changelog") or ""),
    "variant": f"reflect-{iteration}",
  }


def combine_feedback(scores: list[FitnessScore]) -> str:
  parts = [s.feedback for s in scores if s.feedback and s.feedback != "heuristic overlap"]
  return "\n".join(parts[:5])
