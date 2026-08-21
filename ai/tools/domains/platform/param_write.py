"""Write openpilot Params with type detection (mirrors Dashy serverd)."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params


def put_op_param(params: Params, key: str, value: Any, *, block: bool = False) -> None:
  try:
    param_type = params.get_type(key)
  except Exception:
    param_type = None

  if param_type == 1 or isinstance(value, bool):
    params.put_bool(
      key,
      bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes"),
      block=block,
    )
  elif param_type == 2:
    params.put(key, int(value), block=block)
  elif param_type == 3:
    params.put(key, float(value), block=block)
  elif isinstance(value, bool):
    params.put_bool(key, value, block=block)
  else:
    params.put(key, str(value), block=block)


def put_param(params: Params, key: str, value: Any, *, block: bool = False) -> None:
  from ai.common.config_store import is_ai_param, get_config_store
  from ai.common.sp_param_aliases import resolve_sp_param_key

  if is_ai_param(key):
    get_config_store().put(key, value)
    return
  put_op_param(params, resolve_sp_param_key(key), value, block=block)
