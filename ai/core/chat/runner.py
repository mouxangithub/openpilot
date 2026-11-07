"""Shared chat + tool-loop runner for SSE and background jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from openpilot.common.params import Params

from ai.core.llm.client import AIConfig, expand_messages_for_api
from ai.core.llm.model_router import resolve_chat_config
from ai.skills.snapshot import get_skills_prompt
from ai.core.chat.compaction import maybe_compact_messages
from ai.hooks.registry import run_hooks
from ai.system.admin import is_admin_mode
from ai.selfdrive.state import StateReader
from ai.tools.memory_store import format_memory_prompt
from ai.tools.workflows import workflow_system_prompt
from ai.common.prompt_budget import PromptBudget
from ai.agents.prompts import agent_system_prompt
from ai.core.agent.agent import Agent
from ai.core.agent.state import ChatCancelled

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

_MAX_TOOL_ROUNDS = 64
_TOOL_TIMEOUT_SECONDS = 300.0
_LLM_STREAM_TIMEOUT_SECONDS = 120.0


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
    "You are a helpful assistant for the openpilot driving assistant running on the device. " +
    "You have full access to read/write openpilot files, params, shell, and diagnostics. " +
    "You must never send steering, brake, or throttle commands."
  )
  labeled_parts.append(("base", base_prompt, budget.system_max, 100))

  try:
    from ai.core.wspace.safety_rules import safety_rules_prompt_block
    labeled_parts.append(("safety_rules", safety_rules_prompt_block(), 800, 99))
  except Exception:
    pass

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
    from ai.system.paths import workspace_path
    from ai.attachment.store import AttachmentStore
    from ai.attachment.context import attachment_context_prompt
    import re as _re
    _store = AttachmentStore(workspace_path("ai_attachments"))
    ids: list[str] = []
    explicit = body.get("attachments") or []
    if isinstance(explicit, list):
      for aid in explicit:
        if isinstance(aid, str) and aid:
          ids.append(aid)
    for msg in messages:
      if msg.get("role") == "user":
        content = msg.get("content", "")
        if isinstance(content, str):
          ids += _re.findall(r"attachment://([^\s)\]}]+)", content)
    dedup: list[str] = []
    seen: set[str] = set()
    for aid in ids:
      if aid not in seen:
        seen.add(aid)
        dedup.append(aid)
    if dedup:
      attach_block = attachment_context_prompt(_store, dedup)
      if attach_block:
        labeled_parts.append(("attachments", attach_block, budget.memory_max, 60))
  except Exception:
    pass

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
      ("# OP 车主模式\n" +
      "用户是不懂编程、不懂汽修的普通车主。请全程使用通俗中文，避免参数代号堆砌；" +
      "每次改设置前先用大白话解释「改什么、为什么、有什么感觉变化」，并等待用户在界面确认。" +
      "禁止未经确认直接 write_params(confirm=true)。" +
      "可用 consumer_lexicon 含义：跟车距离、变道风格、加减速舒适度等。"),
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
    ("Knowledge base: do not assume prior doc context. When you need manuals, wiki, or saved notes, " +
    "call search_knowledge_base with your own query and limit (repeat with different queries if needed). " +
    "Use list_knowledge_docs to see what is indexed."),
    300,
    50,
  ))
  labeled_parts.append((
    "tool_hint",
    ("Use available tools proactively to diagnose and complete the task without asking for step-by-step confirmation. " +
    "Proceed with writes and diagnostics as needed. " +
    "For specialized tools not in your list, call search_tools then load_tool first."),
    250,
    45,
  ))
  labeled_parts.append((
    "memory_mandatory",
    ("Memory protocol (mandatory): if the user shared durable preferences, vehicle facts, tuning outcomes, " +
    "or workflow steps worth reusing, you MUST call append_daily_memory, update_workspace_file (memory/user), " +
    "and/or update_agent_memory before finishing — do not only promise to remember. " +
    "When workspace_health reports sparse files, enrich USER.md / MEMORY.md from the conversation."),
    350,
    55,
  ))
  if is_admin_mode(params):
    labeled_parts.append((
      "admin",
      ("Open mode (ai_admin_mode=1): all tools and writes are allowed at any time. " +
      "Use read_file/write_file/list_directory/run_shell_command freely on openpilot + AGNOS paths. " +
      "The ONLY hard rule: never send steering/brake/throttle/actuator commands."),
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
  session_log_path: str | None = None,
) -> dict[str, Any]:
  """Run chat with tool loop; delegates to Agent."""
  config = body.get("_config")
  if config is None:
    from ai.server.deps import read_ai_config
    config = read_ai_config(params)

  route_data = body.get("_agent_route") or {}
  agent_id = str(route_data.get("agent_id") or route_data.get("agentId") or "op").strip()
  session_id = str(body.get("sessionId") or body.get("session_id") or "").strip()

  agent = Agent(
    session_id=session_id,
    agent_id=agent_id,
    params=params,
    config=config,
    body=body,
    emit=emit,
    get_state_reader=get_state_reader,
    get_tool_handlers=get_tool_handlers,
    tools=tools,
    max_tool_rounds=max_tool_rounds,
    tool_timeout=_TOOL_TIMEOUT_SECONDS,
    stream_timeout=_LLM_STREAM_TIMEOUT_SECONDS,
    is_cancelled=is_cancelled,
    concurrent_tools=True,
    session_log_path=session_log_path,
  )

  # Unified lifecycle bookkeeping (AgentFactory/Registry alignment).
  from ai.core.agent.registry import agent_registry
  job_id = str(body.get("_job_id") or body.get("jobId") or "").strip()

  async def _cancel() -> bool:
    try:
      agent.cancel()
      return True
    except Exception:
      return False

  entry = agent_registry.resume(
    session_id,
    agent_id,
    job_id=job_id,
    meta={"mode": str(body.get("mode") or body.get("chatMode") or "")},
    cancel_fn=_cancel,
  )
  try:
    return await agent.run()
  finally:
    status = "done"
    if getattr(agent, "state", None) is not None and agent.state.is_cancelled():
      status = "cancelled"
    elif entry is not None:
      agent_registry.mark_done(session_id, status)
