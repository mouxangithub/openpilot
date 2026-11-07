"""Fault-tolerant reads for parameters that may not exist on the device yet.

Two independent failure modes make a bare ``params.get_*()`` unsafe for a
parameter this fork introduced:

1. **The key is not registered.** ``common/params_keys.h`` is compiled into
   ``libparams_c.so``, so a key only exists on the device after that shared
   library has been rebuilt. Until then ``Params.get`` raises
   ``UnknownKeyName``. Reading such a key from a control loop kills the
   daemon, and with it the whole car.

2. **The getter does not take the argument you passed.** ``Params.get_float``
   is ``get_float(key, default=0.0)``; it has no ``return_default`` keyword.
   Passing one raises ``TypeError``, which a naive ``except Exception``
   swallows into a silent default.

Both failures are invisible on a developer machine that has a matching build,
so the reads below go through one helper that is explicit about the
difference between "not registered", "not set" and "set to a value".

The helpers take an untyped ``params`` object on purpose: importing
``openpilot.common.params`` pulls the swaglog -> hardware -> cereal chain
onto every PC host that wants to unit test the code that uses them.
"""
import math
from typing import Any

# Values that mean "the user has not touched this knob". A zero friction or a
# zero lateral-accel factor is not a physically meaningful setting, so a 0.0
# read is treated as unset rather than as a deliberate choice.
UNSET_FLOAT = 0.0


def _is_missing_key_error(exc: BaseException) -> bool:
  """True when the exception means "this parameter is not registered".

  ``UnknownKeyName`` lives in ``openpilot.common.params``, which cannot be
  imported here, so the check is done on the class name. That keeps the
  module free of the openpilot import chain and therefore PC-testable.
  """
  return type(exc).__name__ == "UnknownKeyName"


def read_bool(params: Any, key: str, default: bool = False) -> bool:
  """Read a boolean parameter, falling back to ``default``.

  A missing key and a failed read both mean "off". Callers use this for
  feature switches, where the safe default is the disabled state.
  """
  try:
    return bool(params.get_bool(key))
  except Exception as exc:
    if _is_missing_key_error(exc):
      return default
    raise


def read_float(params: Any, key: str, default: float = 0.0) -> float:
  """Read a float parameter, falling back to ``default``.

  ``Params.get_float`` takes a positional ``default`` and has no
  ``return_default`` keyword, so the raw value is fetched through
  ``get()`` instead: that is the only getter that can return the
  registered default for an unset key.
  """
  try:
    raw = params.get(key, return_default=True)
  except Exception as exc:
    if _is_missing_key_error(exc):
      return float(default)
    raise
  if raw is None:
    return float(default)
  try:
    value = float(raw)
  except (TypeError, ValueError):
    return float(default)
  if not math.isfinite(value):
    return float(default)
  return value


def read_str(params: Any, key: str, default: str = "") -> str:
  """Read a string parameter, falling back to ``default``."""
  try:
    raw = params.get(key, return_default=True)
  except Exception as exc:
    if _is_missing_key_error(exc):
      return default
    raise
  if raw is None:
    return default
  return str(raw)


# The settings tier a key belongs to. Mirrors ParamSettingsTier in
# common/params.h; duplicated rather than imported because importing the
# params extension pulls the swaglog chain onto a PC test host.
SETTINGS_SIMPLE = 0
SETTINGS_ADVANCED = 1


def read_tuning_level(params: Any, key: str, default: int = 0) -> int:
  """How deep a key sits in the tuning ladder: 0 means "not a knob".

  Everything is swallowed here on purpose, unlike the value reads above. A
  device whose libparams_c.so predates the metadata answers with the default,
  and so does a stand-in that has no opinion. That is the honest answer:
  nothing declared a level there, so nothing may depend on one.
  """
  try:
    return int(params.get_tuning_level(key))
  except Exception:
    return int(default)


def read_settings_tier(params: Any, key: str, default: int = SETTINGS_ADVANCED) -> int:
  """Which settings tier a key belongs to: simple (0) or advanced (1)."""
  try:
    return int(params.get_settings_tier(key))
  except Exception:
    return int(default)

