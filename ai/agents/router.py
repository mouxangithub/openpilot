"""Route user intent to builtin specialist agents."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ai.agents.registry import agent_for_workflow, get_agent, list_agents, orchestrator_id
from ai.agents.config import load_disabled_agent_ids


@dataclass
class AgentRoute:
  agent_id: str
  workflow_id: str
  reason: str
  confidence: float = 1.0

  def to_dict(self) -> dict[str, Any]:
    agent = get_agent(self.agent_id) or {}
    return {
      **asdict(self),
      "agentName": agent.get("name", self.agent_id),
      "agentIcon": agent.get("icon", "🤖"),
      "agentDescription": agent.get("description", ""),
    }


def _last_user_text(body: dict[str, Any]) -> str:
  messages = body.get("messages") or []
  for msg in reversed(messages):
    if msg.get("role") != "user":
      continue
    content = msg.get("content", "")
    if isinstance(content, str):
      return content.strip()
    if isinstance(content, list):
      parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
      return " ".join(parts).strip()
    return str(content or "").strip()
  return ""


def _normalize_text(text: str) -> str:
  return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _score_agent(agent: dict[str, Any], text: str) -> float:
  if agent.get("is_orchestrator"):
    return 0.0
  score = 0.0
  norm = _normalize_text(text)
  if not norm:
    return 0.0
  for kw in agent.get("keywords") or []:
    k = _normalize_text(kw)
    if not k:
      continue
    if k in norm:
      score += 2.5 if len(k) >= 4 else 1.5
  # Slash-style hints embedded in text
  if norm.startswith("/"):
    first = norm.split()[0].lstrip("/")
    alias_map = {
      "engage": "triage",
      "logs": "triage",
      "secoc": "secoc",
      "tsk": "secoc",
      "adapt": "adapt",
      "routes": "route",
      "route": "route",
      "batch": "route",
      "tune": "tune",
      "konik": "cloud",
      "cloud": "cloud",
      "pr": "devops",
      "ci": "devops",
      "replay": "pc",
      "cabana": "pc",
    }
    if alias_map.get(first) == agent.get("id"):
      score += 5.0
  return score


def resolve_agent_route(
  body: dict[str, Any],
  *,
  driving: bool = False,
  pc_dev: bool = True,
  params: Any = None,
) -> AgentRoute:
  workflow_id = str(body.get("workflow") or body.get("workflow_id") or "").strip()
  explicit_agent = str(body.get("agentId") or body.get("agent_id") or "").strip()
  user_text = _last_user_text(body)
  disabled = load_disabled_agent_ids(params) if params is not None else set()

  if explicit_agent and get_agent(explicit_agent) and explicit_agent not in disabled:
    return AgentRoute(explicit_agent, workflow_id, "explicit", 1.0)

  if workflow_id:
    agent = agent_for_workflow(workflow_id)
    if agent and agent["id"] not in disabled:
      return AgentRoute(agent["id"], workflow_id, "workflow", 1.0)

  best_id = orchestrator_id()
  best_score = 0.0
  for agent in list_agents(include_orchestrator=True):
    if agent.get("pcOnly") and not pc_dev:
      continue
    if agent["id"] in disabled:
      continue
    full = get_agent(agent["id"])
    if not full:
      continue
    score = _score_agent(full, user_text)
    if score > best_score:
      best_score = score
      best_id = agent["id"]

  if best_score >= 2.0 and best_id != orchestrator_id():
    agent = get_agent(best_id) or {}
    wf = workflow_id
    if not wf and agent.get("workflows"):
      wf = agent["workflows"][0]
    return AgentRoute(best_id, wf, "intent", min(best_score / 6.0, 1.0))

  if driving and best_id not in (orchestrator_id(), "triage", "route"):
    return AgentRoute(orchestrator_id(), workflow_id, "driving_safe", 1.0)

  return AgentRoute(orchestrator_id(), workflow_id, "default", 1.0)
