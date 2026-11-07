"""Graph executor — runs a node graph to completion.

The current implementation supports the common chat/tool loop shape:
start -> llm -> [tool_call -> tool_result -> llm]* -> output.
It is intentionally minimal; richer control flow (parallel branches,
conditional routing) can be added on top of the same Graph/Node model.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ai.core.graph.graph import Edge, Graph
from ai.core.graph.node import Node, NodeKind


@dataclass
class GraphResult:
  ok: bool
  output: Any = None
  error: str = ""
  node_outputs: dict[str, Any] | None = None


NodeHandler = Callable[[Node, dict[str, Any]], Awaitable[Any]]


class GraphExecutor:
  """Executes a graph by walking edges and invoking node handlers."""

  def __init__(self, handlers: dict[NodeKind, NodeHandler] | None = None) -> None:
    self.handlers = handlers or {}

  def register(self, kind: NodeKind, handler: NodeHandler) -> None:
    self.handlers[kind] = handler

  async def run(self, graph: Graph, *, inputs: dict[str, Any] | None = None) -> GraphResult:
    ctx: dict[str, Any] = dict(inputs or {})
    ctx["_outputs"] = {}
    starts = graph.start_nodes()
    if not starts:
      return GraphResult(ok=False, error="graph has no start node")

    current = starts[0]
    visited: set[str] = set()

    while current is not None:
      if current.id in visited:
        return GraphResult(ok=False, error=f"cycle detected at node {current.id}")
      visited.add(current.id)

      handler = self.handlers.get(current.kind)
      if handler is None:
        return GraphResult(ok=False, error=f"no handler for node kind '{current.kind}'")

      try:
        output = await handler(current, ctx)
      except Exception as e:
        return GraphResult(ok=False, error=f"node {current.id} failed: {e}")

      ctx["_outputs"][current.id] = output
      ctx["_last"] = output

      if current.kind == NodeKind.OUTPUT:
        return GraphResult(ok=True, output=output, node_outputs=ctx["_outputs"])

      next_edges = graph.outgoing(current.id)
      if not next_edges:
        return GraphResult(ok=False, error=f"node {current.id} has no outgoing edge")

      # Simple routing: decision nodes can emit a branch name; otherwise take first edge.
      chosen = next_edges[0]
      if current.kind == NodeKind.DECISION and len(next_edges) > 1:
        branch = str(output) if isinstance(output, str) else ""
        for edge in next_edges:
          if edge.condition == branch:
            chosen = edge
            break

      current = graph.nodes.get(chosen.target)
      if current is None:
        return GraphResult(ok=False, error=f"missing target node '{chosen.target}'")

    return GraphResult(ok=False, error="graph execution terminated unexpectedly")


async def _default_llm_handler(node: Node, ctx: dict[str, Any]) -> dict[str, Any]:
  """Placeholder LLM handler that echoes the node's config."""
  return {"node": node.id, "kind": node.kind.value, "config": node.config, "ctx_keys": list(ctx.keys())}


async def _default_tool_call_handler(node: Node, ctx: dict[str, Any]) -> dict[str, Any]:
  return {"node": node.id, "kind": node.kind.value, "tool": node.config.get("tool", "")}


async def _default_tool_result_handler(node: Node, ctx: dict[str, Any]) -> dict[str, Any]:
  return {"node": node.id, "kind": node.kind.value, "result": node.config.get("result", "")}


async def _default_output_handler(node: Node, ctx: dict[str, Any]) -> Any:
  return ctx.get(node.config.get("var", "_last"))


async def _default_start_handler(node: Node, ctx: dict[str, Any]) -> dict[str, Any]:
  return {"started": True}


def default_executor() -> GraphExecutor:
  ex = GraphExecutor()
  ex.register(NodeKind.LLM, _default_llm_handler)
  ex.register(NodeKind.TOOL_CALL, _default_tool_call_handler)
  ex.register(NodeKind.TOOL_RESULT, _default_tool_result_handler)
  ex.register(NodeKind.OUTPUT, _default_output_handler)
  ex.register(NodeKind.START, _default_start_handler)
  return ex
