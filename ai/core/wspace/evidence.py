"""Workspace evidence journal — append-only durable facts.

Each fact carries provenance (who said it, when, source event) and supports
conflict adjudication so long-term memory stays traceable.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai.system.paths import assistant_workspace_dir


@dataclass(frozen=True)
class EvidenceEntry:
  """A single durable fact about the workspace or user."""

  id: str
  topic: str
  fact: str
  source: str
  source_event_id: str
  confidence: float
  at: int
  adjudicated: bool = False
  superseded_by: str = ""

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)


class WorkspaceEvidenceJournal:
  """Append-only journal of workspace facts.

  Facts are written as JSONL so crashes never corrupt prior entries. Conflicts
  are resolved by appending an adjudication entry that marks older facts as
  superseded rather than rewriting them.
  """

  def __init__(self, journal_path: Path | None = None) -> None:
    self._path = journal_path or (assistant_workspace_dir(mkdir=True) / "evidence.jsonl")

  def append(
    self,
    *,
    topic: str,
    fact: str,
    source: str,
    source_event_id: str,
    confidence: float = 1.0,
    entry_id: str = "",
  ) -> EvidenceEntry:
    entry = EvidenceEntry(
      id=entry_id or f"ev_{int(time.time() * 1000)}",
      topic=topic,
      fact=fact,
      source=source,
      source_event_id=source_event_id,
      confidence=max(0.0, min(1.0, confidence)),
      at=int(time.time()),
    )
    self._path.parent.mkdir(parents=True, exist_ok=True)
    with self._path.open("a", encoding="utf-8") as f:
      f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
      f.flush()
    return entry

  def read_all(self) -> list[EvidenceEntry]:
    if not self._path.is_file():
      return []
    entries: list[EvidenceEntry] = []
    with self._path.open("r", encoding="utf-8") as f:
      for line in f:
        line = line.strip()
        if not line:
          continue
        try:
          data = json.loads(line)
          entries.append(EvidenceEntry(**data))
        except (json.JSONDecodeError, TypeError):
          continue
    return entries

  def query(self, topic: str | None = None, min_confidence: float = 0.0) -> list[EvidenceEntry]:
    results = self.read_all()
    if topic:
      results = [e for e in results if e.topic == topic]
    if min_confidence > 0:
      results = [e for e in results if e.confidence >= min_confidence]
    return results

  def adjudicate_conflict(self, winner_id: str, loser_ids: list[str], reason: str = "") -> EvidenceEntry | None:
    """Mark loser facts as superseded and record the adjudication."""
    losers = {e.id for e in self.read_all() if e.id in loser_ids}
    if winner_id not in {e.id for e in self.read_all()}:
      return None
    if not losers:
      return None
    for loser_id in loser_ids:
      self.append(
        topic="_adjudication",
        fact=f"superseded by {winner_id}" + (f": {reason}" if reason else ""),
        source="adjudication",
        source_event_id=loser_id,
        entry_id=loser_id,
      )
    return self.append(
      topic="_adjudication",
      fact=f"winner: {winner_id}" + (f" ({reason})" if reason else ""),
      source="adjudication",
      source_event_id=winner_id,
    )
