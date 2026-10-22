#!/usr/bin/env python3
"""Decision rules for a vision-detected speed limit.

The vision daemon recognises speed-limit signs from the camera and publishes
the reading it is confident about. Turning that reading into a limit the car
acts on needs three guards, because a wrong sign reading is worse than no
reading at all:

  1. A limit far from the reference speed is usually a misread. Such a limit
     is only accepted when the daemon has seen the same value several times
     in a row and the repeated reading agrees with it.
  2. A very low limit is usually a misread too - a small number on a sign,
     a distant plate - so it can be filtered out by a threshold.
  3. A limit can only ever lower the other sources, never raise them.

Pure logic, no openpilot imports, so it stays unit testable on a PC host.
"""
import math

# A vision limit that differs from the reference speed by at least this much
# is treated as a possible misread and needs repeated, agreeing support.
LARGE_REFERENCE_SPEED_DELTA = 30 * 0.44704  # 30 mph in m/s

# How many consecutive agreeing readings a large deviation needs.
LARGE_SET_SPEED_MIN_SUPPORT = 3

# How closely the repeated reading has to match the limit.
SUPPORT_SPEED_TOLERANCE = 0.5 * 0.44704  # 0.5 mph in m/s


def normalize_vision_limit(limit) -> float:
  """The limit in m/s, or 0.0 when it is not a usable value."""
  try:
    limit = float(limit)
  except (TypeError, ValueError):
    return 0.0
  if not math.isfinite(limit) or limit <= 0.0:
    return 0.0
  return limit


def is_low_limit_filtered(limit: float, enabled: bool, threshold: float) -> bool:
  """True when the limit is below the low-limit threshold and gets dropped."""
  if not enabled:
    return False
  try:
    threshold = float(threshold)
  except (TypeError, ValueError):
    return False
  if not math.isfinite(threshold):
    return False
  return 0.0 < limit <= max(threshold, 0.0)


def needs_support(limit: float, reference_speed: float, standstill: bool) -> bool:
  """True when the limit deviates so far that it needs repeated support."""
  if standstill:
    return False
  if reference_speed <= 0.0:
    return False
  return abs(limit - reference_speed) >= LARGE_REFERENCE_SPEED_DELTA


def has_support(count, support_speed, limit: float) -> bool:
  """True when the daemon has seen this limit repeatedly and agrees."""
  try:
    count = int(count)
    support_speed = float(support_speed)
  except (TypeError, ValueError):
    return False
  if not math.isfinite(support_speed):
    return False
  if count < LARGE_SET_SPEED_MIN_SUPPORT:
    return False
  return abs(support_speed - limit) <= SUPPORT_SPEED_TOLERANCE


def resolve_vision_limit(limit, reference_speed: float, standstill: bool, *,
                         support_count=0, support_speed=0.0,
                         low_limit_filter: bool = False, low_limit_threshold: float = 0.0) -> float:
  """The vision limit to act on, in m/s. Zero when there is none.

    reference_speed is the speed the limit is compared against: the set speed
    when there is one, otherwise the current speed.
    """
  limit = normalize_vision_limit(limit)
  if limit <= 0.0:
    return 0.0

  if is_low_limit_filtered(limit, low_limit_filter, low_limit_threshold):
    return 0.0

  if needs_support(limit, reference_speed, standstill):
    if not has_support(support_count, support_speed, limit):
      return 0.0

  return limit


def merge_lower_limit(current: float, candidate: float) -> float:
  """Fold a candidate limit into the current one. Only ever lowers it."""
  candidate = normalize_vision_limit(candidate)
  if candidate <= 0.0:
    return current
  if current <= 0.0 or candidate < current:
    return candidate
  return current
