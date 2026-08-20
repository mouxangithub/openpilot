"""Cabana route registration."""
from __future__ import annotations
from pathlib import Path
from aiohttp import web

from ai.services.cabana.handlers import (
  api_car,
  api_dbc,
  api_dbcs,
  api_route_file,
  api_route_media,
  api_route_summary,
  api_route_thumbnail,
  api_routes,
)
from ai.services.cabana.ai_explain import (
  api_analyze,
  api_explain_batch,
  api_explain_cache,
  api_explain_signal,
)
from ai.services.cabana.live import ws_live
from ai.services.cabana.replay_ws import ws_offline


def register_routes(app: web.Application, static_root: Path) -> None:
  """Register Cabana API routes (UI is embedded in op助手 main page)."""

  async def _cabana_redirect(_request: web.Request) -> web.HTTPFound:
    return web.HTTPFound(location="/?cabana=1")

  app.router.add_get("/cabana", _cabana_redirect)
  app.router.add_get("/cabana/", _cabana_redirect)

  app.router.add_get("/api/cabana/car", api_car)
  app.router.add_get("/api/cabana/dbcs", api_dbcs)
  app.router.add_get("/api/cabana/dbc/{name}", api_dbc)
  app.router.add_get("/api/cabana/routes", api_routes)
  app.router.add_get("/api/cabana/route/{name}/media", api_route_media)
  app.router.add_get("/api/cabana/route/{name}/thumbnail", api_route_thumbnail)
  app.router.add_get("/api/cabana/route/{name}/summary", api_route_summary)
  app.router.add_get("/api/cabana/route/{name}/file", api_route_file)
  app.router.add_get("/api/cabana/ws", ws_live)
  app.router.add_get("/api/cabana/offline/ws", ws_offline)
  app.router.add_post("/api/cabana/analyze", api_analyze)
  app.router.add_post("/api/cabana/explain", api_explain_signal)
  app.router.add_post("/api/cabana/explain_batch", api_explain_batch)
  app.router.add_get("/api/cabana/explain_cache", api_explain_cache)
