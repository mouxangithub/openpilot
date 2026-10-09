"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""`/api/settings` - the catalog, and one round trip for the first screen.

`/api/settings` is the catalog alone (it rarely changes); `/api/settings/snapshot` adds
the current values plus the device facts the device tab shows, so the app renders on one
request instead of four. Writes still go through `/api/param_set` - there is exactly one
write path.
"""
import asyncio
import logging

from aiohttp import web

from ..services.device_info import get_device_network_snapshot
from ..services.settings import carrot_catalog, carrot_values

logger = logging.getLogger("openpilot.carrot.server.settings")


async def api_settings(request: web.Request) -> web.Response:
  try:
    catalog = await asyncio.to_thread(carrot_catalog)
  except Exception as exc:
    logger.warning("carrot_server: settings catalog unavailable: %s", exc)
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "settings": catalog})


async def api_settings_snapshot(request: web.Request) -> web.Response:
  try:
    catalog, values = await asyncio.to_thread(_snapshot)
  except Exception as exc:
    logger.warning("carrot_server: settings snapshot unavailable: %s", exc)
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "settings": catalog, "values": values,
                            "device_network": await asyncio.to_thread(get_device_network_snapshot)})


def _snapshot():
  catalog = carrot_catalog()
  values = carrot_values(list(catalog["by_name"]))
  return catalog, values


async def api_setting_unit_index(request: web.Request) -> web.Response:
  """CarrotPilot's step multipliers have no counterpart here; answer the shape, empty."""
  return web.json_response({"ok": True, "units": {}})


async def api_setting_unit_index_set(request: web.Request) -> web.Response:
  """Accepted and echoed back, so a client that saves the index does not see an error.

  Nothing is persisted: this fork derives every setting's range from its carrot default, so
  a second, client-held copy of the same fact would be one that can drift out of step.
  """
  try:
    body = await request.json()
  except Exception:
    body = {}
  units = body.get("units") if isinstance(body, dict) and isinstance(body.get("units"), dict) else {}
  return web.json_response({"ok": True, "units": units, "persisted": False})


def register(app: web.Application) -> None:
  app.router.add_get("/api/settings", api_settings)
  app.router.add_get("/api/settings/snapshot", api_settings_snapshot)
  app.router.add_get("/api/setting_unit_index", api_setting_unit_index)
  app.router.add_post("/api/setting_unit_index", api_setting_unit_index_set)
