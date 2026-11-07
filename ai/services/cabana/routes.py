"""Cabana route registration."""
from __future__ import annotations
from pathlib import Path
from aiohttp import web

from ai.services.cabana.handlers import (
  api_car,
  api_dbc,
  api_dbcs,
  api_route_export,
  api_route_file,
  api_route_frames,
  api_route_media,
  api_route_summary,
  api_route_thumbnail,
  api_routes,
  api_similar_bits,
)
from ai.services.cabana.ai_explain import (
  api_analyze,
  api_explain_batch,
  api_explain_cache,
  api_explain_signal,
)
from ai.services.cabana.dbc_edit import (
  api_dbc_ai_edit,
  api_dbc_ai_infer,
  api_dbc_commit,
  api_dbc_rollback,
  api_dbc_versions,
)
from ai.services.cabana.live import ws_live
from ai.services.cabana.profile import (
  api_profile_commit,
  api_profile_naming,
  api_profile_scan,
)
from ai.services.cabana.replay_ws import ws_offline
from ai.services.cabana.stream_ws import ws_stream


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
  app.router.add_get("/api/cabana/route/{name}/frames", api_route_frames)
  app.router.add_get("/api/cabana/route/{name}/export", api_route_export)
  app.router.add_post("/api/cabana/tools/similar_bits", api_similar_bits)
  # AI-assisted DBC editing (user DBC store; opendbc originals stay read-only)
  app.router.add_post("/api/cabana/dbc/ai/infer", api_dbc_ai_infer)
  app.router.add_post("/api/cabana/dbc/ai/edit", api_dbc_ai_edit)
  app.router.add_post("/api/cabana/dbc/commit", api_dbc_commit)
  app.router.add_get("/api/cabana/dbc/versions", api_dbc_versions)
  app.router.add_post("/api/cabana/dbc/rollback", api_dbc_rollback)
  # One-click vehicle profile + auto DBC reverse engineering
  app.router.add_post("/api/cabana/profile/scan", api_profile_scan)
  app.router.add_post("/api/cabana/profile/naming", api_profile_naming)
  app.router.add_post("/api/cabana/profile/commit", api_profile_commit)
  app.router.add_get("/api/cabana/ws", ws_live)
  app.router.add_get("/api/cabana/offline/ws", ws_offline)
  app.router.add_get("/api/cabana/stream/ws", ws_stream)
  app.router.add_post("/api/cabana/analyze", api_analyze)
  app.router.add_post("/api/cabana/explain", api_explain_signal)
  app.router.add_post("/api/cabana/explain_batch", api_explain_batch)
  app.router.add_get("/api/cabana/explain_cache", api_explain_cache)
