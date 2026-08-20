"""aiohttp routes for Panda firmware flash — used by op助手 Web UI."""

from __future__ import annotations

import asyncio

from aiohttp import web


def _json(data: dict, *, status: int = 200) -> web.Response:
  return web.json_response(data, status=status)


async def _run_sync(fn, *args, **kwargs):
  loop = asyncio.get_running_loop()
  return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def api_panda_status(_request: web.Request) -> web.Response:
  from ai.tools.panda_flash_tools import panda_firmware_status
  return _json(await _run_sync(panda_firmware_status))


async def api_panda_flash(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  from ai.tools.panda_flash_tools import flash_panda_firmware, offroad_flash_guard
  if bool(body.get("confirm")):
    blocked = offroad_flash_guard()
    if blocked:
      return _json(blocked, status=403)
  return _json(await _run_sync(
    flash_panda_firmware,
    confirm=bool(body.get("confirm")),
    serial=str(body.get("serial") or ""),
    all_pandas=body.get("all", body.get("all_pandas", True)),
    external=bool(body.get("external")),
    internal=bool(body.get("internal")),
    build_firmware=bool(body.get("build_firmware")),
  ))


def register_panda_routes(app: web.Application) -> None:
  app.router.add_get("/api/panda/status", api_panda_status)
  app.router.add_post("/api/panda/flash", api_panda_flash)
