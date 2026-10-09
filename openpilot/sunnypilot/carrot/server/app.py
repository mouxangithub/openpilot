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
from .features import credentials as credentials_feature
from .features import egpu as egpu_feature
from .features import intro as intro_feature
from .features import params as params_feature
from .features import params_extra as params_extra_feature
from .features import preferences as preferences_feature
from .features import settings as settings_feature
from .features import system as system_feature
from .features import tools as tools_feature
from .features import unsupported as unsupported_feature
from .features import ws as ws_feature

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

  params_feature.register(app)
  params_extra_feature.register(app)
  ws_feature.register(app)
  camera_feature.register(app)
  system_feature.register(app)
  settings_feature.register(app)
  preferences_feature.register(app)
  cars_feature.register(app)
  carrot_navi_feature.register(app)
  egpu_feature.register(app)
  bluetooth_feature.register(app)
  tools_feature.register(app)
  credentials_feature.register(app)
  intro_feature.register(app)
  # Registered last: it claims the wildcard prefixes for the subsystems this fork does not
  # run, so a real route must never be shadowed by a refusal.
  unsupported_feature.register(app)
  app.router.add_get("/api/health", _health)
  app.router.add_get("/", _index)
  return app


async def _index(request: web.Request) -> web.Response:
  """What a browser sees when it is pointed at the device - cheaper than guessing."""
  routes = sorted({str(resource.canonical) for resource in request.app.router.resources()})
  return web.json_response({
    "ok": True,
    "service": "carrot_server",
    "port": config.DEFAULT_PORT,
    "routes": routes,
  })


async def _health(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, "status": "ok"})
