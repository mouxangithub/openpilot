"""Session resume/repair reconstruction tests.

Covers the alignment item: resume must deterministically rebuild goal/plan/todo
state and interrupted tool calls from the persisted event log — never hardcoded
None, never fabricated model results.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai.core.session.log import EventType, SessionEvent, SessionLog, SurfaceOp
from ai.core.session.repair import interrupted_turn_closers


class SessionResumeTest(unittest.TestCase):
  def _persist_events(self, events: list[tuple[EventType, dict, SurfaceOp | None]]) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    with open(tmp, "w", encoding="utf-8") as f:
      for et, data, surface_op in events:
        row: dict = {"type": et.value, "data": data}
        if surface_op is not None:
          row["surfaceOp"] = surface_op.value
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return tmp

  def _close_and_cleanup(self, tmp: Path, log: SessionLog | None) -> None:
    if log is not None:
      try:
        log.close()
      except Exception:
        pass
    try:
      tmp.unlink(missing_ok=True)
    except OSError:
      pass

  def test_reconstructed_state_from_tool_events(self) -> None:
    log_path = self._persist_events([
      (EventType.USER_MESSAGE, {"role": "user", "content": "set a goal"}, SurfaceOp.APPEND),
      (EventType.TOOL_CALL, {"turn": 1, "step": 1, "callId": "g1", "name": "goal_create", "arguments": "{}"}, None),
      (EventType.TOOL_RESULT, {"turn": 1, "step": 1, "tool_call_id": "g1", "content": json.dumps({"ok": True, "goal": {"id": "goal-1", "objective": "tune lateral"}})}, SurfaceOp.APPEND),
      (EventType.TOOL_CALL, {"turn": 1, "step": 2, "callId": "t1", "name": "todo_write", "arguments": "{}"}, None),
      (EventType.TOOL_RESULT, {"turn": 1, "step": 2, "tool_call_id": "t1", "content": json.dumps({"ok": True, "todos": [{"id": "a", "content": "step1"}]})}, SurfaceOp.APPEND),
      # interrupted call: TOOL_CALL without matching TOOL_RESULT
      (EventType.TOOL_CALL, {"turn": 2, "step": 1, "callId": "orphan1", "name": "grep_log", "arguments": "{}"}, None),
    ])

    log = SessionLog("sess-recon", persist_path=log_path, load_persisted=True)
    # Correlate TOOL_CALL name -> TOOL_RESULT content by call id, matching the
    # real persisted event shape produced by AgentLoop._step (name lives on
    # TOOL_CALL; result content lives on TOOL_RESULT).
    name_by_call: dict[str, str] = {}
    result_by_call: dict[str, dict] = {}
    call_ids: set[str] = set()
    result_ids: set[str] = set()
    for ev in log.events:
      data = ev.data if isinstance(ev.data, dict) else {}
      if ev.type == EventType.TOOL_CALL:
        cid = str(data.get("callId") or "")
        if cid:
          call_ids.add(cid)
          name_by_call[cid] = str(data.get("name") or "")
      elif ev.type == EventType.TOOL_RESULT:
        cid = str(data.get("tool_call_id") or "")
        if cid:
          result_ids.add(cid)
          try:
            payload = json.loads(data.get("content", "{}")) if isinstance(data.get("content"), str) else data.get("result")
          except (json.JSONDecodeError, TypeError):
            payload = None
          if isinstance(payload, dict):
            result_by_call[cid] = payload

    reconstructed = {"goal": None, "plan": None, "todo": None}
    for cid, name in name_by_call.items():
      payload = result_by_call.get(cid)
      if payload is None:
        continue
      if name.startswith("goal_") and payload.get("goal") is not None:
        reconstructed["goal"] = payload["goal"]
      elif name.startswith("plan_") and payload.get("plan") is not None:
        reconstructed["plan"] = payload["plan"]
      elif name.startswith("todo_") and isinstance(payload, dict):
        reconstructed["todo"] = payload

    self.assertEqual(reconstructed["goal"]["id"], "goal-1")
    self.assertEqual(reconstructed["goal"]["objective"], "tune lateral")
    self.assertIsNone(reconstructed["plan"], "no plan event -> stays None (deterministic)")
    self.assertEqual(reconstructed["todo"]["todos"][0]["id"], "a")
    self.assertEqual(sorted(call_ids - result_ids), ["orphan1"], "interrupted call must be surfaced")
    self.addCleanup(self._close_and_cleanup, log_path, log)

  def test_interrupted_turn_closers_distinguish_missing_start_and_unknown_outcome(self) -> None:
    events = [
      SessionEvent(EventType.ASSISTANT_MESSAGE, 0, 0, {"tool_calls": [{"id": "not-started"}]}),
      SessionEvent(EventType.TOOL_CALL, 1, 0, {"callId": "unknown", "turn": 2, "step": 3, "name": "shell"}),
    ]
    closers = interrupted_turn_closers(events)
    self.assertEqual(closers[0][1]["errorCode"], "TOOL_NOT_STARTED")
    self.assertEqual(closers[1][1]["errorCode"], "TOOL_OUTCOME_UNKNOWN")
    self.assertEqual([item[0] for item in closers[-2:]], [EventType.STEP_END, EventType.TURN_END])
    self.assertEqual(closers[-1][1]["reason"], "interrupted")

  def test_empty_log_reconstructs_none(self) -> None:
    log_path = self._persist_events([])
    log = SessionLog("sess-empty", persist_path=log_path, load_persisted=True)
    self.assertEqual(len(log.events), 0)
    self.assertIsNone(log.last_assistant())
    self.addCleanup(self._close_and_cleanup, log_path, log)


if __name__ == "__main__":
  unittest.main()
