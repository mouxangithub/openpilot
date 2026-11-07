"""API handlers — profile manager."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from ai.core.profiles.manager import ProfileManager
from ai.core.profiles.profile import Profile, ProfileDomain


def _domain(value: str) -> ProfileDomain:
  return ProfileDomain(str(value).strip().lower())


def _profile_from_body(body: dict[str, Any]) -> Profile:
  return Profile(
    id=str(body.get("id", "")).strip(),
    name=str(body.get("name", "")).strip(),
    domain=_domain(body.get("domain", "custom")),
    description=str(body.get("description", "")),
    version=int(body.get("version", 1) or 1),
    settings=dict(body.get("settings") or {}),
    meta=dict(body.get("meta") or {}),
  )


def register_profile_routes(app: web.Application, *, json_response) -> None:
  params = app["params"]
  manager = ProfileManager()

  async def api_profiles(request: web.Request) -> web.Response:
    if request.method == "POST":
      try:
        body = await request.json()
      except Exception:
        return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
      profile = _profile_from_body(body)
      if not profile.id:
        return json_response({"ok": False, "error": "profile id is required"}, status=400)
      try:
        manager.save(profile)
      except Exception as e:
        return json_response({"ok": False, "error": f"Failed to save profile: {e}"}, status=500)
      return json_response({"ok": True, "profile": profile.to_dict()})

    domain = request.query.get("domain", "").strip() or None
    try:
      profiles = manager.list(domain=_domain(domain) if domain else None)
    except Exception as e:
      return json_response({"ok": False, "error": f"Failed to list profiles: {e}"}, status=500)
    return json_response({"ok": True, "profiles": [p.to_dict() for p in profiles]})

  async def api_profile_detail(request: web.Request) -> web.Response:
    domain = request.match_info.get("domain", "").strip()
    profile_id = request.match_info.get("id", "").strip()
    if not domain or not profile_id:
      return json_response({"ok": False, "error": "domain and id are required"}, status=400)
    try:
      profile = manager.get(_domain(domain), profile_id)
    except Exception as e:
      return json_response({"ok": False, "error": f"Failed to get profile: {e}"}, status=500)
    if not profile:
      return json_response({"ok": False, "error": "Profile not found"}, status=404)
    if request.method == "DELETE":
      try:
        ok = manager.remove(_domain(domain), profile_id)
      except Exception as e:
        return json_response({"ok": False, "error": f"Failed to remove profile: {e}"}, status=500)
      return json_response({"ok": ok})
    return json_response({"ok": True, "profile": profile.to_dict()})

  async def api_profile_apply(request: web.Request) -> web.Response:
    try:
      body = await request.json()
    except Exception:
      return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    domain = str(body.get("domain") or body.get("profileDomain") or "").strip()
    profile_id = str(body.get("id") or body.get("profileId") or "").strip()
    if not domain or not profile_id:
      return json_response({"ok": False, "error": "domain and id are required"}, status=400)
    try:
      profile = manager.get(_domain(domain), profile_id)
    except Exception as e:
      return json_response({"ok": False, "error": f"Failed to get profile: {e}"}, status=500)
    if not profile:
      return json_response({"ok": False, "error": "Profile not found"}, status=404)
    brand = str(body.get("brand") or "").strip()
    try:
      result = manager.apply(profile, params=params, brand=brand)
    except Exception as e:
      return json_response({"ok": False, "error": f"Failed to apply profile: {e}"}, status=500)
    return json_response({"ok": True, "result": result, "profile": profile.to_dict()})

  async def api_profile_import(request: web.Request) -> web.Response:
    try:
      body = await request.json()
    except Exception:
      return json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    replace = bool(body.get("replace"))
    try:
      result = manager.import_remote(body, replace=replace)
    except Exception as e:
      return json_response({"ok": False, "error": f"Failed to import profiles: {e}"}, status=500)
    return json_response({"ok": True, **result})

  async def api_profile_export(request: web.Request) -> web.Response:
    try:
      manifest = manager.export_manifest()
    except Exception as e:
      return json_response({"ok": False, "error": f"Failed to export profiles: {e}"}, status=500)
    return json_response({"ok": True, **manifest})

  app.router.add_get("/api/ai/profiles", api_profiles)
  app.router.add_post("/api/ai/profiles", api_profiles)
  app.router.add_get("/api/ai/profiles/{domain}/{id}", api_profile_detail)
  app.router.add_delete("/api/ai/profiles/{domain}/{id}", api_profile_detail)
  app.router.add_post("/api/ai/profiles/apply", api_profile_apply)
  app.router.add_post("/api/ai/profiles/import", api_profile_import)
  app.router.add_get("/api/ai/profiles/export", api_profile_export)
