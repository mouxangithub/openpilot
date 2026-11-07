"""Evolution loop settings (Hermes closed learning loop)."""

from __future__ import annotations

from typing import Any

from ai.common.storage import read_param, read_param_bool


def _int_param(key: str, default: int, *, lo: int = 0, hi: int = 100) -> int:
  try:
    raw = read_param(None, key, str(default))
    return max(lo, min(hi, int(str(raw or default).strip())))
  except (TypeError, ValueError):
    return default


def evolution_enabled() -> bool:
  return read_param_bool(None, "ai_evolution_enabled", True)


def evolution_auto_propose() -> bool:
  return read_param_bool(None, "ai_evolution_auto_propose", False)


def evolution_auto_workspace() -> bool:
  return read_param_bool(None, "ai_evolution_auto_workspace", True)


def evolution_auto_memory() -> bool:
  return read_param_bool(None, "ai_evolution_auto_memory", True)


def evolution_llm_reflect() -> bool:
  return read_param_bool(None, "ai_evolution_llm_reflect", True)


def evolution_tool_desc() -> bool:
  return read_param_bool(None, "ai_evolution_tool_desc", True)


def skills_disclosure_max() -> int:
  return _int_param("ai_skills_disclosure_max", 10, lo=3, hi=30)


def evolution_candidate_count() -> int:
  return _int_param("ai_evolution_candidates", 3, lo=1, hi=5)


def evolution_gepa_iterations() -> int:
  return _int_param("ai_evolution_gepa_iterations", 3, lo=1, hi=20)


def evolution_eval_cases() -> int:
  return _int_param("ai_evolution_eval_cases", 8, lo=3, hi=30)


def evolution_use_dspy() -> bool:
  return read_param_bool(None, "ai_evolution_use_dspy", False)


def evolution_gepa_enabled() -> bool:
  return read_param_bool(None, "ai_evolution_gepa_enabled", True)


def evolution_settings() -> dict[str, Any]:
  return {
    "enabled": evolution_enabled(),
    "autoPropose": evolution_auto_propose(),
    "autoWorkspace": evolution_auto_workspace(),
    "autoMemory": evolution_auto_memory(),
    "llmReflect": evolution_llm_reflect(),
    "toolDescEvolution": evolution_tool_desc(),
    "skillsDisclosureMax": skills_disclosure_max(),
    "evolutionCandidates": evolution_candidate_count(),
    "gepaEnabled": evolution_gepa_enabled(),
    "gepaIterations": evolution_gepa_iterations(),
    "evalCases": evolution_eval_cases(),
    "useDspy": evolution_use_dspy(),
  }
