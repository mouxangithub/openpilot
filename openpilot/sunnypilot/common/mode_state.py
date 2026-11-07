"""Longitudinal mode state: user intent versus automatic decisions.

The seam this skeleton leaves open is where the scenario-driven statuses
(curvature, lead, signal, ...) will attach if this fork ever grows a
conditional-experimental layer. What is real today is the discipline around
the one mode switch this fork actually has:

- Experimental Mode cannot be enabled without its confirmation bit, from any
  writer. The settings UI checked it; the parameter API did not, so a
  companion app could enable a mode the driver never acknowledged.
- While Safe Mode is on, the mode is locked. Safe Mode forces this switch
  back off every few frames, so a writer that ignores the lock would fight
  the enforcer and the driver would see a toggle that flaps.
- The road state must be known and consistent before the mode may change.
  A read of neither/both IsOnroad and IsOffroad means the caller's view of
  the world is broken, and a mode change on top of that is a guess.
- Writes verify by reading back. A write the store silently dropped must
  not be reported as success.

Only user-intent statuses persist. An automatic status ("there was a lead")
must never outlive the scenario that produced it: after a restart it would
be indistinguishable from the user having chosen it. The normalizer is the
enforcement point.
"""

MODE_ON_PARAM = "ExperimentalMode"
MODE_CONFIRMED_PARAM = "ExperimentalModeConfirmed"
MODE_SAFE_PARAM = "SafeMode"
ONROAD_PARAM = "IsOnroad"
OFFROAD_PARAM = "IsOffroad"

# Statuses, ordered the way the reference design numbers them so a later
# scenario layer can extend without renumbering the user-intent ones.
STATUS_OFF = 0
STATUS_USER_DISABLED = 1
STATUS_USER_ENABLED = 2
STATUS_CURVATURE = 3
STATUS_LEAD = 4
STATUS_SIGNAL = 5
STATUS_SPEED = 6
STATUS_SPEED_LIMIT = 7
STATUS_STOP_LIGHT = 8

MANUAL_STATUSES = frozenset({STATUS_OFF, STATUS_USER_DISABLED, STATUS_USER_ENABLED})


def is_manual_status(status: int) -> bool:
  return int(status) in MANUAL_STATUSES


def normalize_persisted_status(status: int) -> int:
  """The only statuses allowed to survive a restart are the user's."""
  status = int(status)
  return status if status in MANUAL_STATUSES else STATUS_OFF


def road_state_known(is_onroad: bool | None, is_offroad: bool | None) -> bool:
  """Both flags present and not contradictory."""
  return is_onroad is not None and is_offroad is not None and is_onroad != is_offroad


def lock_reason(*, is_onroad: bool | None, is_offroad: bool | None,
                safe_mode: bool, capable: bool | None) -> str:
  """Why the mode may not change right now, or "" when it may.

  ``capable`` is tri-state: ``None`` means the caller does not know, which
  is a warning at most -- a companion app that cannot read CarParams must
  still be able to toggle the mode. A known ``False`` (no openpilot
  longitudinal on this car) is a hard lock.
  """
  if not road_state_known(is_onroad, is_offroad):
    return "Longitudinal control mode requires a known, consistent road state."
  if safe_mode:
    return "Longitudinal control mode is locked by Safe Mode."
  if capable is False:
    return "openpilot longitudinal control is unavailable for the detected vehicle."
  return ""


def write_plan(enabled: bool, *, confirmed: bool, acknowledged: bool) -> tuple[tuple[str, bool], ...] | None:
  """The parameter writes that realise the request, or None to refuse.

  Enabling needs the confirmation bit, either already set or handed over by
  the caller in the same request. Disabling never touches the confirmation
  bit: the driver acknowledged the mode once, and a later off/on cycle
  should not quietly re-prompt them.
  """
  if enabled:
    if not confirmed and not acknowledged:
      return None
    if confirmed:
      return ((MODE_ON_PARAM, True),)
    return ((MODE_CONFIRMED_PARAM, True), (MODE_ON_PARAM, True))
  return ((MODE_ON_PARAM, False),)


def selected_mode(on: bool) -> str:
  """The human-readable mode name for a snapshot."""
  return "experimental" if on else "chill"


def requested_mode_active(enabled: bool, confirmed: bool | None) -> bool:
  """Whether the store is asking for the mode, confirmation bit included.

  ``confirmed is None`` means the store has no confirmation bit at all, which
  is the layout cars had before the bit existed. Those are grandfathered: the
  bit exists to stop a *new* enable from skipping the dialog, not to switch
  off a car that has been driving the mode for months. A bit that is present
  and False does block, because that state means someone disabled the mode
  and the switch left over is stale.
  """
  return bool(enabled) and confirmed is not False



def plan_matches_store(plan, read_bool) -> bool:
  """Every planned write is verifiably in the store, by reading it back."""
  for key, value in plan:
    try:
      if bool(read_bool(key)) is not bool(value):
        return False
    except Exception:
      return False
  return True
