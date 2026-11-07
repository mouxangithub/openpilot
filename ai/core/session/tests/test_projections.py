"""Tests for ai.core.session.projections."""

from __future__ import annotations

import unittest

from ai.core.session.log import EventType, SessionEvent
from ai.core.session.model import EventEnvelope
from ai.core.session.projections import (
  EVENT_APPROVAL_ASKED,
  EVENT_APPROVAL_DECIDED,
  EVENT_COMMAND_DONE,
  EVENT_COMMAND_RUN,
  EVENT_PERMISSION_PRESET,
  EVENT_SANDBOX_MODE,
  EventProjectionRegistry,
  ProjectionDefinition,
)


class TestEventProjectionRegistry(unittest.TestCase):
  def test_register_and_fold_session_event(self) -> None:
    registry = EventProjectionRegistry()
    folder = ProjectionDefinition(
      name="last_message",
      zero="",
      event_types={EventType.USER_MESSAGE.value},
      apply=lambda state, event: event.data.get("content", state),
    )
    registry.register(folder)
    events = [
      SessionEvent(EventType.USER_MESSAGE, 0, 0, {"content": "hello"}),
      SessionEvent(EventType.ASSISTANT_MESSAGE, 1, 0, {"content": "hi"}),
    ]
    self.assertEqual(registry.fold(events, "last_message"), "hello")

  def test_fold_all_ignores_unknown_events(self) -> None:
    registry = EventProjectionRegistry()
    registry.register(ProjectionDefinition(
      name="counter",
      zero=0,
      event_types={"user/message"},
      apply=lambda state, event: state + 1,
    ))
    events = [
      SessionEvent(EventType.USER_MESSAGE, 0, 0, {}),
      SessionEvent(EventType.TURN_START, 1, 0, {}),
      SessionEvent(EventType.USER_MESSAGE, 2, 0, {}),
    ]
    result = registry.fold_all(events)
    self.assertEqual(result, {"counter": 2})

  def test_supported_types(self) -> None:
    registry = EventProjectionRegistry()
    registry.register(ProjectionDefinition(
      name="a",
      zero=None,
      event_types={"a/b", "c/d"},
      apply=lambda state, event: state,
    ))
    registry.register(ProjectionDefinition(
      name="b",
      zero=None,
      event_types={"c/d", "e/f"},
      apply=lambda state, event: state,
    ))
    self.assertEqual(registry.supported_types(), {"a/b", "c/d", "e/f"})

  def test_unregister(self) -> None:
    registry = EventProjectionRegistry()
    registry.register(ProjectionDefinition(
      name="x",
      zero=0,
      event_types={"x/y"},
      apply=lambda state, event: state,
    ))
    registry.unregister("x")
    with self.assertRaises(KeyError):
      registry.fold([], "x")

  def test_fold_event_envelope(self) -> None:
    registry = EventProjectionRegistry()
    registry.register(ProjectionDefinition(
      name="preset",
      zero="",
      event_types={EVENT_PERMISSION_PRESET},
      apply=lambda state, event: event.payload.get("preset", state),
    ))
    events = [
      EventEnvelope(
        event_id="e1",
        session_id="s1",
        sequence=1,
        type=EVENT_PERMISSION_PRESET,
        payload={"preset": "workspace"},
      ),
    ]
    self.assertEqual(registry.fold(events, "preset"), "workspace")

  def test_event_constants(self) -> None:
    self.assertEqual(EVENT_SANDBOX_MODE, "sandbox/mode")
    self.assertEqual(EVENT_PERMISSION_PRESET, "permission/preset")
    self.assertEqual(EVENT_APPROVAL_ASKED, "approval/asked")
    self.assertEqual(EVENT_APPROVAL_DECIDED, "approval/decided")
    self.assertEqual(EVENT_COMMAND_RUN, "command/run")
    self.assertEqual(EVENT_COMMAND_DONE, "command/done")


if __name__ == "__main__":
  unittest.main()
