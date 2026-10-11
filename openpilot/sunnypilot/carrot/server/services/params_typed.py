"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Typed parameter access for the carrot HTTP API.

Everything the 7000 API writes has to go through sunnypilot's own `Params`, which is the
single source of truth every daemon reads. `Params.put` casts with
`python2cpp(type(value), params_keys.h's type)` and **raises TypeError on any mismatch** -
writing the int 0 to a BOOL key is an error, not a coercion (this bit us once already with
`OnroadUploads`). So the value coming off the wire is coerced to the declared type here,
up front, and every rejection carries a message the client can show.

Reads go the other way: `Params.get` already returns the declared Python type, so the only
work left is making the result JSON-safe.
"""

from typing import Any

try:
  from openpilot.common.params import UnknownKeyName
except Exception:  # pragma: no cover - openpilot's native params are absent on a bare dev host
  class UnknownKeyName(Exception):
    """Stand-in so this module stays importable (and testable) without the native store."""


class ParamWriteError(Exception):
  """A rejected write: unknown key, unsupported type, or an unparseable value."""


def _unknown_key() -> tuple[type[BaseException], ...]:
  """The exception the store raises for a key it does not have, looked up when a
  write fails rather than captured at import.

  `except <a non-exception>` never matches, so binding this at import makes the
  API's 400-for-an-unknown-key promise depend on import order: a test module that
  stands in for openpilot.common.params in sys.modules (test_carrot_man does)
  leaves whatever was imported in that window holding its stub. The native store
  is asked again per failure, and its class is the only one worth catching.
  """
  try:
    from openpilot.common.params import UnknownKeyName as real
  except Exception:
    real = None
  for candidate in (real, UnknownKeyName):
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
      return (candidate,)
  return ()


# Keys that must never be writable over HTTP. Both are produced by the device itself and
# changing them over the network would either be a no-op or break identification.
_READ_ONLY_KEYS = frozenset((
  "CarParams",
  "CarParamsSP",
  "CarParamsCache",
  "CarParamsPersistent",
  "CarParamsSPCache",
  "CarParamsSPPersistent",
))

# A write to either can take the USB port out from under the other (see _enforce_usb_port).
_USB_PORT_KEYS = frozenset(("AdbEnabled", "JetlinkLink"))


def _as_bool(value: Any) -> bool:
  if isinstance(value, bool):
    return value
  # Only 0/1 are accepted as numbers. Treating any non-zero float as True would let a
  # client silently set a BOOL with a value it never meant as one.
  if isinstance(value, (int, float)):
    if value == 0:
      return False
    if value == 1:
      return True
    raise ParamWriteError(f"cannot read {value!r} as a boolean (expected 0 or 1)")
  if isinstance(value, str):
    text = value.strip().lower()
    if text in ("1", "true", "yes", "on"):
      return True
    if text in ("0", "false", "no", "off", ""):
      return False
  raise ParamWriteError(f"cannot read {value!r} as a boolean")


def _as_int(value: Any) -> int:
  if isinstance(value, bool):
    return int(value)
  if isinstance(value, int):
    return value
  if isinstance(value, float):
    if value != int(value):
      raise ParamWriteError(f"cannot read {value!r} as an integer (has a fraction)")
    return int(value)
  if isinstance(value, str):
    text = value.strip()
    try:
      return int(text)
    except ValueError:
      pass
    try:
      as_float = float(text)
    except ValueError as exc:
      raise ParamWriteError(f"cannot read {value!r} as an integer") from exc
    if as_float != int(as_float):
      raise ParamWriteError(f"cannot read {value!r} as an integer (has a fraction)")
    return int(as_float)
  raise ParamWriteError(f"cannot read {value!r} as an integer")


def _as_float(value: Any) -> float:
  if isinstance(value, bool):
    return float(value)
  if isinstance(value, (int, float)):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value.strip())
    except ValueError as exc:
      raise ParamWriteError(f"cannot read {value!r} as a number") from exc
  raise ParamWriteError(f"cannot read {value!r} as a number")


def _as_string(value: Any) -> str:
  if isinstance(value, str):
    return value
  if isinstance(value, bool):
    return "1" if value else "0"
  if isinstance(value, (int, float)):
    return str(value)
  raise ParamWriteError(f"cannot read {value!r} as a string")


def _as_json(value: Any) -> Any:
  import json

  if isinstance(value, (dict, list)):
    return value
  if isinstance(value, str):
    text = value.strip()
    if not text:
      raise ParamWriteError("cannot read an empty string as JSON")
    try:
      return json.loads(text)
    except ValueError as exc:
      raise ParamWriteError(f"cannot read {value!r} as JSON") from exc
  raise ParamWriteError(f"cannot read {value!r} as JSON")


_COERCERS = {
  "BOOL": _as_bool,
  "INT": _as_int,
  "FLOAT": _as_float,
  "STRING": _as_string,
  "JSON": _as_json,
}


def coerce_for_type(value: Any, key_type) -> Any:
  """Coerce a JSON-decoded value to the Python type `Params.put` will accept.

  `key_type` is a `ParamKeyType` member, but it is dispatched on by *name* rather than by
  importing the enum: `openpilot.common.params` needs the compiled store, and doing the
  import here would make this module - the part that decides what gets written - untestable
  off-device. TIME and BYTES are deliberately unsupported: neither can be expressed
  unambiguously by a JSON client, and guessing would store a value the fork cannot parse.
  """
  name = getattr(key_type, "name", None) or str(key_type).rsplit(".", 1)[-1]
  coercer = _COERCERS.get(name)
  if coercer is None:
    raise ParamWriteError(f"type {name} cannot be written over the API")
  return coercer(value)


def json_safe(value: Any) -> Any:
  """Make a value returned by `Params.get` encodable, without inventing data."""
  if value is None or isinstance(value, (bool, int, float, str)):
    return value
  if isinstance(value, (dict, list)):
    return value
  if isinstance(value, (bytes, bytearray)):
    try:
      return bytes(value).decode("utf-8")
    except UnicodeDecodeError:
      return bytes(value).hex()
  return str(value)


def read_only_reason(name: str) -> str | None:
  if name in _READ_ONLY_KEYS:
    return f"{name} is written by the device and is read-only over the API"
  return None


def set_param_value(params, name: str, value: Any) -> Any:
  """Validate and write one parameter, returning the value that was stored.

  Raises `ParamWriteError` with a client-facing message for anything the caller got wrong
  (unknown key, read-only key, unrepresentable value). Nothing else is allowed to escape:
  a TypeError leaking out of `Params.put` would be reported as a 500 instead of a 400.
  """
  if not isinstance(name, str) or not name.strip():
    raise ParamWriteError("missing name")
  name = name.strip()

  reason = read_only_reason(name)
  if reason is not None:
    raise ParamWriteError(reason)

  try:
    params.check_key(name)
  except _unknown_key() as exc:
    raise ParamWriteError(f"unknown parameter {name}") from exc

  key_type = params.get_type(name)
  try:
    coerced = coerce_for_type(value, key_type)
  except ParamWriteError:
    raise
  except Exception as exc:  # pragma: no cover - defensive, keeps this a 400
    raise ParamWriteError(f"cannot write {value!r} to {name}: {exc}") from exc

  try:
    params.put(name, coerced)
  except _unknown_key() as exc:
    raise ParamWriteError(f"unknown parameter {name}") from exc
  except TypeError as exc:
    raise ParamWriteError(f"type mismatch writing {name}: {exc}") from exc

  if name in _USB_PORT_KEYS:
    _enforce_usb_port(params)

  return coerced


def _enforce_usb_port(params=None) -> None:
  """ADB and Jetlink both need the comma's USB port. AGNOS's ADB gadget (g1) holds
  the only device controller while AdbEnabled is set, and jetlink refuses to take
  it, so the link reads as unavailable until ADB is off.

  `UIStateSP._enforce_usb_port` does this in the native UI's params pass, but that
  pass only runs where a builtin display does, and the carrot servers are the other
  places either key can be written from. Over Wi-Fi the link leaves the port
  alone, and ADB with it. Best-effort: a failure here must not turn a good write
  into a 400."""
  try:
    from openpilot.sunnypilot import jetlink_adapter

    if params is None:
      from openpilot.common.params import Params
      params = Params()
    status = jetlink_adapter.status()
    if status is not None and getattr(status, "enabled", False) and getattr(status, "mode", None) != "wifi" \
        and params.get_bool("AdbEnabled"):
      params.put_bool("AdbEnabled", False)
  except Exception:
    pass


def get_param_values(params, names: list[str], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
  """Read several parameters, never raising for a single bad key.

  A missing or unreadable key falls back to `defaults[name]` (or None) so one odd name
  cannot fail a whole bulk read - the app asks for a list of keys it half-remembers.
  """
  defaults = defaults or {}
  values: dict[str, Any] = {}
  for name in names:
    try:
      values[name] = json_safe(params.get(name))
    except Exception:
      values[name] = json_safe(defaults.get(name))
  return values
