"""Run Python code in a subprocess with timeouts and output capture."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from typing import Any

from ai.sandbox.runtime import RunResult, SandboxRuntime


# Basic guardrails; this is NOT a security boundary on its own.
BLOCKED_PYTHON_PATTERNS: list[tuple[re.Pattern[str], str]] = [
  (re.compile(r"\bimport\s+(os|subprocess|shlex)\b", re.IGNORECASE), "blocked import: {}"),
  (re.compile(r"\b__import__\s*\(\s*['\"]os['\"]\s*\)", re.IGNORECASE), "blocked dynamic import: {}"),
  (re.compile(r"\bos\.(system|popen|spawn|exec|fork)\b", re.IGNORECASE), "blocked os function: {}"),
  (re.compile(r"\bsubprocess\.(run|call|Popen|check_output)\b", re.IGNORECASE), "blocked subprocess function: {}"),
]


class PythonRunner(SandboxRuntime):
  """Subprocess-based Python code runner.

  Code is executed in a fresh ``python`` subprocess. Output is captured and
  truncated to ``max_output_bytes``. The runner is safe enough for trusted
  model output in development, but should be paired with a real sandbox
  (container, E2B, etc.) for untrusted code.
  """

  BLOCKED_PATTERNS = BLOCKED_PYTHON_PATTERNS

  def __init__(
    self,
    *,
    default_timeout: int = 30,
    max_output_bytes: int = 2 * 1024 * 1024,
    python_executable: str | None = None,
    workspace_root: str | None = None,
  ) -> None:
    super().__init__(
      default_timeout=default_timeout,
      max_output_bytes=max_output_bytes,
      workspace_root=workspace_root,
    )
    self.python_executable = python_executable or sys.executable

  def _check_code(self, code: str) -> str | None:
    for pattern, template in self.BLOCKED_PATTERNS:
      match = pattern.search(code)
      if match:
        return template.format(match.group(0))
    return None

  def _build_script(self, code: str, bindings: dict[str, Any] | None) -> str:
    safe_bindings: dict[str, Any] = {}
    if bindings:
      for key, value in bindings.items():
        if callable(value):
          continue
        safe_bindings[key] = value

    binding_lines = "\n".join(
      f"{key} = __dsh_bindings__[{key!r}]"
      for key in safe_bindings
    )

    indented = "\n".join("  " + line for line in code.splitlines())
    return f"""\
import asyncio
import json
import sys

__dsh_bindings__ = {json.dumps(safe_bindings)!r}
__dsh_bindings__ = json.loads(__dsh_bindings__)
{binding_lines}

async def __dsh_main__():
{indented}

try:
  _result = asyncio.run(__dsh_main__())
  sys.stdout.write("__DSH_RESULT__" + json.dumps(_result) + "\\n")
except Exception as _exc:
  sys.stderr.write("__DSH_EXCEPTION__" + repr(_exc) + "\\n")
  sys.exit(1)
"""

  async def _drain_stream(
    self,
    stream: asyncio.StreamReader | None,
  ) -> tuple[str, bool]:
    """Read up to ``max_output_bytes`` from a stream. Returns (text, truncated)."""
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

  async def run_python(
    self,
    code: str,
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    bindings: dict[str, Any] | None = None,
    cwd: str | None = None,
  ) -> RunResult:
    if not str(code).strip():
      return RunResult(ok=False, error="Python code must not be empty", error_kind="invalid_input")
    blocked = self._check_code(code)
    if blocked:
      return RunResult(
        ok=False,
        stderr=blocked,
        error=blocked,
        error_kind="blocked",
      )

    script = self._build_script(code, bindings)
    proc_cwd = cwd or self.workspace_root
    fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="dsh_py_", dir=proc_cwd)
    try:
      os.write(fd, script.encode("utf-8"))
      os.close(fd)
      fd = -1
      proc = await asyncio.create_subprocess_exec(
        self.python_executable,
        "-u",
        tmp_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=proc_cwd,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
      )
      try:
        stdout, stderr = await asyncio.wait_for(
          proc.communicate(),
          timeout=timeout or self.default_timeout,
        )
      except TimeoutError:
        proc.kill()
        await proc.wait()
        return RunResult(
          ok=False,
          error=f"Python code timed out after {timeout or self.default_timeout}s",
          error_kind="timeout",
        )

      out_text = stdout.decode("utf-8", errors="replace")
      err_text = stderr.decode("utf-8", errors="replace")
      if "__DSH_RESULT__" in out_text:
        parts = out_text.split("__DSH_RESULT__", 1)
        out_text = parts[0]
        try:
          json.loads(parts[1].strip().splitlines()[0])
        except Exception:
          pass

      if "__DSH_EXCEPTION__" in err_text:
        exc_msg = err_text.split("__DSH_EXCEPTION__", 1)[1].splitlines()[0]
        return RunResult(
          ok=False,
          stdout=out_text,
          stderr=err_text,
          returncode=proc.returncode,
          error=exc_msg,
          error_kind="exception",
        )

      return RunResult(
        ok=proc.returncode == 0,
        stdout=out_text,
        stderr=err_text,
        returncode=proc.returncode,
      )
    except Exception as exc:
      return RunResult(ok=False, error=str(exc), error_kind="exception")
    finally:
      if fd >= 0:
        os.close(fd)
      try:
        os.unlink(tmp_path)
      except OSError:
        pass

  async def run_shell(
    self,
    command: str | list[str],
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    policy: Any = None,
  ) -> RunResult:
    return RunResult(
      ok=False,
      error="PythonRunner does not run shell commands; use ShellRunner.",
      error_kind="blocked",
    )
