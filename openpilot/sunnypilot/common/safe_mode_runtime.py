"""Applies and restores Safe Mode against the real parameter store.

The rules live in safe_mode.py, which is plain logic. This file is the thin
layer that reads and writes Params, and it keeps every read defensive: a key
that the device's parameter library does not know about yet must leave the
feature alone, not take the caller down.
"""
from typing import Any

from openpilot.sunnypilot.common.param_read import read_bool
from openpilot.sunnypilot.common.safe_mode import (
  SAFE_MODE_BACKUP_PARAM,
  SAFE_MODE_MANAGED_KEYS,
  SAFE_MODE_PARAM,
  SAFE_MODE_REMOVE_KEYS,
  backup_entry,
  can_enter,
  can_restore,
  load_backup,
  missing_backup_keys,
  restore_plan,
  safe_value,
  serialize_backup,
  transition_block_reason,
)


class SafeModeError(Exception):
  """A Safe Mode transition that was refused or could not be confirmed.

  ``status`` is the HTTP status the API should answer with, the same
  convention ``ModeStateError`` uses.
  """

  def __init__(self, reason: str, status: int = 403):
    super().__init__(reason)
    self.status = status


def _get(params, key: str) -> str | None:
  """The raw string value of a key, or None when it is not set.

  Returns None for a key the store does not know about, which is the same
  answer as "not set": Safe Mode must not act on it.

  The store hands back decoded Python values, not text: a BOOL key gives a
  bool and a JSON key gives a dict. Both have to be normalised here, and the
  JSON case is the one that bit: ``str(dict)`` is a Python repr with single
  quotes, which no JSON parser accepts, so the backup document read back as
  empty and Safe Mode refused to record anything.
  """
  try:
    value = params.get(key)
  except Exception:
    return None
  if value is None:
    return None
  if isinstance(value, bytes):
    return value.decode("utf-8", errors="ignore")
  if isinstance(value, bool):
    return "1" if value else "0"
  if isinstance(value, (dict, list)):
    import json
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
  return str(value)


def _stock(params, key: str) -> str | None:
  """The registered stock value of a key, or None when it is not known."""
  try:
    value = params.get_stock_value(key)
  except Exception:
    return None
  if value is None:
    return None
  if isinstance(value, bytes):
    value = value.decode("utf-8", errors="ignore")
  text = str(value)
  return text if text else None


def _default(params, key: str) -> str | None:
  try:
    value = params.get(key, return_default=True)
  except Exception:
    return None
  if value is None or isinstance(value, bool):
    return None if value is None else ("1" if value else "0")
  if isinstance(value, bytes):
    return value.decode("utf-8", errors="ignore")
  return str(value)


def _coerce(params, key: str, text: str):
  """The value to hand ``put`` so the store's own type check passes.

  ``Params.put`` refuses a str for a BOOL, INT, FLOAT, JSON or BYTES key, and
  the refusal surfaces as a TypeError. A bare str therefore made every forced
  value and the entire backup document fail silently: the only write that
  survived was ``remove``, which is how Safe Mode managed to delete the steer
  knobs without recording what they were. The unit tests missed it because a
  fake store accepts any Python object.

  The registered type is read per key and the text is converted to match. A
  key the store does not describe is passed through unchanged, which is what
  a string key wants anyway.
  """
  try:
    kind = getattr(params.get_type(key), "name", "")
  except Exception:
    kind = ""
  if kind == "BOOL":
    return text in ("1", "True", "true")
  if kind == "INT":
    return int(float(text))
  if kind == "FLOAT":
    return float(text)
  if kind == "JSON":
    import json
    return json.loads(text)
  if kind == "BYTES":
    return text.encode("utf-8")
  return text


def _put(params, key: str, value: str) -> bool:
  """Write a key, tolerating a store that does not know it.

  Returns whether anything was written, so the caller can tell whether the
  car has to cycle for the change to take effect.
  """
  try:
    params.put(key, _coerce(params, key, value), block=True)
    return True
  except Exception:
    return False


def _remove(params, key: str) -> bool:
  """Remove a key, tolerating a store that does not know it."""
  try:
    params.remove(key)
    return True
  except Exception:
    return False


def is_safe_mode(params) -> bool:
  """Whether Safe Mode is switched on."""
  return read_bool(params, SAFE_MODE_PARAM, False)


def _write_backup(params, backup: dict) -> bool:
  """Store the backup document. Returns whether the store really kept it."""
  if not _put(params, SAFE_MODE_BACKUP_PARAM, serialize_backup(backup)):
    return False
  return bool(backup_document(params))


def _ensure_backup(params) -> bool:
  """Make sure every managed key is recorded. True when a record exists.

  Nothing may be forced until this holds: the enforcer re-applies whatever the
  flag says, and a forced value with no record of what it replaced cannot be
  undone by the driver.
  """
  backup = load_backup(_get(params, SAFE_MODE_BACKUP_PARAM))
  missing = missing_backup_keys(backup)
  if not missing:
    return True
  for key in missing:
    current = _get(params, key)
    backup[key] = backup_entry(current is not None, current)
  return _write_backup(params, backup)


def apply_safe_mode(params, *, ensure_backup: bool = True) -> bool:
  """Force the managed knobs to their safe values. Returns whether to cycle.

  ``ensure_backup`` is False on the periodic re-apply: once the original
  values are recorded they must not be overwritten with the forced ones.
  """
  changed = False

  if ensure_backup:
    missing = missing_backup_keys(load_backup(_get(params, SAFE_MODE_BACKUP_PARAM)))
    if not _ensure_backup(params):
      # Forcing anything now would delete or overwrite a user value with no
      # way back, so this is a refusal rather than a partial apply.
      return False
    changed = bool(missing)

  for key in SAFE_MODE_REMOVE_KEYS:
    if _get(params, key) is not None:
      if _remove(params, key):
        changed = True
  for key in SAFE_MODE_MANAGED_KEYS:
    if key in SAFE_MODE_REMOVE_KEYS:
      # Handled above: these are removed, never written (see safe_mode.py).
      continue
    target = safe_value(key,
                        current=_get(params, key),
                        stock=_stock(params, key),
                        default=_default(params, key))
    if target is None:
      # Nothing sane to write for this key. Leaving it alone is the only
      # honest option: writing a placeholder would change it to a value
      # nobody chose.
      continue
    if _get(params, key) == target:
      continue
    if _put(params, key, target):
      changed = True

  return changed


def restore_safe_mode(params) -> bool:
  """Undo Safe Mode from the backup. Returns whether anything changed.

  Refused while the car is moving: restoring rewrites the steering
  parameters, which must not happen mid-drive.
  """
  is_onroad = read_bool(params, "IsOnroad", False)
  is_offroad = read_bool(params, "IsOffroad", False)
  if not can_restore(is_onroad, is_offroad):
    return False

  backup = load_backup(_get(params, SAFE_MODE_BACKUP_PARAM))
  changed = False

  for key, value in restore_plan(backup):
    if not backup:
      # Nothing recorded: the keys were never forced, so there is nothing to
      # put back. This happens when Safe Mode was toggled before the backup
      # was ever written.
      break
    if value is None:
      try:
        params.remove(key)
        changed = True
      except Exception:
        pass
    elif _get(params, key) != value:
      if _put(params, key, value):
        changed = True

  try:
    params.remove(SAFE_MODE_BACKUP_PARAM)
  except Exception:
    pass

  return changed


def enforce_safe_mode(params, frame: int) -> bool:
  """Re-apply the forced values on a slow cadence while Safe Mode is on.

  Returns whether anything changed. Returns False when Safe Mode is off, so
  the caller can use it unconditionally.
  """
  if not is_safe_mode(params):
    return False
  from openpilot.sunnypilot.common.safe_mode import SAFE_MODE_ENFORCE_FRAMES
  if frame % SAFE_MODE_ENFORCE_FRAMES != 0:
    return False
  return apply_safe_mode(params, ensure_backup=False)


def backup_document(params) -> dict[str, Any]:
  """The current backup document, for display and tests."""
  return load_backup(_get(params, SAFE_MODE_BACKUP_PARAM))


def _put_bool(params, key: str, value: bool) -> bool:
  """Write a BOOL key. ``put`` with a string would raise a type mismatch."""
  try:
    params.put_bool(key, bool(value), block=True)
    return True
  except Exception:
    return False


def _road_flag(params, key: str) -> bool | None:
  """A road-state flag, or None when the store cannot answer.

  None is not "offroad": it means the state is unknown, and an unknown state
  must not authorise a write that changes how the car steers.
  """
  try:
    return bool(params.get_bool(key))
  except Exception:
    return None


def road_state(params) -> tuple[bool | None, bool | None]:
  """``(is_onroad, is_offroad)``, with None where the store cannot answer."""
  return _road_flag(params, "IsOnroad"), _road_flag(params, "IsOffroad")


def safe_mode_status(params, *, is_onroad: bool | None = None,
                     is_offroad: bool | None = None) -> dict[str, Any]:
  """Everything a caller needs to render Safe Mode without guessing."""
  if is_onroad is None or is_offroad is None:
    onroad, offroad = road_state(params)
    is_onroad = is_onroad if is_onroad is not None else onroad
    is_offroad = is_offroad if is_offroad is not None else offroad

  active = is_safe_mode(params)
  backup = backup_document(params)
  return {
    "active": active,
    "backupKeys": len(backup),
    "isOnroad": is_onroad,
    "isOffroad": is_offroad,
    "canEnter": (not active) and can_enter(is_onroad),
    "canRestore": active and is_onroad is not None and is_offroad is not None
                  and can_restore(is_onroad, is_offroad),
    "reason": transition_block_reason(active, is_onroad, is_offroad),
  }


def set_safe_mode(params, enabled: bool, *, is_onroad: bool | None = None,
                  is_offroad: bool | None = None) -> dict[str, Any]:
  """Switch Safe Mode on or off and return the resulting status.

  Raises ``SafeModeError`` when the transition is refused, or when the store
  does not read back what was just written. Idempotent: asking for the state
  that already holds is a no-op rather than an error, so a UI that re-sends
  its toggle cannot wedge the flag.
  """
  before = safe_mode_status(params, is_onroad=is_onroad, is_offroad=is_offroad)
  if bool(enabled) == before["active"]:
    return before

  reason = before["reason"]
  if reason:
    raise SafeModeError(reason, 403)

  change_wanted = bool(enabled)

  if change_wanted:
    # Take the backup and force the knobs before flipping the flag. The
    # enforcer in controlsd re-applies whatever the flag says, so a flag
    # without a backup would force values that can never be undone.
    apply_safe_mode(params, ensure_backup=True)
    if not backup_document(params):
      # The store refused the record. Leaving the flag clear is the only safe
      # end state: turning Safe Mode on without one is how the steer knobs
      # get deleted with nothing to restore them from.
      raise SafeModeError("Could not record the values Safe Mode would replace; nothing was forced.", 500)
    if not _put_bool(params, SAFE_MODE_PARAM, True):
      raise SafeModeError(f"Could not write {SAFE_MODE_PARAM}.", 500)
  else:
    restore_safe_mode(params)
    if _get(params, SAFE_MODE_BACKUP_PARAM) is not None:
      # The restore did not run, so clearing the flag would strand the
      # forced values with no record of what they used to be.
      raise SafeModeError("Could not restore the backed-up values; Safe Mode is still on.", 500)
    if not _remove(params, SAFE_MODE_PARAM):
      raise SafeModeError(f"Could not clear {SAFE_MODE_PARAM}.", 500)

  # A write that did not stick is the failure mode this guard exists for:
  # the caller must not be told Safe Mode is on when the control loop will
  # not see it.
  stored = read_bool(params, SAFE_MODE_PARAM, not change_wanted)
  if stored != change_wanted:
    raise SafeModeError(f"{SAFE_MODE_PARAM} did not read back as {change_wanted}.", 500)

  return safe_mode_status(params, is_onroad=is_onroad, is_offroad=is_offroad)
