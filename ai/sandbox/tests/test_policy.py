"""Tests for ai.sandbox.policy."""

from __future__ import annotations

import os
import tempfile
import unittest

from ai.sandbox.policy import (
  ConfinedSessionPolicy,
  SessionSandboxPolicyService,
)


class TestSessionSandboxPolicyService(unittest.TestCase):
  def test_default_read_only(self) -> None:
    service = SessionSandboxPolicyService()
    policy = service.resolve(session_id="s1", cwd="/tmp/ws")
    self.assertEqual(policy.session_id, "s1")
    self.assertEqual(policy.mode, "read-only")

  def test_workspace_write_override_via_params(self) -> None:
    service = SessionSandboxPolicyService()
    params = {"ai_sandbox_default_mode": "workspace-write"}
    policy = service.resolve(params, session_id="s2", cwd="/tmp/ws")
    self.assertEqual(policy.mode, "workspace-write")

  def test_session_state_override(self) -> None:
    service = SessionSandboxPolicyService()
    session_state = {"sandbox": {"mode": "workspace-write"}}
    policy = service.resolve(
      {"ai_sandbox_default_mode": "read-only"},
      session_id="s3",
      cwd="/tmp/ws",
      session_state=session_state,
    )
    self.assertEqual(policy.mode, "workspace-write")

  def test_path_containment_escape(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      service = SessionSandboxPolicyService(workspace_root=tmp)
      outside = os.path.abspath(os.path.join(tmp, "..", "outside"))
      policy = service.resolve(session_id="s4", cwd=outside)
      self.assertEqual(policy.containment_root, tmp)

  def test_to_context(self) -> None:
    policy = ConfinedSessionPolicy(
      session_id="s5",
      mode="workspace-write",
      cwd="/tmp/ws",
      containment_root="/tmp/ws",
    )
    ctx = policy.to_context()
    self.assertEqual(ctx["sandbox"]["sessionId"], "s5")
    self.assertEqual(ctx["sandbox"]["mode"], "workspace-write")
    self.assertEqual(ctx["sandbox"]["cwd"], "/tmp/ws")
    self.assertEqual(ctx["sandbox"]["containmentRoot"], "/tmp/ws")


if __name__ == "__main__":
  unittest.main()
