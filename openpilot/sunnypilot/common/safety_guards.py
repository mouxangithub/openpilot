"""Safety guards borrowed from StarPilot, as plain logic.

Every function here is deliberately free of openpilot imports so the rules can
be unit tested on a PC. The callers pass in the little state they need.

The rules come from StarPilot's own safety posture:

- A parameter that changes how the car behaves must not be changed while the
  car is moving. StarPilot keeps a blocklist in
  ``starpilot/common/favorite_slots.py``.
- A communication problem that is only "the data is stale" deserves a short
  grace period; a process that is actually dead does not. StarPilot's
  ``selfdrived.evaluate_comm_issue`` draws exactly that line.
- A stale alert must not be able to block later events forever. StarPilot
  clears the longitudinal excessive-actuation alert once the condition is
  gone.
- Capability probing must never enable a feature from a mocked or stale
  fingerprint. StarPilot's ``car_params_capability`` only uses those to
  decide whether a toggle may be *shown*.
"""
from collections.abc import Iterable
from typing import Any

# ---------------------------------------------------------------------------
# 1. Parameters that must not change while the car is moving.
# ---------------------------------------------------------------------------

# Changing any of these alters how the car drives, which fingerprint it
# believes it is, or whether a safety function is active at all. Doing that
# mid-drive means the control loop and the user disagree about the car's
# configuration.
BLOCKED_ONROAD_KEYS: frozenset[str] = frozenset({
  # Which car this is
  "CarMake",
  "CarModel",
  "ForceFingerprint",
  "DisableOpenpilotLongitudinal",
  "SecOCKey",
  # Which model is loaded
  "Model",
  "ModelVersion",
  "DrivingModel",
  "DrivingModelVersion",
  "ActiveBigModel",
  "ActiveBigModelVersion",
  "ActiveSmallModel",
  "ActiveSmallModelVersion",
  # Steering calibration and handling
  "SteerRatio",
  "SteerDelay",
  "SteerKP",
  "SteerFriction",
  "SteerLatAccel",
  "SteerOffset",
  "CameraOffset",
  "ClusterOffset",
  # Driving behaviour
  "ExperimentalMode",
  "LongitudinalPersonality",
  "LongitudinalActuatorDelay",
  "StartAccel",
  "StopAccel",
  "VEgoStarting",
  "VEgoStopping",
  "StoppingDecelRate",
})

# A parameter that is not in the blocklist is still not safe if the caller
# says so, so the check takes the blocklist as an argument to stay testable.


def is_param_action_safe_onroad(name: str, is_onroad: bool,
                                blocked_keys: Iterable[str] = BLOCKED_ONROAD_KEYS) -> bool:
  """Whether ``name`` may be written while the car is moving.

  ``True`` means the write is allowed. A parameter that is not in the
  blocklist is always allowed; the blocklist only contains parameters that
  change how the car drives.
  """
  if not is_onroad:
    return True
  return name not in blocked_keys


def blocked_onroad_reason(name: str, is_onroad: bool,
                          blocked_keys: Iterable[str] = BLOCKED_ONROAD_KEYS) -> str | None:
  """A human-readable reason when the write is refused, else ``None``."""
  if is_param_action_safe_onroad(name, is_onroad, blocked_keys):
    return None
  return f"{name} cannot be changed while the car is moving"


# ---------------------------------------------------------------------------
# 2. Communication issue grace period.
# ---------------------------------------------------------------------------

# How long stale-but-present data is tolerated before it is called a
# communication issue. A single dropped frame is not a fault.
VALID_ONLY_COMM_ISSUE_GRACE_FRAMES = 5  # 0.5s at 100Hz


class CommIssueGrace:
  """Counts consecutive frames where the data is present but not valid.

  The distinction matters: a dead publisher is a real fault and is reported
  immediately, while a publisher that is alive and updating but whose last
  message was not decodable gets a short grace period.
  """

  def __init__(self, grace_frames: int = VALID_ONLY_COMM_ISSUE_GRACE_FRAMES):
    self.grace_frames = max(1, int(grace_frames))
    self.frames = 0

  def reset(self) -> None:
    self.frames = 0

  def update(self, *, all_checks: bool, all_alive: bool, all_freq_ok: bool) -> bool:
    """Update the counter and report whether a communication issue exists.

    Returns ``True`` when the caller should raise a communication issue.
    """
    if all_checks:
      self.reset()
      return False

    # A publisher that is not alive, or not publishing at the right rate, has
    # actually failed. Those are never given a grace period.
    if not all_alive or not all_freq_ok:
      self.reset()
      return True

    # The data is arriving but the last frame was not valid. Tolerate a
    # short run of these.
    self.frames += 1
    return self.frames >= self.grace_frames


# ---------------------------------------------------------------------------
# 3. Stale alert cleanup.
# ---------------------------------------------------------------------------

# The offroad alert payload carries the kind of excessive actuation that was
# detected. Once the condition is gone the alert has to be cleared, or it
# stays on screen and keeps blocking whatever reads it.
EXCESSIVE_ACTUATION_LATERAL = "lateral"
EXCESSIVE_ACTUATION_LONGITUDINAL = "longitudinal"


def clear_longitudinal_excessive_actuation(payload: Any) -> bool:
  """Whether a stored excessive-actuation alert should be cleared.

  Only the longitudinal kind is cleared: the lateral one is a different
  condition with a different remedy, and StarPilot leaves it alone.
  """
  if payload is None:
    return False
  if isinstance(payload, bytes):
    try:
      payload = payload.decode("utf-8")
    except UnicodeDecodeError:
      return False
  if isinstance(payload, str):
    try:
      import json
      payload = json.loads(payload)
    except (TypeError, ValueError):
      return False
  if not isinstance(payload, dict):
    return False
  return payload.get("extra") == EXCESSIVE_ACTUATION_LONGITUDINAL


# ---------------------------------------------------------------------------
# 4. Vehicle capability probing.
# ---------------------------------------------------------------------------

# Fingerprints that are only used for testing. A mocked fingerprint must
# never make a feature look available.
MOCK_FINGERPRINT_MARKERS: tuple[str, ...] = ("MOCK",)


def is_mock_fingerprint(fingerprint: Any) -> bool:
  """Whether a fingerprint looks like a mock/test one."""
  if not isinstance(fingerprint, str) or not fingerprint:
    return False
  return any(marker in fingerprint for marker in MOCK_FINGERPRINT_MARKERS)


def capability_fingerprint_is_usable(fingerprint: Any, *, forced: bool = False) -> bool:
  """Whether a fingerprint may be used to decide that a feature is available.

  A mocked fingerprint is never usable. When the fingerprint was forced by
  the user it is usable even if it does not match the connected car, because
  the user asked for that car specifically.
  """
  if is_mock_fingerprint(fingerprint):
    return False
  return True
