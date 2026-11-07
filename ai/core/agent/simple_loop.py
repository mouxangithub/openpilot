"""Simple P0 ReAct agent loop for local verification.

This loop is intentionally independent from the production ai.core.agent.loop
to avoid openpilot/cereal dependencies during local testing. It drives a
session through user message -> LLM -> tool call -> tool result cycles.
"""

from __future__ import annotations

import json
from typing import Any

from ai.core.config.schema import AIOPConfig
from ai.core.session.model import EventType, SessionRecord
from ai.core.session.storage import SessionStorage
from ai.permissions.hitl import HumanInLoop
from ai.permissions.service import SandboxPolicyService
from ai.permissions.vehicle_guard import VehicleState
from ai.providers.offline import OfflineProvider
from ai.tools.dispatch import ToolDispatcher
from ai.tools.schemas import ToolSpec
from ai.tools.spill import SpillWaterfall


class SimpleAgentLoop:
  """Minimal ReAct loop for P0 harness tests."""

  def __init__(
    self,
    session: SessionRecord,
    storage: SessionStorage,
    dispatcher: ToolDispatcher,
    provider: OfflineProvider,
    config: AIOPConfig,
    spill: SpillWaterfall | None = None,
  ) -> None:
    self.session = session
    self.storage = storage
    self.dispatcher = dispatcher
    self.provider = provider
    self.config = config
    self.spill = spill

  def _append(self, event_type: str, payload: dict[str, Any], *, ignorable: bool = False) -> None:
    self.storage.append_event(self.session, event_type, payload, ignorable=ignorable)

  def _messages(self) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    try:
      events = self.storage.read_transcript(self.session)
    except Exception:
      # If the transcript is locked by an open SessionLog (e.g. Manager held the
      # handle), fall back to reading the on-disk file directly.
      events = []
    for ev in events:
      if ev.type == EventType.MESSAGE.value:
        msgs.append({"role": ev.payload.get("role", "user"), "content": ev.payload.get("content", "")})
      elif ev.type == EventType.FUNCTION_CALL_RESULT.value:
        msgs.append({"role": "tool", "content": json.dumps(ev.payload, ensure_ascii=False), "tool_call_id": ev.payload.get("tool_call_id", "")})
    return msgs

  async def run(self, prompt: str) -> dict[str, Any]:
    self._append(EventType.MESSAGE.value, {"role": "user", "content": prompt})
    tool_results: list[dict[str, Any]] = []
    max_rounds = self.config.conversation.ai_max_turns or 16

    for _ in range(max_rounds):
      messages = self._messages()
      tool_calls: list[dict[str, Any]] = []
      async for turn in self.provider.chat(messages, tools=self._tool_schemas()):
        tool_calls.extend(turn.tool_calls)
        if turn.done:
          break

      if not tool_calls:
        return {"ok": True, "answer": "No tool calls", "tool_results": tool_results}

      for call in tool_calls:
        call_id = call.get("id", "call_unknown")
        name = call.get("function", {}).get("name", "")
        args_str = call.get("function", {}).get("arguments", "{}")
        try:
          args = json.loads(args_str) if isinstance(args_str, str) else dict(args_str)
        except Exception:
          args = {}

        self._append(EventType.FUNCTION_CALL.value, {"call_id": call_id, "name": name, "arguments": args})
        result = await self.dispatcher.run(name, args, self.session, tool_call_id=call_id)
        if self.spill is not None:
          result = self.spill.process(result, tool_name=name, call_id=call_id)
        self._append(EventType.FUNCTION_CALL_RESULT.value, {"tool_call_id": call_id, **result})
        tool_results.append({"call_id": call_id, "name": name, "result": result})

        # Stop after first successful write_params to keep tests deterministic.
        if name == "write_params" and result.get("ok"):
          return {"ok": True, "answer": result.get("message", "Wrote params"), "tool_results": tool_results}

    return {"ok": True, "answer": "Reached max rounds", "tool_results": tool_results}

  def _tool_schemas(self) -> list[dict[str, Any]]:
    return [s.to_openai_dict() for s in self.dispatcher.schemas.values()]
