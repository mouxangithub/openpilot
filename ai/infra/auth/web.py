"""Web API middleware — LAN access without PIN (trusted local network)."""

from __future__ import annotations

from aiohttp import web

_PUBLIC_PATHS = frozenset({
  "/", "/static/", "/api/ai/bootstrap", "/api/ai/status",
})


def _is_public(path: str) -> bool:
  if path in _PUBLIC_PATHS:
    return True
  if path.startswith("/static/"):
    return True
  return False


@web.middleware
async def ai_auth_middleware(request: web.Request, handler):
  return await handler(request)
