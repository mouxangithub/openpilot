"""Write Params with type detection (mirrors Dashy serverd)."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params


def put_param(params: Params, key: str, value: Any) -> None:
  try:
    param_type = params.get_type(key)
  except Exception:
    param_type = None

  if param_type == 1 or isinstance(value, bool):
    params.put_bool(key, bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes"))
  elif param_type == 2:
    params.put(key, int(value))
  elif param_type == 3:
    params.put(key, float(value))
  elif isinstance(value, bool):
    params.put_bool(key, value)
  else:
    params.put(key, str(value))
