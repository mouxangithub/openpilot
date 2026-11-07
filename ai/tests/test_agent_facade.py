"""Agent facade ↔ AgentLoop public iteration seam tests (G4/U13)."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

import ai.tests.bootstrap_pc  # noqa: F401

from ai.core.agent.loop import AgentLoop
from ai.core.agent.state import AgentMessage, ChatCancelled, InboxTarget
from ai.core.tools.pipeline import ToolPipeline


async def _noop_emit(_: dict[str, Any]) -> None:
  return None


def _make_loop(actions: list[str]) -> AgentLoop:
  """Build a loop with scripted turn actions.

  - "queue":   consume nothing, queue one follow-up, return True
               (input arriving mid-activity)
  - "consume": drain the inbox and return False (turn that handles input)
  - "idle":    touch nothing and return False
  """

  class _StubLoop(AgentLoop):
    async def _turn(self) -> bool:  # noqa: D102
      if not actions:
        return False
      action = actions.pop(0)
      if action == "queue":
        self.state.followup(AgentMessage(role="user", content="arrived mid-turn"))
        return True
      if action == "consume":
        self.state.inbox.claim(InboxTarget.NEXT_TURN, 0)
        self.state.inbox.claim(InboxTarget.NEXT_STEP, 0)
        return False
      return False

  return _StubLoop(
    session_id="facade-test",
    agent_id="agent-facade",
    params=None,
    emit=_noop_emit,
    stream_fn=None,
    tool_pipeline=ToolPipeline(),
  )


class RunUntilIdleTests(unittest.TestCase):
  def test_single_turn_completes_and_returns_ok(self) -> None:
    async def scenario() -> dict[str, Any]:
      return await _make_loop(["idle"]).run_until_idle()

    result = asyncio.run(scenario())
    self.assertTrue(result.get("ok"))
    self.assertEqual(result.get("agentId"), "agent-facade")

  def test_drains_queued_followups(self) -> None:
    async def scenario() -> tuple[dict[str, Any], AgentLoop]:
      loop = _make_loop(["queue", "consume"])
      return await loop.run_until_idle(), loop

    result, loop = asyncio.run(scenario())
    self.assertTrue(result.get("ok"))
    self.assertFalse(loop.state.inbox.has_pending)

  def test_external_cancel_between_turns_raises(self) -> None:
    async def scenario() -> None:
      def cancelled() -> bool:
        return True

      loop = _make_loop(["queue", "idle"])
      await loop.run_until_idle(is_cancelled=cancelled)

    with self.assertRaises(ChatCancelled):
      asyncio.run(scenario())

  def test_state_cancel_breaks_queued_loop_without_external_hook(self) -> None:
    """State-level cancel + pending inbox must not spin forever when the
    caller passes no external is_cancelled hook (QA-noted defensive path)."""
    async def scenario() -> None:
      loop = _make_loop(["queue", "idle"])
      from ai.core.agent.state import CancelCause, CancelCauseKind
      loop.state.cancel(CancelCause(CancelCauseKind.USER, "test"))  # no external callback
      await loop.run_until_idle()

    with self.assertRaises(ChatCancelled):
      asyncio.run(asyncio.wait_for(scenario(), timeout=2.0))

  def test_no_pending_skips_cancel_check(self) -> None:
    async def scenario() -> dict[str, Any]:
      return await _make_loop(["idle"]).run_until_idle(is_cancelled=lambda: True)

    # No queued work → no turn boundary reached → completes normally.
    result = asyncio.run(scenario())
    self.assertTrue(result.get("ok"))

  def test_facade_no_longer_calls_private_run(self) -> None:
    # Static guard: the facade must drive the loop via the public seam only.
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "core" / "agent" / "agent.py").read_text(encoding="utf-8")
    self.assertNotIn("loop._run()", source)
    self.assertIn("run_until_idle", source)


class WhenIdleTests(unittest.TestCase):
  def test_no_active_driver_returns_idle(self) -> None:
    async def scenario() -> dict[str, Any]:
      return await _make_loop(["idle"]).when_idle()

    result = asyncio.run(scenario())
    self.assertTrue(result.get("idle"))

  def test_awaits_active_driver_task(self) -> None:
    async def scenario() -> dict[str, Any]:
      loop = _make_loop(["idle"])
      loop._driver_task = asyncio.create_task(loop._run())
      return await loop.when_idle(timeout=2.0)

    result = asyncio.run(scenario())
    self.assertTrue(result.get("ok"))


if __name__ == "__main__":
  unittest.main()
