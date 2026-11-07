"""Subagent provider capability matrix (dsh subagent/types.ts port).

START-TIME features a provider supports, checked by the runner before
delegating: a request that needs a capability the chosen provider lacks is
rejected with a structured refusal rather than accepted-then-ignored
(the "fail loud, no silent degradation" rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.subagent.models import SubagentTask


@dataclass(frozen=True)
class SubagentCapabilities:
  """Which start-time features a provider supports. One flag per
  SubagentStartRequest option; ``depth_limit`` maps to ``maxDepth``."""

  agent_options: bool = False
  output_schema: bool = False
  depth_limit: bool = False
  tool_filter: bool = False
  persona: bool = False

  def to_dict(self) -> dict[str, bool]:
    return {
      "agentOptions": self.agent_options,
      "outputSchema": self.output_schema,
      "depthLimit": self.depth_limit,
      "toolFilter": self.tool_filter,
      "persona": self.persona,
    }


class SubagentCapabilityError(Exception):
  """Typed refusal: the request needs a capability the provider lacks."""

  def __init__(self, code: str, message: str, capability: str = "") -> None:
    super().__init__(message)
    self.code = code
    self.capability = capability

  def to_dict(self) -> dict[str, Any]:
    return {"ok": False, "error": str(self), "error_code": self.code, "capability": self.capability}


def validate_request(task: SubagentTask, caps: SubagentCapabilities) -> SubagentCapabilityError | None:
  """Return a typed refusal when the task needs a missing capability, else None."""
  if task.output_schema is not None and not caps.output_schema:
    return SubagentCapabilityError(
      "SUBAGENT_CAPABILITY_MISSING",
      f"provider does not support outputSchema; task {task.id} requires it",
      "outputSchema",
    )
  if task.tools and not caps.tool_filter:
    return SubagentCapabilityError(
      "SUBAGENT_CAPABILITY_MISSING",
      f"provider does not support tool filtering; task {task.id} requires it",
      "toolFilter",
    )
  if task.metadata.get("persona") and not caps.persona:
    return SubagentCapabilityError(
      "SUBAGENT_CAPABILITY_MISSING",
      f"provider does not support persona; task {task.id} requires it",
      "persona",
    )
  if task.metadata.get("agent_options") and not caps.agent_options:
    return SubagentCapabilityError(
      "SUBAGENT_CAPABILITY_MISSING",
      f"provider does not support agent options; task {task.id} requires it",
      "agentOptions",
    )
  if task.depth >= task.max_depth and not caps.depth_limit:
    return SubagentCapabilityError(
      "SUBAGENT_CAPABILITY_MISSING",
      f"provider does not support depth limiting; task {task.id} at depth {task.depth} requires it",
      "depthLimit",
    )
  return None


def validate_depth(task: SubagentTask) -> SubagentCapabilityError | None:
  """Delegation depth must stay under the task's own ceiling (all providers)."""
  if task.depth >= task.max_depth:
    return SubagentCapabilityError(
      "SUBAGENT_DEPTH_EXCEEDED",
      f"delegation depth {task.depth} reached the ceiling {task.max_depth} for task {task.id}",
      "depthLimit",
    )
  return None