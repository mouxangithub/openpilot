"""Tests for unified scheduler API (T-P1.1)."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import ai.tests.bootstrap_pc  # noqa: F401


class _FakeParams:
  def __init__(self):
    self._store: dict[str, str] = {}


class TestSchedulerUnified(unittest.TestCase):
  def _fresh_params(self):
    return _FakeParams()

  @patch("ai.tools.domains.platform.scheduler.read_param")
  @patch("ai.tools.domains.platform.scheduler.write_param")
  def test_schedule_legacy_interval(self, mock_write, mock_read):
    from ai.tools.domains.platform.scheduler import list_scheduled_tasks, schedule_task

    p = self._fresh_params()
    mock_read.return_value = None

    res = schedule_task(
      p,
      {
        "name": "legacy interval",
        "action": "chat_notify",
        "trigger": "interval",
        "interval_minutes": 60,
        "payload": {"prompt": "hi"},
      },
    )
    self.assertTrue(res["ok"], res)
    self.assertEqual(res["task"]["trigger"], "interval")
    mock_write.assert_called_once()

    mock_read.return_value = mock_write.call_args[0][2]
    listed = list_scheduled_tasks(p)
    self.assertEqual(len(listed["tasks"]), 1)

  @patch("ai.tools.domains.platform.scheduler.read_param")
  @patch("ai.tools.domains.platform.scheduler.write_param")
  def test_schedule_rrule_computes_next_run(self, mock_write, mock_read):
    from ai.tools.domains.platform.scheduler import schedule_task

    p = self._fresh_params()
    mock_read.return_value = None

    res = schedule_task(
      p,
      {
        "name": "rrule task",
        "action": "chat_notify",
        "trigger": "rrule",
        "payload": {"rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"},
      },
    )
    self.assertTrue(res["ok"], res)
    self.assertEqual(res["task"]["trigger"], "rrule")
    self.assertGreater(res["task"]["next_run"], int(time.time()))

  @patch("ai.tools.domains.platform.scheduler.read_param")
  @patch("ai.tools.domains.platform.scheduler.write_param")
  def test_cancel_scheduled_task(self, mock_write, mock_read):
    from ai.tools.domains.platform.scheduler import cancel_scheduled_task, schedule_task

    p = self._fresh_params()
    mock_read.return_value = None
    res = schedule_task(p, {"name": "to cancel", "action": "chat_notify"})
    tid = res["task"]["id"]
    mock_read.return_value = mock_write.call_args[0][2]
    cancelled = cancel_scheduled_task(p, tid)
    self.assertTrue(cancelled["ok"])
    self.assertEqual(cancelled["removed"], 1)

  @patch("ai.tools.domains.platform.scheduler.read_param")
  @patch("ai.tools.domains.platform.scheduler.write_param")
  def test_invalid_rrule_rejected(self, mock_write, mock_read):
    from ai.tools.domains.platform.scheduler import schedule_task

    p = self._fresh_params()
    mock_read.return_value = None
    res = schedule_task(
      p,
      {
        "name": "bad",
        "action": "chat_notify",
        "trigger": "rrule",
        "payload": {"rrule": "NOT_A_RULE"},
      },
    )
    self.assertFalse(res["ok"])
    self.assertIn("rrule", res["error"].lower())


if __name__ == "__main__":
  unittest.main()
