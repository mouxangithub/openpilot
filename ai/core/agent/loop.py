"""Agent loop over session event log.

This module drives one session through turn and step boundaries, using
AgentState for lifecycle/cancellation and SessionLog as the durable source
of truth. It emits events compatible with the existing SSE protocol.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from ai.core.agent.state import AgentState, CancelCause, CancelCauseKind, ChatCancelled, InboxTarget
from ai.core.session.log import EventType, RequestHeader, SessionLog, SurfaceOp
from ai.core.tools.pipeline import ToolPipeline


def bound_dispatch_log_copy(
  result: Any,
  log_content: str,
  *,
  session_id: str,
  tool_name: str,
  call_id: str,
  params: Any = None,
) -> str:
  """Shrink the session log's copy of an oversized result (best-effort).

  Dispatch-log arm of the spill policy (dsh ``tools/ptc-dispatch-log``).
  Reuses ``spill_text_if_needed`` with ``kind="dispatch"``; returns the
  original serialized payload unchanged when spill is disabled, the payload
  is within budget, or anything fails. Never raises, never touches the
  model-facing ``result``.
  """
  try:
    if isinstance(result, dict) and isinstance(result.get("content"), str):
      text = result["content"]
    else:
      text = log_content
    from ai.tools.result_externalize import spill_text_if_needed
    replaced, _ref = spill_text_if_needed(
      text,
      session_id=session_id,
      tool_name=tool_name,
      call_id=call_id,
      params=params,
      kind="dispatch",
    )
    return replaced if replaced is not None else log_content
  except Exception:
    return log_content

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]
StreamFn = Callable[..., Any]


class AgentLoop:
  """Drives one session with explicit turn/step boundaries and event logging."""

  def __init__(
    self,
    session_id: str,
    agent_id: str,
    params: Any,
    emit: EmitFn,
    stream_fn: StreamFn,
    tool_pipeline: ToolPipeline,
    *,
    max_tool_rounds: int = 64,
    tool_timeout: float = 300.0,
    stream_timeout: float = 120.0,
    workflow_id: str | None = None,
    compaction: Any = None,
  ) -> None:
    self.session_id = session_id
    self.agent_id = agent_id
    self.params = params
    self.emit = emit
    self.stream_fn = stream_fn
    self.tool_pipeline = tool_pipeline
    self.max_tool_rounds = max_tool_rounds
    self.tool_timeout = tool_timeout
    self.stream_timeout = stream_timeout
    self.workflow_id = workflow_id
    self.compaction = compaction
    self.state = AgentState(agent_id, session_id)
    self.log = SessionLog(session_id)
    self._driver_task: asyncio.Task[Any] | None = None

  def _check_cancel(self) -> None:
    if self.state.is_cancelled():
      cause = self.state.cancel_cause() or CancelCause(CancelCauseKind.USER)
      raise ChatCancelled(cause)

  async def emit_event(self, event: dict[str, Any]) -> None:
    await self.emit(event)

  async def add_user_message(self, content: str, *, wakeup: bool = True) -> None:
    from ai.core.agent.state import AgentMessage
    self.state.followup(AgentMessage(role="user", content=content, source="user"))
    if wakeup:
      self._drive_if_idle()

  def _drive_if_idle(self) -> None:
    if self.state.phase.kind == "idle":
      self._driver_task = asyncio.create_task(self._run())

  async def _run(self) -> dict[str, Any]:
    self.state.begin_activity()
    try:
      while await self._turn():
        pass
      return {"ok": True, "agentId": self.agent_id}
    except ChatCancelled:
      return {"ok": False, "error": "cancelled"}
    except Exception as e:
      await self.emit_event({"type": "error", "error": str(e)})
      return {"ok": False, "error": str(e)}
    finally:
      self.state.end_activity()

  async def run_until_idle(
    self,
    *,
    is_cancelled: Callable[[], bool] | None = None,
  ) -> dict[str, Any]:
    """Public iteration seam (dsh ``wakeDriver``/``whenIdle`` equivalent).

    Wakes the driver and runs whole turns until the durable inbox is drained
    and the loop returns to idle. Facade code must call this instead of the
    private ``_run()``: an optional ``is_cancelled`` hook is consulted before
    each queued turn, so an external cancel surfaces as ``ChatCancelled``
    even while work remains queued.
    """
    self.state.wake_driver()
    result = await self._run()
    while self.state.inbox.has_pending:
      # Defensive: a state-level cancel must break the queued-turn loop too,
      # otherwise _run() (which captures ChatCancelled and returns a dict)
      # would spin forever on a permanently pending inbox.
      if self.state.is_cancelled():
        raise ChatCancelled(self.state.cancel_cause() or CancelCause(CancelCauseKind.USER, "cancelled with queued turns"))
      if is_cancelled is not None and is_cancelled():
        # An external (facade-level) cancel: the state machine itself is not
        # cancelled, so surface it as ChatCancelled here rather than starting
        # another turn with doomed work queued.
        raise ChatCancelled(CancelCause(CancelCauseKind.USER, "cancelled between queued turns"))
      result = await self._run()
    return result

  async def when_idle(self, *, timeout: float | None = None) -> dict[str, Any]:
    """Resolve when no driver task is active; returns its result (or idle)."""
    task = self._driver_task
    if task is not None and not task.done():
      if timeout is not None:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
      return await task
    return {"ok": True, "agentId": self.agent_id, "idle": True}

  async def _turn(self) -> bool:
    if self.state.phase.kind != "running":
      return False
    if self.workflow_id:
      from ai.tools.domains.platform.workflow_graph import advance_graph_workflow, get_graph_workflow
      if get_graph_workflow(self.workflow_id) is None:
        # 不是 graph 工作流：内置 prompt 工作流（workflows.py 的 WORKFLOWS，如
        # engage_triage / secoc_tsk）的 prompt 已由 build_chat_messages 注入
        # system 消息，直接按普通回合执行即可，不做 graph 步进。
        from ai.tools.domains.platform.workflows import workflow_system_prompt
        if workflow_system_prompt(self.workflow_id):
          self.workflow_id = None
        else:
          # P2 WorkflowEngine integration: if workflow_id matches a loaded
          # WorkflowEngine definition, advance it once and continue the turn.
          from ai.core.workflow import WorkflowEngine
          from ai.tools.domains.platform.platform_extensions import _workflow_engine_definitions
          definitions = _workflow_engine_definitions()
          if self.workflow_id in definitions:
            engine = WorkflowEngine()
            # Light integration: run the definition once per turn boundary.
            wf_result = await engine.run(definitions[self.workflow_id], {"session_id": self.session_id})
            self.log.append(EventType.LIFECYCLE, {
              "kind": "workflow_engine_advance",
              "workflowId": self.workflow_id,
              "ok": wf_result.ok,
            })
            if not wf_result.ok:
              error = wf_result.message or "workflow engine advance failed"
              await self.emit_event({"type": "error", "error": error})
              self.log.append(EventType.LIFECYCLE, {"kind": "workflow_error", "workflowId": self.workflow_id, "error": error})
              return False
          else:
            error = f"workflow '{self.workflow_id}' not found"
            await self.emit_event({"type": "error", "error": error})
            self.log.append(EventType.LIFECYCLE, {"kind": "workflow_error", "workflowId": self.workflow_id, "error": error})
            return False
      else:
        workflow_result = advance_graph_workflow(self.workflow_id, "step")
        if not workflow_result.get("ok"):
          error = str(workflow_result.get("error") or "workflow advance failed")
          await self.emit_event({"type": "error", "error": error})
          self.log.append(EventType.LIFECYCLE, {"kind": "workflow_error", "workflowId": self.workflow_id, "error": error})
          return False
    phase = self.state.phase.running
    turn = phase.turn + 1
    phase.turn = turn
    phase.step = 0
    self.log.append(EventType.TURN_START, {"turn": turn})
    turn_end_reason = {"kind": "completed"}

    try:
      target = InboxTarget.NEXT_TURN
      continue_without_message = False
      while True:
        self._check_cancel()
        step = phase.step + 1
        claimed = self.state.inbox.claim(target, turn)
        if step == 1 and not claimed:
          turn_end_reason = {"kind": "completed"}
          break
        if not claimed and not continue_without_message:
          break
        continue_without_message = False

        self.log.append(EventType.STEP_START, {"turn": turn, "step": step})
        phase.step = step
        for msg in claimed:
          self.log.append(
            EventType.USER_MESSAGE,
            {"role": msg.role, "content": msg.content},
            surface_op=SurfaceOp.APPEND,
          )

        step_end = await self._step(turn, step)
        self.log.append(EventType.STEP_END, {"turn": turn, "step": step})
        if step_end == "tool_calls":
          continue_without_message = True

        if step_end == "max-tokens":
          turn_end_reason = {"kind": "max-tokens"}
        elif step_end == "completed" and turn_end_reason.get("kind") != "max-tokens":
          turn_end_reason = {"kind": "completed"}

        if step_end == "completed" and not self.state.inbox.has_pending:
          break
        target = InboxTarget.NEXT_STEP
    except ChatCancelled as cc:
      turn_end_reason = {"kind": "aborted", "reason": cc.cause.to_dict()}
      raise
    except Exception as e:
      turn_end_reason = {"kind": "error", "error": str(e)}
      await self.emit_event({"type": "error", "error": str(e)})
    finally:
      self.log.append(EventType.TURN_END, {"turn": turn, "reason": turn_end_reason})

    if not self.state.inbox.has_pending:
      return False
    # reset abort for next turn
    phase.abort = asyncio.get_event_loop().create_future()
    return True

  async def _step(self, turn: int, step: int) -> str:
    # Pre-step compaction seam: event projection + pruner. Any failure is
    # best-effort and must not block the model turn.
    if self.compaction is not None:
      try:
        await self.compaction.compact_if_needed(self, trigger="pressure")
      except Exception:
        pass
    messages = self.log.derive_messages()
    header = self.log.request_header()
    if header is None:
      raise RuntimeError("no request header configured")

    request: dict[str, Any] = {
      "provider": header.provider,
      "model": header.model,
      "messages": messages,
    }
    if header.system is not None:
      request["system"] = header.system
    if header.tools:
      request["tools"] = header.tools

    pending_tool_calls: dict[int, dict[str, Any]] = {}
    assistant_content = ""
    assistant_reasoning = ""

    try:
      async for chunk in self._stream_with_timeout(request):
        self._check_cancel()
        if chunk.error:
          await self.emit_event({"type": "error", "error": chunk.error})
          return "error"
        if chunk.done:
          break
        if chunk.reasoning_content:
          assistant_reasoning += chunk.reasoning_content
          await self.emit_event({"type": "reasoning", "delta": chunk.reasoning_content})
        if chunk.content:
          assistant_content += chunk.content
          await self.emit_event({"type": "content", "delta": chunk.content})
        if chunk.tool_calls:
          for tc in chunk.tool_calls:
            idx = tc.get("index", 0)
            pending_tool_calls.setdefault(idx, {
              "id": tc.get("id", ""),
              "type": tc.get("type", "function"),
              "function": {"name": "", "arguments": ""},
            })
            fn = tc.get("function", {}) or {}
            pending_tool_calls[idx]["function"]["name"] += fn.get("name", "")
            pending_tool_calls[idx]["function"]["arguments"] += fn.get("arguments", "")
            await self.emit_event({"type": "tool_call_delta", "delta": tc})
    except TimeoutError as e:
      await self.emit_event({"type": "error", "error": f"Stream timeout: {e}"})
      return "error"

    tool_calls = [pending_tool_calls[i] for i in sorted(pending_tool_calls.keys())]
    self.log.append(
      EventType.ASSISTANT_MESSAGE,
      {
        "role": "assistant",
        "content": assistant_content,
        "tool_calls": tool_calls,
      },
      surface_op=SurfaceOp.APPEND,
    )

    if not tool_calls:
      return "completed"

    for tc in tool_calls:
      self._check_cancel()
      fn = tc.get("function", {})
      name = fn.get("name", "")
      arguments = fn.get("arguments", "")
      call_id = tc.get("id", f"{name}:{turn}:{step}")
      await self.emit_event({
        "type": "tool_call",
        "id": call_id,
        "name": name,
        "arguments": arguments,
        "agentId": self.agent_id,
      })
      self.log.append(EventType.TOOL_CALL, {"turn": turn, "step": step, "callId": call_id, "name": name, "arguments": arguments})

      result = await self.tool_pipeline.execute(
        call_id=call_id,
        name=name,
        raw_arguments=arguments,
        is_cancelled=self.state.is_cancelled,
        timeout_seconds=self.tool_timeout,
        extra={"session_ctx": self.log},
      )

      await self.emit_event({
        "type": "tool_result",
        "id": call_id,
        "name": name,
        "result": result,
        "agentId": self.agent_id,
      })
      # Dispatch-log arm (dsh tools/ptc-dispatch-log): bound the session
      # log's copy of an oversized result independently of the model-facing
      # waterfall. The model-facing arm deliberately skips read-family tools
      # (read → spill → read-again loop) and nested calls (the caller gets
      # the whole value); the log copy is NOT model context, so it always
      # shrinks to preview + locator — replay/UIs read the full text through
      # the spill artifact exactly as they do for spilled native results.
      log_content = json.dumps(result, ensure_ascii=False, default=str)
      if not (isinstance(result, dict) and result.get("externalized")):
        log_content = self._bound_log_copy(name, call_id, result, log_content)
      self.log.append(
        EventType.TOOL_RESULT,
        {
          "turn": turn,
          "step": step,
          "tool_call_id": call_id,
          "content": log_content,
        },
        surface_op=SurfaceOp.APPEND,
      )

    return "tool_calls"

  def _bound_log_copy(self, name: str, call_id: str, result: Any, log_content: str) -> str:
    return bound_dispatch_log_copy(
      result, log_content,
      session_id=self.session_id, tool_name=name, call_id=call_id, params=self.params,
    )

  async def _stream_with_timeout(self, request: dict[str, Any]) -> Any:
    # stream_fn is expected to return an async iterator.
    iterator = self.stream_fn(request, self.params)
    if hasattr(iterator, "__aiter__"):
      iterator = iterator.__aiter__()
    while True:
      try:
        item = await asyncio.wait_for(iterator.__anext__(), timeout=self.stream_timeout)
      except StopAsyncIteration:
        break
      yield item

  def configure_request(
    self,
    provider: str,
    model: str,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
  ) -> None:
    header = RequestHeader(provider=provider, model=model, system=system, tools=tools)
    self.log.append(EventType.REQUEST_HEADER, {"header": header.to_dict(), "reason": "initial"})

  def cancel(self, kind: CancelCauseKind = CancelCauseKind.USER, reason: str = "") -> None:
    self.state.cancel(CancelCause(kind, reason))


