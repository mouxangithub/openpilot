"""Structured error codes for the P2 workflow runtime."""

from __future__ import annotations

from enum import Enum
from typing import Any


class WorkflowErrorCode(str, Enum):
  """Fail-loud error taxonomy used by WorkflowEngine and its callers.

  Values are prefixed with ``WF_`` to disambiguate from skill/MCP errors.
  """

  INVALID_DEFINITION = "WF_INVALID_DEFINITION"
  TOOL_NOT_FOUND = "WF_TOOL_NOT_FOUND"
  TOOL_FAILED = "WF_TOOL_FAILED"
  AGENT_FAILED = "WF_AGENT_FAILED"
  TIMEOUT = "WF_TIMEOUT"
  CANCELLED = "WF_CANCELLED"
  DISPOSED = "WF_DISPOSED"


def workflow_error_code_from_name(name: str) -> WorkflowErrorCode:
  """Resolve a string to a ``WorkflowErrorCode``.

  Accepts either the enum name (``INVALID_DEFINITION``) or the value
  (``WF_INVALID_DEFINITION``).  Unknown strings map to ``INVALID_DEFINITION``.
  """
  normalized = str(name or "").strip()
  if not normalized:
    return WorkflowErrorCode.INVALID_DEFINITION
  try:
    return WorkflowErrorCode(normalized)
  except ValueError:
    pass
  for code in WorkflowErrorCode:
    if code.name == normalized:
      return code
  return WorkflowErrorCode.INVALID_DEFINITION


class WorkflowError(Exception):
  """Structured exception carrying a ``WorkflowErrorCode``.

  ``fatal`` distinguishes errors that must abort the whole run (default True)
  from errors a combinator may swallow/map to a value (e.g. an inner parallel
  branch that is allowed to fail with ``None``). Mirrors the dsh workflow
  ``WorkflowError.fatal`` semantics (D-P0.1).
  """

  def __init__(
    self,
    message: str,
    code: WorkflowErrorCode = WorkflowErrorCode.INVALID_DEFINITION,
    details: dict[str, Any] | None = None,
    *,
    fatal: bool = True,
  ) -> None:
    super().__init__(message)
    self.message = message
    self.code = code
    self.details = dict(details or {})
    self.fatal = bool(fatal)

  def to_dict(self) -> dict[str, Any]:
    return {
      "ok": False,
      "error": self.message,
      "code": self.code.value,
      "fatal": self.fatal,
      "details": self.details,
    }
