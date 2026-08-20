"""Builtin agent registry for op助手 multi-agent orchestration."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.json"

_SHARED_TOOLS = frozenset({
  "get_agent_memory",
  "update_agent_memory",
  "search_memory_semantic",
  "search_knowledge_base",
  "list_knowledge_docs",
  "get_vehicle_state",
  "read_params",
  "sessions_list",
  "sessions_history",
  "search_past_conversations",
  "get_user_profile",
  "update_user_profile",
  "list_learned_skills",
})


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
  with open(_REGISTRY_PATH, encoding="utf-8") as f:
    data = json.load(f)
  by_id = {a["id"]: a for a in data.get("agents", [])}
  wf_map: dict[str, str] = {}
  for agent in data.get("agents", []):
    for wf in agent.get("workflows") or []:
      wf_map[wf] = agent["id"]
  data["_by_id"] = by_id
  data["_workflow_map"] = wf_map
  return data


def list_agents(*, include_orchestrator: bool = True) -> list[dict[str, Any]]:
  reg = load_registry()
  out: list[dict[str, Any]] = []
  for agent in reg.get("agents", []):
    if not include_orchestrator and agent.get("is_orchestrator"):
      continue
    out.append(public_agent(agent))
  return out


def get_agent(agent_id: str) -> dict[str, Any] | None:
  return load_registry().get("_by_id", {}).get(agent_id)


def orchestrator_id() -> str:
  return str(load_registry().get("orchestrator_id") or "op")


def agent_for_workflow(workflow_id: str) -> dict[str, Any] | None:
  if not workflow_id:
    return None
  aid = load_registry().get("_workflow_map", {}).get(workflow_id)
  return get_agent(aid) if aid else None


def public_agent(agent: dict[str, Any]) -> dict[str, Any]:
  return {
    "id": agent.get("id", ""),
    "name": agent.get("name", ""),
    "nameEn": agent.get("name_en", ""),
    "icon": agent.get("icon", "🤖"),
    "description": agent.get("description", ""),
    "desk": agent.get("desk") or {},
    "workflows": list(agent.get("workflows") or []),
    "isOrchestrator": bool(agent.get("is_orchestrator")),
    "pcOnly": bool(agent.get("pc_only")),
  }


def collect_skill_tools(skill_ids: list[str]) -> set[str]:
  if not skill_ids:
    return set()
  try:
    from ai.skills.loader import list_skills
    by_id = {s["id"]: s for s in list_skills()}
  except Exception:
    return set()
  tools: set[str] = set()
  for sid in skill_ids:
    skill = by_id.get(sid)
    if not skill:
      continue
    for name in skill.get("requires_tools") or []:
      if name:
        tools.add(name)
  return tools


def agent_tool_allowlist(agent: dict[str, Any]) -> set[str] | None:
  if agent.get("tool_mode") == "all" or agent.get("is_orchestrator"):
    return None
  allowed: set[str] = set(_SHARED_TOOLS)
  allowed |= collect_skill_tools(list(agent.get("skills") or []))
  allowed |= set(agent.get("extra_tools") or [])
  prefixes = tuple(agent.get("tool_prefixes") or [])
  if prefixes:
    from ai.tools.agent_tools import TOOL_META
    for name in TOOL_META:
      if name.startswith(prefixes):
        allowed.add(name)
    try:
      from ai.tools.extensions import EXTENSION_TOOL_META
      for name in EXTENSION_TOOL_META:
        if name.startswith(prefixes):
          allowed.add(name)
    except Exception:
      pass
    try:
      from ai.tools.sp_tool_extensions import SP_EXTENSION_TOOL_META
      for name in SP_EXTENSION_TOOL_META:
        if name.startswith(prefixes):
          allowed.add(name)
    except Exception:
      pass
  return allowed


def filter_tools_for_agent(
  tools: list[dict[str, Any]] | None,
  agent: dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
  if not tools or not agent:
    return tools
  allow = agent_tool_allowlist(agent)
  if allow is None:
    return tools
  out: list[dict[str, Any]] = []
  for tool in tools:
    name = tool.get("function", {}).get("name", "")
    if name in allow:
      out.append(tool)
  return out or None
