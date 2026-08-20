"""Cabana handlers module."""
from ai.services.cabana.deps import *
from ai.services.cabana.http import json_response as _json_response
from ai.services.cabana.car_params import _resolve_car_params
from ai.services.cabana.dbc import (
  _build_dbc_catalog,
  _dbc_catalog_cache,
  _get_dbc_dict,
  _load_dbc_content,
  _parse_dbc_signals,
  _pick_preferred_dbc,
  _quick_dbc_catalog,
  _suggest_dbc_for_fingerprint,
)
from ai.services.cabana.replay import (
  _list_route_media,
  _list_routes,
  _media_payload,
  _qcamera_thumbnail_at_time,
  _route_dir,
)

# -----------------------------------------------------------------------------
# API handlers
# -----------------------------------------------------------------------------

async def api_car(request: web.Request) -> web.Response:
  route = request.query.get("route", "").strip()
  loop = asyncio.get_running_loop()
  cp = await loop.run_in_executor(None, lambda: _resolve_car_params(route))
  if cp is None:
    return _json_response({
      "ok": False,
      "error": "CarParams not available",
      "hint": "Drive once, pick a route with carParams in qlog/rlog, or choose a DBC manually.",
      "car": None,
      "dbc_dict": {},
      "suggested_dbc": None,
    })

  suggested_dbc = _suggest_dbc_for_fingerprint(
    cp.get("carFingerprint", ""),
    brand=cp.get("brand", ""),
  )
  dbc_dict = _get_dbc_dict(cp.get("carFingerprint", ""))
  if not suggested_dbc and dbc_dict:
    suggested_dbc = _pick_preferred_dbc(list(dbc_dict.values()))
  return _json_response({
    "ok": True,
    "car": cp,
    "dbc_dict": dbc_dict,
    "suggested_dbc": suggested_dbc,
    "source": cp.get("source", "device"),
  })


async def api_dbcs(request: web.Request) -> web.Response:
  if DBC_PATH is None or not DBC_PATH:
    return _json_response({"ok": False, "error": "opendbc not available"}, status=503)
  quick = str(request.query.get("quick") or "").lower() in ("1", "true", "yes")
  loop = asyncio.get_running_loop()
  if _dbc_catalog_cache is not None:
    catalog = _dbc_catalog_cache
  elif quick:
    catalog = _quick_dbc_catalog()
    loop.run_in_executor(None, _build_dbc_catalog)
  else:
    catalog = await loop.run_in_executor(None, _build_dbc_catalog)
  return _json_response({
    "ok": True,
    "dbcs": [item["name"] for item in catalog],
    "catalog": catalog,
    "quick": quick and _dbc_catalog_cache is None,
  })


def warm_dbc_catalog() -> int:
  """Build DBC catalog cache (safe to call from a background thread)."""
  if DBC_PATH is None or not DBC_PATH:
    return 0
  return len(_build_dbc_catalog())


async def api_dbc(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  if DBC is None:
    return _json_response({"ok": False, "error": "opendbc DBC parser not available"}, status=503)
  loop = asyncio.get_running_loop()
  signals = await loop.run_in_executor(None, lambda: _parse_dbc_signals(name))
  return _json_response({"ok": True, "name": name, "signals": signals})


async def api_route_thumbnail(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  try:
    rel_sec = max(0.0, float(request.query.get("time", "0")))
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "Invalid time"}, status=400)
  loop = asyncio.get_running_loop()
  jpeg = await loop.run_in_executor(None, lambda: _qcamera_thumbnail_at_time(name, rel_sec))
  if not jpeg:
    return _json_response({"ok": False, "error": "No qcamera thumbnail"}, status=404)
  return web.Response(
    body=jpeg,
    content_type="image/jpeg",
    headers={"Cache-Control": "private, max-age=120"},
  )


async def api_route_media(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  result = _media_payload(name)
  if not result.get("ok"):
    return _json_response(result, status=404)
  return _json_response(result)


async def api_route_summary(request: web.Request) -> web.Response:
  from ai.tools.diagnostics_tools import analyze_route_summary
  name = request.match_info["name"]
  return _json_response(analyze_route_summary(name))


async def api_route_file(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  rel = request.query.get("path", "")
  if not rel or ".." in rel.replace("\\", "/"):
    return _json_response({"ok": False, "error": "Invalid path"}, status=400)
  base = _route_dir(name)
  if base is None:
    return _json_response({"ok": False, "error": "Route not found"}, status=404)
  target = (base / rel).resolve()
  try:
    if not str(target).startswith(str(base.resolve())):
      return _json_response({"ok": False, "error": "Forbidden"}, status=403)
  except Exception:
    return _json_response({"ok": False, "error": "Forbidden"}, status=403)
  if not target.is_file():
    return _json_response({"ok": False, "error": "File not found"}, status=404)
  return web.FileResponse(target)


async def api_routes(request: web.Request) -> web.Response:
  from ai.infra.timezone import read_ai_timezone_name

  params = Params()
  tz_name = read_ai_timezone_name(params)
  loop = asyncio.get_running_loop()
  routes = await loop.run_in_executor(None, lambda: _list_routes(params))
  return _json_response({
    "ok": True,
    "routes": routes,
    "route_timezone": tz_name,
  })
