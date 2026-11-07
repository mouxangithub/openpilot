"""Structured tool/API error contract.

Aligns with deepseek-harness' canonical tool-output + error-taxonomy
requirement: every failure carries a stable machine-readable ``code`` plus a
human-readable ``error`` string, an optional ``retryable`` flag and optional
``details``. The ``error`` key stays a plain string so existing callers
(frontend ``formatApiError``, older handlers, tests) keep working unchanged.
"""

from __future__ import annotations

from typing import Any

# Common stable error codes (subset of dsh taxonomy).
ERR_UNKNOWN_TOOL = "UNKNOWN_TOOL"
ERR_TOOL_TIMEOUT = "TOOL_TIMEOUT"
ERR_TOOL_ERROR = "TOOL_ERROR"
ERR_INVALID_INPUT = "INVALID_INPUT"
ERR_BLOCKED = "BLOCKED"
ERR_NOT_FOUND = "NOT_FOUND"
ERR_STALE_REVISION = "STALE_REVISION"
ERR_CANCELLED = "CANCELLED"
ERR_ABORTED = "ABORTED"
ERR_NETWORK = "NETWORK_ERROR"
ERR_DEPENDENCY = "DEPENDENCY_ERROR"

# G12 config / G6 scheduler / G7 subagent / G8 profile error codes.
ERR_CONFIG_INVALID = "CONFIG_INVALID"
ERR_CONFIG_STALE = "CONFIG_STALE"
ERR_SCHEDULE_INVALID = "SCHEDULE_INVALID"
ERR_SUBAGENT_CAPABILITY = "SUBAGENT_CAPABILITY"
ERR_PROFILE_CONFLICT = "PROFILE_CONFLICT"
ERR_STARTUP_DIAG = "STARTUP_DIAG"
ERR_STATIONARY_REQUIRED = "STATIONARY_REQUIRED"
ERR_DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


def tool_error(
  message: str,
  *,
  code: str = ERR_TOOL_ERROR,
  retryable: bool = False,
  details: Any = None,
) -> dict[str, Any]:
  """Return a structured error dict.

  Always includes ``ok=False`` and a plain-string ``error``; adds
  ``error_code`` / ``retryable`` / ``details`` when non-default so the payload
  stays small but remains machine-consumable.
  """
  out: dict[str, Any] = {"ok": False, "error": message}
  if code != ERR_TOOL_ERROR:
    out["error_code"] = code
  if retryable:
    out["retryable"] = True
  if details is not None:
    out["details"] = details
  return out


def ok_result(**fields: Any) -> dict[str, Any]:
  """Return a success dict seeded with ``ok=True`` plus extra fields."""
  return {"ok": True, **fields}
