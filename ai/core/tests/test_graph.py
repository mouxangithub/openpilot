"""Tests for ai.core.graph."""

import asyncio
import unittest

from ai.core.graph.executor import GraphResult, default_executor
from ai.core.graph.graph import Edge, Graph
from ai.core.graph.node import Node, NodeKind


class GraphTestCase(unittest.TestCase):
  def test_build_and_serialize(self):
    g = Graph([
      Node("start", NodeKind.START),
      Node("llm", NodeKind.LLM),
      Node("out", NodeKind.OUTPUT),
    ], [
      Edge("start", "llm"),
      Edge("llm", "out"),
    ])
    self.assertEqual(len(g.nodes), 3)
    self.assertEqual(len(g.edges), 2)
    data = g.to_dict()
    g2 = Graph.from_dict(data)
    self.assertEqual(len(g2.nodes), 3)

  def test_start_nodes(self):
    g = Graph([
      Node("a", NodeKind.START),
      Node("b", NodeKind.LLM),
    ], [Edge("a", "b")])
    self.assertEqual([n.id for n in g.start_nodes()], ["a"])


class GraphExecutorTestCase(unittest.TestCase):
  def test_linear_graph(self):
    g = Graph([
      Node("start", NodeKind.START),
      Node("llm", NodeKind.LLM, config={"model": "gpt-4"}),
      Node("out", NodeKind.OUTPUT, config={"var": "_last"}),
    ], [
      Edge("start", "llm"),
      Edge("llm", "out"),
    ])
    result = asyncio.run(default_executor().run(g))
    self.assertTrue(result.ok)
    self.assertIn("llm", result.node_outputs or {})

  def test_missing_handler(self):
    g = Graph([
      Node("start", NodeKind.START),
      Node("decide", NodeKind.DECISION),
    ], [Edge("start", "decide")])
    result = asyncio.run(default_executor().run(g))
    self.assertFalse(result.ok)

  def test_decision_routing(self):
    g = Graph([
      Node("start", NodeKind.START),
      Node("decide", NodeKind.DECISION),
      Node("yes", NodeKind.OUTPUT, config={"var": "_last"}),
      Node("no", NodeKind.OUTPUT, config={"var": "_last"}),
    ], [
      Edge("start", "decide"),
      Edge("decide", "yes", condition="yes"),
      Edge("decide", "no", condition="no"),
    ])

    async def decide_handler(node, ctx):
      return "yes"

    ex = default_executor()
    ex.register(NodeKind.DECISION, decide_handler)
    result = asyncio.run(ex.run(g))
    self.assertTrue(result.ok)


if __name__ == "__main__":
  unittest.main()
