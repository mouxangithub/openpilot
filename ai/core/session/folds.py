from __future__ import annotations
from typing import Any
from ai.core.session.log import EventType, SessionEvent

def fold_domain_events(events: list[SessionEvent] | tuple[SessionEvent, ...]) -> dict[str, Any]:
  state = {"goal": None, "plan": None, "todo": None, "schedule": None}
  mapping = {
    EventType.GOAL_CHANGE: "goal",
    EventType.PLAN_CHANGE: "plan",
    EventType.TODO_CHANGE: "todo",
    EventType.SCHEDULE_CHANGE: "schedule",
  }
  for event in events:
    key = mapping.get(event.type)
    if key is None or not isinstance(event.data, dict):
      continue
    state[key] = None if event.data.get("tombstone") else event.data.get("snapshot")
  return state
