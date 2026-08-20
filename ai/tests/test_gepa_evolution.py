"""GEPA engine tests (no Params / no network)."""

from __future__ import annotations

import unittest

from ai.evolution.constraints import all_passed, validate_artifact
from ai.evolution.dataset import EvalExample, _split_examples, examples_from_session_traces


class TestGepaConstraints(unittest.TestCase):
  def test_valid_skill(self):
    body = "## Steps\n1. Read params\n2. Explain to user\n"
    res = validate_artifact(body, artifact_type="skill")
    self.assertTrue(all_passed(res))

  def test_oversize_rejected(self):
    body = "x" * 20000
    res = validate_artifact(body, artifact_type="skill")
    self.assertFalse(all_passed(res))

  def test_actuator_pattern_rejected(self):
    body = "## Bad\nSend steer command to test lane keep\n"
    res = validate_artifact(body, artifact_type="skill")
    self.assertFalse(all_passed(res))


class TestGepaDataset(unittest.TestCase):
  def test_split(self):
    rows = [EvalExample(task_input=f"q{i}", expected_behavior=f"r{i}") for i in range(6)]
    ds = _split_examples(rows)
    self.assertGreaterEqual(len(ds.train), 1)

  def test_trace_mining(self):
    traces = [{
      "lastUser": "无法 engage 帮我排查",
      "toolErrors": ["read_params: timeout"],
      "userCorrections": [],
      "signals": ["tool:read_params"],
    }]
    ex = examples_from_session_traces(traces, skill_id="engage-troubleshooting")
    self.assertEqual(len(ex), 1)
    self.assertIn("engage", ex[0].task_input)

  def test_golden_datasets_load(self):
    from ai.evolution.dataset import load_golden_dataset

    expected = {
      "memory-protocol": 5,
      "sp-tuning": 6,
      "engage-troubleshooting": 6,
      "longitudinal-tuning": 5,
      "vehicle-adaptation": 5,
      "health-check": 4,
      "post-tune-validation": 4,
    }
    for skill_id, count in expected.items():
      ds = load_golden_dataset(skill_id)
      self.assertIsNotNone(ds, skill_id)
      assert ds is not None
      self.assertEqual(len(ds.all_examples), count, skill_id)


if __name__ == "__main__":
  unittest.main()
