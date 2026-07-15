"""Optional LAN PIN for op助手 Web API."""

from __future__ import annotations

from aiohttp import web

from openpilot.common.params import Params

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
  path = request.path
  if _is_public(path):
    return await handler(request)

  pin = Params().get("ai_web_pin")
  if not pin:
    return await handler(request)

  pin_str = pin.decode() if isinstance(pin, bytes) else str(pin)
  if not pin_str.strip():
    return await handler(request)

  supplied = (
    request.headers.get("X-AI-Pin")
    or request.headers.get("X-AI-Token")
    or request.query.get("pin")
    or ""
  )
  if supplied != pin_str:
    return web.json_response({"ok": False, "error": "PIN required"}, status=401)
  return await handler(request)
