from aiohttp import web

from ..services import favorite_slots
from ..services.setting_favorites import read_setting_favorites, update_setting_favorites


async def get_setting_favorites(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, **read_setting_favorites()})


async def set_setting_favorites(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "bad request"}, status=400)
  settings = update_setting_favorites(body)
  return web.json_response({"ok": True, **settings})


async def get_favorite_slots(request: web.Request) -> web.Response:
  """The assigned slots with live value/kind, so a client can render one-tap actions."""
  return web.json_response({"ok": True, "slots": favorite_slots.describe_favorite_slots()})


async def apply_favorite_slot(request: web.Request) -> web.Response:
  """Execute one slot. Body: {"slot": 0} or {"key": "..."}, optional {"value": ...}."""
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "bad request"}, status=400)
  slot = body.get("slot")
  slot = slot if isinstance(slot, int) and not isinstance(slot, bool) else None
  key = str(body.get("key") or "").strip() or None
  has_value = "value" in body
  try:
    result = favorite_slots.apply_favorite_slot(
      slot=slot, key=key, value=body.get("value") if has_value else None,
    )
  except favorite_slots.FavoriteSlotError as exc:
    return web.json_response({"ok": False, "error": exc.message, "code": exc.code}, status=400)
  return web.json_response({"ok": True, **result})


def register(app: web.Application) -> None:
  app.router.add_get("/api/setting_favorites", get_setting_favorites)
  app.router.add_post("/api/setting_favorites", set_setting_favorites)
  app.router.add_get("/api/setting_favorites/slots", get_favorite_slots)
  app.router.add_post("/api/setting_favorites/apply", apply_favorite_slot)
