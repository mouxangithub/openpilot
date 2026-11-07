"""RRULE support for the op助手 scheduler.

Wraps simple recurrence rules so tasks can express weekly/monthly patterns
beyond the built-in interval/offroad/wifi/ignition triggers.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RRuleSpec:
  """Minimal RRULE subset sufficient for op助手 automation."""

  freq: str
  interval: int = 1
  byhour: int | None = None
  byminute: int = 0
  byday: list[str] | None = None
  bymonthday: list[int] | None = None

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {"freq": self.freq, "interval": self.interval}
    if self.byhour is not None:
      out["byhour"] = self.byhour
      out["byminute"] = self.byminute
    if self.byday:
      out["byday"] = self.byday
    if self.bymonthday:
      out["bymonthday"] = self.bymonthday
    return out


class RRuleParser:
  """Parse a tiny subset of RFC-5545 RRULE strings."""

  _DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

  @classmethod
  def parse(cls, rrule: str) -> RRuleSpec:
    parts: dict[str, str] = {}
    for token in (rrule or "").upper().replace("RRULE:", "").split(";"):
      if "=" in token:
        k, v = token.split("=", 1)
        parts[k.strip()] = v.strip()
    freq = parts.get("FREQ", "DAILY").lower()
    interval = int(parts.get("INTERVAL", "1") or "1")
    byhour = None
    byminute = 0
    if "BYHOUR" in parts:
      byhour = int(parts["BYHOUR"])
      byminute = int(parts.get("BYMINUTE", "0") or "0")
    byday = [d.strip() for d in parts["BYDAY"].split(",")] if "BYDAY" in parts else None
    bymonthday = [int(d) for d in parts["BYMONTHDAY"].split(",")] if "BYMONTHDAY" in parts else None
    return RRuleSpec(freq=freq, interval=interval, byhour=byhour, byminute=byminute, byday=byday, bymonthday=bymonthday)

  @classmethod
  def parse_nl(cls, text: str) -> RRuleSpec | None:
    """Convert Chinese/English natural language into an RRuleSpec."""
    raw = (text or "").strip().lower()
    if not raw:
      return None
    # Default daily at 9:00
    spec = RRuleSpec(freq="daily", byhour=9, byminute=0)

    if "每周" in raw or "每星期" in raw or "every week" in raw:
      spec = RRuleSpec(freq="weekly", byhour=9, byminute=0)
    elif "每月" in raw or "every month" in raw:
      spec = RRuleSpec(freq="monthly", byhour=9, byminute=0)
    elif "每天" in raw or "每日" in raw or "every day" in raw:
      spec = RRuleSpec(freq="daily", byhour=9, byminute=0)

    # Hour extraction
    m = re.search(r"(\d{1,2})\s*[:点时]\s*(\d{1,2})?", raw)
    if m:
      hour = int(m.group(1))
      minute = int(m.group(2)) if m.group(2) else 0
      spec = RRuleSpec(
        freq=spec.freq,
        interval=spec.interval,
        byhour=hour,
        byminute=minute,
        byday=spec.byday,
        bymonthday=spec.bymonthday,
      )

    # Days of week
    days: list[str] = []
    day_map = {
      "周一": "MO", "星期二": "TU", "周三": "WE", "周四": "TH",
      "周五": "FR", "周六": "SA", "周日": "SU", "周天": "SU",
    }
    for zh, en in day_map.items():
      if zh in raw and en not in days:
        days.append(en)
    if days:
      spec = RRuleSpec(
        freq="weekly",
        interval=spec.interval,
        byhour=spec.byhour,
        byminute=spec.byminute,
        byday=days,
        bymonthday=spec.bymonthday,
      )

    return spec


class RRuleScheduler:
  """Compute next occurrence for an RRuleSpec using a naive local clock."""

  def __init__(self, spec: RRuleSpec) -> None:
    self.spec = spec

  def next_occurrence(self, after: float | None = None) -> float:
    """Return next Unix timestamp matching the rule."""
    now = int(after or time.time())
    t = time.localtime(now)
    # Simple daily/weekly/monthly stepping — sufficient for op助手 scheduling.
    for _ in range(366 * 24 * 4):  # bound search
      if self._matches(t):
        target = time.struct_time((
          t.tm_year, t.tm_mon, t.tm_mday,
          self.spec.byhour or t.tm_hour, self.spec.byminute,
          0, t.tm_wday, t.tm_yday, t.tm_isdst,
        ))
        ts = time.mktime(target)
        if ts > now:
          return ts
      t = self._step(t)
    return float(now + 86400)

  def _matches(self, t: time.struct_time) -> bool:
    if self.spec.byday and self._day_name(t.tm_wday) not in self.spec.byday:
      return False
    if self.spec.bymonthday and t.tm_mday not in self.spec.bymonthday:
      return False
    return True

  def _step(self, t: time.struct_time) -> time.struct_time:
    # Advance one hour for search granularity.
    next_ts = time.mktime(t) + 3600
    return time.localtime(next_ts)

  @staticmethod
  def _day_name(wday: int) -> str:
    return ["SU", "MO", "TU", "WE", "TH", "FR", "SA"][wday]
