"""Unified WebSocket endpoint: /api/cabana/stream/ws (live or replay)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from ai.services.cabana.live import run_live_ws
from ai.services.cabana.replay_ws import run_replay_ws

_FIRST_MSG_TIMEOUT = 3.0


async def ws_stream(request: web.Request) -> web.WebSocketResponse:
  """Unified stream endpoint.

  Mode selection: ``mode`` query param, else the first WS message
  (``{"mode": "replay"|"live", ...}``) within 3s, else live.
  Replay init message: route/speed/start_time/autoplay/full/decode/dbc/encoding.
  """
  ws = web.WebSocketResponse()
  await ws.prepare(request)

  mode = (request.query.get("mode") or "").strip().lower()
  init_msg: dict[str, Any] | None = None

  if not mode:
    try:
      first = await asyncio.wait_for(ws.receive(), timeout=_FIRST_MSG_TIMEOUT)
    except TimeoutError:
      first = None
    if first is not None and first.type == web.WSMsgType.TEXT:
      try:
        parsed = json.loads(first.data)
      except (ValueError, TypeError):
        parsed = None
      if isinstance(parsed, dict):
        init_msg = parsed
        mode = str(parsed.get("mode") or "").strip().lower()
      else:
        init_msg = None

  if mode == "replay":
    await run_replay_ws(request, ws, init_msg=init_msg)
  else:
    await run_live_ws(ws)
  return ws
