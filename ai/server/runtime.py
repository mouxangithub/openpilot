"""Background runtime loops for op助手."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from openpilot.common.swaglog import cloudlog

from ai.server.deps import get_state_reader, params, read_ai_config
from ai.server.handlers.scheduler import scheduler_execute_action, device_wifi_connected
from ai.core.sync.hub import broadcast_status
from ai.tools.scheduler import run_due_tasks

_PARAMS = params()


async def status_watch_loop(_app: web.Application) -> None:
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
      cloudlog.debug(f"aid: status watch: {e}")


async def scheduler_loop(_app: web.Application) -> None:
  while True:
    await asyncio.sleep(60)
    try:
      state = get_state_reader().update(timeout=0)
      await run_due_tasks(
        _PARAMS,
        is_driving=lambda: state.is_driving,
        is_ignition=lambda: state.ignition,
        is_wifi=device_wifi_connected,
        execute_action=scheduler_execute_action,
      )
    except Exception as e:
      cloudlog.error(f"aid: scheduler loop error: {e}")
