"""Multi-specialist orchestration — parallel delegate + OP synthesis."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from openpilot.common.params import Params

from ai.agents.config import load_disabled_agent_ids
from ai.agents.registry import filter_tools_for_agent, get_agent, list_agents, orchestrator_id
from ai.agents.office import on_orchestration_start
from ai.agents.router import AgentRoute, _last_user_text, _score_agent, resolve_agent_route
from ai.core.chat.runner import ChatCancelled, run_chat_loop

EmitFn = Callable[[dict[str, Any]], Any]
ORCHESTRATE_MIN_SCORE = 2.5
MAX_SPECIALISTS = 3


def detect_orchestration_plan(
  body: dict[str, Any],
  *,
  driving: bool = False,
  pc_dev: bool = True,
  params: Params | None = None,
) -> list[AgentRoute] | None:
  """When multiple domains match, return specialist routes for sequential delegation."""
  if body.get("workflow") or body.get("workflow_id") or body.get("agentId") or body.get("agent_id"):
    return None
  if body.get("orchestrate") is False:
    return None
  if body.get("_orchestration_phase"):
    return None

  user_text = _last_user_text(body)
  if not user_text or len(user_text) < 8:
    return None

  disabled = load_disabled_agent_ids(params)
  scored: list[tuple[str, float]] = []
  for agent in list_agents(include_orchestrator=False):
    aid = agent["id"]
    if aid in disabled:
      continue
    if agent.get("pcOnly") and not pc_dev:
      continue
    full = get_agent(aid)
    if not full:
      continue
    score = _score_agent(full, user_text)
    if score >= ORCHESTRATE_MIN_SCORE:
      scored.append((aid, score))

  if len(scored) < 2:
    return None

  scored.sort(key=lambda x: -x[1])
  routes: list[AgentRoute] = []
  for aid, score in scored[:MAX_SPECIALISTS]:
    agent = get_agent(aid) or {}
    wf = ""
    if agent.get("workflows"):
      wf = agent["workflows"][0]
    routes.append(AgentRoute(aid, wf, "orchestrate", min(score / 6.0, 1.0)))
  return routes


def _tools_for_route(
  base_tools: list[dict[str, Any]] | None,
  route_dict: dict[str, Any],
) -> list[dict[str, Any]] | None:
  agent = get_agent(route_dict.get("agent_id") or route_dict.get("agentId") or "")
  if not agent or not base_tools:
    return base_tools
  return filter_tools_for_agent(base_tools, agent)


async def run_chat_with_agents(
  body: dict[str, Any],
  params: Params,
  emit: EmitFn,
  *,
  get_state_reader: Callable,
  get_tool_handlers: Callable,
  tools: list[dict[str, Any]] | None,
  max_tool_rounds: int = 64,
  is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
  plan = body.get("_orchestration_plan")
  if not plan or not isinstance(plan, list) or len(plan) < 2:
    return await run_chat_loop(
      body,
      params,
      emit,
      get_state_reader=get_state_reader,
      get_tool_handlers=get_tool_handlers,
      tools=tools,
      max_tool_rounds=max_tool_rounds,
      is_cancelled=is_cancelled,
    )

  session_id = str(body.get("sessionId") or body.get("session_id") or "").strip()
  job_id = str(body.get("_job_id") or body.get("jobId") or "").strip()
  office = on_orchestration_start(plan, session_id=session_id, job_id=job_id)
  await emit({
    "type": "orchestration_start",
    "plan": plan,
    "count": len(plan),
    "office": office,
  })
  try:
    from ai.core.sync.hub import broadcast_office
    await broadcast_office()
  except Exception:
    pass

  summaries: list[dict[str, Any]] = []

  async def _run_specialist(route_dict: dict[str, Any]) -> dict[str, Any]:
    if is_cancelled and is_cancelled():
      raise ChatCancelled()
    sub_tools = _tools_for_route(tools, route_dict)
    collected: list[str] = []

    async def sub_emit(event: dict[str, Any]) -> None:
      etype = event.get("type")
      aid = route_dict.get("agent_id") or route_dict.get("agentId") or ""
      if etype == "content":
        collected.append(event.get("delta") or "")
        return
      if etype in ("reasoning", "tool_call_delta"):
        return
      if etype in ("tool_call", "tool_result"):
        await emit({
          **event,
          "subagent": True,
          "collapsed": True,
          "agentId": aid,
        })
        return
      if etype in ("agent_handoff", "agent_status", "agent_office", "agent_done"):
        return
      if etype == "prompt_budget":
        return
      await emit(event)

    sub_body = {
      **body,
      "_agent_route": route_dict,
      "_orchestration_phase": "specialist",
    }
    result = await run_chat_loop(
      sub_body,
      params,
      sub_emit,
      get_state_reader=get_state_reader,
      get_tool_handlers=get_tool_handlers,
      tools=sub_tools,
      max_tool_rounds=min(24, max_tool_rounds),
      is_cancelled=is_cancelled,
    )
    if not result.get("ok"):
      raise RuntimeError(result.get("error") or "specialist failed")
    return {
      "agentId": route_dict.get("agent_id") or route_dict.get("agentId"),
      "agentName": route_dict.get("agentName", ""),
      "agentIcon": route_dict.get("agentIcon", "🤖"),
      "content": "".join(collected).strip(),
    }

  results = await asyncio.gather(
    *[_run_specialist(route_dict) for route_dict in plan],
    return_exceptions=True,
  )
  for item in results:
    if isinstance(item, Exception):
      if isinstance(item, ChatCancelled):
        raise item
      return {"ok": False, "error": str(item)}
    summaries.append(item)
    await emit({"type": "agent_summary", **item})

  if is_cancelled and is_cancelled():
    raise ChatCancelled()

  summary_block = "\n\n".join(
    f"【{s.get('agentName') or s.get('agentId')}】\n{s.get('content') or '（已通过工具完成子任务）'}"
    for s in summaries
  )
  synth_messages = list(body.get("messages") or [])
  synth_messages.append({
    "role": "user",
    "content": (
      "各内置专员已完成分工子任务。请用简洁、可执行的中文向用户汇总结论与下一步，"
      "不要重复工具原始 JSON：\n\n" + summary_block
    ),
  })
  op_route = resolve_agent_route({"messages": synth_messages}, driving=False, pc_dev=True).to_dict()
  op_route["agent_id"] = orchestrator_id()
  op_agent = get_agent(orchestrator_id()) or {}
  op_route["agentName"] = op_agent.get("name", "OP 主调度")
  op_route["agentIcon"] = op_agent.get("icon", "🎯")

  synth_body = {
    **body,
    "messages": synth_messages,
    "_agent_route": op_route,
    "_orchestration_phase": "synthesis",
    "_skip_handoff": False,
    "workflow": "",
  }
  await emit({"type": "orchestration_synthesis", "agentId": orchestrator_id()})

  return await run_chat_loop(
    synth_body,
    params,
    emit,
    get_state_reader=get_state_reader,
    get_tool_handlers=get_tool_handlers,
    tools=None,
    max_tool_rounds=min(12, max_tool_rounds),
    is_cancelled=is_cancelled,
  )
