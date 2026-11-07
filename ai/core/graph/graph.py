"""Graph definition and serialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.core.graph.node import Node, NodeKind


@dataclass
class Edge:
  source: str
  target: str
  label: str = ""
  condition: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {
      "source": self.source,
      "target": self.target,
      "label": self.label,
      "condition": self.condition,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> Edge:
    return Edge(
      source=str(data.get("source", "")),
      target=str(data.get("target", "")),
      label=str(data.get("label", "")),
      condition=str(data.get("condition", "")),
    )


class Graph:
  def __init__(self, nodes: list[Node] | None = None, edges: list[Edge] | None = None) -> None:
    self.nodes: dict[str, Node] = {}
    self.edges: list[Edge] = []
    self._outgoing: dict[str, list[Edge]] = {}
    self._incoming: dict[str, list[Edge]] = {}
    for node in nodes or []:
      self.add_node(node)
    for edge in edges or []:
      self.add_edge(edge)

  def add_node(self, node: Node) -> None:
    self.nodes[node.id] = node
    self._outgoing.setdefault(node.id, [])
    self._incoming.setdefault(node.id, [])

  def add_edge(self, edge: Edge) -> None:
    self.edges.append(edge)
    self._outgoing.setdefault(edge.source, []).append(edge)
    self._incoming.setdefault(edge.target, []).append(edge)

  def outgoing(self, node_id: str) -> list[Edge]:
    return list(self._outgoing.get(node_id) or [])

  def incoming(self, node_id: str) -> list[Edge]:
    return list(self._incoming.get(node_id) or [])

  def start_nodes(self) -> list[Node]:
    return [n for n in self.nodes.values() if n.kind == NodeKind.START or not self.incoming(n.id)]

  def to_dict(self) -> dict[str, Any]:
    return {
      "nodes": [n.to_dict() for n in self.nodes.values()],
      "edges": [e.to_dict() for e in self.edges],
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> Graph:
    return Graph(
      nodes=[Node.from_dict(n) for n in data.get("nodes") or []],
      edges=[Edge.from_dict(e) for e in data.get("edges") or []],
    )
