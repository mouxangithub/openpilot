"""Tests for MemoryCandidateSelector."""

from __future__ import annotations

import unittest

from ai.common.memory_selector import MemoryCandidate, MemoryCandidateSelector, candidates_from_hits


class TestMemoryCandidateSelector(unittest.TestCase):
  def test_select_filters_and_dedupes(self) -> None:
    candidates = [
      MemoryCandidate(id="1", topic="tune", content="increase lat accel factor", source="rag", confidence=0.9),
      MemoryCandidate(id="2", topic="tune", content="increase lateral accel factor for toyota", source="rag", confidence=0.85),
      MemoryCandidate(id="3", topic="vehicle", content="Toyota RAV4", source="rag", confidence=0.7),
    ]
    selector = MemoryCandidateSelector(top_k=2)
    selected = selector.select(candidates)
    self.assertEqual(len(selected), 2)
    ids = {s.id for s in selected}
    self.assertIn("1", ids)

  def test_candidates_from_hits(self) -> None:
    hits = [{"id": "a", "title": "doc", "snippet": "hello", "score": 0.8, "method": "vector"}]
    cands = candidates_from_hits(hits)
    self.assertEqual(len(cands), 1)
    self.assertEqual(cands[0].source, "vector")


if __name__ == "__main__":
  unittest.main()
