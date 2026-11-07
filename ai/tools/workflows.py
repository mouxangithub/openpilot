"""Compatibility shim + graph workflow execution backend."""

from __future__ import annotations

from ai.tools.domains.platform.workflows import *  # noqa: F403
from ai.tools.domains.platform.workflow_graph import (  # noqa: F401
  default_graph_executor,
  execute_graph_workflow,
  get_graph_workflow,
  list_graph_workflows,
  load_graphs,
  save_graphs,
)


def execute_workflow(
  workflow_id: str,
  inputs: dict | None = None,
  tool_handlers: dict | None = None,
):
  """Run a workflow by id, preferring graph definitions over prompt-based ones."""
  graph_result = execute_graph_workflow(workflow_id, inputs=inputs, tool_handlers=tool_handlers)
  if graph_result.ok or graph_result.error != f"graph workflow '{workflow_id}' not found":
    return graph_result
  from ai.tools.domains.platform.workflows import workflow_system_prompt
  prompt = workflow_system_prompt(workflow_id)
  if not prompt:
    return {"ok": False, "error": f"workflow '{workflow_id}' not found"}
  return {"ok": True, "mode": "prompt", "prompt": prompt}
