"""E2B-compatible stub that routes to local runners.

This lets callers that expect the ``e2b.Sandbox`` interface work offline or
on hosts where E2B is not configured. It is NOT a security sandbox on its own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ai.sandbox.python_runner import PythonRunner
from ai.sandbox.runtime import RunResult
from ai.sandbox.shell_runner import ShellRunner


@dataclass
class Execution:
  """E2B-like execution result."""

  results: list[Any] = field(default_factory=list)
  logs: list[dict[str, Any]] = field(default_factory=list)
  error: dict[str, Any] | None = None
  execution_id: str | None = None

  @property
  def stdout(self) -> str:
    return "\n".join(
      log["text"] for log in self.logs if log.get("type") == "stdout"
    )

  @property
  def stderr(self) -> str:
    return "\n".join(
      log["text"] for log in self.logs if log.get("type") == "stderr"
    )


class Sandbox:
  """Drop-in replacement for ``e2b.Sandbox``.

  Routes ``run_code`` to :class:`PythonRunner` and ``run_command`` to
  :class:`ShellRunner`. Both runners share the same ``workspace_root`` and
  output limits.
  """

  def __init__(
    self,
    *,
    timeout: int = 60,
    max_output_bytes: int = 2 * 1024 * 1024,
    workspace_root: str | None = None,
    python_runner: PythonRunner | None = None,
    shell_runner: ShellRunner | None = None,
  ) -> None:
    self.timeout = timeout
    self.max_output_bytes = max_output_bytes
    self.workspace_root = workspace_root or os.getcwd()
    self.python_runner = python_runner or PythonRunner(
      default_timeout=timeout,
      max_output_bytes=max_output_bytes,
      workspace_root=self.workspace_root,
    )
    self.shell_runner = shell_runner or ShellRunner(
      default_timeout=timeout,
      max_output_bytes=max_output_bytes,
      workspace_root=self.workspace_root,
    )

  async def run_code(
    self,
    code: str,
    *,
    language: str = "python",
    timeout: int | None = None,  # noqa: ASYNC109
    envs: dict[str, str] | None = None,
  ) -> Execution:
    if language.lower() != "python":
      return Execution(
        error={"name": "UnsupportedLanguage", "value": f"Language {language} is not supported by the local stub."},
      )
    result = await self.python_runner.run_python(
      code,
      timeout=timeout or self.timeout,
      bindings=envs,
    )
    return self._to_execution(result)

  async def run_command(
    self,
    command: str | list[str],
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    envs: dict[str, str] | None = None,
  ) -> Execution:
    result = await self.shell_runner.run_shell(
      command,
      timeout=timeout or self.timeout,
    )
    return self._to_execution(result)

  def _to_execution(self, result: RunResult) -> Execution:
    logs: list[dict[str, Any]] = []
    if result.stdout:
      for line in result.stdout.splitlines():
        logs.append({"type": "stdout", "text": line})
    if result.stderr:
      for line in result.stderr.splitlines():
        logs.append({"type": "stderr", "text": line})
    error = None
    if not result.ok:
      error = {
        "name": result.error_kind or "ExecutionError",
        "value": result.error or "Execution failed",
      }
    return Execution(logs=logs, error=error)

  def close(self) -> None:
    """No-op for API compatibility."""

  async def aclose(self) -> None:
    """No-op async close for API compatibility."""
