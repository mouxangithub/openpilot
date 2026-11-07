"""Workflow event model and factory for durable session logs.

Event types mirror the P2 design contract:
  - workflow/start, workflow/end
  - phase/start, phase/end, phase/log
  - agent-start, agent-end
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowEvent:
  """Single workflow lifecycle event.

  Events are intentionally plain dict-serializable so they can be appended to
  the existing session event store without a schema migration.
  """

  type: str
  run_id: str
  phase_id: str = ""
  payload: dict[str, Any] = field(default_factory=dict)
  timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

  def to_dict(self) -> dict[str, Any]:
    return {
      "type": self.type,
      "run_id": self.run_id,
      "phase_id": self.phase_id,
      "payload": dict(self.payload),
      "timestamp": self.timestamp,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> "WorkflowEvent":
    return WorkflowEvent(
      type=str(data.get("type", "")),
      run_id=str(data.get("run_id", "")),
      phase_id=str(data.get("phase_id", "")),
      payload=dict(data.get("payload") or {}),
      timestamp=int(data.get("timestamp") or int(time.time() * 1000)),
    )


class WorkflowEventFactory:
  """Convenience factory producing consistently-shaped workflow events."""

  def __init__(self, run_id: str) -> None:
    self.run_id = str(run_id)

  def _make(self, type_: str, phase_id: str = "", payload: dict[str, Any] | None = None) -> WorkflowEvent:
    return WorkflowEvent(
      type=type_,
      run_id=self.run_id,
      phase_id=phase_id,
      payload=dict(payload or {}),
    )

  def workflow_start(self, definition_id: str, name: str, inputs: dict[str, Any] | None = None) -> WorkflowEvent:
    return self._make(
      "workflow/start",
      payload={"definition_id": definition_id, "name": name, "inputs": dict(inputs or {})},
    )

  def workflow_end(self, ok: bool, output: Any = None, error: str = "", code: str = "") -> WorkflowEvent:
    payload: dict[str, Any] = {"ok": ok}
    if output is not None:
      payload["output"] = output
    if error:
      payload["error"] = error
    if code:
      payload["code"] = code
    return self._make("workflow/end", payload=payload)

  def phase_start(self, phase_id: str, step_id: str = "", kind: str = "") -> WorkflowEvent:
    return self._make(
      "phase/start",
      phase_id=phase_id,
      payload={"step_id": step_id, "kind": kind},
    )

  def phase_end(self, phase_id: str, ok: bool = True, output: Any = None) -> WorkflowEvent:
    payload: dict[str, Any] = {"ok": ok}
    if output is not None:
      payload["output"] = output
    return self._make("phase/end", phase_id=phase_id, payload=payload)

  def phase_log(self, phase_id: str, message: str, level: str = "info", extra: dict[str, Any] | None = None) -> WorkflowEvent:
    payload: dict[str, Any] = {"message": message, "level": level}
    if extra:
      payload.update(extra)
    return self._make("phase/log", phase_id=phase_id, payload=payload)

  def agent_start(self, phase_id: str, agent_id: str, prompt: str = "") -> WorkflowEvent:
    return self._make(
      "agent-start",
      phase_id=phase_id,
      payload={"agent_id": agent_id, "prompt": prompt},
    )

  def agent_end(self, phase_id: str, agent_id: str, ok: bool = True, result: Any = None) -> WorkflowEvent:
    payload: dict[str, Any] = {"agent_id": agent_id, "ok": ok}
    if result is not None:
      payload["result"] = result
    return self._make("agent-end", phase_id=phase_id, payload=payload)
