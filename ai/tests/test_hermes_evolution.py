"""Hermes evolution unit tests (no Params import)."""

from __future__ import annotations

import unittest

from ai.skills.disclosure import rank_skills, skill_manifest_lines
from ai.tools.skill_evaluation import pick_best_candidate, score_skill_candidate


class TestSkillDisclosure(unittest.TestCase):
  def test_rank_by_query(self):
    entries = [
      {"id": "safety-policy", "name": "安全", "description": "policy"},
      {"id": "sp-tuning", "name": "调优", "description": "tune params longitudinal"},
      {"id": "cabana-can", "name": "CAN", "description": "cabana signals"},
    ]
    selected, deferred = rank_skills(entries, query="调参 longitudinal", max_skills=2)
    ids = [e["id"] for e in selected]
    self.assertIn("safety-policy", ids)
    self.assertIn("sp-tuning", ids)
    self.assertTrue(any(e["id"] == "cabana-can" for e in deferred))

  def test_manifest_lines(self):
    lines = skill_manifest_lines([{"id": "a", "name": "A", "description": "d"}])
    self.assertTrue(lines[0].startswith("- `a`"))


class TestSkillEvaluation(unittest.TestCase):
  def test_pareto_picks_candidate(self):
    hotspot = {"toolErrors": ["read_params: failed"], "signals": ["tool:read_params"]}
    cands = [
      {"body": "short", "hotspot": hotspot},
      {"body": "## Steps\n1. Call read_params after checking keys\n2. On failure retry with fewer keys\n", "hotspot": hotspot},
    ]
    best = pick_best_candidate(cands)
    self.assertIsNotNone(best)
    self.assertIn("scores", best)

  def test_score_skill_candidate(self):
    scores = score_skill_candidate("## A\n1. step", hotspot={"toolErrors": ["x"]})
    self.assertIn("accuracy", scores)


if __name__ == "__main__":
  unittest.main()
