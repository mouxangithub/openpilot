"""Schedule runtime: polls due reminders and dispatches them.

Dispatch contract (dsh ScheduleRuntime): when a record's target instant is
reached, the runtime invokes ``dispatch(record)`` exactly once, then removes
the one-shot / advances the ``every`` anchor via ``store.mark_dispatched``.

The default dispatch parks the framed reminder in a per-session mailbox;
``drain_reminders`` returns and clears it. ``Agent.run_with_loop`` drains the
mailbox at run start and enqueues each reminder as a follow-up user message,
so a reminder that fires between requests is delivered on the next turn
instead of being lost. Custom dispatchers (e.g. queueing an immediate chat
run via command_queue) can be injected through ``ensure_scheduler``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from ai.schedule.store import ScheduleRecord, ScheduleStore, get_schedule_store

DispatchFn = Callable[[ScheduleRecord], Awaitable[None]]

_POLL_INTERVAL_SECONDS = 1.0


def render_reminder_framing(record: ScheduleRecord) -> str:
  """Wrap a due reminder prompt so the model knows it is a scheduled trigger."""
  return f"[Scheduled reminder ({record.kind}) fires now]\n\n{record.prompt}"


_mailboxes: dict[str, list[str]] = {}


async def _default_dispatch(session_id: str, record: ScheduleRecord) -> None:
  _mailboxes.setdefault(session_id, []).append(render_reminder_framing(record))


def drain_reminders(session_id: str) -> list[str]:
  """Return and clear reminders that fired while no chat run was active."""
  return _mailboxes.pop(session_id, [])


class SchedulerRuntime:
  """One polling loop per session; idempotent start/stop."""

  def __init__(
    self,
    session_id: str,
    *,
    store: ScheduleStore | None = None,
    dispatch: DispatchFn | None = None,
    now_fn: Callable[[], datetime] | None = None,
  ) -> None:
    self.session_id = session_id
    self.store = store or get_schedule_store()
    self.dispatch: DispatchFn = dispatch or (lambda record: _default_dispatch(session_id, record))
    self._now = now_fn or (lambda: datetime.now(timezone.utc))
    self._task: asyncio.Task | None = None
    self._stopping = asyncio.Event()

  def start(self) -> None:
    if self._task is None or self._task.done():
      self._stopping = asyncio.Event()
      self._task = asyncio.create_task(self._run())

  async def stop(self) -> None:
    self._stopping.set()
    if self._task is not None:
      try:
        await self._task
      except asyncio.CancelledError:
        pass
      self._task = None

  async def _run(self) -> None:
    while not self._stopping.is_set():
      try:
        await self.tick()
      except asyncio.CancelledError:
        raise
      except Exception:
        pass  # never let one bad record kill the loop
      try:
        await asyncio.wait_for(self._stopping.wait(), timeout=_POLL_INTERVAL_SECONDS)
        return  # stop requested
      except asyncio.TimeoutError:
        continue

  async def tick(self) -> list[dict[str, Any]]:
    """Dispatch every due record once. Returns dispatch summaries."""
    now = self._now()
    dispatched: list[dict[str, Any]] = []
    for record in self.store.list():
      if record.kind not in ("after", "at", "every") or not record.scheduled_at:
        continue
      due = datetime.fromisoformat(record.scheduled_at.replace("Z", "+00:00"))
      if due > now:
        continue
      await self.dispatch(record)
      self.store.mark_dispatched(record, now=now)
      dispatched.append({"id": record.id, "kind": record.kind, "prompt": record.prompt})
    return dispatched


_runtimes: dict[str, SchedulerRuntime] = {}
_registry_lock = asyncio.Lock()


async def ensure_scheduler(
  session_id: str,
  *,
  store: ScheduleStore | None = None,
  dispatch: DispatchFn | None = None,
) -> SchedulerRuntime:
  """Start (or return the running) scheduler for a session."""
  async with _registry_lock:
    rt = _runtimes.get(session_id)
    if rt is None or rt._task is None or rt._task.done():
      rt = SchedulerRuntime(session_id, store=store, dispatch=dispatch)
      rt.start()
      _runtimes[session_id] = rt
    return rt


async def stop_scheduler(session_id: str) -> bool:
  async with _registry_lock:
    rt = _runtimes.pop(session_id, None)
  if rt is None:
    return False
  await rt.stop()
  return True
