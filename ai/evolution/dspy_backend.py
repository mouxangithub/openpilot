"""Optional DSPy+GEPA backend — used when dspy is installed and enabled."""

from __future__ import annotations

from typing import Any


def dspy_available() -> bool:
  try:
    import dspy  # noqa: F401
    return True
  except ImportError:
    return False


async def evolve_with_dspy(
  *,
  skill_body: str,
  dataset: Any,
  iterations: int,
  optimizer_model: str,
  eval_model: str,
) -> dict[str, Any]:
  """Best-effort DSPy GEPA compile. Returns {ok, body, engine: 'dspy-gepa'}."""
  if not dspy_available():
    return {"ok": False, "error": "dspy not installed"}

  import dspy
  from ai.evolution.dataset import EvalDataset

  if not isinstance(dataset, EvalDataset) or not dataset.train:
    return {"ok": False, "error": "dataset empty"}

  class SkillModule(dspy.Module):
    def __init__(self, text: str):
      super().__init__()
      self.skill_text = text

    def forward(self, task_input: str = ""):
      return dspy.Prediction(output=f"Skill-guided plan for: {task_input}\n{self.skill_text[:1500]}")

  def metric(example, prediction, trace=None):
    out = getattr(prediction, "output", "") or ""
    if not out.strip():
      return 0.0
    exp = getattr(example, "expected_behavior", "") or ""
    ew = set(exp.lower().split())
    ow = set(out.lower().split())
    return 0.3 + 0.7 * (len(ew & ow) / max(1, len(ew)))

  lm = dspy.LM(eval_model or optimizer_model)
  dspy.configure(lm=lm)
  module = SkillModule(skill_body)
  trainset = dataset.to_dspy_examples("train") if hasattr(dataset, "to_dspy_examples") else []
  valset = dataset.to_dspy_examples("val") if hasattr(dataset, "to_dspy_examples") else []

  try:
    optimizer = dspy.GEPA(metric=metric, max_steps=iterations)
    optimized = optimizer.compile(module, trainset=trainset, valset=valset or trainset)
    body = getattr(optimized, "skill_text", skill_body)
    return {"ok": True, "body": body, "engine": "dspy-gepa"}
  except Exception as e:
    try:
      optimizer = dspy.MIPROv2(metric=metric, auto="light")
      optimized = optimizer.compile(module, trainset=trainset)
      body = getattr(optimized, "skill_text", skill_body)
      return {"ok": True, "body": body, "engine": "dspy-mipro", "warning": str(e)}
    except Exception as e2:
      return {"ok": False, "error": f"GEPA and MIPROv2 failed: {e2}"}
