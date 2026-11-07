"""opendbc-side Params accessor for the BYD port.

opendbc must stay importable standalone (unit tests / other consumers), so it
cannot hard-depend on ``openpilot.common.params``. This module tries to reach
the running openpilot instance and falls back to defaults otherwise, keeping
the tunables functional in the full system and harmless in isolation.
"""
import os

try:
  from openpilot.common.params import Params as _OpenpilotParams
except ImportError:
  _OpenpilotParams = None


class BydParams:
  """Thin wrapper: reads real Params when available, otherwise env/defaults."""

  def __init__(self):
    self._params = _OpenpilotParams() if _OpenpilotParams is not None else None
    self._cache: dict[str, object] = {}

  def _get(self, key: str, default: object) -> object:
    if self._params is not None:
      try:
        return self._params.get(key, encoding="utf8") or default
      except Exception:
        return default
    # standalone fallback: env override, then default
    env = os.environ.get(key)
    if env is not None:
      return env
    return default

  def get_bool(self, key: str, default: bool = False) -> bool:
    val = self._get(key, default)
    if isinstance(val, bool):
      return val
    if isinstance(val, (int, float)):
      return val != 0
    if isinstance(val, str):
      return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)

  def get_int(self, key: str, default: int = 0) -> int:
    val = self._get(key, default)
    try:
      return int(val)
    except (TypeError, ValueError):
      return default

  def get_float(self, key: str, default: float = 0.0) -> float:
    val = self._get(key, default)
    try:
      return float(val)
    except (TypeError, ValueError):
      return default
