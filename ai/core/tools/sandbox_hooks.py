"""Shared sandbox runners and policy resolution for shell/python tools.

Holds process-level singletons for ``ShellRunner`` and ``PythonRunner`` so
``tools/agent_tools`` shell handlers and the ``run_python_code`` harness tool
execute through the same sandbox boundary with one policy point.
"""
from __future__ import annotations

from typing import Any

from ai.sandbox.runtime import ConfinedSessionPolicy, SandboxPolicyService
from ai.system.paths import workspace_path

_shell_runner: Any = None
_python_runner: Any = None
_policy_service: SandboxPolicyService | None = None


def sandbox_shell_enabled(params: Any = None) -> bool:
  try:
    from ai.common.storage import read_param_bool
    return read_param_bool(params, "ai_sandbox_shell", True)
  except Exception:
    return True


def shell_runner() -> Any:
  """Return the process-level ShellRunner (create on first use)."""
  global _shell_runner
  if _shell_runner is None:
    from ai.sandbox.shell_runner import ShellRunner
    _shell_runner = ShellRunner(
      workspace_root=str(workspace_path("", mkdir=True)),
      fully_open=True,
    )
  return _shell_runner


def python_runner() -> Any:
  """Return the process-level PythonRunner (create on first use)."""
  global _python_runner
  if _python_runner is None:
    from ai.sandbox.python_runner import PythonRunner
    _python_runner = PythonRunner(workspace_root=str(workspace_path("", mkdir=True)))
  return _python_runner


def sandbox_policy(
  params: Any = None,
  *,
  session_id: str = "",
  cwd: str | None = None,
) -> ConfinedSessionPolicy:
  """Resolve a replayable session-scoped policy (read-only by default)."""
  global _policy_service
  if _policy_service is None:
    _policy_service = SandboxPolicyService(workspace_root=str(workspace_path("", mkdir=True)))
  return _policy_service.resolve(params, session_id=session_id, cwd=cwd)


def sandbox_host_fallback_enabled(params: Any = None) -> bool:
  """Host fallback is opt-in for compatibility; sandbox errors stay contained."""
  try:
    from ai.common.storage import read_param_bool
    return read_param_bool(params, "ai_sandbox_host_fallback", False)
  except Exception:
    return False


def _with_context(result: Any, policy: ConfinedSessionPolicy) -> dict[str, Any]:
  payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
  payload.setdefault("sandbox", policy.to_dict())
  return payload


async def run_shell_via_sandbox(
  command: str,
  *,
  timeout: int = 60,
  params: Any = None,
  session_id: str = "",
  cwd: str | None = None,
) -> dict[str, Any]:
  """Run a command in the session containment root with structured context.

  Host execution is only enabled by the explicit ``ai_sandbox_host_fallback``
  compatibility parameter; normal sandbox failures return a structured error.
  """
  policy = sandbox_policy(params, session_id=session_id, cwd=cwd)
  try:
    runner = shell_runner()
    result = await runner.run_shell(
      command,
      timeout=timeout,
      policy=policy,
      cwd=policy.containment_root,
    )
    return _with_context(result, policy)
  except Exception as exc:
    from openpilot.common.swaglog import cloudlog
    cloudlog.error(
      f"aid: sandbox shell unavailable session={session_id!r} cwd={policy.containment_root!r}: {exc}"
    )
    if sandbox_host_fallback_enabled(params):
      from ai.system.shell import run_shell_command
      return await run_shell_command(command, timeout=timeout)
    return {
      "ok": False,
      "error": str(exc),
      "errorKind": "sandbox-unavailable",
      "sandbox": policy.to_dict(),
    }


async def run_python_via_sandbox(
  code: str,
  *,
  timeout: int = 30,
  params: Any = None,
  session_id: str = "",
  cwd: str | None = None,
  bindings: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Run Python under the same session-scoped policy/cwd seam as shell."""
  policy = sandbox_policy(params, session_id=session_id, cwd=cwd)
  try:
    result = await python_runner().run_python(
      code,
      timeout=timeout,
      bindings=bindings,
      cwd=policy.containment_root,
    )
    return _with_context(result, policy)
  except Exception as exc:
    return {
      "ok": False,
      "error": str(exc),
      "errorKind": "sandbox-unavailable",
      "sandbox": policy.to_dict(),
    }