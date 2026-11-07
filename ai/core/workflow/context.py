"""Variable scope and run context for the WorkflowEngine.

Provides lightweight ``${...}`` expression resolution over a nested scope
chain. Supported references:
  - ``inputs.x``
  - ``steps.step_id.output`` / ``steps.step_id.output.field``
  - ``globals.y``
  - ``item`` (loop iteration variable, set in child scope)
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from ai.core.workflow.errors import WorkflowError, WorkflowErrorCode


_EXPR_RE = re.compile(r"\$\{([^}]+)\}")


def _is_truthy(value: Any) -> bool:
  """Pythonic truthy with special handling for strings."""
  if isinstance(value, str):
    return value.lower() not in ("", "false", "0", "null", "none")
  if isinstance(value, (list, dict)):
    return len(value) > 0
  return bool(value)


def _compare_op(left: Any, op: str, right: Any) -> bool:
  """Evaluate a binary comparison after light type coercion."""
  # Numeric coercion
  if isinstance(left, (int, float)) and isinstance(right, (int, float)):
    if op == "==":
      return left == right
    if op == "!=":
      return left != right
    if op == "<":
      return left < right
    if op == ">":
      return left > right
    if op == "<=":
      return left <= right
    if op == ">=":
      return left >= right
    return False

  # Boolean / string comparison
  def _coerce_bool(value: Any) -> Any:
    if isinstance(value, str):
      lowered = value.lower()
      if lowered in ("true", "1", "yes"):
        return True
      if lowered in ("false", "0", "no", "null", "none"):
        return False
    return value

  left = _coerce_bool(left)
  right = _coerce_bool(right)
  if isinstance(left, bool) or isinstance(right, bool):
    if op == "==":
      return bool(left) == bool(right)
    if op == "!=":
      return bool(left) != bool(right)
    return False
  if op == "==":
    return str(left) == str(right)
  if op == "!=":
    return str(left) != str(right)
  return False


@dataclass
class Scope:
  """A nested variable scope."""

  variables: dict[str, Any] = field(default_factory=dict)
  parent: "Scope | None" = None

  def get(self, name: str, default: Any = None) -> Any:
    if name in self.variables:
      return self.variables[name]
    if self.parent is not None:
      return self.parent.get(name, default)
    return default

  def set(self, name: str, value: Any) -> None:
    self.variables[name] = value

  def resolve(self, expression: str) -> Any:
    """Resolve a simple dotted expression against this scope."""
    if not expression:
      return None
    parts = [p.strip() for p in str(expression).split(".") if p.strip()]
    if not parts:
      return None
    root = parts[0]
    value = self.get(root)
    for part in parts[1:]:
      if value is None:
        return None
      if isinstance(value, dict):
        value = value.get(part)
      elif isinstance(value, list):
        try:
          idx = int(part)
          value = value[idx] if 0 <= idx < len(value) else None
        except ValueError:
          return None
      elif hasattr(value, part):
        value = getattr(value, part)
      else:
        return None
    return value


@dataclass
class RunContext:
  """Mutable runtime context for one workflow run."""

  run_id: str
  inputs: dict[str, Any]
  scope: Scope = field(default_factory=Scope)
  outputs: dict[str, Any] = field(default_factory=dict)
  cancelled: bool = False
  disposed: bool = False
  cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
  phases: list[dict[str, Any]] = field(default_factory=list)
  logs: list[str] = field(default_factory=list)

  def __post_init__(self) -> None:
    if "inputs" not in self.scope.variables:
      self.scope.set("inputs", dict(self.inputs))
    if "globals" not in self.scope.variables:
      self.scope.set("globals", {})
    if "steps" not in self.scope.variables:
      self.scope.set("steps", {})

  @staticmethod
  def create(run_id: str, inputs: dict[str, Any] | None = None) -> "RunContext":
    return RunContext(run_id=run_id, inputs=dict(inputs or {}))

  def resolve(self, expression: str) -> Any:
    """Resolve ``expression`` after interpolating ``${...}`` references."""
    if not isinstance(expression, str):
      return expression

    def _replace(match: re.Match[str]) -> str:
      inner = match.group(1).strip()
      value = self.scope.resolve(inner)
      if value is None:
        return ""
      if isinstance(value, (dict, list)):
        try:
          return json.dumps(value, ensure_ascii=False)
        except Exception:
          return str(value)
      return str(value)

    resolved = _EXPR_RE.sub(_replace, expression)
    # If the whole expression was a single interpolated reference and the raw
    # value was structured, return the structured value instead of a JSON
    # string. This lets subsequent steps reference ``steps.x.output.field``.
    single = _EXPR_RE.fullmatch(expression)
    if single:
      structured = self.scope.resolve(single.group(1).strip())
      if structured is not None:
        return structured
    return resolved

  def resolve_value(self, value: Any) -> Any:
    """Recursively resolve string values in primitives/containers."""
    if isinstance(value, str):
      single = _EXPR_RE.fullmatch(value)
      if single:
        structured = self.scope.resolve(single.group(1).strip())
        if structured is not None:
          return structured
      resolved = self.resolve(value)
      # Try to keep structured literals that were JSON-encoded during interpolation.
      if isinstance(resolved, str) and resolved.startswith("[") and resolved.endswith("]"):
        try:
          parsed = json.loads(resolved)
          if isinstance(parsed, list):
            return parsed
        except Exception:
          pass
      if isinstance(resolved, str) and resolved.startswith("{") and resolved.endswith("}"):
        try:
          parsed = json.loads(resolved)
          if isinstance(parsed, dict):
            return parsed
        except Exception:
          pass
      return resolved
    if isinstance(value, dict):
      return {k: self.resolve_value(v) for k, v in value.items()}
    if isinstance(value, list):
      return [self.resolve_value(v) for v in value]
    return value

  def set(self, name: str, value: Any) -> None:
    self.scope.set(name, value)

  def get(self, name: str, default: Any = None) -> Any:
    return self.scope.get(name, default)

  def bind_step_output(self, step_id: str, value: Any) -> None:
    """Bind a step result under ``steps.<step_id>.output``."""
    steps = self.scope.get("steps") or {}
    if not isinstance(steps, dict):
      steps = {}
    steps.setdefault(step_id, {})["output"] = value
    self.scope.set("steps", steps)

  def evaluate_condition(self, condition: str) -> bool:
    """Evaluate a condition expression.

    Supports simple comparisons like:
      ${steps.check.ok} == true
      ${inputs.score} > 5
      ${steps.list.result} != []
    """
    if not condition:
      return True

    # Normalize == true/false shorthand
    resolved = self.resolve(condition)
    if not isinstance(resolved, str):
      return _is_truthy(resolved)

    # Comparison parsing: left OP right
    for op in ("==", "!=", "<=", ">=", "<", ">"):
      if op in resolved:
        left, _, right = resolved.partition(op)
        left = left.strip()
        right = right.strip()
        if not left and not right:
          continue
        # If left looks like an unresolved ${...}, treat as false.
        if left.startswith("${") and left.endswith("}"):
          return False
        return _compare_op(self.resolve_value(left), op, self.resolve_value(right))
    return _is_truthy(resolved)

  def check_cancelled(self) -> None:
    """Raise WorkflowError if the run has been cancelled or disposed."""
    if self.disposed:
      raise WorkflowError("workflow run disposed", WorkflowErrorCode.DISPOSED)
    if self.cancelled or self.cancel_event.is_set():
      raise WorkflowError("workflow run cancelled", WorkflowErrorCode.CANCELLED)

  def enter_phase(self, phase_id: str, step_id: str, kind: str) -> dict[str, Any]:
    phase = {"id": phase_id, "step_id": step_id, "kind": kind, "ok": True}
    self.phases.append(phase)
    return phase

  def log(self, message: str) -> None:
    self.logs.append(message)


import json  # noqa: E402  # used in resolve for structured interpolation
