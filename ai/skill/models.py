"""Skill domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

SkillId = str
SkillPolicy = Literal["auto", "confirm", "disabled"]
SkillScope = Literal["global", "session", "project"]


@dataclass(frozen=True)
class SkillInvocationPolicy:
  """Explicit caller policy (D-P1.3)."""

  model_invocable: bool = True
  user_invocable: bool = True

  def to_dict(self) -> dict[str, bool]:
    return {
      "modelInvocable": self.model_invocable,
      "userInvocable": self.user_invocable,
    }

  @staticmethod
  def from_value(value: Any) -> "SkillInvocationPolicy":
    if isinstance(value, SkillInvocationPolicy):
      return value
    if isinstance(value, dict):
      return SkillInvocationPolicy(
        model_invocable=bool(value.get("modelInvocable", value.get("model_invocable", True))),
        user_invocable=bool(value.get("userInvocable", value.get("user_invocable", True))),
      )
    return SkillInvocationPolicy() 


SkillInvocationStatus = Literal["pending", "allowed", "denied", "running", "success", "error"]
SkillErrorCode = Literal[
  "SKILL_NOT_FOUND",
  "SKILL_DISABLED",
  "SKILL_REQUIRES_CONFIRMATION",
  "SKILL_INVALID_ARGS",
  "SKILL_EXECUTION_ERROR",
]


class SkillError(Exception):
  def __init__(self, message: str, code: SkillErrorCode) -> None:
    super().__init__(message)
    self.message = message
    self.code = code

  def to_dict(self) -> dict[str, Any]:
    return {"ok": False, "error": self.message, "code": self.code}


@dataclass(frozen=True)
class SkillParameter:
  name: str
  type: str
  description: str
  required: bool = True

  def to_dict(self) -> dict[str, Any]:
    return {
      "name": self.name,
      "type": self.type,
      "description": self.description,
      "required": self.required,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> SkillParameter:
    return SkillParameter(
      name=str(data.get("name", "")),
      type=str(data.get("type", "string")),
      description=str(data.get("description", "")),
      required=bool(data.get("required", True)),
    )


@dataclass(frozen=True)
class SkillDependency:
  """Structured dependency declaration for a skill."""

  name: str
  version_constraint: str = ""
  optional: bool = False

  def to_dict(self) -> dict[str, Any]:
    return {
      "name": self.name,
      "version_constraint": self.version_constraint,
      "optional": self.optional,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> SkillDependency:
    return SkillDependency(
      name=str(data.get("name", "")),
      version_constraint=str(data.get("version_constraint", "")),
      optional=bool(data.get("optional", False)),
    )


@dataclass
class Skill:
  id: SkillId
  name: str
  description: str
  policy: SkillPolicy
  parameters: list[SkillParameter]
  handler: Callable[..., Any] | None = field(default=None, compare=False, repr=False)
  metadata: dict[str, Any] = field(default_factory=dict)
  # P2 lifecycle fields
  scope: SkillScope = "global"
  version: str = "0.0.0"
  capabilities: list[str] = field(default_factory=list)
  dependencies: list[SkillDependency] = field(default_factory=list)
  source: str = ""
  # D-P0.3 rank for scope merge priority; lower rank = higher priority.
  rank: int = 600
  # D-P1.3 explicit caller policy.
  invocation_policy: SkillInvocationPolicy = field(default_factory=SkillInvocationPolicy)

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "name": self.name,
      "description": self.description,
      "policy": self.policy,
      "parameters": [p.to_dict() for p in self.parameters],
      "metadata": dict(self.metadata),
      "scope": self.scope,
      "version": self.version,
      "capabilities": list(self.capabilities),
      "dependencies": [d.to_dict() for d in self.dependencies],
      "source": self.source,
      "rank": self.rank,
      "invocationPolicy": self.invocation_policy.to_dict(),
    }

  @staticmethod
  def from_dict(data: dict[str, Any], handler: Callable[..., Any] | None = None) -> Skill:
    raw_deps = data.get("dependencies") or []
    deps: list[SkillDependency] = []
    if isinstance(raw_deps, list):
      for dep in raw_deps:
        if isinstance(dep, dict):
          deps.append(SkillDependency.from_dict(dep))
        elif isinstance(dep, str):
          deps.append(SkillDependency(name=dep))
    return Skill(
      id=str(data.get("id", "")),
      name=str(data.get("name", "")),
      description=str(data.get("description", "")),
      policy=str(data.get("policy", "confirm")),
      parameters=[SkillParameter.from_dict(p) for p in data.get("parameters", [])],
      handler=handler,
      metadata=dict(data.get("metadata") or {}),
      scope=str(data.get("scope", "global")),
      version=str(data.get("version", "0.0.0")),
      capabilities=list(data.get("capabilities") or []),
      dependencies=deps,
      source=str(data.get("source", "")),
      rank=int(data.get("rank", data.get("metadata", {}).get("rank", 600))),
      invocation_policy=SkillInvocationPolicy.from_value(
        data.get("invocationPolicy", data.get("invocation_policy"))
      ),
    )

  @property
  def version_from_metadata(self) -> str:
    """Backward-compatible version lookup into metadata."""
    return str(self.metadata.get("version") or self.version or "0.0.0")


@dataclass
class SkillInvocation:
  skill_id: SkillId
  args: dict[str, Any]
  status: SkillInvocationStatus
  result: Any = None
  error: str | None = None
  request_id: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {
      "skillId": self.skill_id,
      "args": dict(self.args),
      "status": self.status,
      "result": self.result,
      "error": self.error,
      "requestId": self.request_id,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> SkillInvocation:
    return SkillInvocation(
      skill_id=str(data.get("skillId", data.get("skill_id", ""))),
      args=dict(data.get("args") or {}),
      status=str(data.get("status", "pending")),
      result=data.get("result"),
      error=data.get("error") if data.get("error") else None,
      request_id=str(data.get("requestId", data.get("request_id", ""))),
    )
