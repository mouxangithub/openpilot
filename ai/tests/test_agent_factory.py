"""Tests for the central Agent factory (A-P0.4)."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import ai.tests.bootstrap_pc  # noqa: F401  (installs openpilot mocks)
from openpilot.common.params import Params


class TestAgentFactory(unittest.TestCase):
  def test_create_agent_wires_defaults(self):
    from ai.core.agent.agent import Agent
    from ai.core.agent.factory import AgentFactory
    from ai.core.llm.client import AIConfig

    async def _noop_emit(_event):
      pass

    factory = AgentFactory(params=Params())
    agent = factory.create_agent(
      session_id="factory-session",
      body={"ai_use_agent_loop": True},
      agent_id="factory-agent",
      emit=_noop_emit,
      tools=[],
    )
    self.assertIsInstance(agent, Agent)
    self.assertEqual(agent.session_id, "factory-session")
    self.assertEqual(agent.agent_id, "factory-agent")
    self.assertTrue(agent.ai_use_agent_loop)
    self.assertIsNotNone(agent.log)

  def test_default_emit_is_runnable(self):
    from ai.core.agent.factory import AgentFactory
    factory = AgentFactory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      emitter = factory.default_emit()
      result = loop.run_until_complete(emitter({"type": "tool_call"}))
      self.assertIsNone(result)
    finally:
      loop.close()

  def test_tool_handlers_factory_returns_dict(self):
    from ai.core.agent.factory import AgentFactory
    factory = AgentFactory(params=Params())
    handlers_fn = factory.tool_handlers_factory()
    handlers = handlers_fn()
    self.assertIsInstance(handlers, dict)
    # The full make_handlers set includes both extension and harness tools.
    self.assertIn("goal_create", handlers)

  def test_session_log_path_derives_valid_path(self):
    from ai.core.agent.factory import AgentFactory
    factory = AgentFactory()
    path = factory.session_log_path("sess-123")
    self.assertIsInstance(path, str)
    self.assertIn("sess-123", path)
    self.assertIsNone(factory.session_log_path(""))


if __name__ == "__main__":
  unittest.main()