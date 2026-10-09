"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Web settings, favorites and setting profiles - the parts only the client cares about.

Setting profiles are the one part that touches real parameters, and they do it through
`params_backup`: creating one snapshots the carrot catalog, applying one restores through
the same validated write path a backup uses. So a profile cannot save a value the settings
screen itself would have rejected.
"""

from aiohttp import web

from ..services.preferences import (
  SettingProfileError,
  apply_setting_profile,
  create_setting_profile,
  delete_setting_profile,
  preview_setting_profile,
  read_setting_favorites,
  read_setting_profiles,
  read_web_settings,
  resolve_web_capabilities,
  update_setting_favorites,
  update_setting_profile,
  update_web_settings,
)

POPULAR_VALUES_NOTE = " ".join((
  "not implemented: this would upload the device's settings to a fleet server to download",
  "aggregate values. This fork does not ship a telemetry upload, so the endpoint answers",
  "an empty result instead of sending anything.",
))


async def api_web_settings_get(request: web.Request) -> web.Response:
  settings = read_web_settings()
  return web.json_response({"ok": True, "settings": settings, "capabilities": resolve_web_capabilities(settings)})


async def api_web_settings_post(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  settings = update_web_settings(body)
  return web.json_response({"ok": True, "settings": settings, "capabilities": resolve_web_capabilities(settings)})


async def api_favorites_get(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, **read_setting_favorites()})


async def api_favorites_post(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({"ok": False, "error": "invalid json"}, status=400)
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  return web.json_response({"ok": True, **update_setting_favorites(body)})


async def api_profiles_get(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, **read_setting_profiles()})


async def api_profiles_create(request: web.Request) -> web.Response:
  """Save the current settings as a named profile. Body: {"name": "..."}."""
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  try:
    profile = create_setting_profile(body.get("name", ""))
  except SettingProfileError as exc:
    return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=400)
  return web.json_response({"ok": True, "profile": profile})


async def _profile_action(request: web.Request, action):
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  profile_id = str(body.get("id") or body.get("profile_id") or "").strip()
  if not profile_id:
    return web.json_response({"ok": False, "error": "missing id"}, status=400)
  try:
    result = action(profile_id, body.get("values") if isinstance(body.get("values"), dict) else None)
  except KeyError:
    return web.json_response({"ok": False, "error": "profile not found"}, status=404)
  except SettingProfileError as exc:
    return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=400)
  return web.json_response({"ok": True, **result})


def _delete(profile_id: str, _values) -> dict:
  delete_setting_profile(profile_id)
  return {"profiles": read_setting_profiles()["profiles"]}


async def api_profiles_apply(request: web.Request) -> web.Response:
  return await _profile_action(request, lambda profile_id, values: apply_setting_profile(profile_id, values))


async def api_profiles_preview(request: web.Request) -> web.Response:
  return await _profile_action(request, lambda profile_id, values: {"preview": preview_setting_profile(profile_id, values)})


async def api_profiles_delete(request: web.Request) -> web.Response:
  return await _profile_action(request, _delete)


async def api_profiles_update(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  if not isinstance(body, dict):
    return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
  profile_id = str(body.get("id") or body.get("profile_id") or "").strip()
  if not profile_id:
    return web.json_response({"ok": False, "error": "missing id"}, status=400)
  try:
    profile = update_setting_profile(profile_id, body)
  except KeyError:
    return web.json_response({"ok": False, "error": "profile not found"}, status=404)
  except SettingProfileError as exc:
    return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=400)
  return web.json_response({"ok": True, "profile": profile})


async def api_popular_values(request: web.Request) -> web.Response:
  return web.json_response({
    "ok": True,
    "enabled": False,
    "car_key_type": "CarSelected3",
    "car_key": "",
    "values": {},
    "note": POPULAR_VALUES_NOTE,
  })


async def api_popular_values_detail(request: web.Request) -> web.Response:
  return web.json_response({
    "ok": True,
    "enabled": False,
    "car_key_type": "CarSelected3",
    "car_key": "",
    "param_name": str(request.query.get("name", "")),
    "detail": {},
    "note": POPULAR_VALUES_NOTE,
  })


async def api_popular_values_refresh(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, "enabled": False, "note": POPULAR_VALUES_NOTE})


def register(app: web.Application) -> None:
  app.router.add_get("/api/web_settings", api_web_settings_get)
  app.router.add_post("/api/web_settings", api_web_settings_post)
  app.router.add_get("/api/setting_favorites", api_favorites_get)
  app.router.add_post("/api/setting_favorites", api_favorites_post)
  app.router.add_get("/api/setting_profiles", api_profiles_get)
  app.router.add_post("/api/setting_profiles", api_profiles_create)
  app.router.add_post("/api/setting_profiles/apply", api_profiles_apply)
  app.router.add_post("/api/setting_profiles/preview", api_profiles_preview)
  app.router.add_post("/api/setting_profiles/update", api_profiles_update)
  app.router.add_post("/api/setting_profiles/delete", api_profiles_delete)
  app.router.add_get("/api/setting_popular_values", api_popular_values)
  app.router.add_get("/api/setting_popular_values/detail", api_popular_values_detail)
  app.router.add_post("/api/setting_popular_values/refresh", api_popular_values_refresh)
