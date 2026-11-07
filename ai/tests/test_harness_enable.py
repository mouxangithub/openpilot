"""Harness 集成接线的隔离回归测试。"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ai.tests.bootstrap_pc  # noqa: F401

from ai.tools import harness_tools as ht
from ai.core.session.log import EventType, SessionLog
from ai.core.session.repair import repair_session_log


class RepairSandboxTests(unittest.TestCase):
  def test_repair_closers_are_idempotent(self):
    path = Path(tempfile.mkdtemp()) / "session.jsonl"
    log = SessionLog("repair-test", persist_path=str(path))
    log.append(EventType.TURN_START, {"turn": 1})
    log.append(EventType.STEP_START, {"turn": 1, "step": 1})
    log.append(EventType.TOOL_CALL, {"turn": 1, "step": 1, "callId": "c1", "name": "x"})
    repaired = repair_session_log(log)
    self.assertEqual([e.type for e in repaired], [EventType.TOOL_RESULT, EventType.STEP_END, EventType.TURN_END])
    self.assertEqual(repair_session_log(log), [])
    self.assertTrue(any(e.type == EventType.TOOL_CALL for e in log.events))
    log.close()

  def test_sandbox_context_and_fallback_default(self):
    from ai.core.tools import sandbox_hooks as sh
    with patch.object(sh, "sandbox_policy") as policy:
      policy.return_value.containment_root = "."
      policy.return_value.to_dict.return_value = {"sessionId": "s"}
      runner = AsyncMock()
      runner.run_shell.return_value = type("R", (), {"to_dict": lambda self: {"ok": True}})()
      with patch.object(sh, "shell_runner", return_value=runner):
        result = asyncio.run(sh.run_shell_via_sandbox("pwd", session_id="s", cwd="."))
      self.assertTrue(result["ok"])
      self.assertFalse(sh.sandbox_host_fallback_enabled(None))
      runner.run_shell.assert_awaited_once()


class HarnessEnableTests(unittest.TestCase):
  def test_schema_and_handlers(self):
    schemas = ht.harness_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    self.assertTrue({"goal_create", "plan_generate", "todo_write", "lsp", "run_python_code"} <= names)
    handlers = {}
    ht.register_harness_handlers(handlers)
    self.assertTrue({"goal_create", "plan_generate", "todo_write", "lsp"} <= handlers.keys())

  def test_goal_plan_todo_and_error_envelope(self):
    root = Path(tempfile.mkdtemp())
    with patch.object(ht, "_goal_store", return_value=__import__("ai.goal.store", fromlist=["GoalStore"]).GoalStore(root / "g")), patch.object(ht, "_plan_store", return_value=__import__("ai.plan.store", fromlist=["PlanStore"]).PlanStore(root / "p")), patch.object(ht, "_todo_store", return_value=__import__("ai.todo.store", fromlist=["TodoStore"]).TodoStore(root / "t")):
      goal = ht._h_goal_create({"objective": "test"})
      self.assertTrue(goal["ok"])
      self.assertTrue(ht._h_todo_write({"todos": [{"content": "x"}]})["ok"])
      self.assertTrue(ht._h_plan_generate({"title": "p", "steps": []})["ok"])
      self.assertFalse(ht._h_goal_create({"objective": ""})["ok"])
      self.assertIn("error", ht._h_goal_create({"objective": ""}))

  def test_python_blocked_and_empty(self):
    blocked = asyncio.run(ht._h_run_python_code({"code": "import os; os.system('x')"}))
    self.assertFalse(blocked["ok"])
    empty = asyncio.run(ht._h_run_python_code({"code": "   "}))
    self.assertFalse(empty["ok"])
    self.assertIn("error", empty)

  def test_shell_empty_sandbox(self):
    from ai.tools.agent_tools import make_handlers
    from types import SimpleNamespace
    reader = lambda: SimpleNamespace(update=lambda timeout=0: SimpleNamespace(is_driving=False))
    handlers = make_handlers(get_state_reader=reader)
    empty = asyncio.run(handlers["run_shell"]({"command": ""}))
    self.assertFalse(empty["ok"])
    with patch("ai.core.tools.sandbox_hooks.run_shell_via_sandbox", new=AsyncMock(return_value={"ok": True, "stdout": "ok"})) as run:
      result = asyncio.run(handlers["run_shell"]({"command": "printf ok", "sessionId": "s", "cwd": "."}))
      self.assertTrue(result["ok"])
      run.assert_awaited_once()

  def test_workflow_lsp_mcp_errors(self):
    self.assertFalse(asyncio.run(ht._h_workflow_advance({"workflow_id": "missing", "action": "step"}))["ok"])
    self.assertFalse(asyncio.run(ht._h_workflow_advance({"workflow_id": "missing", "node_id": "missing", "action": "step"}))["ok"])
    self.assertFalse(asyncio.run(ht._h_lsp({"action": "hover", "uri": "file:///x", "line": 1, "character": 1}))["ok"])
    handlers = {}
    with patch.object(ht, "_load_mcp_servers", return_value=[]):
      ht.register_mcp_handlers(handlers)
    self.assertNotIn("mcp__denied__tool", handlers)
    with patch("ai.mcp.host.discover_mcp_tools", new=AsyncMock(return_value={"ok": True, "tools": [{"name": "bad", "inputSchema": "invalid"}]})):
      result = asyncio.run(ht._h_mcp_discover({"server_id": "x"}))
    self.assertFalse(result["ok"])

  def test_build_tool_schemas_includes_harness(self):
    from ai.tools.agent_tools import build_tool_schemas
    schemas = build_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    for name in ("goal_create", "plan_generate", "todo_write"):
      self.assertIn(name, names)

  def test_make_handlers_includes_harness(self):
    from ai.tools.agent_tools import make_handlers
    from types import SimpleNamespace
    reader = lambda: SimpleNamespace(update=lambda timeout=0: SimpleNamespace(is_driving=False))
    handlers = make_handlers(get_state_reader=reader)
    for name in ("goal_create", "plan_generate", "todo_write"):
      self.assertIn(name, handlers)

  def test_agent_run_defaults_to_loop(self):
    from ai.core.agent.agent import Agent
    from ai.core.llm.client import AIConfig
    from openpilot.common.params import Params
    from unittest.mock import AsyncMock, patch

    async def _noop_emit(_event):
      pass

    def _make_agent(ai_use_agent_loop: bool):
      return Agent(
        session_id="test-session",
        agent_id="test-agent",
        params=Params(),
        config=AIConfig(provider="offline", model="offline-mock", api_key=""),
        body={"ai_use_agent_loop": ai_use_agent_loop},
        emit=_noop_emit,
        get_state_reader=lambda: SimpleNamespace(update=lambda timeout=0: SimpleNamespace(is_driving=False)),
        get_tool_handlers=lambda: {},
        tools=None,
        ai_use_agent_loop=ai_use_agent_loop,
      )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      with patch.object(Agent, "run_with_loop", new=AsyncMock(return_value={"ok": True})) as loop_mock:
        agent = _make_agent(True)
        result = loop.run_until_complete(agent.run())
        self.assertTrue(result["ok"])
        loop_mock.assert_awaited_once()

      with patch.object(Agent, "run_with_loop", new=AsyncMock(return_value={"ok": True})) as loop_mock:
        with patch.object(Agent, "_build_messages", new=AsyncMock(return_value=(AIConfig(provider="offline", model="offline-mock", api_key=""), []))) as _bm:
          with patch.object(Agent, "_stream_round", new=AsyncMock(return_value=({"role": "assistant", "content": "ok"}, []))) as _sr:
            with patch.object(Agent, "_run_post_chat", new=AsyncMock()) as _pc:
              agent = _make_agent(False)
              result = loop.run_until_complete(agent.run())
              self.assertTrue(result["ok"])
              loop_mock.assert_not_awaited()
              _sr.assert_awaited_once()
    finally:
      loop.close()
      asyncio.set_event_loop(None)


if __name__ == "__main__":
  unittest.main()
