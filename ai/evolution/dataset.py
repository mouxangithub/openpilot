"""Evaluation datasets — synthetic, session mining, golden (Hermes-compatible)."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pathlib import Path
from typing import Any


def golden_datasets_root() -> Path:
  return Path(__file__).resolve().parent / "datasets"


@dataclass
class EvalExample:
  task_input: str
  expected_behavior: str
  difficulty: str = "medium"
  category: str = "general"
  source: str = "synthetic"

  def to_dict(self) -> dict[str, str]:
    return {
      "task_input": self.task_input,
      "expected_behavior": self.expected_behavior,
      "difficulty": self.difficulty,
      "category": self.category,
      "source": self.source,
    }


@dataclass
class EvalDataset:
  train: list[EvalExample] = field(default_factory=list)
  val: list[EvalExample] = field(default_factory=list)
  holdout: list[EvalExample] = field(default_factory=list)

  @property
  def all_examples(self) -> list[EvalExample]:
    return self.train + self.val + self.holdout

  def save(self, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", self.train), ("val", self.val), ("holdout", self.holdout)):
      with (path / f"{name}.jsonl").open("w", encoding="utf-8") as f:
        for ex in rows:
          f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")

  @classmethod
  def load(cls, path: Path) -> EvalDataset:
    ds = cls()
    for name in ("train", "val", "holdout"):
      fp = path / f"{name}.jsonl"
      if not fp.is_file():
        continue
      rows: list[EvalExample] = []
      with fp.open(encoding="utf-8") as f:
        for line in f:
          if line.strip():
            d = json.loads(line)
            rows.append(EvalExample(**{k: d[k] for k in d if k in EvalExample.__dataclass_fields__}))
      setattr(ds, name, rows)
    return ds

  def to_dspy_examples(self, split: str = "train") -> list[Any]:
    try:
      import dspy
    except ImportError:
      return []
    rows = getattr(self, split, []) or []
    return [
      dspy.Example(
        task_input=ex.task_input,
        expected_behavior=ex.expected_behavior,
      ).with_inputs("task_input")
      for ex in rows
    ]


def _split_examples(examples: list[EvalExample]) -> EvalDataset:
  random.shuffle(examples)
  n = len(examples)
  if n == 0:
    return EvalDataset()
  n_train = max(1, int(n * 0.5))
  n_val = max(1, int(n * 0.25)) if n > 2 else 0
  return EvalDataset(
    train=examples[:n_train],
    val=examples[n_train:n_train + n_val] if n_val else [],
    holdout=examples[n_train + n_val:] if n > n_train + n_val else [],
  )


def load_golden_dataset(skill_id: str) -> EvalDataset | None:
  base = golden_datasets_root() / skill_id
  if (base / "train.jsonl").is_file():
    ds = EvalDataset.load(base)
    if ds.all_examples:
      return ds
  single = base / "golden.jsonl"
  if single.is_file():
    rows: list[EvalExample] = []
    with single.open(encoding="utf-8") as f:
      for line in f:
        if line.strip():
          d = json.loads(line)
          rows.append(EvalExample(**{k: d[k] for k in d if k in EvalExample.__dataclass_fields__}))
    return _split_examples(rows)
  return None


def examples_from_session_traces(traces: list[dict[str, Any]], *, skill_id: str, limit: int = 12) -> list[EvalExample]:
  """Mine eval cases from OP session hotspots (Hermes sessiondb equivalent)."""
  out: list[EvalExample] = []
  for t in traces[:limit]:
    user = str(t.get("lastUser") or "").strip()
    if len(user) < 8:
      continue
    errors = t.get("toolErrors") or []
    corrections = t.get("userCorrections") or []
    rubric_parts = [f"Skill `{skill_id}` should guide the agent to resolve the user request safely."]
    if errors:
      rubric_parts.append("Avoid repeating tool errors: " + "; ".join(errors[:2]))
    if corrections:
      rubric_parts.append("Honor user correction: " + corrections[0][:200])
    rubric_parts.append("Use openpilot tools; no vehicle actuator commands; actionable steps in Chinese if user wrote Chinese.")
    out.append(EvalExample(
      task_input=user[:800],
      expected_behavior=" ".join(rubric_parts),
      difficulty="hard" if errors else "medium",
      category="trace",
      source="sessiondb",
    ))
  return out


_OP_FALLBACK_CASES: list[EvalExample] = [
  EvalExample(
    task_input="跟车太远怎么调？",
    expected_behavior="Explain FollowDistanceGap in plain language, preview param change, wait for user confirm before write.",
    category="tuning",
  ),
  EvalExample(
    task_input="无法 engage，帮我看看",
    expected_behavior="Run health/readiness checks, read events and params, structured triage without guessing.",
    category="engage",
  ),
  EvalExample(
    task_input="记住我开的是丰田 RAV4",
    expected_behavior="Call memory tools (daily + USER.md); acknowledge without promising without tool write.",
    category="memory",
  ),
]


async def build_eval_dataset(
  *,
  skill_id: str,
  skill_body: str,
  config: Any,
  ai_config: Any,
  eval_source: str = "sessiondb",
  num_cases: int = 8,
  traces: list[dict[str, Any]] | None = None,
  dataset_path: str = "",
) -> EvalDataset:
  if eval_source == "golden":
    if dataset_path:
      ds = EvalDataset.load(Path(dataset_path))
      if ds.all_examples:
        return ds
    golden = load_golden_dataset(skill_id)
    if golden and golden.all_examples:
      return golden

  if eval_source in ("sessiondb", "trace") and traces:
    mined = examples_from_session_traces(traces, skill_id=skill_id, limit=num_cases)
    if mined:
      return _split_examples(mined)

  if eval_source == "synthetic" and ai_config and getattr(ai_config, "is_configured", False):
    from ai.evolution.synthetic import generate_synthetic_dataset
    return await generate_synthetic_dataset(skill_body, skill_id=skill_id, num_cases=num_cases, config=ai_config)

  # Fallback static OP cases + skill name hint
  rows = list(_OP_FALLBACK_CASES)
  if skill_id:
    rows.insert(0, EvalExample(
      task_input=f"使用 {skill_id} 技能帮我解决一个典型问题",
      expected_behavior=f"Follow procedures in skill `{skill_id}` with tools; concise actionable answer.",
      category=skill_id,
      source="fallback",
    ))
  return _split_examples(rows[:num_cases])
