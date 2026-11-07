"""User-facing timezone helpers for route timestamps and UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from openpilot.common.params import Params

DEFAULT_AI_TIMEZONE = "Asia/Shanghai"

# Shown in settings dropdown (IANA id -> label key suffix).
AI_TIMEZONE_OPTIONS: list[tuple[str, str]] = [
  ("Asia/Shanghai", "Asia/Shanghai"),
  ("Asia/Tokyo", "Asia/Tokyo"),
  ("Asia/Seoul", "Asia/Seoul"),
  ("America/Los_Angeles", "America/Los_Angeles"),
  ("America/New_York", "America/New_York"),
  ("Europe/London", "Europe/London"),
  ("UTC", "UTC"),
]

# Fixed offsets when IANA tz database is unavailable (e.g. Windows without tzdata).
_TZ_FIXED_OFFSET_HOURS: dict[str, float] = {
  "Asia/Shanghai": 8,
  "Asia/Tokyo": 9,
  "Asia/Seoul": 9,
  "America/Los_Angeles": -8,
  "America/New_York": -5,
  "Europe/London": 0,
  "UTC": 0,
}


def _zone_or_fixed(name: str) -> ZoneInfo | timezone:
  try:
    return ZoneInfo(name)
  except Exception:
    if name == "UTC":
      return timezone.utc
    hours = _TZ_FIXED_OFFSET_HOURS.get(name, _TZ_FIXED_OFFSET_HOURS[DEFAULT_AI_TIMEZONE])
    return timezone(timedelta(hours=hours))


def read_ai_timezone_name(params: Params | None = None) -> str:
  from ai.common.storage import read_param
  raw = read_param(params, "ai_timezone")
  if not raw:
    return DEFAULT_AI_TIMEZONE
  name = raw.decode() if isinstance(raw, bytes) else str(raw)
  name = name.strip()
  return name or DEFAULT_AI_TIMEZONE


def get_route_timezone(params: Params | None = None) -> ZoneInfo | timezone:
  return _zone_or_fixed(read_ai_timezone_name(params))
