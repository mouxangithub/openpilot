"""Unified read/write: ai_* → config.json, everything else → openpilot Params."""

from __future__ import annotations

import errno
from typing import Any

from openpilot.common.params import Params

from ai.common.config_store import get_config_store, is_ai_param
from ai.common.sp_param_aliases import resolve_sp_param_key
from ai.tools.param_write import put_op_param


def format_persist_error(exc: BaseException) -> str:
  if isinstance(exc, OSError) and exc.errno in (errno.ENOSPC, 28):
    return (
      "设备存储空间已满，无法保存配置。请清理 /data 分区（删除旧行车片段、大体积日志或 Git 缓存），"
      "SSH 执行 df -h /data 查看剩余空间后重试。"
    )
  return str(exc)


def read_param(params: Params | None, key: str, default: Any = None, *, block: bool = False) -> Any:
  if is_ai_param(key):
    return get_config_store().get(key, default)
  p = params or Params()
  key = resolve_sp_param_key(key)
  try:
    val = p.get(key, block=block)
  except Exception:
    return default
  if val is None:
    return default
  return val


def read_param_bool(params: Params | None, key: str, default: bool = False) -> bool:
  if is_ai_param(key):
    return get_config_store().get_bool(key, default)
  p = params or Params()
  key = resolve_sp_param_key(key)
  try:
    return p.get_bool(key, block=False)
  except Exception:
    raw = read_param(p, key, None)
    if raw is None:
      return default
    if isinstance(raw, bytes):
      raw = raw.decode(errors="replace")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def write_param(params: Params | None, key: str, value: Any, *, block: bool = False) -> None:
  if is_ai_param(key):
    get_config_store().put(key, value)
    return
  from ai.tools.param_write import put_op_param
  put_op_param(params or Params(), resolve_sp_param_key(key), value, block=block)


def write_param_bool(params: Params | None, key: str, value: bool, *, block: bool = False) -> None:
  if is_ai_param(key):
    get_config_store().put_bool(key, value)
    return
  p = params or Params()
  p.put_bool(resolve_sp_param_key(key), value, block=block)


def remove_param(params: Params | None, key: str) -> None:
  if is_ai_param(key):
    get_config_store().remove(key)
    return
  (params or Params()).remove(resolve_sp_param_key(key))
