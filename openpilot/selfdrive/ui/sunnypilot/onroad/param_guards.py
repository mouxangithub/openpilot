"""
Safe parameter readers for onroad widgets.

The StarPilot ports in this directory read gating params that are deliberately
NOT registered in ``common/params_keys.h`` (that file is shared and must not be
touched). ``Params.check_key`` raises ``UnknownKeyName`` for any unregistered
key - even on read - so every access needs a guard that falls back to an
in-code default. Centralising that here keeps the widgets readable and makes
the "unregistered param" list auditable in one place.
"""


def safe_get_bool(params, key: str, default: bool = False) -> bool:
  """Read a bool param, falling back to `default` for unregistered keys."""
  try:
    return bool(params.get_bool(key))
  except Exception:
    return default


def safe_get_int(params, key: str, default: int = 0) -> int:
  """Read an int param, falling back to `default` for unregistered keys."""
  try:
    return int(params.get_int(key, default))
  except Exception:
    return default


def safe_get_float(params, key: str, default: float = 0.0) -> float:
  """Read a float param, falling back to `default` for unregistered keys."""
  try:
    return float(params.get_float(key, default))
  except Exception:
    return default


def safe_get_str(params, key: str, default: str = "") -> str:
  """Read a str param, falling back to `default` for unregistered keys."""
  try:
    value = params.get(key, encoding="utf-8")
    return default if value is None else str(value)
  except Exception:
    return default


def safe_get_json(params, key: str, default=None):
  """Read a JSON param (dict), falling back to `default` when absent/invalid."""
  import json

  raw = safe_get_str(params, key, "")
  if not raw:
    return default
  try:
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else default
  except (ValueError, TypeError):
    return default
