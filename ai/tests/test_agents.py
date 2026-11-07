"""Tests for builtin multi-agent routing."""

import unittest


class AgentRoutingTests(unittest.TestCase):
  def test_list_agents(self):
    from ai.agents.registry import list_agents, orchestrator_id

    agents = list_agents(include_orchestrator=True)
    self.assertGreaterEqual(len(agents), 8)
    self.assertEqual(orchestrator_id(), "op")

  def test_workflow_maps_to_agent(self):
    from ai.agents.registry import agent_for_workflow

    triage = agent_for_workflow("engage_triage")
    self.assertIsNotNone(triage)
    self.assertEqual(triage["id"], "triage")

  def test_resolve_engage_intent(self):
    from ai.agents.router import resolve_agent_route

    route = resolve_agent_route({
      "messages": [{"role": "user", "content": "无法 engage，LKAS 故障"}],
    })
    self.assertEqual(route.agent_id, "triage")
    self.assertEqual(route.workflow_id, "engage_triage")

  def test_resolve_tune_intent(self):
    from ai.agents.router import resolve_agent_route

    route = resolve_agent_route({
      "messages": [{"role": "user", "content": "帮我调参，纵向跟车太冲"}],
    })
    self.assertEqual(route.agent_id, "tune")

  def test_explicit_workflow(self):
    from ai.agents.router import resolve_agent_route

    route = resolve_agent_route({
      "workflow": "secoc_tsk",
      "messages": [{"role": "user", "content": "hi"}],
    })
    self.assertEqual(route.agent_id, "secoc")

  def test_filter_tools_scoped(self):
    from ai.agents.registry import filter_tools_for_agent, get_agent

    agent = get_agent("secoc")
    self.assertIsNotNone(agent)
    tools = filter_tools_for_agent([
      {"function": {"name": "tsk_extract_key"}},
      {"function": {"name": "git_commit"}},
    ], agent)
    names = {t["function"]["name"] for t in (tools or [])}
    self.assertIn("tsk_extract_key", names)
    self.assertNotIn("git_commit", names)

  def test_office_handoff(self):
    from ai.agents.office import on_handoff, office_snapshot

    route = {
      "agent_id": "triage",
      "agentName": "分诊员",
      "reason": "workflow",
    }
    snap = on_handoff(route, session_id="s1", job_id="j1")
    self.assertEqual(snap["sessionId"], "s1")
    self.assertTrue(any(a["id"] == "triage" and a["status"] == "assigned" for a in snap["agents"]))
    self.assertGreater(len(office_snapshot()["tasks"]), 0)

  def test_office_orchestration_start(self):
    from ai.agents.office import on_orchestration_start

    plan = [
      {"agent_id": "triage", "agentName": "分诊员"},
      {"agent_id": "tune", "agentName": "调参师"},
    ]
    snap = on_orchestration_start(plan, session_id="s2", job_id="j2")
    self.assertEqual(snap["sessionId"], "s2")
    statuses = {a["id"]: a["status"] for a in snap["agents"]}
    self.assertEqual(statuses.get("triage"), "assigned")
    self.assertEqual(statuses.get("tune"), "assigned")
    self.assertEqual(statuses.get("op"), "working")

  def test_orchestrate_multi_domain(self):
    from ai.agents.orchestrator import detect_orchestration_plan

    plan = detect_orchestration_plan({
      "messages": [{"role": "user", "content": "无法 engage，还要调纵向跟车手感太冲"}],
    }, pc_dev=True)
    self.assertIsNotNone(plan)
    self.assertGreaterEqual(len(plan), 2)
    ids = {r.agent_id for r in plan}
    self.assertTrue("triage" in ids or "tune" in ids)

  def test_disabled_agent_skipped(self):
    from unittest.mock import patch
    from ai.agents.router import resolve_agent_route

    with patch("ai.agents.router.load_disabled_agent_ids", return_value={"triage"}):
      route = resolve_agent_route({
        "messages": [{"role": "user", "content": "无法 engage，LKAS 故障"}],
      }, params=object())
    self.assertNotEqual(route.agent_id, "triage")

  def test_orchestrator_passthrough_single(self):
    import asyncio
    from unittest.mock import AsyncMock, patch
    from ai.agents.orchestrator import run_chat_with_agents

    body = {"messages": [{"role": "user", "content": "hi"}]}
    with patch("ai.agents.orchestrator.run_chat_loop", new_callable=AsyncMock) as mock_loop:
      mock_loop.return_value = {"ok": True}
      result = asyncio.run(run_chat_with_agents(
        body, object(), AsyncMock(),
        get_state_reader=lambda: None,
        get_tool_handlers=lambda: {},
        tools=None,
      ))
    self.assertTrue(result["ok"])
    mock_loop.assert_awaited_once()


if __name__ == "__main__":
  unittest.main()
