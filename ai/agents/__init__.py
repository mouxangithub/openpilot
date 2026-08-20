"""Builtin multi-agent orchestration for op助手."""

from ai.agents.registry import (
  agent_for_workflow,
  filter_tools_for_agent,
  get_agent,
  list_agents,
  orchestrator_id,
  public_agent,
)
from ai.agents.router import AgentRoute, resolve_agent_route
from ai.agents.prompts import agent_system_prompt
from ai.agents.office import office_snapshot, on_chat_done, on_handoff, on_tool_done, on_tool_start

__all__ = [
  "AgentRoute",
  "agent_for_workflow",
  "agent_system_prompt",
  "filter_tools_for_agent",
  "get_agent",
  "list_agents",
  "office_snapshot",
  "on_chat_done",
  "on_handoff",
  "on_tool_done",
  "on_tool_start",
  "orchestrator_id",
  "public_agent",
  "resolve_agent_route",
]
