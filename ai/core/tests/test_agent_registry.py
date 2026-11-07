"""AgentRegistry lifecycle tests."""

from __future__ import annotations

import asyncio
import unittest

from ai.core.agent.registry import AgentRegistry


class AgentRegistryTest(unittest.IsolatedAsyncioTestCase):
  def setUp(self) -> None:
    self.reg = AgentRegistry()

  def test_create_list_mark_done(self) -> None:
    self.reg.create("s1", "op", job_id="j1")
    self.reg.create("s2", "tune", job_id="j2", meta={"mode": "unlimited"})
    active = self.reg.list(active_only=True)
    self.assertEqual(len(active), 2)
    self.reg.mark_done("s1", "done")
    active = self.reg.list(active_only=True)
    self.assertEqual(len(active), 1)
    self.assertEqual(active[0]["agentId"], "tune")
    self.assertEqual(active[0]["meta"]["mode"], "unlimited")
    self.assertIsNotNone(self.reg.get("s1"))
    self.assertEqual(self.reg.get("s1").status, "done")

  def test_resume_reuses_entry(self) -> None:
    e1 = self.reg.create("s1", "op")
    e2 = self.reg.resume("s1", "op", job_id="j2")
    self.assertIs(e1, e2, "resume must reuse the existing entry")
    self.assertEqual(e2.job_id, "j2")
    self.assertEqual(e2.status, "running")

  async def test_cancel_session_invokes_cancel_fn(self) -> None:
    calls: list[str] = []

    async def cancel_a() -> bool:
      calls.append("a")
      return True

    async def cancel_b() -> bool:
      calls.append("b")
      return False

    self.reg.create("sa", "op", cancel_fn=cancel_a)
    self.reg.create("sb", "op", cancel_fn=cancel_b)
    self.assertTrue(await self.reg.cancel_session("sa"))
    self.assertFalse(await self.reg.cancel_session("sb"))
    # No entry => cancel returns False without error.
    self.assertFalse(await self.reg.cancel_session("missing"))
    self.assertEqual(sorted(calls), ["a", "b"])
    self.assertEqual(self.reg.get("sa").status, "cancelled")
    self.assertEqual(self.reg.get("sb").status, "running")

  def test_clear(self) -> None:
    self.reg.create("s1", "op")
    self.reg.clear()
    self.assertEqual(len(self.reg.list(active_only=False)), 0)

  async def test_module_singleton(self) -> None:
    # Even isolated instances share nothing; module singleton is a separate
    # object, so exercising the default makes sure imports are safe.
    from ai.core.agent.registry import agent_registry
    self.assertIsInstance(agent_registry, AgentRegistry)
    await asyncio.sleep(0)


if __name__ == "__main__":
  unittest.main()