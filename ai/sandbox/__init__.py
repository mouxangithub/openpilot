"""Sandbox / code-runtime package for op助手.

Provides a local, dependency-light implementation of the DeepSeek Harness
sandbox and code-runtime seams.
"""

from ai.sandbox.e2b_stub import Execution, Sandbox
from ai.sandbox.python_runner import PythonRunner
from ai.sandbox.runtime import (
  ConfinedSandboxMode,
  RunResult,
  SandboxExecutionPolicy,
  SandboxMode,
  SandboxPolicy,
  SandboxRuntime,
)
from ai.sandbox.shell_runner import ShellRunner

__all__ = [
  "Execution",
  "PythonRunner",
  "RunResult",
  "Sandbox",
  "SandboxExecutionPolicy",
  "SandboxMode",
  "SandboxPolicy",
  "SandboxRuntime",
  "ShellRunner",
  "ConfinedSandboxMode",
]
