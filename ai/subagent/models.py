"""Subagent domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SubagentStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
SubagentStopReason = Literal["completed", "max-tokens", "aborted", "refusal", "error"]


@dataclass
class SubagentTask:
  id: str
  agent_id: str
  prompt: str
  session_id: str = ""
  workflow: str = ""
  tools: list[str] | None = None
  output_schema: dict[str, Any] | None = None
  depth: int = 0
  max_depth: int = 3
  parent_id: str | None = None
  status: SubagentStatus = "pending"
  result_summary: str = ""
  provider: str = "in-process"
  origin: str = "user"
  delegation_depth: int | None = None
  metadata: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {
      "id": self.id,
      "agentId": self.agent_id,
      "prompt": self.prompt,
      "sessionId": self.session_id,
      "workflow": self.workflow,
      "tools": self.tools,
      "depth": self.depth,
      "maxDepth": self.max_depth,
      "parentId": self.parent_id,
      "status": self.status,
      "resultSummary": self.result_summary,
      "provider": self.provider,
      "origin": self.origin,
      "metadata": dict(self.metadata),
    }
    if self.delegation_depth is not None:
      out["delegationDepth"] = self.delegation_depth
    if self.output_schema is not None:
      out["outputSchema"] = self.output_schema
    return out

  @staticmethod
  def from_dict(data: dict[str, Any]) -> SubagentTask:
    return SubagentTask(
      id=str(data.get("id", "")),
      agent_id=str(data.get("agentId") or data.get("agent_id") or ""),
      prompt=str(data.get("prompt", "")),
      session_id=str(data.get("sessionId") or data.get("session_id") or ""),
      workflow=str(data.get("workflow", "")),
      tools=list(data.get("tools")) if data.get("tools") else None,
      output_schema=data.get("outputSchema") or data.get("output_schema") or None,
      depth=int(data.get("depth", 0)),
      max_depth=int(data.get("maxDepth") or data.get("max_depth", 3)),
      parent_id=data.get("parentId") or data.get("parent_id") or None,
      status=str(data.get("status", "pending")),
      result_summary=str(data.get("resultSummary") or data.get("result_summary", "")),
      provider=str(data.get("provider", "in-process") or "in-process"),
      origin=str(data.get("origin", "user") or "user"),
      delegation_depth=data.get("delegationDepth") or data.get("delegation_depth"),
      metadata=dict(data.get("metadata") or {}),
    )


@dataclass
class SubagentResult:
  task_id: str
  ok: bool
  output: str = ""
  structured: Any = None
  stop_reason: SubagentStopReason = "error"
  error: str = ""
  error_code: str = ""
  events: list[dict[str, Any]] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "taskId": self.task_id,
      "ok": self.ok,
      "output": self.output,
      "structured": self.structured,
      "stopReason": self.stop_reason,
      "error": self.error,
      "errorCode": self.error_code,
      "events": list(self.events),
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> SubagentResult:
    return SubagentResult(
      task_id=str(data.get("taskId") or data.get("task_id") or ""),
      ok=bool(data.get("ok", False)),
      output=str(data.get("output", "")),
      structured=data.get("structured"),
      stop_reason=str(data.get("stopReason") or data.get("stop_reason", "error")),
      error=str(data.get("error", "")),
      error_code=str(data.get("errorCode") or data.get("error_code") or ""),
      events=list(data.get("events") or []),
    )
