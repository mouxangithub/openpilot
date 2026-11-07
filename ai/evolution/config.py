"""Evolution run configuration (Hermes self-evolution compatible knobs)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ai.common.evolution_config import (
  evolution_candidate_count,
  evolution_eval_cases,
  evolution_gepa_iterations,
  evolution_use_dspy,
)
from ai.skills.loader import list_skills


@dataclass
class EvolutionRunConfig:
  skill_id: str = ""
  iterations: int = 3
  eval_cases: int = 8
  eval_source: str = "sessiondb"  # sessiondb | synthetic | golden | trace
  dataset_path: str = ""
  candidate_count: int = 3
  use_dspy: bool = False
  dry_run: bool = False
  focus: str = ""
  trace_session_id: str = ""

  @classmethod
  def from_params(cls, skill_id: str = "", **overrides: object) -> EvolutionRunConfig:
    cfg = cls(
      skill_id=skill_id,
      iterations=evolution_gepa_iterations(),
      eval_cases=evolution_eval_cases(),
      candidate_count=evolution_candidate_count(),
      use_dspy=evolution_use_dspy(),
    )
    for k, v in overrides.items():
      if hasattr(cfg, k) and v is not None:
        setattr(cfg, k, v)
    if cfg.iterations < 1:
      cfg.iterations = 1
    return cfg


# Hermes guardrail defaults (PLAN.md)
MAX_SKILL_CHARS = 15_000
MAX_TOOL_DESC_CHARS = 500
MAX_GROWTH_RATIO = 0.35


def skills_root() -> Path:
  return Path(__file__).resolve().parent.parent / "skills"


def golden_datasets_root() -> Path:
  return Path(__file__).resolve().parent / "datasets"


def resolve_skill_entry(skill_id: str) -> dict | None:
  sid = (skill_id or "").strip()
  for entry in list_skills():
    if entry.get("id") == sid:
      return entry
  return None
