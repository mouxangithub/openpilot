"""aiohttp routes for TSK API — UI is in op 助手 settings sidebar."""

from __future__ import annotations

import asyncio

from aiohttp import web

from ai.tsk import service as tsk_service


def _json(data: dict, *, status: int = 200) -> web.Response:
  return web.json_response(data, status=status)


async def tsk_legacy_redirect(_request: web.Request) -> web.Response:
  raise web.HTTPFound("/?settings=secoc")


async def api_tsk_health(_request: web.Request) -> web.Response:
  return _json(tsk_service.get_health())


async def api_tsk_status(_request: web.Request) -> web.Response:
  return _json(tsk_service.get_key_status())


async def api_tsk_summary(_request: web.Request) -> web.Response:
  return _json(tsk_service.get_summary())


async def api_tsk_can_status(_request: web.Request) -> web.Response:
  return _json(tsk_service.get_can_status())


async def api_tsk_dataflash_status(_request: web.Request) -> web.Response:
  return _json(tsk_service.get_dataflash_status())


async def _run_sync(fn, *args, **kwargs):
  loop = asyncio.get_running_loop()
  return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def api_tsk_extract(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_extract))


async def api_tsk_match(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_match_and_install))


async def api_tsk_install_key(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  key = (body.get("key") or "").strip()
  return _json(await _run_sync(tsk_service.run_install_key, key))


async def api_tsk_uninstall(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_uninstall))


async def api_tsk_can_collect(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_can_collect_start))


async def api_tsk_dataflash_dump(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_dataflash_dump_start))


async def api_tsk_clear_cache(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_clear_cache))


async def api_tsk_reboot_device(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_reboot_device))


async def api_tsk_restart_manager(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_restart_manager))


async def api_tsk_restart_pandad(_request: web.Request) -> web.Response:
  return _json(await _run_sync(tsk_service.run_restart_pandad))


async def api_tsk_cancel_job(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  job = str(body.get("job") or "all")
  return _json(await _run_sync(tsk_service.run_cancel_job, job))


async def api_tsk_offroad_alert(_request: web.Request) -> web.Response:
  return _json(tsk_service.get_offroad_alert_status())


def register_tsk_routes(app: web.Application) -> None:
  app.router.add_get("/tsk/", tsk_legacy_redirect)
  app.router.add_get("/tsk", tsk_legacy_redirect)

  app.router.add_get("/api/tsk/health", api_tsk_health)
  app.router.add_get("/api/tsk/status", api_tsk_status)
  app.router.add_get("/api/tsk/summary", api_tsk_summary)
  app.router.add_get("/api/tsk/can-status", api_tsk_can_status)
  app.router.add_get("/api/tsk/dataflash-status", api_tsk_dataflash_status)
  app.router.add_post("/api/tsk/extract", api_tsk_extract)
  app.router.add_post("/api/tsk/match", api_tsk_match)
  app.router.add_post("/api/tsk/install-key", api_tsk_install_key)
  app.router.add_post("/api/tsk/uninstall", api_tsk_uninstall)
  app.router.add_post("/api/tsk/can-collect", api_tsk_can_collect)
  app.router.add_post("/api/tsk/dataflash-dump", api_tsk_dataflash_dump)
  app.router.add_post("/api/tsk/clear-cache", api_tsk_clear_cache)
  app.router.add_post("/api/tsk/reboot-device", api_tsk_reboot_device)
  app.router.add_post("/api/tsk/restart-manager", api_tsk_restart_manager)
  app.router.add_post("/api/tsk/restart-pandad", api_tsk_restart_pandad)
  app.router.add_post("/api/tsk/cancel-job", api_tsk_cancel_job)
  app.router.add_get("/api/tsk/offroad-alert", api_tsk_offroad_alert)

  # Legacy paths (old :11111 bookmarks)
  app.router.add_get("/api/health", api_tsk_health)
  app.router.add_get("/api/status", api_tsk_status)
  app.router.add_get("/api/can-status", api_tsk_can_status)
  app.router.add_get("/api/dataflash-status", api_tsk_dataflash_status)
  app.router.add_post("/api/extract", api_tsk_extract)
  app.router.add_post("/api/match", api_tsk_match)
  app.router.add_post("/api/install-key", api_tsk_install_key)
  app.router.add_post("/api/uninstall", api_tsk_uninstall)
  app.router.add_post("/api/can-collect", api_tsk_can_collect)
  app.router.add_post("/api/dataflash-dump", api_tsk_dataflash_dump)
  app.router.add_post("/api/clear-cache", api_tsk_clear_cache)


def init_tsk_for_aid(port: int) -> None:
  tsk_service.initialize(public_port=port)
