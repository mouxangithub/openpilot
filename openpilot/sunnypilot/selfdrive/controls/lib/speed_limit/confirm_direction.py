"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Per-direction confirmation of speed-limit changes.

The existing confirm-speed-threshold rule answers "is this change big or low
enough to ask about". This one answers a different question: "is this change
going the direction I want to be asked about". A driver may want a prompt when
the limit drops (the car is about to slow down, which is worth knowing) but
not when it rises, or the other way round.

The two rules are combined with an OR at the call site, so this one can only
ever *add* a prompt. That matters: if it could suppress the threshold prompt,
a limit drop could reach the driver with no warning at all.

Pure logic with no openpilot imports, so it stays importable and unit
testable on a PC host (the module that consumes it pulls in fcntl through
swaglog, which does not exist on Windows).
"""

CONFIRM_NEVER = 0
CONFIRM_LOWER = 1
CONFIRM_HIGHER = 2
CONFIRM_BOTH = 3

CONFIRM_POLICIES = (CONFIRM_NEVER, CONFIRM_LOWER, CONFIRM_HIGHER, CONFIRM_BOTH)


def confirm_needed_for_direction(current_limit_conv: int, new_limit_conv: int, policy: int) -> bool:
  """Whether a limit change of this direction asks the driver first.

  A change to the same value is not a change, so it never asks. An unknown
  policy value reads as "never", which is the behaviour the fork had before
  the setting existed: an unreadable setting must not start prompting.
  """
  if current_limit_conv <= 0 or new_limit_conv <= 0:
    return False
  if new_limit_conv == current_limit_conv:
    return False

  going_down = new_limit_conv < current_limit_conv
  if policy == CONFIRM_BOTH:
    return True
  if policy == CONFIRM_LOWER:
    return going_down
  if policy == CONFIRM_HIGHER:
    return not going_down
  return False
