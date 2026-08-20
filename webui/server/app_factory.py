"""aiohttp application factory."""

from __future__ import annotations

from aiohttp import web

from webui.server.bridge.state_hub import start_state_hub
from webui.server.bridge.ws_handler import start_ws_broadcast
from webui.server.routes import register_routes
from webui.server.routes.dev import register_dev_routes


def create_app() -> web.Application:
  start_state_hub()
  app = web.Application()
  register_routes(app)
  register_dev_routes(app)
  start_ws_broadcast(app)

  @web.middleware
  async def cors(request, handler):
    if request.method == "OPTIONS":
      resp = web.Response(status=204)
    else:
      resp = await handler(request)
    origin = request.headers.get("Origin")
    if origin:
      resp.headers["Access-Control-Allow-Origin"] = origin
      resp.headers["Vary"] = "Origin"
      resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
      resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
      resp.headers["Access-Control-Max-Age"] = "86400"
    return resp

  app.middlewares.insert(0, cors)

  @web.middleware
  async def no_cache_js(request, handler):
    resp = await handler(request)
    if request.path.startswith("/static/js/") or request.path.startswith("/static/css/"):
      resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp

  app.middlewares.insert(0, no_cache_js)

  import os
  if os.environ.get("WEBUI_DEV_PC") == "1":
    @web.middleware
    async def no_cache_static(request, handler):
      resp = await handler(request)
      if request.path.startswith("/static/") or request.path == "/":
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
      return resp
    app.middlewares.insert(0, no_cache_static)

  return app
