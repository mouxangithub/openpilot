"""User-facing timezone helpers for route timestamps and UI."""

from __future__ import annotations

from datetime import datetime, timezone
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


def read_ai_timezone_name(params: Params | None = None) -> str:
  p = params or Params()
  raw = p.get("ai_timezone")
  if not raw:
    return DEFAULT_AI_TIMEZONE
  name = raw.decode() if isinstance(raw, bytes) else str(raw)
  name = name.strip()
  return name or DEFAULT_AI_TIMEZONE


def get_route_timezone(params: Params | None = None) -> ZoneInfo:
  name = read_ai_timezone_name(params)
  try:
    return ZoneInfo(name)
  except Exception:
    return ZoneInfo(DEFAULT_AI_TIMEZONE)
