"""Pure-Python tests — no openpilot import required."""

from __future__ import annotations

import re
import unittest


def parse_nl_task_spec(text: str) -> dict | None:
  """Copy of scheduler NL parser for isolated testing."""
  raw = (text or "").strip()
  if not raw:
    return None
  spec: dict = {"name": raw[:80]}
  if "每天" in raw or "每日" in raw:
    m = re.search(r"(\d{1,2})\s*点", raw)
    hour = int(m.group(1)) if m else 9
    spec.update({
      "trigger": "daily_at",
      "interval_minutes": 1440,
      "payload": {"hour": hour, "minute": 0},
    })
  elif "停车" in raw or "offroad" in raw.lower():
    spec.update({"trigger": "on_offroad", "interval_minutes": 60, "payload": {}})
  elif "wifi" in raw.lower() or "无线" in raw:
    spec.update({"trigger": "on_wifi", "interval_minutes": 60, "payload": {}})
  else:
    spec.update({"trigger": "interval", "interval_minutes": 60, "payload": {}})

  if any(k in raw for k in ("日志", "log")):
    spec["action"] = "read_last_log"
  elif any(k in raw for k in ("用量", "usage", "token")):
    spec["action"] = "read_usage"
  elif any(k in raw for k in ("复盘", "trip", "行程")):
    spec["action"] = "post_drive_review_offroad"
  elif any(k in raw for k in ("通知", "提醒", "推送")):
    spec["action"] = "chat_notify"
    spec["payload"] = {**(spec.get("payload") or {}), "prompt": raw}
  else:
    spec["action"] = "chat_notify"
    spec["payload"] = {**(spec.get("payload") or {}), "prompt": raw}
  return spec


class SchedulerNlTests(unittest.TestCase):
  def test_daily_log(self):
    spec = parse_nl_task_spec("每天9点检查日志")
    self.assertIsNotNone(spec)
    self.assertEqual(spec["trigger"], "daily_at")
    self.assertEqual(spec["payload"]["hour"], 9)
    self.assertEqual(spec["action"], "read_last_log")

  def test_chat_notify(self):
    spec = parse_nl_task_spec("每小时推送提醒检查 engage")
    self.assertEqual(spec["action"], "chat_notify")
    self.assertIn("prompt", spec["payload"])


if __name__ == "__main__":
  unittest.main()
