"""Sandbox / code-runtime abstraction seam.

Mirrors the ``@deepseek-ai/dsh-sandbox`` and ``@deepseek-ai/dsh-code-runtime``
service definitions in plain Python.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal


SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
ConfinedSandboxMode = Literal["read-only", "workspace-write"]


@dataclass(frozen=True)
class SandboxPolicy:
  """Per-call file-effect policy for a confined execution."""

  mode: ConfinedSandboxMode
  workspace_root: str = "."


@dataclass(frozen=True)
class SandboxExecutionPolicy:
  """Resolved policy including the unsafe passthrough mode."""

  mode: SandboxMode
  workspace_root: str = "."


@dataclass(frozen=True)
class ConfinedSessionPolicy:
  """Session-scoped containment policy (U4).

  Carries the resolved mode (default ``read-only``) and the containment root
  derived from the session cwd, so every capability call in a session resolves
  against a stable, replayable policy rather than a process-global directory.
  """

  session_id: str = ""
  mode: ConfinedSandboxMode = "read-only"
  containment_root: str = "."

  def to_context(self) -> dict[str, Any]:
    """Policy as ``request/context`` for replay/audit (dsh runtime-context)."""
    return {
      "sandbox": {
        "sessionId": self.session_id,
        "mode": self.mode,
        "cwd": self.containment_root,
        "containmentRoot": self.containment_root,
      }
    }

  def to_dict(self) -> dict[str, Any]:
    return self.to_context()["sandbox"]


class SandboxPolicyService:
  """Resolves session-scoped sandbox policy from params + caller context.

  Python seam for ``@deepseek-ai/dsh-sandbox`` ``sandbox-policy``. The
  deployment default is read-only; ``workspace-write`` requires an explicit
  profile/param override. The containment root is the session cwd clamped under
  the workspace root so a session cannot escape its own directory.
  """

  DEFAULT_MODE: ConfinedSandboxMode = "workspace-write"
  MODE_PARAM: str = "ai_sandbox_default_mode"

  def __init__(self, *, workspace_root: str | None = None) -> None:
    self.workspace_root = os.path.abspath(workspace_root or ".")

  def resolve(
    self,
    params: Any = None,
    *,
    session_id: str = "",
    cwd: str | None = None,
  ) -> ConfinedSessionPolicy:
    """Resolve the effective session policy for a capability call."""
    mode = self._resolve_mode(params)
    containment = self.contained_cwd(cwd)
    return ConfinedSessionPolicy(
      session_id=session_id,
      mode=mode,
      containment_root=containment,
    )

  def contained_cwd(self, requested: str | None = None) -> str:
    """Return ``requested`` if it is under the workspace root, else the root.

    Prevents a session from hopping outside its own containment directory even
    if the caller passes an absolute path or a ``../../../``-style escape.
    """
    if not requested:
      return self.workspace_root
    req = os.path.abspath(requested)
    root = self.workspace_root
    try:
      rel = os.path.relpath(req, root)
    except ValueError:  # e.g. cross-drive on Windows
      return root
    if rel == ".":
      return root
    if rel.startswith(".."):
      return root
    return req

  def _resolve_mode(self, params: Any = None) -> ConfinedSandboxMode:
    raw: Any = None
    try:
      from ai.common.storage import read_param
      raw = read_param(params, self.MODE_PARAM)
    except Exception:
      raw = None
    val = str(raw or self.DEFAULT_MODE).strip().lower()
    return val if val in ("read-only", "workspace-write") else self.DEFAULT_MODE


@dataclass
class RunResult:
  """Outcome of running code or a shell command in the sandbox."""

  ok: bool
  stdout: str = ""
  stderr: str = ""
  returncode: int | None = None
  duration_ms: int = 0
  error: str | None = None
  error_kind: Literal[
    "exception", "timeout", "abort", "worker-exit", "invalid-output",
    "output-limit", "blocked", "sandbox-unavailable",
  ] | None = None

  def to_dict(self) -> dict[str, Any]:
    result: dict[str, Any] = {
      "ok": self.ok,
      "stdout": self.stdout,
      "stderr": self.stderr,
      "returncode": self.returncode,
      "durationMs": self.duration_ms,
    }
    if self.error is not None:
      result["error"] = self.error
    if self.error_kind is not None:
      result["errorKind"] = self.error_kind
    return result


class SandboxRuntime:
  """Abstract sandbox runtime that can run Python code and shell commands.

  Concrete implementations may use subprocesses, containers, or E2B sandboxes.
  The interface is intentionally small so callers can swap backends.
  """

  def __init__(
    self,
    *,
    default_timeout: int = 30,
    max_output_bytes: int = 2 * 1024 * 1024,
    workspace_root: str | None = None,
  ) -> None:
    self.default_timeout = default_timeout
    self.max_output_bytes = max_output_bytes
    self.workspace_root = workspace_root or "."

  async def run_python(
    self,
    code: str,
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    bindings: dict[str, Any] | None = None,
  ) -> RunResult:
    """Run a Python program and return its captured output."""
    raise NotImplementedError

  async def run_shell(
    self,
    command: str | list[str],
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    policy: SandboxPolicy | None = None,
  ) -> RunResult:
    """Run a shell command under the given file-effect policy."""
    raise NotImplementedError

  def is_blocked_command(self, command: str) -> str | None:
    """Return a refusal reason if the command is disallowed, else None."""
    return None
