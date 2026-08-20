"""Shared chat + tool-loop runner for SSE and background jobs."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from openpilot.common.params import Params

from ai.core.llm.client import AIConfig, expand_messages_for_api
from ai.core.chat.sanitize import strip_leaked_tool_calls
from ai.core.llm.model_router import chat_completion_with_failover, resolve_chat_config
from ai.skills.snapshot import get_skills_prompt
from ai.core.chat.compaction import maybe_compact_messages
from ai.hooks.registry import run_hooks
from ai.system.admin import is_admin_mode
from ai.selfdrive.state import StateReader
from ai.tools.memory_store import format_memory_prompt
from ai.tools.workflows import workflow_system_prompt
from ai.common.prompt_budget import PromptBudget
from ai.tools.deferred_loading import (
  handle_load_tool,
  handle_search_tools,
  resolve_active_tools,
  session_key as deferred_session_key,
)
from ai.tools.agent_tools import execute_tool_async
from ai.core.llm.usage import record_usage
from ai.agents.prompts import agent_system_prompt
from ai.agents.office import on_handoff, on_tool_start, on_tool_done, on_chat_done, set_agent_status

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

_MAX_TOOL_ROUNDS = 64


async def _broadcast_office_ws() -> None:
  try:
    from ai.core.sync.hub import broadcast_office
    await broadcast_office()
  except Exception:
    pass


async def _emit_with_office(emit: EmitFn, event: dict[str, Any]) -> None:
  await emit(event)
  if event.get("office") is not None or event.get("type") in {
    "agent_handoff", "agent_office", "agent_status", "agent_done", "orchestration_start",
  }:
    await _broadcast_office_ws()


class ChatCancelled(Exception):
  pass


async def build_chat_messages(
  body: dict[str, Any],
  params: Params,
  config: AIConfig,
  *,
  get_state_reader: Callable[[], StateReader],
  tools: list[dict[str, Any]] | None,
  available_tool_names: set[str] | None,
) -> tuple[AIConfig, list[dict[str, Any]]]:
  raw_messages = body.get("messages", [])
  force_compact = bool(body.get("compact") or body.get("_force_compaction"))
  if not body.get("_skip_compaction"):
    raw_messages = await maybe_compact_messages(
      raw_messages,
      params,
      config,
      session_id=str(body.get("sessionId") or body.get("session_id") or ""),
      force=force_compact,
    )
  messages = expand_messages_for_api(raw_messages)

  workflow_id = str(body.get("workflow", "") or body.get("workflow_id", "")).strip()
  route_data = body.get("_agent_route") or {}
  agent_id = str(route_data.get("agent_id") or route_data.get("agentId") or "").strip()
  drive_state = get_state_reader().update(timeout=0)

  last_user_text = ""
  for msg in reversed(messages):
    if msg.get("role") == "user":
      c = msg.get("content", "")
      last_user_text = c if isinstance(c, str) else str(c)
      break

  config = resolve_chat_config(
    config,
    params,
    workflow_id=workflow_id,
    user_text=last_user_text,
    body=body,
  )

  budget = PromptBudget.for_model(getattr(config, "model", "") or "", params)
  labeled_parts: list[tuple[str, str, int, int]] = []

  base_prompt = config.system_prompt or (
    "You are a helpful assistant for the openpilot driving assistant running on the device. "
    "You have full access to read/write openpilot files, params, shell, and diagnostics. "
    "You must never send steering, brake, or throttle commands."
  )
  labeled_parts.append(("base", base_prompt, budget.system_max, 100))

  agent_prompt = agent_system_prompt(agent_id, route_data) if agent_id else ""
  if agent_prompt:
    labeled_parts.append(("agent", agent_prompt, 800, 90))

  skills_block = get_skills_prompt(
    params,
    brand=drive_state.brand or "",
    available_tools=available_tool_names,
    query=last_user_text,
  )
  if skills_block:
    labeled_parts.append(("skills", skills_block, budget.skills_max, 80))

  try:
    from ai.tools.skill_learning import learned_skills_prompt
    learned = learned_skills_prompt(params)
    if learned:
      labeled_parts.append(("learned_skills", learned, 600, 70))
  except Exception:
    pass

  try:
    from ai.tools.memory_protocol import memory_protocol_prompt_block
    proto = memory_protocol_prompt_block()
    if proto:
      labeled_parts.append(("memory_protocol", proto, 500, 95))
  except Exception:
    pass

  workspace_blocks: list[str] = []
  try:
    from ai.core.wspace.store import workspace_prompt_blocks
    workspace_blocks = list(workspace_prompt_blocks())
  except Exception:
    pass
  if workspace_blocks:
    labeled_parts.append(("workspace", "\n\n".join(workspace_blocks), 1200, 75))

  try:
    from ai.tools.daily_memory import build_daily_memory_prompt_block
    daily_block = build_daily_memory_prompt_block()
    if daily_block:
      labeled_parts.append(("daily_memory", daily_block, 800, 72))
  except Exception:
    pass

  try:
    from ai.fork.fork_prompt import fork_context_prompt_block
    fork_block = fork_context_prompt_block()
    if fork_block:
      labeled_parts.append(("fork", fork_block, 600, 60))
  except Exception:
    pass

  wf_prompt = workflow_system_prompt(workflow_id) if workflow_id else ""
  if wf_prompt:
    labeled_parts.append(("workflow", wf_prompt, budget.workflow_max, 85))

  consumer_mode = bool(body.get("consumerMode") or body.get("consumer_mode"))
  if consumer_mode:
    labeled_parts.append((
      "consumer",
      "# OP 车主模式\n"
      "用户是不懂编程、不懂汽修的普通车主。请全程使用通俗中文，避免参数代号堆砌；"
      "每次改设置前先用大白话解释「改什么、为什么、有什么感觉变化」，并等待用户在界面确认。"
      "禁止未经确认直接 write_params(confirm=true)。"
      "可用 consumer_lexicon 含义：跟车距离、变道风格、加减速舒适度等。",
      600,
      88,
    ))

  memory_block = format_memory_prompt(params)
  if memory_block:
    labeled_parts.append(("memory", memory_block, budget.memory_max, 78))

  try:
    from ai.tools.workspace_enrich import enrichment_prompt_block
    enrich = enrichment_prompt_block(params)
    if enrich:
      labeled_parts.append(("enrichment", enrich, 500, 65))
  except Exception:
    pass

  labeled_parts.append((
    "knowledge_hint",
    "Knowledge base: do not assume prior doc context. When you need manuals, wiki, or saved notes, "
    "call search_knowledge_base with your own query and limit (repeat with different queries if needed). "
    "Use list_knowledge_docs to see what is indexed.",
    300,
    50,
  ))
  labeled_parts.append((
    "tool_hint",
    "Use available tools proactively to diagnose and complete the task without asking for step-by-step confirmation. "
    "Proceed with writes and diagnostics as needed. "
    "For specialized tools not in your list, call search_tools then load_tool first.",
    250,
    45,
  ))
  labeled_parts.append((
    "memory_mandatory",
    "Memory protocol (mandatory): if the user shared durable preferences, vehicle facts, tuning outcomes, "
    "or workflow steps worth reusing, you MUST call append_daily_memory, update_workspace_file (memory/user), "
    "and/or update_agent_memory before finishing — do not only promise to remember. "
    "When workspace_health reports sparse files, enrich USER.md / MEMORY.md from the conversation.",
    350,
    55,
  ))
  if is_admin_mode(params):
    labeled_parts.append((
      "admin",
      "Open mode (ai_admin_mode=1): all tools and writes are allowed at any time. "
      "Use read_file/write_file/list_directory/run_shell_command freely on openpilot + AGNOS paths. "
      "The ONLY hard rule: never send steering/brake/throttle/actuator commands.",
      300,
      40,
    ))

  if body.get("includeState", True):
    state = get_state_reader().update(timeout=0)
    labeled_parts.append(("vehicle_state", state.summary_line(), 200, 30))

  system_parts, budget_report = budget.assemble_system_parts(labeled_parts)
  body["_prompt_budget"] = budget_report

  system_msg = {"role": "system", "content": "\n\n".join(system_parts)}
  return config, [system_msg] + messages


async def run_chat_loop(
  body: dict[str, Any],
  params: Params,
  emit: EmitFn,
  *,
  get_state_reader: Callable[[], StateReader],
  get_tool_handlers: Callable[[], dict[str, Any]],
  tools: list[dict[str, Any]] | None,
  max_tool_rounds: int = _MAX_TOOL_ROUNDS,
  is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
  """Run chat with tool loop; emit event dicts (same schema as SSE)."""
  config = body.get("_config")
  if config is None:
    from ai.server.deps import read_ai_config
    config = read_ai_config(params)

  session_id = str(body.get("sessionId") or body.get("session_id") or "").strip()
  job_id = str(body.get("_job_id") or body.get("jobId") or "").strip()

  _orig_emit = emit

  async def emit(event: dict[str, Any]) -> None:
    if session_id:
      try:
        from ai.tools.domains.platform.transcript_store import append_event
        append_event(session_id, event, job_id=job_id)
      except Exception:
        pass
    await _orig_emit(event)

  available_tool_names = None
  if tools:
    available_tool_names = {t.get("function", {}).get("name", "") for t in tools}

  config, chat_messages = await build_chat_messages(
    body,
    params,
    config,
    get_state_reader=get_state_reader,
    tools=tools,
    available_tool_names=available_tool_names,
  )

  route_data = body.get("_agent_route") or {}
  agent_id = str(route_data.get("agent_id") or route_data.get("agentId") or "op").strip()
  defer_key = deferred_session_key(session_id, job_id)

  if not body.get("_skip_handoff"):
    handoff = {**route_data, "type": "agent_handoff"}
    office = on_handoff(route_data, session_id=session_id, job_id=job_id)
    await _emit_with_office(emit, handoff)
    await _emit_with_office(emit, {"type": "agent_office", "office": office})

  budget_report = body.get("_prompt_budget")
  if budget_report:
    await emit({"type": "prompt_budget", "budget": budget_report})

  def _check_cancel() -> None:
    if is_cancelled and is_cancelled():
      raise ChatCancelled()

  total_usage: dict[str, Any] | None = None
  handlers = get_tool_handlers()
  all_tools = tools

  for _round in range(max_tool_rounds):
    _check_cancel()
    active_tools = resolve_active_tools(all_tools, defer_key, params) if all_tools else None
    if body.get("trace"):
      await emit({
        "type": "trace",
        "round": _round,
        "agentId": agent_id,
        "message": f"chat round {_round + 1}",
      })
    hook_round = await run_hooks("before_chat_round", {
      "round": _round,
      "agent_id": agent_id,
      "session_id": session_id,
      "body": body,
    })
    if hook_round.get("block"):
      await emit({"type": "error", "error": hook_round.get("reason") or "Blocked by hook"})
      return {"ok": False, "error": hook_round.get("reason") or "blocked"}
    pending_tool_calls: dict[int, dict[str, Any]] = {}
    assistant_content = ""
    assistant_reasoning = ""

    async for chunk, active_cfg in chat_completion_with_failover(
      config, params, chat_messages, tools=active_tools, body=body,
    ):
      config = active_cfg
      _check_cancel()
      if chunk.error:
        await emit({"type": "error", "error": chunk.error})
        return {"ok": False, "error": chunk.error}

      if chunk.done:
        break

      if chunk.usage:
        total_usage = chunk.usage

      if chunk.reasoning_content:
        assistant_reasoning += chunk.reasoning_content
        await emit({"type": "reasoning", "delta": chunk.reasoning_content})

      if chunk.content:
        assistant_content += chunk.content
        stripped = strip_leaked_tool_calls(chunk.content)
        if stripped:
          await emit({"type": "content", "delta": stripped})

      if chunk.tool_calls:
        for tc in chunk.tool_calls:
          idx = tc.get("index", 0)
          if idx not in pending_tool_calls:
            pending_tool_calls[idx] = {
              "id": tc.get("id", ""),
              "type": tc.get("type", "function"),
              "function": {"name": "", "arguments": ""},
            }
          fn = tc.get("function", {}) or {}
          if fn.get("name"):
            pending_tool_calls[idx]["function"]["name"] += fn["name"]
          if fn.get("arguments"):
            pending_tool_calls[idx]["function"]["arguments"] += fn["arguments"]
          await emit({"type": "tool_call_delta", "delta": tc})

    assistant_msg: dict[str, Any] = {"role": "assistant"}
    if assistant_content:
      cleaned_content = strip_leaked_tool_calls(assistant_content)
      if cleaned_content:
        assistant_msg["content"] = cleaned_content
      elif pending_tool_calls:
        assistant_msg["content"] = None
    if assistant_reasoning:
      assistant_msg["reasoning_content"] = assistant_reasoning
    if pending_tool_calls:
      tool_list = []
      for i in sorted(pending_tool_calls.keys()):
        tc = pending_tool_calls[i]
        if not tc.get("id"):
          fn_name = (tc.get("function") or {}).get("name", "tool")
          tc["id"] = f"{fn_name}:{i}"
        tool_list.append(tc)
      assistant_msg["tool_calls"] = tool_list
    chat_messages.append(assistant_msg)

    if not pending_tool_calls:
      break

    for tc in assistant_msg["tool_calls"]:
      _check_cancel()
      fn = tc.get("function", {})
      name = fn.get("name", "")
      arguments = fn.get("arguments", "")
      await emit({
        "type": "tool_call",
        "id": tc.get("id", ""),
        "name": name,
        "arguments": arguments,
        "agentId": agent_id,
      })
      office = on_tool_start(agent_id, name)
      await _emit_with_office(emit, {"type": "agent_status", "agentId": agent_id, "status": "working", "tool": name, "office": office})
      hook_ctx = await run_hooks("before_tool_call", {
        "name": name,
        "arguments": arguments,
        "agent_id": agent_id,
        "session_id": session_id,
        "body": {**body, "_get_state_reader": get_state_reader, "_params": params},
      })
      if hook_ctx.get("block"):
        result = {"ok": False, "error": hook_ctx.get("reason") or "Tool blocked by hook"}
      elif name == "search_tools":
        try:
          args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
          args = {}
        result = handle_search_tools(args, session_id=session_id, job_id=job_id)
      elif name == "load_tool":
        try:
          args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
          args = {}
        result = handle_load_tool(args, session_id=session_id, job_id=job_id)
      else:
        result = await execute_tool_async(handlers, name, arguments)
      hook_ctx = await run_hooks("after_tool_call", {
        **hook_ctx,
        "result": result,
        "session_id": session_id,
        "name": name,
        "body": {**body, "_params": params},
      })
      result = hook_ctx.get("result", result)
      if artifact := hook_ctx.get("canvas_artifact"):
        await emit({"type": "canvas", "artifact": artifact, "sessionId": session_id})
      ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
      office = on_tool_done(agent_id, name, ok=ok)
      await emit({
        "type": "tool_result",
        "id": tc.get("id", ""),
        "name": name,
        "result": result,
        "agentId": agent_id,
        "verbose": bool(body.get("verbose")),
      })
      await _emit_with_office(emit, {"type": "agent_status", "agentId": agent_id, "status": "assigned", "office": office})
      chat_messages.append({
        "role": "tool",
        "tool_call_id": tc.get("id", ""),
        "content": json.dumps(result, ensure_ascii=False, default=str),
      })

  if total_usage:
    record_usage(
      params,
      total_usage,
      provider=config.provider,
      model=config.model,
      source="chat",
      session_id=session_id,
      job_id=job_id,
    )
    await emit({"type": "usage", "usage": total_usage})

  if session_id:
    try:
      from ai.tools.session_index import append_to_session_index
      for msg in reversed(chat_messages):
        if msg.get("role") in ("user", "assistant"):
          append_to_session_index(
            session_id,
            str(msg.get("role")),
            msg.get("content"),
            title=str(route_data.get("agentName") or agent_id),
          )
          if msg.get("role") == "user":
            break
    except Exception:
      pass

  if not body.get("_orchestration_phase") == "specialist":
    last_user_text = ""
    for msg in reversed(chat_messages):
      if msg.get("role") == "user":
        c = msg.get("content", "")
        last_user_text = c if isinstance(c, str) else str(c)
        break
    try:
      from ai.core.runtime.evolution_pipeline import run_post_chat_pipeline
      from ai.tools.memory_protocol import conversation_tail
      await run_post_chat_pipeline(
        params,
        session_id=str(session_id or ""),
        last_user_text=last_user_text,
        recent_messages=conversation_tail(chat_messages),
        config=config,
      )
    except Exception:
      pass

  if body.get("_orchestration_phase") == "specialist":
    office = set_agent_status(agent_id, "idle")
    await _emit_with_office(emit, {"type": "agent_status", "agentId": agent_id, "status": "idle", "office": office})
  else:
    office = on_chat_done(agent_id)
    await _emit_with_office(emit, {"type": "agent_done", "agentId": agent_id, "office": office})
  await emit({
    "type": "done",
    "resolvedModel": config.model,
    "agentId": agent_id,
  })
  return {"ok": True, "resolvedModel": config.model, "agentId": agent_id}
