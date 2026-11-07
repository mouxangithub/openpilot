"""Tests for G7 subagent lineage."""
from __future__ import annotations
import unittest

from ai.subagent.lineage import SubagentLineage


class LineageTest(unittest.TestCase):
  def test_add_edge_children(self) -> None:
    lg = SubagentLineage()
    lg.add_edge("root", "c1", "run1", 1, "tool")
    lg.add_edge("root", "c2", "run2", 1, "tool")
    lg.add_edge("c1", "g1", "run3", 2, "tool")
    self.assertEqual(len(lg.children("root")), 2)
    self.assertEqual(len(lg.children("c1")), 1)
    self.assertEqual(lg.children("c1")[0]["childTask"], "g1")
    self.assertEqual(lg.roots(), ["root"])

  def test_rebuild_from_events(self) -> None:
    events = [
      {"type": "SUBAGENT_START", "data": {"taskId": "c1", "parentTask": "root", "depth": 1, "origin": "tool", "runId": "r1"}},
      {"type": "SUBAGENT_END", "data": {"taskId": "c1", "runId": "r1"}},
      {"type": "SUBAGENT_START", "data": {"taskId": "c2", "parentTask": "root", "depth": 1, "origin": "tool", "runId": "r2"}},
      {"type": "SUBAGENT_END", "data": {"taskId": "c2", "runId": "r2"}},
    ]
    lg = SubagentLineage()
    lg.rebuild_from_events(events)
    self.assertEqual(lg.roots(), ["root"])
    self.assertEqual(len(lg.children("root")), 2)

  def test_orphan_root(self) -> None:
    lg = SubagentLineage()
    lg.add_edge("", "solo", "r", 0, "user")
    self.assertEqual(lg.roots(), ["solo"])


if __name__ == "__main__":
  unittest.main()