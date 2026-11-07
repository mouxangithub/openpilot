"""Unit tests for ai.sandbox runners and E2B stub."""

from __future__ import annotations

import tempfile
import unittest

from ai.sandbox.e2b_stub import Sandbox
from ai.sandbox.python_runner import PythonRunner
from ai.sandbox.runtime import SandboxPolicyService
from ai.sandbox.shell_runner import ShellRunner


class TestPythonRunner(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.runner = PythonRunner(workspace_root=self.tmp.name, default_timeout=10)

  async def asyncTearDown(self) -> None:
    self.tmp.cleanup()

  async def test_simple_code(self) -> None:
    result = await self.runner.run_python("print('hello')\nreturn 42")
    self.assertTrue(result.ok)
    self.assertIn("hello", result.stdout)

  async def test_timeout(self) -> None:
    result = await self.runner.run_python("import time\ntime.sleep(10)", timeout=1)
    self.assertFalse(result.ok)
    self.assertEqual(result.error_kind, "timeout")

  async def test_blocked_import(self) -> None:
    result = await self.runner.run_python("import os\nos.system('echo hi')")
    self.assertFalse(result.ok)
    self.assertEqual(result.error_kind, "blocked")

  async def test_exception(self) -> None:
    result = await self.runner.run_python("raise ValueError('boom')")
    self.assertFalse(result.ok)
    self.assertEqual(result.error_kind, "exception")
    self.assertIn("boom", result.error or "")


class TestShellRunner(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.runner = ShellRunner(workspace_root=self.tmp.name, default_timeout=10)

  async def asyncTearDown(self) -> None:
    self.tmp.cleanup()

  async def test_echo(self) -> None:
    result = await self.runner.run_shell(["echo", "hello"])
    self.assertTrue(result.ok)
    self.assertIn("hello", result.stdout)

  async def test_blocked_destructive(self) -> None:
    result = await self.runner.run_shell("rm -rf /")
    self.assertFalse(result.ok)
    self.assertEqual(result.error_kind, "blocked")

  async def test_timeout(self) -> None:
    result = await self.runner.run_shell("python -c \"import time; time.sleep(10)\"", timeout=1)
    self.assertFalse(result.ok)
    self.assertEqual(result.error_kind, "timeout")

  async def test_session_policy_containment_and_default_open(self) -> None:
    service = SandboxPolicyService(workspace_root=self.tmp.name)
    policy = service.resolve(session_id="session-1", cwd="../outside")
    self.assertEqual(policy.session_id, "session-1")
    self.assertEqual(policy.containment_root, service.workspace_root)
    # Default sandbox is now workspace-write (fully-open intent).
    self.assertEqual(policy.mode, "workspace-write")
    result = await self.runner.run_shell("echo hi > created.txt", policy=policy)
    self.assertTrue(result.ok)

  async def test_explicit_readonly_blocks_mutation(self) -> None:
    from ai.sandbox.runtime import ConfinedSessionPolicy
    policy = ConfinedSessionPolicy(
      session_id="ro",
      mode="read-only",
      containment_root=self.tmp.name,
    )
    result = await self.runner.run_shell("echo hi > created_ro.txt", policy=policy)
    self.assertFalse(result.ok)
    self.assertEqual(result.error_kind, "blocked")


class TestE2BStub(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.sandbox = Sandbox(workspace_root=self.tmp.name, timeout=10)

  async def asyncTearDown(self) -> None:
    self.tmp.cleanup()

  async def test_run_code(self) -> None:
    execution = await self.sandbox.run_code("print('from e2b')\nreturn 7")
    self.assertIsNone(execution.error)
    self.assertIn("from e2b", execution.stdout)

  async def test_run_command(self) -> None:
    execution = await self.sandbox.run_command("echo stub")
    self.assertIsNone(execution.error)
    self.assertIn("stub", execution.stdout)


if __name__ == "__main__":
  unittest.main()
