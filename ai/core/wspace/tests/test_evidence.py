"""Tests for WorkspaceEvidenceJournal."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.core.wspace.evidence import WorkspaceEvidenceJournal


class TestWorkspaceEvidenceJournal(unittest.TestCase):
  def setUp(self) -> None:
    self.path = Path(tempfile.mkdtemp()) / "evidence.jsonl"
    self.journal = WorkspaceEvidenceJournal(self.path)

  def test_append_and_query(self) -> None:
    self.journal.append(topic="vehicle", fact="Toyota RAV4", source="user", source_event_id="e1")
    entries = self.journal.query(topic="vehicle")
    self.assertEqual(len(entries), 1)
    self.assertEqual(entries[0].fact, "Toyota RAV4")

  def test_adjudicate_conflict(self) -> None:
    a = self.journal.append(topic="vehicle", fact="A", source="user", source_event_id="e1")
    b = self.journal.append(topic="vehicle", fact="B", source="user", source_event_id="e2")
    result = self.journal.adjudicate_conflict(winner_id=a.id, loser_ids=[b.id], reason="user corrected")
    self.assertIsNotNone(result)


if __name__ == "__main__":
  unittest.main()
