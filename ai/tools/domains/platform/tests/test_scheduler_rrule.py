"""Tests for scheduler_rrule."""

from __future__ import annotations

import time
import unittest

from ai.tools.domains.platform.scheduler_rrule import RRuleParser, RRuleScheduler


class TestSchedulerRRule(unittest.TestCase):
  def test_parse_daily(self) -> None:
    spec = RRuleParser.parse("FREQ=DAILY;BYHOUR=9;BYMINUTE=0")
    self.assertEqual(spec.freq, "daily")
    self.assertEqual(spec.byhour, 9)

  def test_parse_nl_weekly(self) -> None:
    spec = RRuleParser.parse_nl("每周一和周五14点检查日志")
    self.assertIsNotNone(spec)
    self.assertEqual(spec.freq, "weekly")
    self.assertEqual(spec.byhour, 14)
    self.assertIn("MO", spec.byday or [])
    self.assertIn("FR", spec.byday or [])

  def test_next_occurrence(self) -> None:
    spec = RRuleParser.parse("FREQ=DAILY;BYHOUR=23;BYMINUTE=59")
    sched = RRuleScheduler(spec)
    ts = sched.next_occurrence()
    self.assertGreater(ts, time.time())


if __name__ == "__main__":
  unittest.main()
