"""Tests for G6 agent scheduler (at / cron / every) and pure-Python cron parser."""
from __future__ import annotations
import asyncio
import unittest

from ai.tools.domains.agent_scheduler import AgentScheduler
from ai.tools.domains.scheduler_cron import parse_cron


class CronParseTest(unittest.TestCase):
  def test_star_every_minute(self) -> None:
    s = parse_cron("* * * * *")
    self.assertTrue(s.matches(0, 0, 1, 1, 0))
    self.assertTrue(s.matches(59, 23, 31, 12, 6))

  def test_specific_time(self) -> None:
    s = parse_cron("30 9 * * *")
    self.assertTrue(s.matches(30, 9, 15, 6, 3))
    self.assertFalse(s.matches(31, 9, 15, 6, 3))

  def test_step(self) -> None:
    s = parse_cron("*/15 * * * *")
    self.assertTrue(s.matches(0, 5, 1, 1, 0))
    self.assertTrue(s.matches(15, 5, 1, 1, 0))
    self.assertFalse(s.matches(10, 5, 1, 1, 0))

  def test_invalid_field_count(self) -> None:
    with self.assertRaises(ValueError):
      parse_cron("* * * *")


class AgentSchedulerTest(unittest.TestCase):
  def test_schedule_every(self) -> None:
    s = AgentScheduler()
    out = s.schedule("a1", "every 5m", {"task": "x"})
    self.assertTrue(out["ok"])
    self.assertEqual(out["job"]["kind"], "every")
    self.assertTrue(len(s.list("a1")) == 1)
    self.assertEqual(s.list("a1")[0]["spec"], "every 5m")

  def test_schedule_invalid(self) -> None:
    s = AgentScheduler()
    out = s.schedule("a1", "never", {})
    self.assertFalse(out["ok"])
    self.assertEqual(out["error_code"], "SCHEDULE_INVALID")

  def test_cancel(self) -> None:
    s = AgentScheduler()
    out = s.schedule("a1", "every 1m", {})
    jid = out["job"]["id"]
    self.assertTrue(s.cancel(jid))
    self.assertFalse(s.cancel(jid))

  def test_at_and_cron(self) -> None:
    s = AgentScheduler()
    self.assertTrue(s.schedule("a1", "at 23:59", {})["ok"])
    self.assertTrue(s.schedule("a1", "cron 0 9 * * 1-5", {})["ok"])


if __name__ == "__main__":
  unittest.main()