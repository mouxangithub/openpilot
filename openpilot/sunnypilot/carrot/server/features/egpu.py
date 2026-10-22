"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""eGPU status: `/api/egpu/model`.

This fork has no `big_model` download/compile pipeline to report on - the eGPU (Chestnut)
shows up as `deviceState.chestnutPresent` plus the `chestnutState` telemetry service, which
is exactly what the native eGPU panel reads. So the endpoint answers with that, and says
`available: false` when no eGPU has ever been seen rather than inventing a compile state.
"""
import logging

from aiohttp import web



logger = logging.getLogger("openpilot.carrot.server.egpu")

EGPU_NOTE = "eGPU is reported through deviceState/chestnutState; no big-model compile pipeline here"


def _runtime(request: web.Request):
  from .system import RUNTIME_KEY

  holder = request.app.get(RUNTIME_KEY)
  return holder.get() if holder is not None else None


async def api_status(request: web.Request) -> web.Response:
  runtime = _runtime(request)
  device = chestnut = {}
  if runtime is not None:
    try:
      runtime.snapshot()
      device = runtime._last.get("deviceState") or {}
      chestnut = runtime._last.get("chestnutState") or {}
    except Exception as exc:
      logger.warning("carrot_server: egpu snapshot failed: %s", exc)
  present = bool(device.get("chestnutPresent"))
  payload = {
    "ok": True,
    "available": present,
    "state": "active" if present else "absent",
    "present": present,
    "telemetry": chestnut,
    "note": EGPU_NOTE,
  }
  return web.json_response(payload)


async def api_compile_restart(_request: web.Request) -> web.Response:
  """Nothing compiles a big model here, so the request is answered, not honoured."""
  return web.json_response({"ok": False, "error": "no big-model compile pipeline in this fork",
                            "rebootRequested": False}, status=501)


def register(app: web.Application) -> None:
  app.router.add_get("/api/egpu/model", api_status)
  app.router.add_post("/api/egpu/model/compile-restart", api_compile_restart)
