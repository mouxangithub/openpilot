"""Built-in GEPA evolution engine for OP Agent skills."""

from __future__ import annotations

import time
from typing import Any

from ai.core.llm.client import AIConfig
from ai.server.deps import read_ai_config
from ai.evolution.config import EvolutionRunConfig
from ai.evolution.constraints import all_passed, validate_artifact
from ai.evolution.dataset import EvalDataset, build_eval_dataset
from ai.evolution.dspy_backend import dspy_available, evolve_with_dspy
from ai.evolution.fitness import score_skill_on_split
from ai.evolution.reflect_mutate import combine_feedback, reflective_mutate
from ai.evolution.skill_source import load_skill_for_evolution
from ai.tools.skill_evaluation import pick_best_candidate
from ai.tools.skill_learning import propose_learned_skill


def gepa_status() -> dict[str, Any]:
  from ai.common.evolution_config import evolution_settings
  return {
    "ok": True,
    "engine": "op-gepa",
    "dspyAvailable": dspy_available(),
    "settings": evolution_settings(),
    "upstream": "https://github.com/NousResearch/hermes-agent-self-evolution",
  }


async def evolve_skill_gepa(
  params: Any,
  *,
  skill_id: str,
  run: EvolutionRunConfig | None = None,
  config: AIConfig | None = None,
  traces: list[dict[str, Any]] | None = None,
  hotspot: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Full Hermes-style skill evolution with eval dataset + constraints + approval gate."""
  cfg = config or read_ai_config(params)
  run = run or EvolutionRunConfig.from_params(skill_id=skill_id)

  if run.dry_run:
    skill = load_skill_for_evolution(skill_id)
    return {
      "ok": bool(skill.get("ok")),
      "dryRun": True,
      "skill": skill.get("name"),
      "evalSource": run.eval_source,
      "iterations": run.iterations,
      "dspy": run.use_dspy and dspy_available(),
    }

  skill = load_skill_for_evolution(skill_id)
  if not skill.get("ok"):
    return skill

  baseline = str(skill.get("body") or "")
  baseline_constraints = validate_artifact(baseline, artifact_type="skill")
  if not all_passed(baseline_constraints):
    # warn but continue — Hermes does same
    pass

  dataset = await build_eval_dataset(
    skill_id=skill_id,
    skill_body=baseline,
    config=run,
    ai_config=cfg,
    eval_source=run.eval_source,
    num_cases=run.eval_cases,
    traces=traces,
    dataset_path=run.dataset_path,
  )

  if not dataset.all_examples:
    return {"ok": False, "error": "no eval examples — try synthetic or session traces"}

  started = time.time()
  engine = "op-reflect-gepa"

  # Optional full DSPy GEPA path
  if run.use_dspy and dspy_available() and cfg.is_configured:
    dspy_res = await evolve_with_dspy(
      skill_body=baseline,
      dataset=dataset,
      iterations=run.iterations,
      optimizer_model=cfg.model,
      eval_model=cfg.model,
    )
    if dspy_res.get("ok"):
      evolved_body = str(dspy_res.get("body") or baseline)
      engine = str(dspy_res.get("engine") or "dspy-gepa")
      candidates = [{"body": evolved_body, "variant": engine, "hotspot": hotspot}]
    else:
      candidates = []
  else:
    candidates = []

  # Native reflective GEPA loop
  if not candidates:
    current = baseline
    feedback = ""
    for i in range(max(1, run.iterations)):
      mut = await reflective_mutate(
        cfg,
        baseline_body=current,
        hotspot=hotspot,
        feedback=feedback,
        focus=run.focus,
        iteration=i + 1,
      )
      if mut.get("ok"):
        candidates.append({
          "body": mut["body"],
          "variant": mut.get("variant", f"reflect-{i+1}"),
          "hotspot": hotspot,
          "changelog": mut.get("changelog", ""),
        })
        current = mut["body"]
      # Score on val for feedback next round
      _, scores = await score_skill_on_split(
        cfg, skill_text=current, examples=dataset.val or dataset.train, use_llm=False,
      )
      feedback = combine_feedback(scores)

  # Attach baseline for Pareto
  candidates.insert(0, {"body": baseline, "variant": "baseline", "hotspot": hotspot})
  best = pick_best_candidate(candidates)
  if not best:
    return {"ok": False, "error": "no candidates"}

  evolved_body = str(best.get("body") or baseline)
  evolved_constraints = validate_artifact(evolved_body, artifact_type="skill", baseline_text=baseline)
  if not all_passed(evolved_constraints):
    return {
      "ok": False,
      "error": "evolved skill failed constraints",
      "constraints": [c.__dict__ for c in evolved_constraints],
      "variant": best.get("variant"),
    }

  baseline_score, _ = await score_skill_on_split(
    cfg, skill_text=baseline, examples=dataset.holdout or dataset.val, use_llm=cfg.is_configured,
  )
  evolved_score, _ = await score_skill_on_split(
    cfg, skill_text=evolved_body, examples=dataset.holdout or dataset.val, use_llm=cfg.is_configured,
  )

  title = f"GEPA · {skill.get('name') or skill_id}"
  if run.focus:
    title += f" ({run.focus[:30]})"

  proposal = propose_learned_skill(
    params,
    title=title,
    body=evolved_body + f"\n\n---\n_evolved: gepa | engine={engine} | Δscore={evolved_score - baseline_score:+.3f}_\n",
    tags=["evolved", "gepa", skill_id, str(best.get("variant") or "v1")],
    auto_approve=False,
  )

  elapsed = time.time() - started
  return {
    **proposal,
    "ok": proposal.get("ok", True),
    "engine": engine,
    "skillId": skill_id,
    "baselineScore": round(baseline_score, 4),
    "evolvedScore": round(evolved_score, 4),
    "improvement": round(evolved_score - baseline_score, 4),
    "constraints": [c.__dict__ for c in evolved_constraints],
    "paretoScores": best.get("scores"),
    "variant": best.get("variant"),
    "candidates": len(candidates),
    "evalExamples": len(dataset.all_examples),
    "elapsedSec": round(elapsed, 2),
    "datasetSplits": {
      "train": len(dataset.train),
      "val": len(dataset.val),
      "holdout": len(dataset.holdout),
    },
  }
