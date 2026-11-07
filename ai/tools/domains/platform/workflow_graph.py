"""Graph-based workflow execution backend.

Uses ai.core.graph.* to run custom workflows defined as nodes and edges,
side-by-side with the existing prompt-based workflow system.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ai.core.graph.executor import GraphExecutor, GraphResult, NodeHandler
from ai.core.graph.graph import Graph
from ai.core.graph.node import NodeKind
from ai.system.paths import workspace_path


_GRAPH_PATH: Path | None = None
_STATE_PATH: Path | None = None


def _state_path() -> Path:
  global _STATE_PATH
  if _STATE_PATH is None:
    _STATE_PATH = workspace_path("workflows", mkdir=True) / "runtime_state.json"
  return _STATE_PATH


def _load_state() -> dict[str, Any]:
  try:
    return json.loads(_state_path().read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return {}


def _save_state(state: dict[str, Any]) -> None:
  _state_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def graph_path() -> Path:
  global _GRAPH_PATH
  if _GRAPH_PATH is None:
    d = workspace_path("workflows", mkdir=True)
    d.mkdir(parents=True, exist_ok=True)
    _GRAPH_PATH = d / "graphs.json"
  return _GRAPH_PATH


def load_graphs() -> dict[str, dict[str, Any]]:
  path = graph_path()
  if not path.is_file():
    return {}
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
  except (OSError, json.JSONDecodeError):
    return {}


def save_graphs(graphs: dict[str, dict[str, Any]]) -> dict[str, Any]:
  path = graph_path()
  cleaned: dict[str, dict[str, Any]] = {}
  for wid, w in (graphs or {}).items():
    if not isinstance(w, dict):
      continue
    wid = str(wid).strip()
    if not wid:
      continue
    try:
      graph = Graph.from_dict(w.get("graph", {}))
      cleaned[wid] = {
        "name": str(w.get("name") or wid),
        "graph": graph.to_dict(),
        "custom": True,
      }
    except Exception:
      continue
  try:
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(cleaned), "path": str(path)}
  except OSError as e:
    return {"ok": False, "error": str(e)}


def get_graph_workflow(workflow_id: str) -> Graph | None:
  graphs = load_graphs()
  w = graphs.get(workflow_id)
  if not w:
    return None
  try:
    return Graph.from_dict(w.get("graph", {}))
  except Exception:
    return None


async def _llm_node_handler(node: Any, ctx: dict[str, Any]) -> dict[str, Any]:
  return {"node": node.id, "kind": "llm", "config": node.config, "ctx_keys": list(ctx.keys())}


async def _tool_call_node_handler(node: Any, ctx: dict[str, Any]) -> dict[str, Any]:
  tool_name = node.config.get("tool", "")
  handlers = ctx.get("_tool_handlers", {})
  handler = handlers.get(tool_name)
  if handler is None:
    return {"ok": False, "error": f"tool '{tool_name}' not found"}
  args = node.config.get("arguments") or {}
  if asyncio.iscoroutinefunction(handler):
    result = await handler(args)
  else:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: handler(args))
  return {"ok": True, "tool": tool_name, "result": result}


async def _tool_result_node_handler(node: Any, ctx: dict[str, Any]) -> dict[str, Any]:
  return {"node": node.id, "kind": "tool_result", "config": node.config}


async def _output_node_handler(node: Any, ctx: dict[str, Any]) -> Any:
  return ctx.get("_last")


async def _start_node_handler(_node: Any, ctx: dict[str, Any]) -> dict[str, Any]:
  return {"started": True}


import asyncio


def default_graph_executor(tool_handlers: dict[str, Any] | None = None) -> GraphExecutor:
  ex = GraphExecutor()
  ex.register(NodeKind.START, _start_node_handler)
  ex.register(NodeKind.LLM, _llm_node_handler)
  ex.register(NodeKind.TOOL_CALL, _tool_call_node_handler)
  ex.register(NodeKind.TOOL_RESULT, _tool_result_node_handler)
  ex.register(NodeKind.OUTPUT, _output_node_handler)
  return ex


async def execute_graph_workflow(
  workflow_id: str,
  inputs: dict[str, Any] | None = None,
  tool_handlers: dict[str, Any] | None = None,
) -> GraphResult:
  graph = get_graph_workflow(workflow_id)
  if graph is None:
    return GraphResult(ok=False, error=f"graph workflow '{workflow_id}' not found")
  ctx = dict(inputs or {})
  ctx["_tool_handlers"] = tool_handlers or {}
  executor = default_graph_executor(tool_handlers)
  return await executor.run(graph, inputs=ctx)


def advance_graph_workflow(workflow_id: str, action: str, node_id: str | None = None) -> dict[str, Any]:
  graph = get_graph_workflow(workflow_id)
  if graph is None:
    return {"ok": False, "error": f"graph workflow '{workflow_id}' not found"}
  state = _load_state()
  current = node_id or state.get(workflow_id, {}).get("node") or (graph.start_nodes()[0].id if graph.start_nodes() else "")
  if current not in graph.nodes:
    return {"ok": False, "error": f"node '{current}' not found"}
  if action == "pause":
    state[workflow_id] = {"node": current, "status": "paused"}
  elif action == "resume":
    state[workflow_id] = {"node": current, "status": "running"}
  elif action == "retry":
    state[workflow_id] = {"node": current, "status": "retrying"}
  elif action == "step":
    outgoing = graph.outgoing(current)
    nxt = outgoing[0].target if outgoing else None
    state[workflow_id] = {"node": nxt or current, "status": "completed" if nxt is None else "running"}
  else:
    return {"ok": False, "error": f"unsupported action: {action}"}
  _save_state(state)
  return {"ok": True, "graph": workflow_id, "node": current, "next": state[workflow_id]["node"], "status": state[workflow_id]["status"], "action": action}


def list_graph_workflows() -> list[dict[str, Any]]:
  return [
    {"id": wid, "name": w.get("name", wid), "mode": "graph", "custom": True}
    for wid, w in load_graphs().items()
  ]


def graph_workflow_requires_tools(workflow_id: str) -> dict[str, Any]:
  """Return the set of tool names referenced by TOOL_CALL nodes in a graph workflow."""
  graph = get_graph_workflow(workflow_id)
  if graph is None:
    return {"ok": False, "error": f"graph workflow '{workflow_id}' not found"}
  tools: set[str] = set()
  for node in graph.nodes.values():
    if node.kind == NodeKind.TOOL_CALL:
      tool = (node.config or {}).get("tool")
      if tool:
        tools.add(str(tool))
  return {"ok": True, "workflowId": workflow_id, "requiresTools": sorted(tools)}


async def run_graph_workflow_step(
  workflow_id: str,
  action: str,
  *,
  node_id: str | None = None,
  inputs: dict[str, Any] | None = None,
  tool_handlers: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Advance or execute a single step of a graph workflow.

  Combines stateful advancement (pause/resume/step/retry) with optional
  per-step tool execution when ``tool_handlers`` are provided.
  """
  advance = advance_graph_workflow(workflow_id, action, node_id=node_id)
  if not advance.get("ok"):
    return advance

  if tool_handlers and inputs is not None and action in ("step", "resume"):
    result = await execute_graph_workflow(workflow_id, inputs=inputs, tool_handlers=tool_handlers)
    advance["stepResult"] = {
      "ok": result.ok,
      "error": result.error,
      "outputs": result.outputs if hasattr(result, "outputs") else {},
    }

  return advance
