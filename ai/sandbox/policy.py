"""Session-scoped sandbox policy resolution.

This module lives alongside ``ai.sandbox.runtime`` but does not modify it.
It provides ``SessionSandboxPolicyService``, which resolves a per-session,
replayable ``ConfinedSessionPolicy`` that can be snapshotted into a
``request/context`` event.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal


type ConfinedSandboxMode = Literal["read-only", "workspace-write"]


@dataclass(frozen=True)
class ConfinedSessionPolicy:
  """Resolved sandbox policy for a single session.

  Attributes:
    session_id: The session identifier.
    mode: Contained sandbox mode.
    cwd: Original working directory requested by the caller.
    containment_root: Effective containment root clamped under workspace.
  """

  session_id: str = ""
  mode: ConfinedSandboxMode = "read-only"
  cwd: str = "."
  containment_root: str = "."

  def to_context(self) -> dict[str, Any]:
    """Return a ``request/context``-compatible snapshot."""
    return {
      "sandbox": {
        "sessionId": self.session_id,
        "mode": self.mode,
        "cwd": self.cwd,
        "containmentRoot": self.containment_root,
      }
    }

  def to_dict(self) -> dict[str, Any]:
    return {
      "sessionId": self.session_id,
      "mode": self.mode,
      "cwd": self.cwd,
      "containmentRoot": self.containment_root,
    }


class SessionSandboxPolicyService:
  """Resolve confined sandbox policy for a session.

  Supports:
    - A deployment-wide default mode parameter.
    - A per-session override delivered via ``session_state`` (typically from a
      ``sandbox/mode`` projection).
    - Path containment so a session cannot escape the workspace root.
  """

  DEFAULT_MODE: ConfinedSandboxMode = "read-only"
  MODE_PARAM: str = "ai_sandbox_default_mode"

  def __init__(self, *, workspace_root: str | None = None) -> None:
    self.workspace_root = os.path.abspath(workspace_root or ".")

  def resolve(
    self,
    params: Any = None,
    *,
    session_id: str = "",
    cwd: str | None = None,
    session_state: dict[str, Any] | None = None,
  ) -> ConfinedSessionPolicy:
    """Resolve the effective confined policy for a session.

    Args:
      params: Parameter bag (dict-like or params object) to read default mode.
      session_id: Session identifier.
      cwd: Requested working directory.
      session_state: Optional derived session state (e.g. projection fold).

    Returns:
      A ``ConfinedSessionPolicy`` carrying the resolved mode and containment.
    """
    mode = self._resolve_mode(params, session_state)
    requested_cwd = cwd or "."
    containment = self.contained_cwd(requested_cwd)
    return ConfinedSessionPolicy(
      session_id=session_id,
      mode=mode,
      cwd=os.path.abspath(requested_cwd),
      containment_root=containment,
    )

  def contained_cwd(self, requested: str | None = None) -> str:
    """Return ``requested`` if under workspace root, else the root.

    Prevents directory-escape attacks (absolute paths or ``../`` chains).
    """
    if not requested:
      return self.workspace_root
    req = os.path.abspath(requested)
    root = self.workspace_root
    try:
      rel = os.path.relpath(req, root)
    except ValueError:
      return root
    if rel == ".":
      return root
    if rel.startswith(".."):
      return root
    return req

  def _resolve_mode(
    self,
    params: Any = None,
    session_state: dict[str, Any] | None = None,
  ) -> ConfinedSandboxMode:
    """Pick mode from session override, params, then default."""
    if session_state is not None:
      override = session_state.get("mode")
      if override not in ("read-only", "workspace-write") and isinstance(session_state.get("sandbox"), dict):
        override = session_state["sandbox"].get("mode")
      if override in ("read-only", "workspace-write"):
        return override
    raw = _read_param(params, self.MODE_PARAM)
    val = str(raw or self.DEFAULT_MODE).strip().lower()
    if val in ("read-only", "workspace-write"):
      return val
    return self.DEFAULT_MODE


def _read_param(params: Any, key: str) -> Any:
  """Read a parameter from a dict-like or attribute-based bag."""
  if params is None:
    return None
  if isinstance(params, dict):
    return params.get(key)
  return getattr(params, key, None)
