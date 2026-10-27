"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""aiohttp application for the carrot API server (port 7000).

One process, one app, one `Params` handle. The app is built by `create_app` so tests can
mount it with a fake `Params`, and the module deliberately does not import `Params` at
import time - `carrot_server.py` decides when the real store is needed.
"""

import asyncio
import contextlib
import logging

from aiohttp import ClientSession, web

from . import config
from .features import bluetooth as bluetooth_feature
from .features import camera as camera_feature
from .features import opui_proxy as opui_proxy_feature
from .features import carrot_navi as carrot_navi_feature
from .features import cars as cars_feature
from .features import dashcam as dashcam_feature
from .features import egpu as egpu_feature
from .features import intro as intro_feature
from .features import lan_services as lan_services_feature
from .features import mapbox_tokens as mapbox_tokens_feature
from .features import params as params_feature
from .features import params_extra as params_extra_feature
from .features import screenrecord as screenrecord_feature
from .features import setting_favorites as setting_favorites_feature
from .features import setting_popular_values as setting_popular_values_feature
from .features import setting_profiles as setting_profiles_feature
from .features import settings as settings_feature
from .features import ssh_keys as ssh_keys_feature
from .features import static as static_feature
from .features import stream as stream_feature
from .features import support_terminal as support_terminal_feature
from .features import system as system_feature
from .features import terminal as terminal_feature
from .features import tools as tools_feature
from .features import version_history as version_history_feature
from .features import unsupported as unsupported_feature
from .features import vision_diag as vision_diag_feature
from .features import vision_test as vision_test_feature
from .features import web_settings as web_settings_feature
from .features import wheel_controls as wheel_controls_feature
from .features import push as push_feature
from .features import web_sound as web_sound_feature
from .features import ws as ws_feature
from .features import xiaoge as xiaoge_feature
from .features.static import handle_index
from .services import weather as weather_service
from .services.auto_update import auto_update_loop
from .services.git_status import git_status_loop
from .services.heartbeat import heartbeat_loop
from .services.params import HAS_PARAMS
from .services.popular_values import start_popular_value_upload
from .services.settings import get_settings_cached
from .services.static_assets import start_precompress

logger = logging.getLogger("openpilot.carrot.server")

# The app payloads here are small JSON documents; the 8 MB CarrotPilot allows is for the
# camera/raw WebSockets, which will be added as separate transports.
MAX_BODY_BYTES = 1024 * 1024


def _do_gc_and_trim() -> None:
  """gc.collect + malloc_trim; runs in the thread pool (cp parity, app.py)."""
  import gc

  gc.collect()
  try:
    import ctypes

    libc = ctypes.CDLL("libc.so.6")
    libc.malloc_trim(0)
  except Exception:
    pass


async def _malloc_trim_loop(app: web.Application) -> None:
  """Periodic gc + malloc_trim to reclaim leaked objects and return C heap (cp parity).

  Skipped while raw WebSocket clients are attached or CarrotVision is active, so the
  trim never competes with an active vision consumer."""
  while True:
    await asyncio.sleep(30.0)
    hub = app.get(ws_feature.RAW_HUB_KEY)
    if hub is not None and hub.client_count() > 0:
      continue
    params = app.get(params_feature.PARAMS_KEY)
    try:
      if params is not None and params.get_bool("CarrotVisionActive"):
        continue
    except Exception:
      pass
    await asyncio.to_thread(_do_gc_and_trim)


async def _warm_settings_cache() -> None:
  """Build the /api/settings cache at startup so the first settings-page open does not
  pay for it on its critical path. Best-effort (cp parity)."""
  try:
    await asyncio.to_thread(get_settings_cached)
  except Exception:
    pass


async def _background_tasks_ctx(app: web.Application):
  """cp-parity background services for the 7000 server.

  cp's app.py starts these in on_startup; this fork wires them through a cleanup ctx
  instead. Most visibly, `hb_last` is initialised here so /api/heartbeat_status always
  answers with a heartbeat document - a null `hb` reads as "7000 未收到信息" in the App.
  """
  app["hb_last"] = {"ok": None, "msg": "not yet", "ts": 0}
  if HAS_PARAMS:
    app["hb_task"] = asyncio.create_task(heartbeat_loop(app))
  app["git_status_task"] = asyncio.create_task(git_status_loop())
  app["auto_update_task"] = asyncio.create_task(auto_update_loop())
  app["popular_value_upload_task"] = start_popular_value_upload(app)
  app["malloc_trim_task"] = asyncio.create_task(_malloc_trim_loop(app))
  app["settings_warm_task"] = asyncio.create_task(_warm_settings_cache())
  app["precompress_task"] = start_precompress(config.WEB_DIR)
  try:
    yield
  finally:
    task_keys = ("hb_task", "git_status_task", "auto_update_task", "popular_value_upload_task",
                 "malloc_trim_task", "settings_warm_task", "precompress_task")
    for key in task_keys:
      task = app.pop(key, None)
      if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
          await task


@web.middleware
async def json_error_middleware(request: web.Request, handler):
  """Answer with JSON, never with an aiohttp HTML traceback.

  A malformed but valid-JSON request must not look like a crash to the app, and an
  unexpected exception must still be diagnosable - hence the log plus a JSON body.
  """
  try:
    return await handler(request)
  except web.HTTPException:
    raise
  except Exception as exc:
    logger.exception("carrot_server: unhandled error on %s", request.path)
    return web.json_response({"ok": False, "error": f"internal error: {exc}"}, status=500)


def create_app(params=None) -> web.Application:
  """Build the application. `params` defaults to the real store."""
  if params is None:
    from openpilot.common.params import Params

    params = Params()

  app = web.Application(client_max_size=MAX_BODY_BYTES, middlewares=[json_error_middleware])
  app[params_feature.PARAMS_KEY] = params

  # CarrotPilot's features.register_all() order, minus egpu_model (this fork keeps its own
  # egpu.py, which reads the chestnut/jetlink stack rather than CarrotPilot's big_model
  # pipeline) and plus the features this fork added (camera, params_extra).
  static_feature.register(app)          # "/" - the panel, with the asset manifest injected
  intro_feature.register(app)
  carrot_navi_feature.register(app)
  stream_feature.register(app)
  support_terminal_feature.register(app)
  ws_feature.register(app)
  settings_feature.register(app)
  params_feature.register(app)
  params_extra_feature.register(app)
  setting_favorites_feature.register(app)
  setting_popular_values_feature.register(app)
  setting_profiles_feature.register(app)
  web_settings_feature.register(app)
  wheel_controls_feature.register(app)
  version_history_feature.register(app)
  push_feature.register(app)            # PWA manifest/sw + Web Push subscriptions
  ssh_keys_feature.register(app)
  mapbox_tokens_feature.register(app)
  cars_feature.register(app)
  system_feature.register(app)
  terminal_feature.register(app)
  dashcam_feature.register(app)
  egpu_feature.register(app)
  screenrecord_feature.register(app)
  tools_feature.register(app)
  xiaoge_feature.register(app)
  vision_test_feature.register(app)
  vision_diag_feature.register(app)
  web_sound_feature.register(app)
  bluetooth_feature.register(app)
  camera_feature.register(app)
  lan_services_feature.register(app)
  # The 5080 webui daemon's API (model manager, vehicle selection), pass-through.
  opui_proxy_feature.register(app)
  # Registered last: it claims the wildcard prefixes for the subsystems this fork still does
  # not run, so a real route must never be shadowed by a refusal.
  unsupported_feature.register(app)
  app.router.add_get("/api/health", _health)
  # The route listing used to sit at "/". It moved here when the panel took over "/", so
  # anything that used it to discover the surface still gets the same JSON.
  app.router.add_get("/api/routes", _routes)
  # The static feature owns "/"; this is the same handler under the name the recovery server
  # and older links use.
  app.router.add_get("/index.html", handle_index)

  # Static last, on purpose: every explicit route above - including unsupported.py's
  # `{tail:.*}` refusals - has to win the match, and a prefix resource at "/" would shadow
  # them if it were registered first.
  app.router.add_static("/shared-assets/", config.SELFDRIVE_ASSETS_DIR, show_index=False)
  # show_index is off, unlike CarrotPilot: nothing in the panel needs a directory listing,
  # and one would expose web/src and web/tests over the LAN.
  app.router.add_static("/", config.WEB_DIR, show_index=False)

  # Shared outbound ClientSession (stream proxy, ssh key checks, popular-value
  # upload, the xiaoge proxy). cp parity: created on startup, closed on cleanup.
  async def _http_session_ctx(app: web.Application):
    app["http"] = ClientSession()
    try:
      yield
    finally:
      session = app.pop("http", None)
      if session is not None:
        await session.close()

  app.cleanup_ctx.append(_http_session_ctx)

  # Weather adaptation needs somewhere with a clock that is allowed to block on
  # a socket, and this is the only long-lived process in the fork that already
  # does. It does nothing unless both WeatherOffsetsEnabled and
  # WeatherAutoDetect are on, so an off-road device with the feature off makes
  # no outbound request at all.
  async def _weather_ctx(app: web.Application):
    task = asyncio.create_task(weather_service.weather_loop(app))
    try:
      yield
    finally:
      task.cancel()
      with contextlib.suppress(asyncio.CancelledError):
        await task

  app.cleanup_ctx.append(_weather_ctx)

  # cp-parity background loops: heartbeat, git status, auto update, popular value
  # upload, malloc trim, settings warm-up, static precompress. Started after the
  # http session ctx so app["http"] exists for the popular-value upload.
  app.cleanup_ctx.append(_background_tasks_ctx)
  return app



async def _routes(request: web.Request) -> web.Response:
  """The JSON route listing, for anything that wants to discover the surface.

  "/" now serves the web panel (index.html) rather than this; see config.WEB_DIR.
  """
  routes = sorted({str(resource.canonical) for resource in request.app.router.resources()})
  return web.json_response({
    "ok": True,
    "service": "carrot_server",
    "port": config.DEFAULT_PORT,
    "routes": routes,
  })


async def _health(request: web.Request) -> web.Response:
  # `weather` is whatever the poller last wrote, so the feature can be checked
  # with one curl instead of a param read plus a log dig. It is absent until
  # the first reading and stays at "clear" when the feature is off.
  return web.json_response({"ok": True, "status": "ok", "weather": request.app.get("weather")})
