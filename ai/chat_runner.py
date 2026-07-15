"""Shared chat + tool-loop runner for SSE and background jobs."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from openpilot.common.params import Params

from ai.client import AIConfig, chat_completion, expand_messages_for_api
from ai.embedding import load_embedding_config
from ai.model_router import resolve_chat_config
from ai.skills.loader import build_skills_prompt, load_enabled_skill_ids
from ai.system.admin import is_admin_mode
from ai.selfdrive.state import StateReader
from ai.tools.memory_store import format_memory_prompt
from ai.tools.rag_store import format_rag_prompt, search_documents
from ai.tools.workflows import workflow_system_prompt
from ai.tools.agent_tools import execute_tool_async
from ai.usage_log import record_usage

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

_MAX_TOOL_ROUNDS = 64


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
  messages = expand_messages_for_api(raw_messages)

  workflow_id = str(body.get("workflow", "") or body.get("workflow_id", "")).strip()
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

  system_parts: list[str] = []
  if config.system_prompt:
    system_parts.append(config.system_prompt)
  else:
    system_parts.append(
      "You are a helpful assistant for the openpilot driving assistant running on the device. "
      "You have full access to read/write openpilot files, params, shell, and diagnostics. "
      "You must never send steering, brake, or throttle commands."
    )

  skills_block = build_skills_prompt(
    load_enabled_skill_ids(params),
    brand=drive_state.brand or "",
    available_tools=available_tool_names,
  )
  if skills_block:
    system_parts.append(skills_block)

  wf_prompt = workflow_system_prompt(workflow_id) if workflow_id else ""
  if wf_prompt:
    system_parts.append(wf_prompt)

  memory_block = format_memory_prompt(params)
  if memory_block:
    system_parts.append(memory_block)

  embed_cfg = load_embedding_config(params, config)
  rag_res = await search_documents(params, last_user_text, limit=3, embed_config=embed_cfg)
  rag_block = format_rag_prompt(params, query=last_user_text, limit=3, hits=rag_res.get("hits"))
  if rag_block:
    system_parts.append(rag_block)

  system_parts.append(
    "Use available tools proactively to diagnose and complete the task without asking for step-by-step confirmation. "
    "Proceed with writes and diagnostics as needed."
  )
  if is_admin_mode(params):
    system_parts.append(
      "Open mode (ai_admin_mode=1): all tools and writes are allowed at any time. "
      "Use read_file/write_file/list_directory/run_shell_command freely on openpilot + AGNOS paths. "
      "The ONLY hard rule: never send steering/brake/throttle/actuator commands."
    )

  if body.get("includeState", True):
    state = get_state_reader().update(timeout=0)
    system_parts.append(state.summary_line())

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
    from ai.client import load_config_from_params
    config = load_config_from_params(params)

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

  def _check_cancel() -> None:
    if is_cancelled and is_cancelled():
      raise ChatCancelled()

  total_usage: dict[str, Any] | None = None
  handlers = get_tool_handlers()

  for _round in range(max_tool_rounds):
    _check_cancel()
    pending_tool_calls: dict[int, dict[str, Any]] = {}
    assistant_content = ""
    assistant_reasoning = ""

    async for chunk in chat_completion(config, chat_messages, tools=tools):
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
        await emit({"type": "content", "delta": chunk.content})

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
      assistant_msg["content"] = assistant_content
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
      })
      result = await execute_tool_async(handlers, name, arguments)
      await emit({
        "type": "tool_result",
        "id": tc.get("id", ""),
        "name": name,
        "result": result,
      })
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
    )
    await emit({"type": "usage", "usage": total_usage})

  await emit({
    "type": "done",
    "resolvedModel": config.model,
  })
  return {"ok": True, "resolvedModel": config.model}
