"""Pick a CarParams snapshot that may be trusted for capability decisions.

The persistent snapshot can be a MOCK while the car process is still
starting up. Showing a setting that the car does not support is a papercut;
enabling a control path from a wrong snapshot is a crash. This module keeps
the two apart.

The rules, borrowed from StarPilot's ``car_params_capability``:

- A MOCK fingerprint is never usable.
- The live snapshot is preferred; the persistent one is the fallback.
- When the user forced a fingerprint, only that exact model is accepted.
- A previous route's snapshot is only used when it matches the forced model
  exactly, and only to decide whether a toggle may be *shown*. It never
  enables a control path on its own.

The module is free of openpilot imports so it can be tested on a PC. The
caller passes the raw bytes and this module asks for the fingerprint through
the callback, which keeps the capnp dependency out of here.
"""
from collections.abc import Callable
from typing import Any

# The fingerprint the car process writes while it is still starting up.
MOCK_FINGERPRINT = "MOCK"

# The snapshots that may hold a real fingerprint, in the order they are
# preferred. Onroad the live snapshot exists; offroad only the persistent
# one does.
ONROAD_KEYS = ("CarParams", "CarParamsPersistent")
OFFROAD_KEYS = ("CarParamsPersistent",)


def _fingerprint_of(raw: bytes | None,
                    extract: Callable[[bytes], str] | None) -> str:
  """The fingerprint inside a CarParams blob, or "" when it cannot be read."""
  if not raw:
    return ""
  if extract is None:
    return ""
  try:
    return str(extract(raw) or "")
  except Exception:
    return ""


def capability_snapshot(params: Any, *, is_onroad: bool,
                        extract: Callable[[bytes], str] | None = None,
                        get: Callable[[str], Any] | None = None,
                        get_bool: Callable[[str], bool] | None = None) -> bytes | None:
  """The CarParams snapshot that may be used for a capability decision.

  ``params`` is only used through the two callables, so this function works
  with the real Params and with a test double. ``get`` must return the raw
  bytes of a param and ``get_bool`` a boolean flag.

  Returns ``None`` when no trustworthy snapshot is available.
  """
  if get is None or get_bool is None:
    return None

  try:
    model = str(get("CarModel") or "")
  except Exception:
    model = ""

  try:
    forced = bool(get_bool("ForceFingerprint"))
  except Exception:
    forced = False

  keys = ONROAD_KEYS if is_onroad else OFFROAD_KEYS
  for key in keys:
    try:
      raw = get(key)
    except Exception:
      continue
    fingerprint = _fingerprint_of(raw, extract)
    if not fingerprint or fingerprint == MOCK_FINGERPRINT:
      continue
    if forced and model and fingerprint != model:
      # The car is not the model the user forced; nothing here is usable.
      return None
    return raw

  if forced and model:
    try:
      previous = get("CarParamsPrevRoute")
    except Exception:
      previous = None
    if _fingerprint_of(previous, extract) == model:
      return previous

  return None


def capability_fingerprint(snapshot: bytes | None,
                           extract: Callable[[bytes], str] | None) -> str:
  """The fingerprint of a snapshot, or "" when it cannot be read."""
  return _fingerprint_of(snapshot, extract)
