"""Declarative workflow definition parser and validator.

Workflow definitions are plain dicts (YAML/JSON/Python-lite) describing a
sequence of typed steps. ``WorkflowDefinition`` exposes a tiny DSL surface
that the engine interprets without external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ai.core.workflow.errors import WorkflowError, WorkflowErrorCode


class StepKind(str, Enum):
  """Supported workflow step kinds."""

  TOOL = "tool"
  AGENT = "agent"
  PARALLEL = "parallel"
  CONDITION = "condition"
  LOOP = "loop"
  GRAPH = "graph"
  LOG = "log"


@dataclass
class RetryPolicy:
  """Retry policy for a single step."""

  max_attempts: int = 1
  backoff: float = 0.0
  on_error: str = "fail"  # fail | continue

  def to_dict(self) -> dict[str, Any]:
    return {
      "max_attempts": self.max_attempts,
      "backoff": self.backoff,
      "on_error": self.on_error,
    }

  @staticmethod
  def from_dict(data: dict[str, Any] | None) -> "RetryPolicy":
    if not isinstance(data, dict):
      return RetryPolicy()
    max_attempts = data.get("max_attempts") if data.get("max_attempts") is not None else data.get("maxAttempts")
    backoff = data.get("backoff") if data.get("backoff") is not None else data.get("backoffSeconds")
    on_error = data.get("on_error") if data.get("on_error") is not None else data.get("onError")
    return RetryPolicy(
      max_attempts=int(max_attempts) if max_attempts is not None else 1,
      backoff=float(backoff) if backoff is not None else 0.0,
      on_error=str(on_error) if on_error is not None else "fail",
    )


@dataclass
class Step:
  """A single workflow step.

  Fields are intentionally permissive: only ``id`` and ``kind`` are required.
  The engine selects behaviour based on ``kind`` and whichever optional fields
  are present.
  """

  id: str
  kind: StepKind
  inputs: dict[str, Any] = field(default_factory=dict)
  condition: str = ""
  for_each: str = ""  # loop iterable expression, e.g. "item in ${steps.list.result}"
  parallel: list["Step"] = field(default_factory=list)
  branches: list["Step"] = field(default_factory=list)  # condition branches
  agent: dict[str, Any] = field(default_factory=dict)
  graph_id: str = ""  # kind=graph target workflow id
  output_binding: str = ""  # variable name to bind step result to
  retry: RetryPolicy = field(default_factory=RetryPolicy)
  description: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "kind": self.kind.value,
      "inputs": dict(self.inputs),
      "condition": self.condition,
      "for_each": self.for_each,
      "parallel": [s.to_dict() for s in self.parallel],
      "branches": [s.to_dict() for s in self.branches],
      "agent": dict(self.agent),
      "graph_id": self.graph_id,
      "output_binding": self.output_binding,
      "retry": self.retry.to_dict(),
      "description": self.description,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> "Step":
    if not isinstance(data, dict):
      raise WorkflowError("step must be an object", WorkflowErrorCode.INVALID_DEFINITION)
    step_id = str(data.get("id") or "").strip()
    if not step_id:
      raise WorkflowError("step missing required 'id'", WorkflowErrorCode.INVALID_DEFINITION)
    raw_kind = data.get("kind") or data.get("type")
    if not raw_kind:
      raise WorkflowError(f"step '{step_id}' missing 'kind'", WorkflowErrorCode.INVALID_DEFINITION)
    try:
      kind = StepKind(str(raw_kind).lower())
    except ValueError as exc:
      raise WorkflowError(
        f"step '{step_id}' has unsupported kind '{raw_kind}'",
        WorkflowErrorCode.INVALID_DEFINITION,
      ) from exc

    def _steps(key: str) -> list["Step"]:
      items = data.get(key)
      if not isinstance(items, list):
        return []
      out: list[Step] = []
      for item in items:
        try:
          out.append(Step.from_dict(item))
        except WorkflowError:
          raise
        except Exception as exc:
          raise WorkflowError(
            f"step '{step_id}' has invalid nested step under '{key}': {exc}",
            WorkflowErrorCode.INVALID_DEFINITION,
          ) from exc
      return out

    return Step(
      id=step_id,
      kind=kind,
      inputs=dict(data.get("inputs") or {}),
      condition=str(data.get("condition") or data.get("if") or "").strip(),
      for_each=str(data.get("for_each") or data.get("forEach") or data.get("for") or "").strip(),
      parallel=_steps("parallel"),
      branches=_steps("branches") or _steps("then"),
      agent=dict(data.get("agent") or {}),
      graph_id=str(data.get("graph_id") or data.get("graphId") or "").strip(),
      output_binding=str(data.get("output_binding") or data.get("output") or "").strip(),
      retry=RetryPolicy.from_dict(data.get("retry")),
      description=str(data.get("description") or "").strip(),
    )


@dataclass
class WorkflowDefinition:
  """Parsed and validated workflow definition."""

  id: str
  name: str
  version: str
  inputs_schema: dict[str, Any]
  steps: list[Step]
  outputs: dict[str, Any]

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "name": self.name,
      "version": self.version,
      "inputs_schema": dict(self.inputs_schema),
      "steps": [s.to_dict() for s in self.steps],
      "outputs": dict(self.outputs),
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> "WorkflowDefinition":
    if not isinstance(data, dict):
      raise WorkflowError("workflow definition must be an object", WorkflowErrorCode.INVALID_DEFINITION)
    def_id = str(data.get("id") or data.get("definition_id") or "").strip()
    if not def_id:
      raise WorkflowError("workflow missing required 'id'", WorkflowErrorCode.INVALID_DEFINITION)
    steps_data = data.get("steps")
    if not isinstance(steps_data, list) or not steps_data:
      raise WorkflowError("workflow must contain a non-empty 'steps' list", WorkflowErrorCode.INVALID_DEFINITION)
    steps = []
    for item in steps_data:
      try:
        steps.append(Step.from_dict(item))
      except WorkflowError:
        raise
      except Exception as exc:
        raise WorkflowError(
          f"invalid step in workflow '{def_id}': {exc}",
          WorkflowErrorCode.INVALID_DEFINITION,
        ) from exc

    return WorkflowDefinition(
      id=def_id,
      name=str(data.get("name") or def_id),
      version=str(data.get("version") or "0.1.0"),
      inputs_schema=dict(data.get("inputs_schema") or data.get("inputsSchema") or {}),
      steps=steps,
      outputs=dict(data.get("outputs") or {}),
    )

  @staticmethod
  def from_yaml(path: str | Path) -> "WorkflowDefinition":
    p = Path(path)
    try:
      import yaml
      data = yaml.safe_load(p.read_text(encoding="utf-8"))
      if not isinstance(data, dict):
        raise WorkflowError("YAML root must be a mapping", WorkflowErrorCode.INVALID_DEFINITION)
      return WorkflowDefinition.from_dict(data)
    except WorkflowError:
      raise
    except Exception as exc:
      raise WorkflowError(
        f"failed to load workflow YAML from {p}: {exc}",
        WorkflowErrorCode.INVALID_DEFINITION,
      ) from exc

  def validate(self) -> list[str]:
    """Validate the definition and return a list of human-readable errors."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    def _validate_step(step: Step, path: str) -> None:
      if step.id in seen_ids:
        errors.append(f"duplicate step id '{step.id}' at {path}")
      seen_ids.add(step.id)

      if step.kind == StepKind.CONDITION and not step.condition:
        errors.append(f"condition step '{step.id}' missing 'condition'")
      if step.kind == StepKind.LOOP and not step.for_each:
        errors.append(f"loop step '{step.id}' missing 'for_each'")
      if step.kind == StepKind.PARALLEL and not step.parallel:
        errors.append(f"parallel step '{step.id}' missing 'parallel'")
      if step.kind == StepKind.GRAPH and not step.graph_id:
        errors.append(f"graph step '{step.id}' missing 'graph_id'")
      if step.kind == StepKind.AGENT and not step.agent:
        errors.append(f"agent step '{step.id}' missing 'agent'")

      for idx, child in enumerate(step.parallel):
        _validate_step(child, f"{path}.parallel[{idx}]")
      for idx, child in enumerate(step.branches):
        _validate_step(child, f"{path}.branches[{idx}]")

    for idx, step in enumerate(self.steps):
      _validate_step(step, f"steps[{idx}]")

    return errors

  def validate_or_raise(self) -> None:
    errors = self.validate()
    if errors:
      raise WorkflowError(
        "; ".join(errors),
        WorkflowErrorCode.INVALID_DEFINITION,
      )
