"""Deterministic closures for interrupted session turns."""

from __future__ import annotations

from typing import Any, Iterable

from ai.core.session.log import EventType, SessionEvent, SessionLog, SurfaceOp


def interrupted_turn_closers(events: Iterable[SessionEvent]) -> list[tuple[EventType, dict[str, Any], SurfaceOp | None]]:
  """Build synthetic tool/step/turn endings without retrying side effects."""
  events = list(events)
  calls: dict[str, dict[str, Any]] = {}
  results: set[str] = set()
  assistant_calls: dict[str, dict[str, Any]] = {}
  for event in events:
    data = event.data if isinstance(event.data, dict) else {}
    if event.type == EventType.TOOL_CALL:
      call_id = str(data.get("callId") or data.get("tool_call_id") or "")
      if call_id:
        calls[call_id] = dict(data)
    elif event.type == EventType.FUNCTION_CALL:
      # P0 harness simple_loop writes function_call events with call_id.
      call_id = str(data.get("call_id") or data.get("callId") or "")
      if call_id:
        calls[call_id] = dict(data)
    elif event.type == EventType.TOOL_RESULT:
      call_id = str(data.get("tool_call_id") or data.get("callId") or "")
      if call_id:
        results.add(call_id)
    elif event.type == EventType.FUNCTION_CALL_RESULT:
      call_id = str(data.get("tool_call_id") or data.get("call_id") or data.get("callId") or "")
      if call_id:
        results.add(call_id)
    elif event.type == EventType.ASSISTANT_MESSAGE:
      for call in data.get("tool_calls", []) if isinstance(data.get("tool_calls"), list) else []:
        if isinstance(call, dict):
          call_id = str(call.get("id") or call.get("callId") or "")
          if call_id:
            assistant_calls[call_id] = call

  missing_started = sorted(set(assistant_calls) - set(calls))
  orphaned = sorted(set(calls) - results)
  closers: list[tuple[EventType, dict[str, Any], SurfaceOp | None]] = []
  affected_steps: set[tuple[Any, Any]] = set()
  affected_turns: set[Any] = set()
  for call_id in missing_started:
    call = assistant_calls[call_id]
    data = {"tool_call_id": call_id, "content": "TOOL_NOT_STARTED", "errorCode": "TOOL_NOT_STARTED"}
    closers.append((EventType.TOOL_RESULT, data, SurfaceOp.APPEND))
  for call_id in orphaned:
    call = calls[call_id]
    data = {"tool_call_id": call_id, "content": "TOOL_OUTCOME_UNKNOWN", "errorCode": "TOOL_OUTCOME_UNKNOWN"}
    closers.append((EventType.TOOL_RESULT, data, SurfaceOp.APPEND))
    step, turn = call.get("step"), call.get("turn")
    affected_steps.add((turn, step))
    affected_turns.add(turn)
  for turn, step in sorted(affected_steps, key=lambda x: (str(x[0]), str(x[1]))):
    closers.append((EventType.STEP_END, {"turn": turn, "step": step, "reason": "interrupted"}, None))
  for turn in sorted(affected_turns, key=str):
    closers.append((EventType.TURN_END, {"turn": turn, "reason": "interrupted"}, None))
  return closers


def repair_session_log(log: SessionLog) -> list[SessionEvent]:
  """Append missing closures once and return the newly appended events."""
  existing = {(event.type, str(event.data)) for event in log.events}
  repaired: list[SessionEvent] = []
  for event_type, data, surface_op in interrupted_turn_closers(log.events):
    key = (event_type, str(data))
    if key in existing:
      continue
    repaired.append(log.append(event_type, data, surface_op=surface_op))
    existing.add(key)
  return repaired
