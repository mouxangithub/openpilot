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

import logging

from aiohttp import web

from . import config
from .features import bluetooth as bluetooth_feature
from .features import camera as camera_feature
from .features import carrot_navi as carrot_navi_feature
from .features import cars as cars_feature
from .features import dashcam as dashcam_feature
from .features import egpu as egpu_feature
from .features import intro as intro_feature
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
from .features import unsupported as unsupported_feature
from .features import vision_diag as vision_diag_feature
from .features import vision_test as vision_test_feature
from .features import web_settings as web_settings_feature
from .features import web_sound as web_sound_feature
from .features import ws as ws_feature
from .features import xiaoge as xiaoge_feature
from .features.static import handle_index

logger = logging.getLogger("openpilot.carrot.server")

# The app payloads here are small JSON documents; the 8 MB CarrotPilot allows is for the
# camera/raw WebSockets, which will be added as separate transports.
MAX_BODY_BYTES = 1024 * 1024


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
  return web.json_response({"ok": True, "status": "ok"})
