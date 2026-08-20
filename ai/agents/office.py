"""In-memory office visualization state (per aid process)."""

from __future__ import annotations

import time
from typing import Any

from ai.agents.registry import list_agents, orchestrator_id

_MAX_TASKS = 30
_office: dict[str, Any] = {
  "sessionId": "",
  "jobId": "",
  "agents": {},
  "tasks": [],
  "activeCount": 0,
  "updatedAt": 0,
}


def _idle_agents() -> dict[str, dict[str, Any]]:
  agents: dict[str, dict[str, Any]] = {}
  for agent in list_agents(include_orchestrator=True):
    agents[agent["id"]] = {
      "id": agent["id"],
      "name": agent["name"],
      "icon": agent["icon"],
      "desk": agent.get("desk") or {},
      "status": "idle",
      "tool": "",
      "task": "",
      "updatedAt": 0,
    }
  return agents


def reset_office(session_id: str = "", job_id: str = "") -> dict[str, Any]:
  _office["sessionId"] = session_id
  _office["jobId"] = job_id
  _office["agents"] = _idle_agents()
  _office["tasks"] = []
  _office["activeCount"] = 0
  _office["updatedAt"] = int(time.time())
  return office_snapshot()


def office_snapshot() -> dict[str, Any]:
  agents = _office.get("agents") or _idle_agents()
  active = sum(1 for a in agents.values() if a.get("status") not in ("idle", ""))
  return {
    "sessionId": _office.get("sessionId") or "",
    "jobId": _office.get("jobId") or "",
    "agents": list(agents.values()),
    "tasks": list(_office.get("tasks") or [])[-_MAX_TASKS:],
    "activeCount": active,
    "updatedAt": _office.get("updatedAt") or 0,
  }


def _touch() -> None:
  _office["updatedAt"] = int(time.time())


def set_agent_status(
  agent_id: str,
  status: str,
  *,
  tool: str = "",
  task: str = "",
  session_id: str = "",
  job_id: str = "",
) -> dict[str, Any]:
  if not _office.get("agents"):
    reset_office(session_id, job_id)
  if session_id:
    _office["sessionId"] = session_id
  if job_id:
    _office["jobId"] = job_id
  agents = _office["agents"]
  if agent_id not in agents:
    agents[agent_id] = {"id": agent_id, "name": agent_id, "icon": "🤖", "desk": {}, "status": "idle"}
  entry = agents[agent_id]
  entry["status"] = status
  entry["tool"] = tool or entry.get("tool") or ""
  entry["task"] = task or entry.get("task") or ""
  entry["updatedAt"] = int(time.time())
  _touch()
  return office_snapshot()


def log_office_task(
  agent_id: str,
  message: str,
  *,
  status: str = "info",
  tool: str = "",
) -> None:
  tasks = _office.setdefault("tasks", [])
  tasks.append({
    "id": f"t_{int(time.time() * 1000)}_{len(tasks)}",
    "agentId": agent_id,
    "message": message,
    "status": status,
    "tool": tool,
    "at": int(time.time()),
  })
  if len(tasks) > _MAX_TASKS:
    del tasks[: len(tasks) - _MAX_TASKS]
  _touch()


def on_orchestration_start(
  plan: list[dict[str, Any]],
  *,
  session_id: str = "",
  job_id: str = "",
) -> dict[str, Any]:
  """Mark OP + planned specialists for multi-agent orchestration visualization."""
  reset_office(session_id, job_id)
  op = orchestrator_id()
  log_office_task(op, "多专员编排启动", status="working")
  set_agent_status(op, "working", task="编排指挥", session_id=session_id, job_id=job_id)
  for route in plan or []:
    aid = str(route.get("agent_id") or route.get("agentId") or "").strip()
    if not aid:
      continue
    name = route.get("agentName") or aid
    log_office_task(aid, f"「{name}」排队待执行", status="assigned")
    set_agent_status(aid, "assigned", task="orchestrate", session_id=session_id, job_id=job_id)
  return office_snapshot()


def on_handoff(route: dict[str, Any], session_id: str = "", job_id: str = "") -> dict[str, Any]:
  aid = route.get("agent_id") or orchestrator_id()
  name = route.get("agentName") or aid
  reset_office(session_id, job_id)
  log_office_task(aid, f"「{name}」已接手任务", status="assigned")
  return set_agent_status(aid, "assigned", task=route.get("reason") or "", session_id=session_id, job_id=job_id)


def on_tool_start(agent_id: str, tool_name: str) -> dict[str, Any]:
  log_office_task(agent_id, f"执行 {tool_name}", status="working", tool=tool_name)
  return set_agent_status(agent_id, "working", tool=tool_name)


def on_tool_done(agent_id: str, tool_name: str, ok: bool = True) -> dict[str, Any]:
  log_office_task(agent_id, f"{tool_name} {'完成' if ok else '失败'}", status="done" if ok else "error", tool=tool_name)
  return set_agent_status(agent_id, "assigned", tool="")


def on_chat_done(agent_id: str) -> dict[str, Any]:
  log_office_task(agent_id, "任务完成", status="done")
  snap = set_agent_status(agent_id, "idle", tool="", task="")
  # Reset all to idle after completion
  for entry in _office.get("agents", {}).values():
    if entry.get("status") != "idle":
      entry["status"] = "idle"
      entry["tool"] = ""
      entry["task"] = ""
  _touch()
  return snap
