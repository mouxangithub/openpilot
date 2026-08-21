"""LLM-as-judge fitness scoring (Hermes fitness.py, API-native)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ai.core.llm.client import chat_completion_collect
from ai.evolution.dataset import EvalExample

_JUDGE_SYSTEM = """Score an agent draft against a rubric. JSON only:
{"correctness":0-1,"procedure_following":0-1,"conciseness":0-1,"feedback":"actionable improvement"}"""


@dataclass
class FitnessScore:
  correctness: float = 0.0
  procedure_following: float = 0.0
  conciseness: float = 0.0
  feedback: str = ""

  @property
  def composite(self) -> float:
    return max(0.0, min(1.0, 0.5 * self.correctness + 0.3 * self.procedure_following + 0.2 * self.conciseness))


def _parse_score(v: Any) -> float:
  try:
    return max(0.0, min(1.0, float(v)))
  except (TypeError, ValueError):
    return 0.5


def fast_heuristic_score(example: EvalExample, draft: str) -> FitnessScore:
  """Cheap proxy during inner GEPA iterations."""
  out = (draft or "").strip()
  if not out:
    return FitnessScore(feedback="empty draft")
  exp_words = set(example.expected_behavior.lower().split())
  out_words = set(out.lower().split())
  overlap = len(exp_words & out_words) / max(1, len(exp_words))
  base = 0.25 + 0.75 * overlap
  return FitnessScore(
    correctness=base,
    procedure_following=base * 0.9,
    conciseness=max(0.3, 1.0 - min(1.0, len(out) / 4000)),
    feedback="heuristic overlap",
  )


async def judge_draft(
  config: Any,
  *,
  skill_text: str,
  example: EvalExample,
  draft: str,
  use_llm: bool = True,
) -> FitnessScore:
  if not use_llm or not getattr(config, "is_configured", False):
    return fast_heuristic_score(example, draft)

  payload = json.dumps({
    "task_input": example.task_input,
    "expected_behavior": example.expected_behavior,
    "skill_excerpt": skill_text[:2500],
    "agent_draft": draft[:3000],
  }, ensure_ascii=False)

  content, _, err = await chat_completion_collect(
    config,
    [{"role": "system", "content": _JUDGE_SYSTEM}, {"role": "user", "content": payload}],
    max_tokens=400,
    temperature=0.1,
  )
  if err or not content:
    return fast_heuristic_score(example, draft)

  text = content.strip()
  if text.startswith("```"):
    text = re.sub(r"^```\w*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
  try:
    data = json.loads(text)
  except json.JSONDecodeError:
    return fast_heuristic_score(example, draft)

  return FitnessScore(
    correctness=_parse_score(data.get("correctness")),
    procedure_following=_parse_score(data.get("procedure_following")),
    conciseness=_parse_score(data.get("conciseness")),
    feedback=str(data.get("feedback") or ""),
  )


async def score_skill_on_split(
  config: Any,
  *,
  skill_text: str,
  examples: list[EvalExample],
  use_llm: bool = False,
) -> tuple[float, list[FitnessScore]]:
  if not examples:
    return 0.0, []
  scores: list[FitnessScore] = []
  for ex in examples[:6]:
    draft = f"Following skill instructions:\n{skill_text[:1200]}\n\nUser: {ex.task_input}\n\nPlan: apply tools and answer."
    sc = await judge_draft(config, skill_text=skill_text, example=ex, draft=draft, use_llm=use_llm)
    scores.append(sc)
  avg = sum(s.composite for s in scores) / len(scores)
  return avg, scores
