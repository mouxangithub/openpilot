"""Memory candidate selector — filter/dedupe/conflict-resolve recall hits.

Translates raw recall hits into a prompt-ready context block. Inspired by
learn-workbuddy s15 prompt_assembly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryCandidate:
  """A unit of memory being considered for prompt inclusion."""

  id: str
  topic: str
  content: str
  source: str
  confidence: float
  scope: str = "workspace"
  authority: float = 1.0


class MemoryCandidateSelector:
  """Select and rank memory candidates for prompt assembly."""

  def __init__(
    self,
    *,
    top_k: int = 8,
    min_confidence: float = 0.0,
    dedupe_threshold: float = 0.85,
  ) -> None:
    self.top_k = top_k
    self.min_confidence = min_confidence
    self.dedupe_threshold = dedupe_threshold

  def select(self, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    """Return filtered, deduped, ranked candidates."""
    filtered = [c for c in candidates if c.confidence >= self.min_confidence]
    # Sort by composite score: confidence * authority, then recency/source.
    filtered.sort(key=lambda c: (c.confidence * c.authority, c.scope, c.topic), reverse=True)
    selected: list[MemoryCandidate] = []
    for cand in filtered:
      if len(selected) >= self.top_k:
        break
      if self._is_duplicate(cand, selected):
        continue
      selected.append(cand)
    return selected

  def _is_duplicate(self, cand: MemoryCandidate, selected: list[MemoryCandidate]) -> bool:
    for existing in selected:
      if cand.topic == existing.topic:
        sim = self._simple_similarity(cand.content, existing.content)
        if sim >= self.dedupe_threshold:
          return True
    return False

  @staticmethod
  def _simple_similarity(a: str, b: str) -> float:
    """Jaccard similarity over tokenized words."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
      return 0.0
    inter = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(inter) / len(union)


def candidates_from_hits(hits: list[dict[str, Any]]) -> list[MemoryCandidate]:
  """Convert generic recall hits (RAG/vector/keyword) into MemoryCandidates."""
  out: list[MemoryCandidate] = []
  for h in hits:
    out.append(MemoryCandidate(
      id=str(h.get("id") or h.get("doc_id") or ""),
      topic=str(h.get("title") or h.get("topic") or "doc"),
      content=str(h.get("snippet") or h.get("text") or h.get("content") or ""),
      source=str(h.get("method") or h.get("source") or "recall"),
      confidence=float(h.get("score") or h.get("confidence") or 0.5),
      scope=str(h.get("scope") or "workspace"),
    ))
  return out
