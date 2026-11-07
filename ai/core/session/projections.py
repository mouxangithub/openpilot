"""Event Projection Registry.

Provides a lightweight, pure-Python fold registry for deriving read models
from a session event stream. Folders can consume either `SessionEvent`
instances (log layer) or `EventEnvelope` instances (storage/model layer).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ai.core.session.log import EventType, SessionEvent
from ai.core.session.model import EventEnvelope


EVENT_SANDBOX_MODE = "sandbox/mode"
EVENT_PERMISSION_PRESET = "permission/preset"
EVENT_APPROVAL_ASKED = "approval/asked"
EVENT_APPROVAL_DECIDED = "approval/decided"
EVENT_COMMAND_RUN = "command/run"
EVENT_COMMAND_DONE = "command/done"

ProjectionFolder = Callable[[Any, Any], Any]


@dataclass(frozen=True)
class ProjectionDefinition:
  """A named folder over a subset of session event types.

  Attributes:
    name: Stable identifier for the projection.
    zero: Initial state value.
    event_types: Set of event type strings this folder cares about.
    apply: Pure synchronous function ``apply(state, event) -> state``.
    version: Optional projection schema version.
  """

  name: str
  zero: Any
  event_types: set[str]
  apply: ProjectionFolder
  version: str = "1.0"

  def __post_init__(self) -> None:
    if not self.name:
      raise ValueError("projection name is required")
    if not isinstance(self.event_types, set):
      object.__setattr__(self, "event_types", set(self.event_types))
    if not self.event_types:
      raise ValueError("event_types must not be empty")


class EventProjectionRegistry:
  """Registry and runner for session event projections.

  Each registered projection receives only events whose type string appears
  in its ``event_types`` set. The registry is agnostic to whether events are
  delivered as `SessionEvent` or `EventEnvelope`.
  """

  def __init__(self) -> None:
    self._folders: dict[str, ProjectionDefinition] = {}

  def register(self, folder: ProjectionDefinition) -> None:
    """Register a projection folder.

    Args:
      folder: The projection definition to register.

    Raises:
      ValueError: If a projection with the same name is already registered.
    """
    if folder.name in self._folders:
      raise ValueError(f"projection already registered: {folder.name}")
    self._folders[folder.name] = folder

  def unregister(self, name: str) -> None:
    """Remove a previously registered projection.

    Args:
      name: Projection name to remove.

    Raises:
      KeyError: If the projection is not registered.
    """
    if name not in self._folders:
      raise KeyError(f"projection not found: {name}")
    del self._folders[name]

  def fold(self, events: Iterable[Any], projection: str) -> Any:
    """Fold ``events`` through a single named projection.

    Args:
      events: Sequence of `SessionEvent` or `EventEnvelope`.
      projection: Name of the projection to run.

    Returns:
      The folded state for the requested projection.

    Raises:
      KeyError: If the projection is not registered.
    """
    folder = self._folders.get(projection)
    if folder is None:
      raise KeyError(f"projection not found: {projection}")
    state = folder.zero
    for event in events:
      type_str = _event_type_of(event)
      if type_str in folder.event_types:
        state = folder.apply(state, event)
    return state

  def fold_all(self, events: Iterable[Any]) -> dict[str, Any]:
    """Fold ``events`` through every registered projection.

    Returns:
      Mapping from projection name to folded state.
    """
    event_list = list(events)
    results: dict[str, Any] = {}
    for name, folder in self._folders.items():
      state = folder.zero
      for event in event_list:
        type_str = _event_type_of(event)
        if type_str in folder.event_types:
          state = folder.apply(state, event)
      results[name] = state
    return results

  def supported_types(self) -> set[str]:
    """Return the union of event types consumed by all registered folders."""
    result: set[str] = set()
    for folder in self._folders.values():
      result.update(folder.event_types)
    return result


def _event_type_of(event: Any) -> str:
  """Extract the event type string from either event model."""
  if isinstance(event, EventEnvelope):
    return event.type
  if isinstance(event, SessionEvent):
    return str(event.type)
  if isinstance(event, dict):
    raw = event.get("type", "")
    if isinstance(raw, EventType):
      return str(raw)
    return str(raw)
  raise TypeError(f"unsupported event type: {type(event).__name__}")
