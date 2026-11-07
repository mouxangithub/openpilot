"""Tests for fork SSE pipeline helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ai.fork.analyze_fork import analyze_fork_with_ai
from ai.fork.fork_emit import PHASE_LABELS, emit_phase


class TestForkEmit(unittest.TestCase):
  def test_phase_labels_cover_pipeline(self) -> None:
    expected = {
      "scan",
      "cache",
      "read_files",
      "llm_analyze",
      "parse",
      "save_analysis",
      "llm_draft",
      "save_drafts",
    }
    self.assertTrue(expected.issubset(set(PHASE_LABELS)))


class TestAnalyzeForkCached(unittest.IsolatedAsyncioTestCase):
  async def test_cached_analysis_emits_phases(self) -> None:
    events: list[dict] = []

    async def emit(event: dict) -> None:
      events.append(event)

    root = Path(__file__).resolve().parents[2]
    with patch("ai.fork.analyze_fork.scan_openpilot_repo") as scan_mock, patch(
      "ai.fork.analyze_fork.load_cached_analysis"
    ) as cache_mock:
      scan_mock.return_value = {"git_commit": "abc123"}
      cache_mock.return_value = {"analysis": {"fork_name": "Test", "summary": "ok"}}
      with patch("ai.fork.analyze_fork.derive_fork_identity", return_value={"fork_id": "test"}):
        with patch("ai.fork.analyze_fork.compact_scan_for_api", return_value={}):
          result = await analyze_fork_with_ai(object(), root, force=False, emit=emit)

    self.assertTrue(result["ok"])
    self.assertTrue(result["cached"])
    phase_ids = [e["id"] for e in events if e.get("type") == "phase"]
    self.assertIn("scan", phase_ids)
    self.assertIn("cache", phase_ids)
    self.assertNotIn("llm_analyze", phase_ids)


if __name__ == "__main__":
  unittest.main()
