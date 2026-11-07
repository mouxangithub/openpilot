"""Minimal pure-Python cron expression parser (5-field POSIX style).

Supports ``*``, lists ``1,2``, ranges ``1-5`` and step ``*/2`` members. No
external dependency (avoids croniter). Field order: minute hour day-of-month
month day-of-week. Handles the two common wildcard day aliases ``?`` and ``*``.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_RANGE_DOMAINS: dict[int, tuple[int, int]] = {
  0: (0, 59),  # minute
  1: (0, 23),  # hour
  2: (1, 31),  # day of month
  3: (1, 12),  # month
  4: (0, 6),   # day of week (0=Sunday)
}

_ALIASES: dict[str, dict[int, int]] = {
  3: {v: k for k, v in enumerate(("jan", "feb", "mar", "apr", "may", "jun",
                                 "jul", "aug", "sep", "oct", "nov", "dec"), start=1)},
  4: {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6},
}


class CronSchedule:
  def __init__(self, expression: str) -> None:
    fields = expression.split()
    if len(fields) != 5:
      raise ValueError(f"cron expression must have 5 fields, got {len(fields)}")
    self._sets: list[set[int]] = [self._parse_field(fields[i], i) for i in range(5)]
    self.expression = expression

  def _parse_field(self, field: str, index: int) -> set[int]:
    lo, hi = MAX_RANGE_DOMAINS[index]
    if field == "*" or field == "?":
      return set(range(lo, hi + 1))
    if field.startswith("*/"):
      step = int(field[2:])
      if step <= 0:
        raise ValueError(f"invalid step in field {field!r}")
      return set(range(lo, hi + 1, step))
    result: set[int] = set()
    aliases = _ALIASES.get(index, {})
    for part in field.split(","):
      part = part.strip().lower()
      part = aliases.get(part, part)
      step = 1
      if "/" in part:
        part, step_s = part.split("/", 1)
        step = int(step_s)
        if step <= 0:
          raise ValueError(f"invalid step in part {part!r}")
      if "-" in part:
        a_s, b_s = part.split("-", 1)
        a = int(aliases.get(a_s, a_s))
        b = int(aliases.get(b_s, b_s))
        result.update(range(a, b + 1, step))
      else:
        result.add(int(part))
    return {v for v in result if lo <= v <= hi}

  def matches(self, minute: int, hour: int, dom: int, month: int, dow: int) -> bool:
    if minute not in self._sets[0]:
      return False
    if hour not in self._sets[1]:
      return False
    if month not in self._sets[3]:
      return False
    dom_ok = dom in self._sets[2]
    dow_ok = dow in self._sets[4]
    dom_restricted = self._is_restricted(2)
    dow_restricted = self._is_restricted(4)
    # POSIX: when both DOM and DOW are restricted, either matching fires.
    if dom_restricted and dow_restricted:
      return dom_ok or dow_ok
    return dom_ok and dow_ok

  def _is_restricted(self, idx: int) -> bool:
    lo, hi = MAX_RANGE_DOMAINS[idx]
    return self._sets[idx] != set(range(lo, hi + 1))


def parse_cron(expression: str) -> CronSchedule:
  return CronSchedule(expression)