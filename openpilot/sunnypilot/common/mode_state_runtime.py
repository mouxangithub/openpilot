"""Applies mode state against the real parameter store.

The rules live in mode_state.py, which is plain logic. This file adds the
two things the logic cannot do for itself: the advisory sidecar lock that
keeps concurrent writers from interleaving half a plan, and the read-back
verification that turns a dropped write into an error instead of a lie.
"""

import os
from contextlib import contextmanager

from openpilot.sunnypilot.common.param_read import read_bool
from openpilot.sunnypilot.common.safe_mode_runtime import is_safe_mode
from openpilot.sunnypilot.common.mode_state import (
  MODE_CONFIRMED_PARAM,
  MODE_ON_PARAM,
  OFFROAD_PARAM,
  ONROAD_PARAM,
  lock_reason,
  plan_matches_store,
  requested_mode_active,
  selected_mode,
  write_plan,
)

# The lock lives next to the other tmpfs files so it shares their lifetime:
# gone after a reboot, never inside the persisted parameter store. A stale
# lock cannot outlive the boot that created it.
LOCK_FN = "/tmp/.mode_state_lock"

# The store may refuse an unknown key (a device whose parameter library
# predates a key); the runtime treats that as "cannot verify" rather than
# as success.
PC = not os.path.isfile("/AGNOS")


class ModeStateError(Exception):
  """A refused or unverifiable mode change, with an HTTP-ish status."""

  def __init__(self, message: str, status: int = 409):
    super().__init__(message)
    self.status = status


@contextmanager
def _mode_lock(exclusive: bool):
  if PC:
    # No flock on this platform (and the tests must run without it).
    yield
    return
  import fcntl

  fd = os.open(LOCK_FN, os.O_CREAT | os.O_RDWR, 0o644)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
    yield
  finally:
    try:
      fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
      os.close(fd)


def _road_flag(params, key: str) -> bool | None:
  """A road flag as a real bool, or None when the store will not say."""
  try:
    value = params.get(key)
  except Exception:
    return None
  if value is None:
    return None
  if isinstance(value, bool):
    return value
  text = value.decode("utf-8", "ignore") if isinstance(value, bytes) else str(value)
  if text in ("1", "True", "true"):
    return True
  if text in ("0", "False", "false"):
    return False
  return None


def _confirmed_flag(params) -> bool | None:
  """The confirmation bit as tri-state: True, False, or None when unwritten.

  ``read_bool`` cannot tell "unwritten" from "false", and for this bit the
  difference decides whether a car that predates the bit keeps its mode.
  """
  try:
    raw = params.get(MODE_CONFIRMED_PARAM)
  except Exception:
    return None
  if raw is None:
    return None
  if isinstance(raw, bytes):
    return raw.decode("utf-8", "ignore") not in ("", "0", "False", "false")
  if isinstance(raw, str):
    return raw not in ("", "0", "False", "false")
  return bool(raw)


def experimental_mode_requested(params) -> bool:
  """Whether the store is asking for Experimental Mode right now.

  The single read every consumer should use. controlsd and selfdrived used to
  take the switch alone, which meant any writer could enable the mode without
  the driver ever seeing the dialog; routing them through here makes the
  confirmation bit part of the switch rather than a UI-only convention.
  """
  if not read_bool(params, MODE_ON_PARAM, False):
    return False
  return requested_mode_active(True, _confirmed_flag(params))


def snapshot(params, capable: bool | None = None) -> dict:
  """The mode as the store holds it, plus whether it may change."""
  is_onroad = _road_flag(params, ONROAD_PARAM)
  is_offroad = _road_flag(params, OFFROAD_PARAM)
  safe_mode = is_safe_mode(params)
  reason = lock_reason(is_onroad=is_onroad, is_offroad=is_offroad,
                       safe_mode=safe_mode, capable=capable)
  on = read_bool(params, MODE_ON_PARAM, False)
  confirmed = read_bool(params, MODE_CONFIRMED_PARAM, False)
  return {
    "mode": selected_mode(on),
    "values": {MODE_ON_PARAM: on, MODE_CONFIRMED_PARAM: confirmed},
    "locked": bool(reason),
    "reason": reason,
    "experimental_confirmed": confirmed,
  }


def set_experimental_mode(params, enabled: bool, *, acknowledged: bool = False,
                          expected: dict | None = None, capable: bool | None = None) -> dict:
  """Realise a user's mode request, or raise ModeStateError.

  ``expected`` is the caller's snapshot of the store, for optimistic
  concurrency: when handed in, the write only happens if the store still
  matches it, so a stale settings page cannot clobber a newer change.
  """
  with _mode_lock(exclusive=True):
    current = snapshot(params, capable)
    if current["locked"]:
      raise ModeStateError(current["reason"], 403)
    if expected is not None and current["values"] != expected:
      raise ModeStateError("Longitudinal mode changed elsewhere. Refresh before retrying.", 409)

    plan = write_plan(bool(enabled), confirmed=current["experimental_confirmed"],
                      acknowledged=bool(acknowledged))
    if plan is None:
      raise ModeStateError("Experimental Mode requires explicit acknowledgement before enabling.", 403)

    for key, value in plan:
      try:
        params.put(key, value, block=True)
      except Exception as exc:
        raise ModeStateError(f"Longitudinal mode update failed on {key}.", 500) from exc

    if not plan_matches_store(plan, lambda key: read_bool(params, key, False)):
      raise ModeStateError("Mode write could not be verified; refresh before retrying.", 500)

    return snapshot(params, capable)
