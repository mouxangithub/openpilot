"""Run shell commands safely with timeouts, output capture, and command blocking."""

from __future__ import annotations

import asyncio
import re
import shlex
from typing import Any

from ai.sandbox.runtime import (
  ConfinedSessionPolicy,
  RunResult,
  SandboxPolicy,
  SandboxRuntime,
)


# Commands that are never allowed, even under "danger-full-access" policy.
DEFAULT_BLOCKED_COMMANDS: list[str] = [
  "rm -rf /",
  "rm -rf /*",
  ":(){ :|:& };:",
  "mkfs",
  "dd if=/dev/zero",
  "> /dev/sda",
  "format ",
  "del /f /s /q \\",
  "rd /s /q \\",
]

# Patterns that suggest vehicle-control or destructive behavior.
BLOCKED_PATTERNS: list[re.Pattern[str]] = [
  re.compile(r"\bcar\.(send|control|apply)\b", re.IGNORECASE),
  re.compile(r"\b(steer|steering).{0,40}\b(angle|torque|cmd|command)\b", re.IGNORECASE),
  re.compile(r"\bthrottle\b.{0,20}\b(cmd|command|set)\b", re.IGNORECASE),
  re.compile(r"\bbrake\b.{0,20}\b(cmd|command|press)\b", re.IGNORECASE),
  re.compile(r"\bpanda\.(set|control|send)\b", re.IGNORECASE),
  re.compile(r"\bcontrolsd\b", re.IGNORECASE),
  re.compile(r"\bactuator\b", re.IGNORECASE),
  re.compile(r"\bsendcan\b|\bcan\.send\b", re.IGNORECASE),
]


class ShellRunner(SandboxRuntime):
  """Shell command runner with explicit blocking and output limits.

  This runner does NOT implement kernel-level sandboxing. It is suitable for
  whitelisted diagnostics and development helpers. Combine it with
  ``SandboxPolicy``-aware backends (container, E2B, etc.) for real isolation.
  """

  def __init__(
    self,
    *,
    default_timeout: int = 60,
    max_output_bytes: int = 2 * 1024 * 1024,
    blocked_commands: list[str] | None = None,
    workspace_root: str | None = None,
    fully_open: bool = False,
  ) -> None:
    super().__init__(
      default_timeout=default_timeout,
      max_output_bytes=max_output_bytes,
      workspace_root=workspace_root,
    )
    self.blocked_commands = blocked_commands or DEFAULT_BLOCKED_COMMANDS
    self.blocked_patterns = BLOCKED_PATTERNS
    # Fully-open mode: danger/self-destructive and vehicle-control commands are
    # ALLOWED (no block) but still recorded to the audit trail so nothing is
    # silently hidden. User opted into unrestricted operation.
    self.fully_open = fully_open

  def is_blocked_command(self, command: str) -> str | None:
    if self.fully_open:
      return None
    lowered = command.lower()
    for blocked in self.blocked_commands:
      if blocked.lower() in lowered:
        return f"Blocked command pattern: {blocked!r}"
    for pattern in self.blocked_patterns:
      if pattern.search(command):
        return "Blocked command: matches vehicle-control or destructive pattern"
    return None

  def audit_dangerous_command(self, command: str) -> None:
    """Record a fully-open command that would normally be blocked.

    Pure bookkeeping: never blocks execution, only appends an audit entry.
    """
    if not self.fully_open:
      return
    lowered = command.lower()
    matched = ""
    for blocked in self.blocked_commands:
      if blocked.lower() in lowered:
        matched = f"destructive:{blocked!r}"
        break
    if not matched:
      for pattern in self.blocked_patterns:
        if pattern.search(command):
          matched = "vehicle-control pattern"
          break
    if not matched:
      return
    try:
      from ai.tools.domains.platform.audit_store import record_audit
      record_audit(action="fully_open_command", tool="shell", ok=True,
                   detail={"command": command, "matched": matched})
    except Exception:
      pass

  # State-changing shell prefixes that are rejected under read-only policy.
  _READONLY_MUTATION = re.compile(
    r"^\s*(?:(?:rm|mv|cp|mkdir|rmdir|touch|chmod|chown|ln|dd|tee|truncate|"
    r"install|del|rd|format|mklink|copy|move|set\s+[A-Za-z_])(?:\s|$)"
    r"|>|>>|:\s*>)",
    re.IGNORECASE,
  )

  def readonly_violation(self, command: str) -> str | None:
    """Return a refusal reason if ``command`` mutates under read-only policy."""
    if self._READONLY_MUTATION.search(command) or re.search(r"(?:^|\s)(?:>>|>)(?:\s|\S)", command):
      return "Read-only sandbox: command would mutate the filesystem"
    return None

  @staticmethod
  def _mode_of(policy: Any | None) -> str | None:
    return getattr(policy, "mode", None) if policy else None

  @staticmethod
  def _containment_of(policy: Any | None) -> str | None:
    if policy is None:
      return None
    return (
      getattr(policy, "containment_root", None)
      or getattr(policy, "workspace_root", None)
    )

  def _to_shell_string(self, command: str | list[str]) -> str:
    if isinstance(command, list):
      return " ".join(shlex.quote(str(arg)) for arg in command)
    return str(command)

  async def _drain_stream(
    self,
    stream: asyncio.StreamReader | None,
  ) -> tuple[str, bool]:
    if stream is None:
      return "", False
    chunks: list[bytes] = []
    total = 0
    while True:
      chunk = await stream.read(8192)
      if not chunk:
        break
      chunks.append(chunk)
      total += len(chunk)
      if total > self.max_output_bytes:
        break
    data = b"".join(chunks)
    truncated = len(data) > self.max_output_bytes
    if truncated:
      data = data[: self.max_output_bytes]
    return data.decode("utf-8", errors="replace"), truncated

  async def run_shell(
    self,
    command: str | list[str],
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    policy: SandboxPolicy | ConfinedSessionPolicy | None = None,
    cwd: str | None = None,
  ) -> RunResult:
    shell = self._to_shell_string(command)
    blocked = self.is_blocked_command(shell)
    if blocked:
      return RunResult(
        ok=False,
        stderr=blocked,
        error=blocked,
        error_kind="blocked",
      )
    # Fully-open: still record normally-blocked commands to the audit trail.
    self.audit_dangerous_command(shell)

    mode = self._mode_of(policy)
    if mode == "read-only":
      violation = self.readonly_violation(shell)
      if violation:
        return RunResult(
          ok=False,
          stderr=violation,
          error=violation,
          error_kind="blocked",
        )

    # Session-scoped containment: prefer the explicit per-call cwd, then the
    # policy containment root, falling back to the process-global workspace.
    proc_cwd = cwd or self._containment_of(policy) or self.workspace_root

    try:
      proc = await asyncio.create_subprocess_shell(
        shell,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=proc_cwd,
      )
      try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
          proc.communicate(),
          timeout=timeout or self.default_timeout,
        )
      except TimeoutError:
        proc.kill()
        await proc.wait()
        return RunResult(
          ok=False,
          error=f"Shell command timed out after {timeout or self.default_timeout}s",
          error_kind="timeout",
        )

      out_text = stdout_bytes.decode("utf-8", errors="replace")
      err_text = stderr_bytes.decode("utf-8", errors="replace")
      if len(out_text) > self.max_output_bytes:
        out_text = out_text[: self.max_output_bytes] + "\n... (truncated)"
      if len(err_text) > self.max_output_bytes:
        err_text = err_text[: self.max_output_bytes] + "\n... (truncated)"
      return RunResult(
        ok=proc.returncode == 0,
        stdout=out_text,
        stderr=err_text,
        returncode=proc.returncode,
      )
    except Exception as exc:
      return RunResult(ok=False, error=str(exc), error_kind="exception")

  async def run_python(
    self,
    code: str,
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    bindings: dict[str, Any] | None = None,
  ) -> RunResult:
    return RunResult(
      ok=False,
      error="ShellRunner does not run Python code; use PythonRunner.",
      error_kind="blocked",
    )
