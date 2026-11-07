"""Tests for ai.core.session.cost."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.core.session.cost import CostTracker, get_cost_summary, record_usage


def test_record_usage_and_summary():
  tracker = CostTracker()
  tracker.record_usage("openai", "gpt-4", 100, 50, 0.005)
  tracker.record_usage("openai", "gpt-4", 200, 100, 0.010)
  tracker.record_usage("anthropic", "claude", 10, 5, 0.001)
  summary = tracker.get_cost_summary()
  assert summary["total_requests"] == 3
  assert summary["total_cost"] == pytest.approx(0.016)
  assert summary["total_tokens"] == 465
  by_model = {m["model"]: m for m in summary["by_model"]}
  assert by_model["gpt-4"]["input_tokens"] == 300
  assert by_model["gpt-4"]["output_tokens"] == 150


def test_negative_tokens_clamped():
  tracker = CostTracker()
  tracker.record_usage("x", "y", -5, -10, 0.0)
  summary = tracker.get_cost_summary()
  assert summary["total_tokens"] == 0


def test_persistence(tmp_path: Path):
  path = tmp_path / "cost.jsonl"
  tracker = CostTracker(persist_path=path)
  tracker.record_usage("p", "m", 1, 1, 0.001)
  assert path.exists()
  lines = path.read_text(encoding="utf-8").strip().splitlines()
  assert len(lines) == 1


def test_global_tracker():
  record_usage("global_provider", "global_model", 5, 5, 0.0001)
  summary = get_cost_summary()
  models = [m["model"] for m in summary["by_model"]]
  assert "global_model" in models
