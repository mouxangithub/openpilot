"""G6 — agent-scoped durable schedule (after / at / every).

Proves behavior, not existence:
- strict creation validation (exactly one selector, positive delays, every
  >= 300s, future 'at', non-empty prompt) with typed error codes;
- create/list/delete roundtrip persisted to disk;
- mutations project schedule/change snapshot/tombstone through the sink;
- runtime dispatches exactly once when due: one-shot removed, every
  advances anchor-aligned and stays active; not-yet-due untouched;
- default dispatch parks the framed prompt in the session mailbox and
  drain_reminders returns/clears it.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai.schedule.runtime import SchedulerRuntime, drain_reminders, render_reminder_framing
from ai.schedule.store import (
  MIN_EVERY_INTERVAL_SECONDS,
  ScheduleInputError,
  ScheduleStore,
  get_schedule_store,
)


def _utc(*args) -> datetime:
  return datetime(*args, tzinfo=timezone.utc)


class ScheduleValidationTests(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.store = ScheduleStore(Path(self.tmp.name))

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def test_after_requires_positive_seconds(self) -> None:
    with self.assertRaises(ScheduleInputError) as cm:
      self.store.create_after("ping", 0)
    self.assertEqual(cm.exception.code, "invalid_rule")
    with self.assertRaises(ScheduleInputError):
      self.store.create_after("ping", -5)
    with self.assertRaises(ScheduleInputError):
      self.store.create_after("ping", "60")

  def test_every_requires_minimum_interval(self) -> None:
    with self.assertRaises(ScheduleInputError) as cm:
      self.store.create_every("ping", MIN_EVERY_INTERVAL_SECONDS - 1)
    self.assertEqual(cm.exception.code, "invalid_rule")
    record = self.store.create_every("ping", MIN_EVERY_INTERVAL_SECONDS)
    self.assertEqual(record.kind, "every")

  def test_at_requires_future_rfc3339(self) -> None:
    with self.assertRaises(ScheduleInputError) as cm:
      self.store.create_at("ping", "not-a-time")
    self.assertEqual(cm.exception.code, "invalid_at")
    with self.assertRaises(ScheduleInputError) as cm:
      self.store.create_at("ping", "2020-01-01T00:00:00Z")
    self.assertEqual(cm.exception.code, "invalid_at")

  def test_prompt_must_be_nonempty(self) -> None:
    with self.assertRaises(ScheduleInputError) as cm:
      self.store.create_after("   ", 60)
    self.assertEqual(cm.exception.code, "invalid_prompt")


class ScheduleStoreTests(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.base = Path(self.tmp.name)
    self.store = ScheduleStore(self.base)

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def test_create_list_delete_roundtrip_persisted(self) -> None:
    record = self.store.create_after("check oil", 60)
    self.assertEqual(len(self.store.list()), 1)
    self.assertTrue((self.base / "schedules.json").exists())
    raw = json.loads((self.base / "schedules.json").read_text(encoding="utf-8"))
    self.assertIn(record.id, raw["schedules"])
    self.assertTrue(self.store.delete(record.id))
    self.assertEqual(self.store.list(), [])
    self.assertFalse(self.store.delete(record.id))

  def test_event_sink_snapshot_and_tombstone(self) -> None:
    events: list[dict] = []
    self.store.set_event_sink(events.append)
    record = self.store.create_after("hello", 60)
    self.assertEqual(len(events), 1)
    self.assertFalse(events[0]["tombstone"])
    self.assertEqual(events[0]["snapshot"]["id"], record.id)
    self.store.delete(record.id)
    self.assertEqual(len(events), 2)
    self.assertTrue(events[1]["tombstone"])
    self.assertEqual(events[1]["snapshot"]["id"], record.id)

  def test_singleton_base_dir_override(self) -> None:
    tmp2 = tempfile.TemporaryDirectory()
    try:
      store = get_schedule_store(Path(tmp2.name))
      self.assertIs(get_schedule_store(), store)
    finally:
      tmp2.cleanup()


class RuntimeDispatchTests(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.store = ScheduleStore(Path(self.tmp.name))
    self.now = _utc(2026, 9, 5, 12, 0, 0)

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def _runtime(self, dispatched: list) -> SchedulerRuntime:
    async def dispatch(record):
      dispatched.append(record)
    return SchedulerRuntime("sched-test", store=self.store, dispatch=dispatch, now_fn=lambda: self.now)

  def test_one_shot_dispatched_then_removed(self) -> None:
    self.store.create_after("late task", 30, now=self.now)
    due_record = self.store.create_after("due task", 60, now=_utc(2026, 9, 5, 11, 0, 0))
    dispatched: list = []
    rt = self._runtime(dispatched)
    result = asyncio.run(rt.tick())
    self.assertEqual([r.id for r in dispatched], [due_record.id])
    self.assertEqual(len(result), 1)
    self.assertEqual(self.store.get(due_record.id), None, "one-shot must be removed after dispatch")
    self.assertEqual(len(self.store.list()), 1, "not-yet-due record untouched")

  def test_every_advances_anchor_aligned(self) -> None:
    record = self.store.create_every("standup", 300, now=_utc(2026, 9, 5, 11, 0, 0))
    # now is 12:00; the record was scheduled for 11:05 and never dispatched,
    # so tick must advance it to the first anchor after 12:00 (12:05)...
    dispatched: list = []
    rt = self._runtime(dispatched)
    asyncio.run(rt.tick())
    self.assertEqual(len(dispatched), 1, "fires once per tick pass even if many periods elapsed")
    advanced = self.store.get(record.id)
    self.assertIsNotNone(advanced, "every record stays active")
    self.assertEqual(advanced.scheduled_at, "2026-09-05T12:05:00Z")

  def test_default_dispatch_mailbox_and_drain(self) -> None:
    record = self.store.create_after("mailbox check", 60, now=_utc(2026, 9, 5, 11, 0, 0))
    rt = SchedulerRuntime("mailbox-test", store=self.store, now_fn=lambda: self.now)
    asyncio.run(rt.tick())
    drained = drain_reminders("mailbox-test")
    self.assertEqual(len(drained), 1)
    self.assertIn(record.prompt, drained[0])
    self.assertIn("Scheduled reminder", drained[0])
    self.assertEqual(drain_reminders("mailbox-test"), [], "second drain returns empty")

  def test_framing_mentions_kind(self) -> None:
    record = self.store.create_every("loop task", 600)
    framing = render_reminder_framing(record)
    self.assertIn("(every)", framing)
    self.assertIn("loop task", framing)


if __name__ == "__main__":
  unittest.main()
