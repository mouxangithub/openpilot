"""Agent-scoped durable reminders (dsh @deepseek-ai/dsh-schedule port).

Three record kinds over a session-owned store:
- ``after`` — one-shot, delay in seconds from creation;
- ``at``    — one-shot, absolute RFC 3339 UTC instant;
- ``every`` — fixed-rate recurring, anchored at creation, min 5 minutes.

Mutations emit ``schedule/change`` snapshot/tombstone events through the
optional event sink (same seam as goal/plan/todo), so the reminder state is
replayable from the session log. The runtime polls for due records and
dispatches them via a callback (default: enqueue a chat request through
``ai.core.chat.command_queue``).
"""

from ai.schedule.store import (
  MIN_EVERY_INTERVAL_SECONDS,
  ScheduleInputError,
  ScheduleRecord,
  ScheduleStore,
  get_schedule_store,
  set_schedule_base_dir,
)
from ai.schedule.runtime import (
  SchedulerRuntime,
  drain_reminders,
  ensure_scheduler,
  render_reminder_framing,
  stop_scheduler,
)

__all__ = [
  "MIN_EVERY_INTERVAL_SECONDS",
  "ScheduleInputError",
  "ScheduleRecord",
  "ScheduleStore",
  "get_schedule_store",
  "set_schedule_base_dir",
  "SchedulerRuntime",
  "drain_reminders",
  "ensure_scheduler",
  "render_reminder_framing",
  "stop_scheduler",
]
