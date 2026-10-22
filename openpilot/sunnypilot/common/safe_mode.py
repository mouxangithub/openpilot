"""Safe Mode: put the driving-related knobs back to a conservative baseline.

When something is wrong and the cause is not yet known, the useful move is to
remove the variables. Safe Mode does that: it forces every knob this fork
added back to a conservative value, remembers what they were, and restores
them afterwards.

Two rules make this safe rather than merely convenient:

- The restore is refused while the car is moving. Restoring rewrites the
  steering ratio, the friction and the personality; doing that mid-drive
  means the control loop and the user disagree about the car for as long as
  the writes take.
- The backup is taken before anything is forced, so a failure part way
  through still leaves a record of where the values were.

The parameter list covers only the switches this fork actually ships. A list
copied wholesale from another fork would name keys that are not registered
here, and every one of those would raise when read.
"""
import json
from typing import Any

SAFE_MODE_PARAM = "SafeMode"
SAFE_MODE_BACKUP_PARAM = "SafeModeBackup"

# How often the forced values are re-applied while Safe Mode is on. Other
# processes and the settings UI can write these keys too, and a knob that
# drifts back to a user value while Safe Mode is on defeats the point.
SAFE_MODE_ENFORCE_FRAMES = 20

# The knobs Safe Mode forces. These are the switches this fork added and the
# lateral model parameters the learners keep adjusting.
SAFE_MODE_MANAGED_KEYS: tuple[str, ...] = (
  # Driving mode
  "ExperimentalMode",
  "LongitudinalPersonality",
  # Lateral learners and their manual knobs
  "ForceAutoTune",
  "ForceAutoTuneOff",
  "SteerRatio",
  "SteerDelay",
  "SteerFriction",
  "SteerKP",
  "SteerLatAccel",
  "UseAutoSteerDelay",
  "CustomSR",
  # Features this fork added
  "LaneCenteringEnabled",
  "LaneCenterOffset",
  "LaneCenteringE2EAuthority",
  "NNFFMode",
  "FlmRuntimeOverridesEnabled",
  "LongitudinalFollowingProfileEnabled",
  "WeatherOffsetsEnabled",
  "VisionSpeedLimitEnabled",
  "VisionSpeedLimitLowLimitFilter",
  "LeadDuplicateGuardEnabled",
  "ModelLeadTrajectoryEnabled",
  "CscCurvatureLearningEnabled",
)

# The values Safe Mode forces. Anything not listed here falls back to its
# stock value, and then to the registered default.
SAFE_MODE_FIXED_VALUES: dict[str, str] = {
  "ExperimentalMode": "0",
  "LongitudinalPersonality": "1",  # 1 = standard (0 = aggressive, 2 = relaxed)
  "ForceAutoTune": "0",
  "ForceAutoTuneOff": "0",
  "UseAutoSteerDelay": "1",
  "CustomSR": "0",
  "LaneCenteringEnabled": "0",
  "LaneCenterOffset": "0.0",
  "LaneCenteringE2EAuthority": "0",
  "NNFFMode": "0",
  "FlmRuntimeOverridesEnabled": "0",
  "LongitudinalFollowingProfileEnabled": "0",
  "WeatherOffsetsEnabled": "0",
  "VisionSpeedLimitEnabled": "0",
  "VisionSpeedLimitLowLimitFilter": "0",
  "LeadDuplicateGuardEnabled": "0",
  "ModelLeadTrajectoryEnabled": "0",
  "CscCurvatureLearningEnabled": "0",
}

# The steer knobs are "0.0 means not set" parameters: every consumer falls
# back to the vehicle's stock value when the key is absent, and a stored 0.0
# would be read back as a present-but-invalid value by at least one of them
# (the FLM workspace's get_float with a stock default). For these, Safe Mode
# removes the key instead of writing anything, which is what "reset to
# stock" actually means here.
SAFE_MODE_REMOVE_KEYS: tuple[str, ...] = (
  "SteerDelay",
  "SteerFriction",
  "SteerKP",
  "SteerLatAccel",
  "SteerRatio",
)

# A registered stock value of "0.0" is indistinguishable from "not known",
# so Safe Mode refuses to write it; the caller falls back to removing the
# key or to the registered default.
UNKNOWN_STOCK = "0.0"


def _decode(payload: Any) -> dict:
  """Parse a stored backup document, returning {} when it is unusable."""
  if payload is None:
    return {}
  if isinstance(payload, dict):
    return payload
  if isinstance(payload, bytes):
    try:
      payload = payload.decode("utf-8")
    except UnicodeDecodeError:
      return {}
  if not isinstance(payload, str):
    return {}
  if not payload.strip():
    return {}
  try:
    parsed = json.loads(payload)
  except (TypeError, ValueError):
    return {}
  return parsed if isinstance(parsed, dict) else {}


def load_backup(payload: Any) -> dict[str, dict]:
  """The backup document as {key: {"present": bool, "value": str|None}}."""
  raw = _decode(payload)
  backup: dict[str, dict] = {}
  for key, entry in raw.items():
    if not isinstance(entry, dict):
      continue
    value = entry.get("value")
    backup[str(key)] = {
      "present": bool(entry.get("present")),
      "value": None if value is None else str(value),
    }
  return backup


def serialize_backup(backup: dict[str, dict]) -> str:
  """Serialize a backup document for storage."""
  return json.dumps(backup, separators=(",", ":"), sort_keys=True)


def safe_value(key: str, *, current: str | None, stock: str | None,
               default: str | None) -> str | None:
  """The value Safe Mode should write for a key.

  A fixed value wins. Otherwise the stock value is used, and only when that
  is known; writing a placeholder stock value would change the parameter to
  something nobody chose. ``None`` means "leave this key alone".
  """
  fixed = SAFE_MODE_FIXED_VALUES.get(key)
  if fixed is not None:
    return fixed

  if stock is not None and stock != UNKNOWN_STOCK:
    return stock

  # No stock value registered for this key. The default is the honest
  # answer, but only when the key carries one.
  if default:
    return default
  return None


def can_enter(is_onroad: bool | None) -> bool:
  """Whether Safe Mode may be switched on now.

  Switching it on rewrites the steering knobs, and the on-road blocklist
  refuses exactly those writes while the car is moving. Safe Mode must not
  exempt itself from its own rule: a steering ratio rewritten mid-drive is
  either ignored, because the control loop read it at start-up, or applied
  half way through a solve, and both leave the driver guessing what the car
  is actually running. So switching it on is a parked operation as well.

  ``None`` means the road state could not be read, which is not good enough
  to authorise a write.
  """
  return is_onroad is False


def can_restore(is_onroad: bool, is_offroad: bool) -> bool:
  """Whether the backup may be restored now.

  Restoring rewrites the steering parameters, so it has to happen while the
  car is parked. Both flags have to be known and not contradictory; a
  missing pair of flags means the state is unknown and the answer is no.
  """
  return (not is_onroad) and bool(is_offroad)


def transition_block_reason(active: bool, is_onroad: bool | None, is_offroad: bool | None) -> str | None:
  """Why a Safe Mode transition is refused right now, or None when it is allowed.

  Kept here rather than in the runtime so the wording, the gate and the
  status payload cannot drift apart.
  """
  if active:
    if is_onroad is None or is_offroad is None:
      return "The road state is unknown; Safe Mode can only be undone while parked."
    if not can_restore(is_onroad, is_offroad):
      return "Safe Mode rewrites the steering knobs; park the car before undoing it."
    return None
  if is_onroad is None:
    return "The road state is unknown; Safe Mode can only be switched on while parked."
  if not can_enter(is_onroad):
    return "Safe Mode rewrites the steering knobs; park the car before switching it on."
  return None


def restore_plan(backup: dict[str, dict],
                 managed_keys: tuple[str, ...] = SAFE_MODE_MANAGED_KEYS) -> list[tuple[str, str | None]]:
  """The writes needed to undo Safe Mode.

  Returns a list of ``(key, value)``. A value of ``None`` means the key was
  not set before Safe Mode, so restoring means removing it.
  """
  plan: list[tuple[str, str | None]] = []
  seen: set[str] = set()
  for key in managed_keys:
    seen.add(key)
    entry = backup.get(key, {"present": False, "value": None})
    plan.append((key, entry["value"] if entry["present"] else None))
  for key, entry in backup.items():
    if key in seen:
      continue
    plan.append((key, entry["value"] if entry["present"] else None))
  return plan


def backup_entry(present: bool, value: str | None) -> dict:
  """A backup entry for one key."""
  return {"present": bool(present), "value": None if value is None else str(value)}


def missing_backup_keys(backup: dict[str, dict],
                        managed_keys: tuple[str, ...] = SAFE_MODE_MANAGED_KEYS) -> list[str]:
  """Managed keys that are not in the backup yet.

  The backup is built up the first time Safe Mode is entered, and a later
  version may add keys; those are appended without disturbing the existing
  record.
  """
  return [key for key in managed_keys if key not in backup]
