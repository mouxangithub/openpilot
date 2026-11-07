"""Agent state machine with inbox and cancellation.

A small port of the dsh-agent concepts to Python: status, phase, inbox,
and explicit cancel cause.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AgentStatus(StrEnum):
  IDLE = "idle"
  RUNNING = "running"
  MAINTENANCE = "maintenance"


class CancelCauseKind(StrEnum):
  USER = "user"
  PARENT = "parent"
  HOOK = "hook"
  DISPOSED = "disposed"


@dataclass(frozen=True)
class CancelCause:
  kind: CancelCauseKind
  reason: str = ""

  def to_dict(self) -> dict[str, str]:
    return {"kind": self.kind.value, "reason": self.reason}


class InboxTarget(StrEnum):
  NEXT_TURN = "next-turn"
  NEXT_STEP = "next-step"


@dataclass
class AgentMessage:
  role: str
  content: str | None = None
  tool_calls: list[dict[str, Any]] | None = None
  source: str = "user"

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {"role": self.role, "source": self.source}
    if self.content is not None:
      out["content"] = self.content
    if self.tool_calls is not None:
      out["tool_calls"] = self.tool_calls
    return out


class AgentInbox:
  """Queued input for an agent: next-turn vs next-step."""

  def __init__(self) -> None:
    self.next_turn: list[AgentMessage] = []
    self.next_step: list[AgentMessage] = []

  @property
  def has_pending(self) -> bool:
    return bool(self.next_turn or self.next_step)

  def splice(
    self,
    target: InboxTarget,
    delete_count: int,
    start: int,
    messages: list[AgentMessage],
  ) -> None:
    queue = self.next_turn if target == InboxTarget.NEXT_TURN else self.next_step
    queue[start:start + delete_count] = messages

  def clear(self) -> None:
    self.next_turn.clear()
    self.next_step.clear()

  def claim(self, target: InboxTarget, _turn: int) -> list[AgentMessage]:
    if target == InboxTarget.NEXT_TURN:
      claimed = list(self.next_turn)
      self.next_turn.clear()
      return claimed
    claimed = list(self.next_step)
    self.next_step.clear()
    return claimed


@dataclass
class _RunningPhase:
  abort: asyncio.Future[CancelCause]
  turn: int
  step: int
  wake_requested: bool = False


@dataclass
class _MaintenancePhase:
  abort: asyncio.Future[CancelCause]
  last_turn: int
  wake_requested: bool = False


class AgentPhase:
  """Immutable-ish phase container."""

  def __init__(self) -> None:
    self.kind: str = "idle"
    self.last_turn: int = 0
    self._running: _RunningPhase | None = None
    self._maintenance: _MaintenancePhase | None = None

  @property
  def status(self) -> AgentStatus:
    if self.kind == "running":
      return AgentStatus.RUNNING
    if self.kind == "maintenance":
      return AgentStatus.MAINTENANCE
    return AgentStatus.IDLE

  def enter_running(self) -> _RunningPhase:
    self.kind = "running"
    self._running = _RunningPhase(abort=asyncio.get_event_loop().create_future(), turn=self.last_turn, step=0)
    return self._running

  def enter_maintenance(self) -> _MaintenancePhase:
    self.kind = "maintenance"
    self._maintenance = _MaintenancePhase(abort=asyncio.get_event_loop().create_future(), last_turn=self.last_turn)
    return self._maintenance

  def enter_idle(self, last_turn: int) -> None:
    self.kind = "idle"
    self.last_turn = last_turn
    self._running = None
    self._maintenance = None

  @property
  def running(self) -> _RunningPhase:
    if self._running is None:
      raise RuntimeError("not running")
    return self._running

  @property
  def maintenance(self) -> _MaintenancePhase:
    if self._maintenance is None:
      raise RuntimeError("not in maintenance")
    return self._maintenance

  @property
  def abort(self) -> asyncio.Future[CancelCause] | None:
    if self._running is not None:
      return self._running.abort
    if self._maintenance is not None:
      return self._maintenance.abort
    return None


StatusCallback = Callable[[AgentStatus, AgentStatus], None]


class AgentState:
  """Owns phase transitions, inbox, and cancellation for one agent session."""

  def __init__(self, agent_id: str, session_id: str) -> None:
    self.agent_id = agent_id
    self.session_id = session_id
    self.inbox = AgentInbox()
    self.phase = AgentPhase()
    self._status_listeners: list[StatusCallback] = []
    # Lazily created: AgentState must be constructible without a running event
    # loop (e.g. unit tests / synchronous wiring). The first access materialises
    # a completed future so `when_idle()` returns immediately until
    # `begin_activity()` replaces it.
    self._activity_done: asyncio.Future[None] | None = None

  def _activity_future(self) -> asyncio.Future[None]:
    """Return the current activity future, creating a completed one on demand."""
    fut = self._activity_done
    if fut is None:
      fut = asyncio.get_event_loop().create_future()
      fut.set_result(None)
      self._activity_done = fut
    return fut

  def on_status(self, cb: StatusCallback) -> Callable[[], None]:
    self._status_listeners.append(cb)

    def remove() -> None:
      try:
        self._status_listeners.remove(cb)
      except ValueError:
        pass
    return remove

  def _set_status(self, new_status: AgentStatus) -> None:
    old = self.phase.status
    if old == new_status:
      return
    if new_status == AgentStatus.RUNNING:
      self.phase.enter_running()
    elif new_status == AgentStatus.MAINTENANCE:
      self.phase.enter_maintenance()
    else:
      self.phase.enter_idle(self.phase.last_turn)
    for cb in list(self._status_listeners):
      try:
        cb(old, new_status)
      except Exception:
        pass

  def send(self, message: AgentMessage, target: InboxTarget, wakeup: bool) -> None:
    waking_after_abort = wakeup and self.phase.kind != "idle" and self.phase.abort is not None and self.phase.abort.done()
    resolved_target = InboxTarget.NEXT_TURN if waking_after_abort else target
    self.inbox.splice(resolved_target, 0, len(self.inbox.next_turn if resolved_target == InboxTarget.NEXT_TURN else self.inbox.next_step), [message])
    if wakeup:
      self.wake_driver(waking_after_abort)

  def followup(self, message: AgentMessage) -> None:
    self.send(message, InboxTarget.NEXT_TURN, True)

  def steer(self, message: AgentMessage) -> None:
    self.send(message, InboxTarget.NEXT_STEP, True)

  def inject(self, message: AgentMessage) -> None:
    self.send(message, InboxTarget.NEXT_STEP, False)

  def cancel(self, cause: CancelCause, *, keep_inbox: bool = False) -> None:
    if not keep_inbox:
      self.inbox.clear()
      if self.phase.kind != "idle":
        phase = self.phase.running if self.phase.kind == "running" else self.phase.maintenance
        phase.wake_requested = False
    if self.phase.abort is not None and not self.phase.abort.done():
      self.phase.abort.set_result(cause)
    else:
      # Latch a cancel even when idle so the next wake can observe it.
      self._latched_cancel = cause

  def wake_driver(self, wake_after_abort: bool = False) -> None:
    if self.phase.kind != "idle":
      if self.phase.kind in ("maintenance",) or wake_after_abort:
        phase = self.phase.maintenance if self.phase.kind == "maintenance" else self.phase.running
        phase.wake_requested = True
      return
    self._set_status(AgentStatus.RUNNING)

  def start_maintenance(self) -> None:
    if self.phase.kind != "idle":
      raise RuntimeError(f"agent {self.agent_id} already has active work")
    self._set_status(AgentStatus.MAINTENANCE)

  def end_maintenance(self) -> None:
    if self.phase.kind != "maintenance":
      return
    self._set_status(AgentStatus.IDLE)
    maintenance = self.phase.maintenance
    if maintenance.wake_requested and self.inbox.has_pending:
      self.wake_driver()

  async def when_idle(self) -> None:
    while True:
      activity = self._activity_future()
      await activity
      if activity is self._activity_done:
        return

  def is_cancelled(self) -> bool:
    if getattr(self, "_latched_cancel", None) is not None:
      return True
    abort = self.phase.abort
    return abort is not None and abort.done()

  def cancel_cause(self) -> CancelCause | None:
    latched = getattr(self, "_latched_cancel", None)
    if latched is not None:
      return latched
    abort = self.phase.abort
    if abort is None or not abort.done():
      return None
    try:
      return abort.result()
    except Exception:
      return CancelCause(CancelCauseKind.DISPOSED, "abort future failed")

  def begin_activity(self) -> None:
    self._activity_done = asyncio.get_event_loop().create_future()

  def end_activity(self) -> None:
    fut = self._activity_done
    if fut is not None and not fut.done():
      fut.set_result(None)


class ChatCancelled(Exception):
  """Raised when the agent loop is cancelled by user, parent, hook, or dispose."""

  def __init__(self, cause: CancelCause | None = None) -> None:
    self.cause = cause or CancelCause(CancelCauseKind.USER)
    super().__init__(self.cause.reason)
