"""Goal domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GoalId = str
GoalPhase = Literal["active", "paused", "blocked", "complete"]
GoalActivation = Literal["armed", "disarmed"]
GoalOperation = Literal["create", "edit", "pause", "resume", "complete", "block", "clear"]
GoalErrorCode = Literal[
  "GOAL_NOT_FOUND",
  "GOAL_ALREADY_EXISTS",
  "GOAL_STALE_REVISION",
  "GOAL_INVALID_OBJECTIVE",
  "GOAL_INVALID_MAX_ROUNDS",
  "GOAL_INVALID_BLOCK_REASON",
  "GOAL_INVALID_EDIT",
  "GOAL_INVALID_TRANSITION",
]


class GoalError(Exception):
  def __init__(self, message: str, code: GoalErrorCode) -> None:
    super().__init__(message)
    self.message = message
    self.code = code

  def to_dict(self) -> dict[str, Any]:
    return {"ok": False, "error": self.message, "code": self.code}


@dataclass(frozen=True)
class GoalRef:
  id: GoalId
  revision: int

  def to_dict(self) -> dict[str, Any]:
    return {"id": self.id, "revision": self.revision}

  @staticmethod
  def from_dict(data: dict[str, Any]) -> GoalRef:
    return GoalRef(id=str(data.get("id", "")), revision=int(data.get("revision", 0)))


@dataclass(frozen=True)
class GoalBlockReason:
  code: str
  message: str

  def to_dict(self) -> dict[str, Any]:
    return {"code": self.code, "message": self.message}

  @staticmethod
  def from_dict(data: dict[str, Any]) -> GoalBlockReason:
    return GoalBlockReason(
      code=str(data.get("code", "")),
      message=str(data.get("message", "")),
    )


@dataclass(frozen=True)
class GoalSnapshot:
  id: GoalId
  revision: int
  objective: str
  phase: GoalPhase
  max_goal_rounds: int
  blocked_reason: GoalBlockReason | None = None

  @property
  def ref(self) -> GoalRef:
    return GoalRef(id=self.id, revision=self.revision)

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {
      "id": self.id,
      "revision": self.revision,
      "objective": self.objective,
      "phase": self.phase,
      "maxGoalRounds": self.max_goal_rounds,
    }
    if self.blocked_reason is not None:
      out["blockedReason"] = self.blocked_reason.to_dict()
    return out

  @staticmethod
  def from_dict(data: dict[str, Any]) -> GoalSnapshot:
    blocked = data.get("blockedReason")
    return GoalSnapshot(
      id=str(data.get("id", "")),
      revision=int(data.get("revision", data.get("revision", 0))),
      objective=str(data.get("objective", "")),
      phase=str(data.get("phase", "active")),
      max_goal_rounds=int(data.get("maxGoalRounds", data.get("max_goal_rounds", 256))),
      blocked_reason=GoalBlockReason.from_dict(blocked) if blocked else None,
    )


@dataclass
class GoalProjection:
  goal: GoalSnapshot
  rounds_started: int
  created_at: int
  updated_at: int

  def to_dict(self) -> dict[str, Any]:
    return {
      "goal": self.goal.to_dict(),
      "roundsStarted": self.rounds_started,
      "createdAt": self.created_at,
      "updatedAt": self.updated_at,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> GoalProjection:
    return GoalProjection(
      goal=GoalSnapshot.from_dict(data.get("goal") or {}),
      rounds_started=int(data.get("roundsStarted", data.get("rounds_started", 0))),
      created_at=int(data.get("createdAt", data.get("created_at", 0))),
      updated_at=int(data.get("updatedAt", data.get("updated_at", 0))),
    )


@dataclass
class GoalView:
  id: GoalId
  revision: int
  objective: str
  phase: GoalPhase
  max_goal_rounds: int
  rounds_started: int
  created_at: int
  updated_at: int
  activation: GoalActivation = "disarmed"
  blocked_reason: GoalBlockReason | None = None

  @property
  def ref(self) -> GoalRef:
    return GoalRef(id=self.id, revision=self.revision)

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {
      "id": self.id,
      "revision": self.revision,
      "objective": self.objective,
      "phase": self.phase,
      "maxGoalRounds": self.max_goal_rounds,
      "roundsStarted": self.rounds_started,
      "createdAt": self.created_at,
      "updatedAt": self.updated_at,
      "activation": self.activation,
    }
    if self.blocked_reason is not None:
      out["blockedReason"] = self.blocked_reason.to_dict()
    return out

  @staticmethod
  def from_dict(data: dict[str, Any]) -> GoalView:
    blocked = data.get("blockedReason") or data.get("blocked_reason")
    return GoalView(
      id=str(data.get("id", "")),
      revision=int(data.get("revision", 0)),
      objective=str(data.get("objective", "")),
      phase=str(data.get("phase", "active")),
      max_goal_rounds=int(data.get("maxGoalRounds", data.get("max_goal_rounds", 256))),
      rounds_started=int(data.get("roundsStarted", data.get("rounds_started", 0))),
      created_at=int(data.get("createdAt", data.get("created_at", 0))),
      updated_at=int(data.get("updatedAt", data.get("updated_at", 0))),
      activation=str(data.get("activation", "disarmed")),
      blocked_reason=GoalBlockReason.from_dict(blocked) if blocked else None,
    )


@dataclass
class CreateGoalRequest:
  objective: str
  max_goal_rounds: int | None = None


@dataclass
class EditGoalRequest:
  objective: str | None = None
  max_goal_rounds: int | None = None


@dataclass
class GoalProjectionState:
  current: GoalProjection | None = None
  seen_goal_ids: list[GoalId] = field(default_factory=list)
  failure: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "current": self.current.to_dict() if self.current else None,
      "seenGoalIds": list(self.seen_goal_ids),
      "failure": self.failure,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> GoalProjectionState:
    current = data.get("current")
    return GoalProjectionState(
      current=GoalProjection.from_dict(current) if current else None,
      seen_goal_ids=list(data.get("seenGoalIds", data.get("seen_goal_ids", []))),
      failure=data.get("failure") if data.get("failure") else None,
    )
