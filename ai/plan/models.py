"""Plan domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PlanStatus = Literal["draft", "active", "paused", "complete", "cancelled"]
StepStatus = Literal["pending", "in_progress", "completed", "skipped"]


@dataclass
class PlanStep:
  id: str
  description: str
  status: StepStatus = "pending"
  tool: str | None = None
  depends_on: list[str] = field(default_factory=list)
  metadata: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "description": self.description,
      "status": self.status,
      "tool": self.tool,
      "dependsOn": list(self.depends_on),
      "metadata": dict(self.metadata),
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> PlanStep:
    return PlanStep(
      id=str(data.get("id", "")),
      description=str(data.get("description", "")),
      status=str(data.get("status", "pending")),
      tool=data.get("tool") if data.get("tool") else None,
      depends_on=list(data.get("dependsOn", data.get("depends_on", []))),
      metadata=dict(data.get("metadata") or {}),
    )


@dataclass
class Plan:
  id: str
  title: str
  status: PlanStatus = "draft"
  steps: list[PlanStep] = field(default_factory=list)
  goal_id: str | None = None
  created_at: int = 0
  updated_at: int = 0
  metadata: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "title": self.title,
      "status": self.status,
      "steps": [s.to_dict() for s in self.steps],
      "goalId": self.goal_id,
      "createdAt": self.created_at,
      "updatedAt": self.updated_at,
      "metadata": dict(self.metadata),
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> Plan:
    return Plan(
      id=str(data.get("id", "")),
      title=str(data.get("title", "")),
      status=str(data.get("status", "draft")),
      steps=[PlanStep.from_dict(s) for s in data.get("steps") or []],
      goal_id=data.get("goalId") or data.get("goal_id") or None,
      created_at=int(data.get("createdAt", data.get("created_at", 0))),
      updated_at=int(data.get("updatedAt", data.get("updated_at", 0))),
      metadata=dict(data.get("metadata") or {}),
    )

  @property
  def is_complete(self) -> bool:
    return all(s.status in ("completed", "skipped") for s in self.steps)

  def step_by_id(self, step_id: str) -> PlanStep | None:
    for step in self.steps:
      if step.id == step_id:
        return step
    return None


@dataclass
class PlanProjection:
  active: bool = False
  pending: bool = False

  def to_dict(self) -> dict[str, Any]:
    return {"active": self.active, "pending": self.pending}

  @staticmethod
  def from_dict(data: dict[str, Any]) -> PlanProjection:
    return PlanProjection(
      active=bool(data.get("active", False)),
      pending=bool(data.get("pending", False)),
    )


@dataclass
class PlanModeState:
  active: bool = False
  wanted: bool | None = None
  running_command_id: str | None = None
  running_wanted: bool | None = None
  active_at_last_header: bool | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "active": self.active,
      "wanted": self.wanted,
      "runningCommandId": self.running_command_id,
      "runningWanted": self.running_wanted,
      "activeAtLastHeader": self.active_at_last_header,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> PlanModeState:
    return PlanModeState(
      active=bool(data.get("active", False)),
      wanted=data.get("wanted") if data.get("wanted") is not None else None,
      running_command_id=data.get("runningCommandId") or data.get("running_command_id") or None,
      running_wanted=data.get("runningWanted") if data.get("runningWanted") is not None else None,
      active_at_last_header=data.get("activeAtLastHeader") if data.get("activeAtLastHeader") is not None else None,
    )
