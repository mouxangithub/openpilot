"""Unified Agent facade: state machine + session log + tool pipeline + cancellation.

The Agent class is the single entry point for driving one session. It owns:
- AgentState (lifecycle, inbox, cancellation)
- SessionLog (append-only source of truth)
- ToolPipeline (guard + async/sync execution)
- event emission and office integration

It replaces the procedural run_chat_loop while keeping the same SSE event schema.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

from ai.core.agent.state import AgentState, CancelCause, CancelCauseKind, ChatCancelled
from ai.core.chat.sanitize import strip_leaked_tool_calls
from ai.core.llm.client import AIConfig
from ai.core.llm.model_router import chat_completion_with_failover
from ai.core.session.log import EventType, RequestHeader, SessionLog, SurfaceOp
from ai.core.tools.pipeline import ToolPipeline

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]
StateReaderFn = Callable[[], Any]
ToolHandlersFn = Callable[[], dict[str, Any]]

_MAX_TOOL_RESULT_CHARS = 12_000


def _truncate_tool_content(content: str, *, max_chars: int = _MAX_TOOL_RESULT_CHARS) -> str:
  if len(content) <= max_chars:
    return content
  return content[:max_chars] + f"\n…[truncated, {len(content) - max_chars} chars omitted]"


class Agent:
  """Drives one agent session from first message through turn completion."""

  def __init__(
    self,
    session_id: str,
    agent_id: str,
    params: Params,
    config: AIConfig,
    body: dict[str, Any],
    emit: EmitFn,
    *,
    get_state_reader: StateReaderFn,
    get_tool_handlers: ToolHandlersFn,
    tools: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = 64,
    tool_timeout: float = 300.0,
    stream_timeout: float = 120.0,
    is_cancelled: Callable[[], bool] | None = None,
    concurrent_tools: bool = True,
    session_log_path: str | None = None,
    ai_use_agent_loop: bool = True,
  ) -> None:
    self.session_id = session_id
    self.agent_id = agent_id
    self.job_id = str(body.get("_job_id") or body.get("jobId") or "").strip()
    self.params = params
    self.config = config
    self.body = body
    self._emit = emit
    self.get_state_reader = get_state_reader
    self.get_tool_handlers = get_tool_handlers
    self.all_tools = tools
    self.max_tool_rounds = max(max_tool_rounds, 1)
    self.tool_timeout = tool_timeout
    self.stream_timeout = stream_timeout
    self.is_cancelled_callback = is_cancelled
    self.concurrent_tools = concurrent_tools
    self.verbose = bool(body.get("verbose"))
    self.ai_use_agent_loop = ai_use_agent_loop

    self.state = AgentState(agent_id, session_id)
    self.log = SessionLog(session_id, persist_path=session_log_path)
    self.pipeline = ToolPipeline(get_tool_handlers())
    self._install_spill_post_hook()
    try:
      from ai.core.tools.guard import install_hook_guards
      install_hook_guards(
        self.pipeline,
        agent_id=agent_id,
        session_id=session_id,
        params=params,
        body=body,
        get_state_reader=get_state_reader,
      )
    except Exception:
      pass
    self._total_usage: dict[str, Any] | None = None
    self._chat_messages: list[dict[str, Any]] = []
    self._resolved_model: str | None = None
    self._handoff_emitted = False

  @property
  def is_cancelled(self) -> bool:
    if self.state.is_cancelled():
      return True
    if self.is_cancelled_callback is not None and self.is_cancelled_callback():
      return True
    return False

  def cancel(self, kind: CancelCauseKind = CancelCauseKind.USER, reason: str = "") -> None:
    self.state.cancel(CancelCause(kind, reason))

  def _install_spill_post_hook(self) -> None:
    """Register a post-execute waterfall that externalizes oversized tool results.

    Port of dsh `spill-policy`: registered as the OUTERMOST waterfall stage, so
    it awaits ``next()`` (downstream listeners settle the result first) and then
    bounds whatever content was accepted. Only plain-text content spills; value
    replacements, nested (parent) calls, and read/grep tools pass through; any
    spill failure keeps the original inline result (best-effort).
    """
    try:
      from ai.core.tools.pipeline import ToolResult

      def _skip(name: str) -> bool:
        lowered = (name or "").lower()
        return lowered in ("read", "read_file", "read_file_text") or "grep" in lowered

      async def _spill(exec_ctx, result: ToolResult, next_stage) -> ToolResult:
        name = getattr(exec_ctx, "name", "")
        downstream = await next_stage()
        # read → spill → read again loop: never spill read-family tools.
        if _skip(name):
          return downstream
        # Only accepted results spill; corrective/blocked decisions pass.
        if not downstream.ok:
          return downstream
        # Nested composite (parent) calls skip the model-facing arm.
        if exec_ctx.extra.get("parent") is not None:
          return downstream

        from ai.tools.result_externalize import externalize_if_needed, spill_text_if_needed
        text = downstream.content
        if text is None:
          # Non-plain-text result: fall back to JSON externalization of the
          # dict value (keeps existing behavior for structured results).
          value = downstream.value
          if isinstance(value, dict) and value.get("ok") is not False:
            pointer, _artifact = externalize_if_needed(
              value,
              session_id=self.session_id,
              tool_name=name,
              params=self.params,
            )
            if pointer is not value:
              return ToolResult(
                ok=True, value=pointer, content=downstream.content,
                block=pointer, meta=downstream.meta,
              )
          return downstream

        replaced, ref = spill_text_if_needed(
          text,
          session_id=self.session_id,
          tool_name=name,
          call_id=exec_ctx.call_id,
          params=self.params,
        )
        if replaced is None:
          return downstream
        pointer = {
          "ok": True,
          "externalized": True,
          "ref": ref["ref"],
          "path": ref["path"],
          "tool": name,
          "size_bytes": ref["size_bytes"],
          "summary": text[:200],
          "preview": replaced,
          "hint": ref["hint"],
        }
        return ToolResult(
          ok=True,
          value=pointer,
          content=replaced,
          block={"type": "text", "text": replaced},
          meta=downstream.meta,
        )

      self.pipeline.add_post_waterfall(_spill)
    except Exception as e:
      cloudlog.warning(f"aid: spill post hook install failed: {e}")

  def _check_cancel(self) -> None:
    if self.is_cancelled:
      cause = self.state.cancel_cause() or CancelCause(CancelCauseKind.USER, "external cancel flag")
      raise ChatCancelled(cause)

  async def emit(self, event: dict[str, Any]) -> None:
    """Emit an event to the consumer and append to transcript store."""
    self._check_cancel()
    if self.session_id:
      try:
        from ai.tools.domains.platform.transcript_store import append_event
        append_event(self.session_id, event, job_id=self.job_id)
      except Exception:
        pass
    await self._emit(event)

  async def emit_with_office(self, event: dict[str, Any]) -> None:
    """Emit event plus broadcast office WS when it touches agent office state."""
    await self.emit(event)
    if event.get("office") is not None or event.get("type") in {
      "agent_handoff", "agent_office", "agent_status", "agent_done", "orchestration_start",
    }:
      try:
        from ai.core.sync.hub import broadcast_office
        await broadcast_office()
      except Exception:
        pass

  async def _build_messages(self) -> tuple[AIConfig, list[dict[str, Any]]]:
    from ai.core.chat.runner import build_chat_messages
    available_tool_names = None
    if self.all_tools:
      available_tool_names = {t.get("function", {}).get("name", "") for t in self.all_tools}
    return await build_chat_messages(
      self.body,
      self.params,
      self.config,
      get_state_reader=self.get_state_reader,
      tools=self.all_tools,
      available_tool_names=available_tool_names,
    )

  def _active_tools(self) -> list[dict[str, Any]] | None:
    if not self.all_tools:
      return None
    try:
      from ai.tools.harness_tools import _mcp_handlers, _mcp_schemas
      for name, handler in _mcp_handlers.items():
        if name not in self.pipeline._tools:
          self.pipeline.register_primitive(name, handler)
      known = {t.get("function", {}).get("name") for t in self.all_tools}
      self.all_tools.extend(t for t in _mcp_schemas if t.get("function", {}).get("name") not in known)
    except Exception:
      pass
    try:
      from ai.tools.deferred_loading import resolve_active_tools, session_key as deferred_session_key
      defer_key = deferred_session_key(self.session_id, self.job_id)
      return resolve_active_tools(self.all_tools, defer_key, self.params)
    except Exception:
      return self.all_tools

  async def _configure_request_header(self, system: str | None, tools: list[dict[str, Any]] | None) -> None:
    header = RequestHeader(
      provider=self.config.provider or "",
      model=self.config.model or "",
      system=system,
      tools=tools,
    )
    self.log.append(EventType.REQUEST_HEADER, {"header": header.to_dict(), "reason": "initial"})

  async def _seed_user_messages(self) -> None:
    for msg in self._chat_messages:
      if msg.get("role") == "user":
        self.log.append(
          EventType.USER_MESSAGE,
          {"role": "user", "content": msg.get("content", "")},
          surface_op=SurfaceOp.APPEND,
        )

  async def _maybe_emit_handoff(self) -> None:
    if self.body.get("_skip_handoff"):
      return
    route_data = self.body.get("_agent_route") or {}
    handoff = {**route_data, "type": "agent_handoff"}
    try:
      from ai.agents.office import on_handoff
      office = on_handoff(route_data, session_id=self.session_id, job_id=self.job_id)
      await self.emit_with_office(handoff)
      await self.emit_with_office({"type": "agent_office", "office": office})
      self._handoff_emitted = True
    except Exception:
      await self.emit(handoff)

  async def _run_before_chat_round_hook(self, round_idx: int) -> dict[str, Any] | None:
    try:
      from ai.hooks.registry import run_hooks
      return await run_hooks("before_chat_round", {
        "round": round_idx,
        "agent_id": self.agent_id,
        "session_id": self.session_id,
        "body": self.body,
      })
    except Exception as e:
      cloudlog.warning(f"aid: before_chat_round hook failed: {e}")
      return None

  async def _stream_round(
    self,
    round_idx: int,
    active_tools: list[dict[str, Any]] | None,
  ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Stream one assistant turn. Returns (assistant_msg, pending_tool_calls_list) or raises ChatCancelled."""
    pending_tool_calls: dict[int, dict[str, Any]] = {}
    assistant_content = ""
    assistant_reasoning = ""

    stream_timeout = float(self.body.get("streamTimeout") or self.stream_timeout)
    try:
      async def _iter() -> Any:
        async for chunk, active_cfg in chat_completion_with_failover(
          self.config,
          self.params,
          self._chat_messages,
          tools=active_tools,
          body=self.body,
          session_id=self.session_id,
        ):
          self.config = active_cfg
          yield chunk

      iterator = _iter()
      while True:
        try:
          chunk = await asyncio.wait_for(iterator.__anext__(), timeout=stream_timeout)
        except StopAsyncIteration:
          break
        self._check_cancel()
        if chunk.error:
          await self.emit({"type": "error", "error": chunk.error})
          return None, []
        if chunk.done:
          if chunk.usage:
            self._total_usage = chunk.usage
          break
        if chunk.usage:
          self._total_usage = chunk.usage
        if chunk.reasoning_content:
          assistant_reasoning += chunk.reasoning_content
          await self.emit({"type": "reasoning", "delta": chunk.reasoning_content})
        if chunk.content:
          assistant_content += chunk.content
          stripped = strip_leaked_tool_calls(chunk.content)
          if stripped:
            await self.emit({"type": "content", "delta": stripped})
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
            await self.emit({"type": "tool_call_delta", "delta": tc})
    except TimeoutError as e:
      cloudlog.warning(f"aid: chat stream timeout: {e}")
      await self.emit({"type": "error", "error": f"Stream timeout: {e}"})
      return None, []

    assistant_msg: dict[str, Any] = {"role": "assistant"}
    cleaned_content = strip_leaked_tool_calls(assistant_content)
    if cleaned_content:
      assistant_msg["content"] = cleaned_content
    elif pending_tool_calls:
      assistant_msg["content"] = None
    if assistant_reasoning:
      assistant_msg["reasoning_content"] = assistant_reasoning

    tool_list: list[dict[str, Any]] = []
    for i in sorted(pending_tool_calls.keys()):
      tc = pending_tool_calls[i]
      if not tc.get("id"):
        fn_name = (tc.get("function") or {}).get("name", "tool")
        tc["id"] = f"{fn_name}:{i}"
      tool_list.append(tc)
    if tool_list:
      assistant_msg["tool_calls"] = tool_list

    self._chat_messages.append(assistant_msg)
    self.log.append(
      EventType.ASSISTANT_MESSAGE,
      {
        "role": "assistant",
        "content": assistant_msg.get("content"),
        "tool_calls": assistant_msg.get("tool_calls"),
      },
      surface_op=SurfaceOp.APPEND,
    )

    return assistant_msg, tool_list

  async def _run_before_tool_hook(
    self,
    name: str,
    arguments: str,
    call_id: str,
  ) -> dict[str, Any]:
    try:
      from ai.hooks.registry import run_hooks
      return await run_hooks("before_tool_call", {
        "name": name,
        "arguments": arguments,
        "agent_id": self.agent_id,
        "session_id": self.session_id,
        "body": {**self.body, "_get_state_reader": self.get_state_reader, "_params": self.params},
      })
    except Exception as e:
      cloudlog.warning(f"aid: before_tool_call hook failed: {e}")
      return {}

  async def _run_after_tool_hook(
    self,
    hook_ctx: dict[str, Any],
    name: str,
    result: dict[str, Any],
  ) -> dict[str, Any]:
    try:
      from ai.hooks.registry import run_hooks
      return await run_hooks("after_tool_call", {
        **hook_ctx,
        "result": result,
        "session_id": self.session_id,
        "name": name,
        "body": {**self.body, "_params": self.params},
      })
    except Exception as e:
      cloudlog.warning(f"aid: after_tool_call hook failed: {e}")
      return {}

  async def _run_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    round_idx: int,
  ) -> None:
    """Run tool calls. Emission stays ordered; bodies may execute concurrently."""
    from ai.agents.office import on_tool_start, on_tool_done

    prepared: list[dict[str, Any]] = []

    # Phase 1: sequential tool_call events + pre-guard hooks.
    for idx, tc in enumerate(tool_calls):
      self._check_cancel()
      fn = tc.get("function", {}) or {}
      name = fn.get("name", "")
      arguments = fn.get("arguments", "")
      call_id = tc.get("id", f"{name}:{round_idx}:{idx}")
      is_special = name in ("search_tools", "load_tool")

      await self.emit({
        "type": "tool_call",
        "id": call_id,
        "name": name,
        "arguments": arguments,
        "agentId": self.agent_id,
      })
      try:
        office = on_tool_start(self.agent_id, name)
        await self.emit_with_office({
          "type": "agent_status",
          "agentId": self.agent_id,
          "status": "working",
          "tool": name,
          "office": office,
        })
      except Exception:
        pass

      hook_ctx: dict[str, Any] = {}
      blocked = False
      if is_special:
        hook_ctx = await self._run_before_tool_hook(name, arguments, call_id)
        blocked = bool(hook_ctx.get("block"))

      prepared.append({
        "tc": tc,
        "name": name,
        "arguments": arguments,
        "call_id": call_id,
        "hook_ctx": hook_ctx,
        "blocked": blocked,
        "special": is_special,
      })
      self.log.append(
        EventType.TOOL_CALL,
        {"turn": round_idx, "step": 0, "callId": call_id, "name": name, "arguments": arguments},
      )

    # Phase 2: execute unblocked tool bodies (concurrent when enabled).
    async def _exec(p: dict[str, Any]) -> dict[str, Any]:
      if p["blocked"]:
        reason = p["hook_ctx"].get("reason") or "Tool blocked by hook"
        return {"ok": False, "error": reason}
      if p["special"]:
        return await self._execute_special_tool(p["name"], p["arguments"])
      return await self.pipeline.execute(
        call_id=p["call_id"],
        name=p["name"],
        raw_arguments=p["arguments"],
        is_cancelled=lambda: self.is_cancelled,
        timeout_seconds=self.tool_timeout,
        extra={"session_ctx": self.log},
      )

    tasks = [asyncio.create_task(_exec(p)) for p in prepared]
    try:
      if self.concurrent_tools and len(tasks) > 1:
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
      else:
        raw_results = [await t for t in tasks]
    except asyncio.CancelledError:
      for t in tasks:
        if not t.done():
          t.cancel()
      await asyncio.gather(*tasks, return_exceptions=True)
      raise

    # Phase 3: post hooks (special tools only), result emission, log append — ordered.
    for p, raw in zip(prepared, raw_results):
      self._check_cancel()
      name = p["name"]
      call_id = p["call_id"]

      if isinstance(raw, ChatCancelled):
        raise raw
      if isinstance(raw, BaseException):
        result: dict[str, Any] = {"ok": False, "error": f"Tool execution failed: {raw}"}
      else:
        result = raw if isinstance(raw, dict) else {"ok": True, "value": raw}

      if p["special"]:
        hook_ctx = await self._run_after_tool_hook(p["hook_ctx"], name, result)
        result = hook_ctx.get("result", result)
        if artifact := hook_ctx.get("canvas_artifact"):
          await self.emit({"type": "canvas", "artifact": artifact, "sessionId": self.session_id})

      ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
      try:
        office = on_tool_done(self.agent_id, name, ok=ok)
        await self.emit_with_office({
          "type": "agent_status",
          "agentId": self.agent_id,
          "status": "assigned",
          "office": office,
        })
      except Exception:
        pass

      result_json = json.dumps(result, ensure_ascii=False, default=str)
      await self.emit({
        "type": "tool_result",
        "id": call_id,
        "name": name,
        "result": result,
        "agentId": self.agent_id,
        "verbose": self.verbose,
      })
      self.log.append(
        EventType.TOOL_RESULT,
        {
          "turn": round_idx,
          "step": 0,
          "tool_call_id": call_id,
          "content": _truncate_tool_content(result_json),
        },
        surface_op=SurfaceOp.APPEND,
      )
      self._chat_messages.append({
        "role": "tool",
        "tool_call_id": call_id,
        "content": _truncate_tool_content(result_json),
      })

  async def _execute_special_tool(
    self,
    name: str,
    arguments: str,
  ) -> dict[str, Any]:
    """Execute search_tools / load_tool, which bypass the normal pipeline."""
    try:
      args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
      args = {}
    if name == "search_tools":
      from ai.tools.deferred_loading import handle_search_tools
      return handle_search_tools(args, session_id=self.session_id, job_id=self.job_id)
    if name == "load_tool":
      from ai.tools.deferred_loading import handle_load_tool
      return handle_load_tool(args, session_id=self.session_id, job_id=self.job_id)
    return {"ok": False, "error": f"Unknown special tool '{name}'"}

  async def _run_post_chat(self) -> None:
    if self.body.get("_orchestration_phase") == "specialist":
      try:
        from ai.agents.office import set_agent_status
        office = set_agent_status(self.agent_id, "idle")
        await self.emit_with_office({"type": "agent_status", "agentId": self.agent_id, "status": "idle", "office": office})
      except Exception:
        pass
      return

    try:
      from ai.agents.office import on_chat_done
      office = on_chat_done(self.agent_id)
      await self.emit_with_office({"type": "agent_done", "agentId": self.agent_id, "office": office})
    except Exception:
      pass

    if self._total_usage:
      try:
        from ai.core.llm.usage import record_usage
        record_usage(
          self.params,
          self._total_usage,
          provider=self.config.provider,
          model=self.config.model,
          source="chat",
          session_id=self.session_id,
          job_id=self.job_id,
        )
        await self.emit({"type": "usage", "usage": self._total_usage})
      except Exception as e:
        cloudlog.warning(f"aid: record usage failed: {e}")

    try:
      from ai.tools.session_index import append_to_session_index
      route_data = self.body.get("_agent_route") or {}
      title = str(route_data.get("agentName") or self.agent_id)
      for msg in reversed(self._chat_messages):
        if msg.get("role") in ("user", "assistant"):
          append_to_session_index(
            self.session_id,
            str(msg.get("role")),
            msg.get("content"),
            title=title,
          )
          if msg.get("role") == "user":
            break
    except Exception:
      pass
    try:
      from ai.mcp.host import close_mcp_sessions_for_session
      await close_mcp_sessions_for_session(self.session_id)
    except Exception:
      pass

    if self.body.get("_orchestration_phase") == "specialist":
      return

    try:
      from ai.core.runtime.evolution_pipeline import run_post_chat_pipeline
      from ai.tools.memory_protocol import conversation_tail
      last_user_text = ""
      for msg in reversed(self._chat_messages):
        if msg.get("role") == "user":
          c = msg.get("content", "")
          last_user_text = c if isinstance(c, str) else str(c)
          break
      await run_post_chat_pipeline(
        self.params,
        session_id=str(self.session_id or ""),
        last_user_text=last_user_text,
        recent_messages=conversation_tail(self._chat_messages),
        config=self.config,
      )
    except Exception:
      pass

  async def run_with_loop(self) -> dict[str, Any]:
    """Drive the session using AgentLoop as the core turn/step engine.

    Keeps Agent's message building, header config, handoff, and post-chat
    hooks, but delegates the stream + tool-call loop to AgentLoop so the
    lower-level loop module is exercised by the chat runner.
    """
    from ai.core.agent.loop import AgentLoop

    try:
      self.config, self._chat_messages = await self._build_messages()
      active_tools = self._active_tools()
      system_content = None
      if self._chat_messages and self._chat_messages[0].get("role") == "system":
        system_content = self._chat_messages[0].get("content")
      await self._configure_request_header(system_content, active_tools)
      await self._seed_user_messages()
      await self._maybe_emit_handoff()

      budget_report = self.body.get("_prompt_budget")
      if budget_report:
        await self.emit({"type": "prompt_budget", "budget": budget_report})

      async def _stream_fn(request: dict[str, Any], _params: Any) -> Any:
        async for chunk, active_cfg in chat_completion_with_failover(
          self.config,
          self.params,
          request.get("messages", []),
          tools=request.get("tools"),
          body=self.body,
          session_id=self.session_id,
        ):
          self.config = active_cfg
          yield chunk

      loop = AgentLoop(
        session_id=self.session_id,
        agent_id=self.agent_id,
        params=self.params,
        emit=self.emit,
        stream_fn=_stream_fn,
        tool_pipeline=self.pipeline,
        max_tool_rounds=self.max_tool_rounds,
        tool_timeout=self.tool_timeout,
        stream_timeout=self.stream_timeout,
        workflow_id=str(self.body.get("workflow_id") or self.body.get("workflowId") or self.body.get("workflow") or "").strip() or None,
      )
      # Pre-step compaction seam (G3): token-metered budget from params.
      try:
        from ai.core.session.compaction import DEFAULT_MAX_TOKENS, CompactionConfig, CompactionService
        max_tokens = DEFAULT_MAX_TOKENS
        try:
          from ai.common.storage import read_param
          raw = read_param(self.params, "ai_compaction_max_tokens", str(DEFAULT_MAX_TOKENS))
          max_tokens = max(1024, min(int(str(raw or DEFAULT_MAX_TOKENS)), 1_000_000))
        except Exception:
          pass
        loop.compaction = CompactionService(
          session_log=loop.log,
          llm_stream=None,
          config=CompactionConfig(max_tokens=max_tokens),
        )
      except Exception:
        loop.compaction = None
      # Share durable log with the lower-level loop.
      loop.log.close()
      loop.log = self.log

      header = self.log.request_header()
      if header is not None:
        loop.configure_request(header.provider, header.model, header.system, header.tools)

      # Queue the seeded user messages without starting a background driver.
      # The loop is driven explicitly below; starting both paths races on the
      # shared AgentState and can leave the request stuck at "loop did not start".
      from ai.core.agent.state import AgentMessage, InboxTarget
      for msg in self._chat_messages:
        if msg.get("role") == "user":
          loop.state.send(
            AgentMessage(role="user", content=str(msg.get("content", "")), source="user"),
            InboxTarget.NEXT_TURN,
            wakeup=False,
          )

      # Deliver reminders that fired while no run was active: drain the
      # schedule runtime mailbox into the seeded turns (dsh dispatches them
      # as user turns; here they ride the already-driven session).
      try:
        from ai.schedule.runtime import drain_reminders
        for reminder in drain_reminders(self.session_id):
          loop.state.send(
            AgentMessage(role="user", content=reminder, source="schedule"),
            InboxTarget.NEXT_TURN,
            wakeup=False,
          )
      except Exception:
        pass  # schedule delivery is best-effort, never block the chat run

      # Drive the session through the loop's public iteration seam (dsh
      # wakeDriver/whenIdle semantics): wake + drain queued follow-ups.
      # The facade must not invoke the loop's private run entry directly.
      result: dict[str, Any] = await loop.run_until_idle(
        is_cancelled=lambda: self.is_cancelled,
      )

      if result.get("ok"):
        self._resolved_model = getattr(self.config, "model", None)
        await self._run_post_chat()
        await self.emit({
          "type": "done",
          "resolvedModel": self._resolved_model,
          "agentId": self.agent_id,
        })
        return {"ok": True, "resolvedModel": self._resolved_model, "agentId": self.agent_id}
      return result
    except ChatCancelled:
      try:
        await self.emit({"type": "error", "error": "cancelled"})
      except Exception:
        pass
      return {"ok": False, "error": "cancelled"}
    except Exception as e:
      cloudlog.error(f"aid: Agent.run_with_loop error: {e}")
      try:
        await self.emit({"type": "error", "error": str(e)})
      except Exception:
        pass
      return {"ok": False, "error": str(e)}

  async def run(self) -> dict[str, Any]:
    """Drive the session to completion and return the run result."""
    if (
      self.body.get("useAgentLoop")
      or self.body.get("use_agent_loop")
      or self.body.get("ai_use_agent_loop")
      or self.ai_use_agent_loop
    ):
      return await self.run_with_loop()
    try:
      self.config, self._chat_messages = await self._build_messages()
      active_tools = self._active_tools()
      system_content = None
      if self._chat_messages and self._chat_messages[0].get("role") == "system":
        system_content = self._chat_messages[0].get("content")
      await self._configure_request_header(system_content, active_tools)
      await self._seed_user_messages()
      await self._maybe_emit_handoff()

      budget_report = self.body.get("_prompt_budget")
      if budget_report:
        await self.emit({"type": "prompt_budget", "budget": budget_report})

      for round_idx in range(self.max_tool_rounds):
        self._check_cancel()
        active_tools = self._active_tools()
        if self.body.get("trace"):
          await self.emit({
            "type": "trace",
            "round": round_idx,
            "agentId": self.agent_id,
            "message": f"chat round {round_idx + 1}",
          })

        hook_ctx = await self._run_before_chat_round_hook(round_idx)
        if hook_ctx and hook_ctx.get("block"):
          reason = hook_ctx.get("reason") or "Blocked by hook"
          await self.emit({"type": "error", "error": reason})
          return {"ok": False, "error": reason}

        assistant_msg, tool_calls = await self._stream_round(round_idx, active_tools)
        if assistant_msg is None:
          return {"ok": False, "error": "stream failed"}

        if not tool_calls:
          break

        await self._run_tool_calls(tool_calls, round_idx)

      self._resolved_model = getattr(self.config, "model", None)
      await self._run_post_chat()
      await self.emit({
        "type": "done",
        "resolvedModel": self._resolved_model,
        "agentId": self.agent_id,
      })
      return {"ok": True, "resolvedModel": self._resolved_model, "agentId": self.agent_id}
    except ChatCancelled:
      try:
        await self.emit({"type": "error", "error": "cancelled"})
      except Exception:
        pass
      return {"ok": False, "error": "cancelled"}
    except Exception as e:
      cloudlog.error(f"aid: Agent.run error: {e}")
      try:
        await self.emit({"type": "error", "error": str(e)})
      except Exception:
        pass
      return {"ok": False, "error": str(e)}
