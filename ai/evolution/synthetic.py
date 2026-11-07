"""Synthetic eval case generation via configured LLM (no DSPy required)."""

from __future__ import annotations

import json
import random
from typing import Any

from ai.core.llm.client import chat_completion_collect
from ai.evolution.dataset import EvalDataset, EvalExample, _split_examples

_SYSTEM = """You generate evaluation cases for an openpilot OP Agent skill.
Output JSON array only. Each item: task_input, expected_behavior, difficulty (easy|medium|hard), category.
Cases must be realistic for in-car tuning, diagnostics, SecOC, routes — no actuator commands."""


async def generate_synthetic_dataset(
  skill_body: str,
  *,
  skill_id: str = "",
  num_cases: int = 8,
  config: Any,
) -> EvalDataset:
  prompt = (
    f"Skill id: {skill_id}\n"
    f"Generate {num_cases} diverse test cases.\n\n"
    f"SKILL.md:\n{skill_body[:6000]}"
  )
  content, _, err = await chat_completion_collect(
    config,
    [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
    max_tokens=2000,
    temperature=0.4,
  )
  if err or not content:
    return _split_examples([])

  text = content.strip()
  if text.startswith("```"):
    text = text.split("\n", 1)[-1]
    if text.endswith("```"):
      text = text[:-3]
  try:
    raw = json.loads(text)
  except json.JSONDecodeError:
    import re
    m = re.search(r"\[.*\]", text, re.DOTALL)
    raw = json.loads(m.group()) if m else []

  rows: list[EvalExample] = []
  for item in raw if isinstance(raw, list) else []:
    if not isinstance(item, dict):
      continue
    ti = str(item.get("task_input") or "").strip()
    eb = str(item.get("expected_behavior") or "").strip()
    if ti and eb:
      rows.append(EvalExample(
        task_input=ti,
        expected_behavior=eb,
        difficulty=str(item.get("difficulty") or "medium"),
        category=str(item.get("category") or "general"),
        source="synthetic",
      ))
  random.shuffle(rows)
  return _split_examples(rows[:num_cases])
