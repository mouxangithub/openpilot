"""Background runtime loops for op助手."""

from __future__ import annotations

import asyncio
import json
import traceback
import warnings
from typing import Any

from aiohttp import web

try:
  from openpilot.common.swaglog import cloudlog
  _OP_AVAILABLE = True
except Exception as _op_err:
  _OP_AVAILABLE = False
  cloudlog = None  # type: ignore[misc,assignment]
  warnings.warn(f"aid: openpilot unavailable, runtime loops disabled: {_op_err}")

try:
  from ai.server.deps import get_state_reader, params, read_ai_config
  _PARAMS = params()
except Exception:
  get_state_reader = None  # type: ignore[misc,assignment]
  params = None  # type: ignore[misc,assignment]
  read_ai_config = None  # type: ignore[misc,assignment]
  _PARAMS = None

try:
  from ai.server.handlers.scheduler import scheduler_execute_action, device_wifi_connected
except Exception:
  scheduler_execute_action = None  # type: ignore[misc,assignment]
  device_wifi_connected = None  # type: ignore[misc,assignment]

try:
  from ai.core.sync.hub import broadcast_status
except Exception:
  broadcast_status = None  # type: ignore[misc,assignment]

try:
  from ai.tools.scheduler import run_due_tasks
except Exception:
  run_due_tasks = None  # type: ignore[misc,assignment]


async def status_watch_loop(_app: web.Application) -> None:
  if get_state_reader is None or read_ai_config is None or broadcast_status is None:
    return
  last_sig: str | None = None
  while True:
    await asyncio.sleep(3)
    try:
      state = get_state_reader().update(timeout=0)
      config = read_ai_config()
      sig = json.dumps({
        "driving": state.is_driving,
        "state": state.to_dict(),
        "model": config.model,
        "provider": config.provider,
        "configured": config.is_configured,
      }, sort_keys=True, default=str)
      if sig != last_sig:
        last_sig = sig
        await broadcast_status(state, config)
    except Exception as e:
      if cloudlog is not None:
        cloudlog.debug(f"aid: status watch: {e}")


async def scheduler_loop(_app: web.Application) -> None:
  if run_due_tasks is None or scheduler_execute_action is None or device_wifi_connected is None or _PARAMS is None:
    return
  while True:
    await asyncio.sleep(60)
    try:
      state = get_state_reader().update(timeout=0)
      wifi = await device_wifi_connected()
      await run_due_tasks(
        _PARAMS,
        is_driving=lambda: state.is_driving,
        is_ignition=lambda: state.ignition,
        is_wifi=lambda: wifi,
        execute_action=scheduler_execute_action,
      )
    except Exception as e:
      if cloudlog is not None:
        cloudlog.error(f"aid: scheduler loop error: {e}")
        cloudlog.error(f"aid: scheduler loop traceback: {traceback.format_exc()}")
