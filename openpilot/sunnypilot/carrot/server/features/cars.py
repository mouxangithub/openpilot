"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""`/api/cars` - the supported-car list, read from opendbc and never duplicated here.

opendbc is the single source: whatever a `values.CAR` entry documents as a car doc is
what the app is told is supported, so a new port shows up with no change to the server.
"""
import asyncio
import logging

from aiohttp import web

logger = logging.getLogger("openpilot.carrot.server.cars")

SUPPORTED_CAR_BRANDS = (
  "hyundai",
  "gm",
  "toyota",
  "mazda",
  "ford",
  "volkswagen",
  "tesla",
  "honda",
  "nissan",
  "subaru",
  "chrysler",
  "volvo",
  "audi",
)


def load_supported_cars():
  """`{maker: [doc names]}`, plus which brands answered."""
  makers: dict = {}
  sources = []
  for brand in SUPPORTED_CAR_BRANDS:
    try:
      values = __import__(f"opendbc.car.{brand}.values", fromlist=["CAR"])
    except Exception:
      continue
    sources.append(brand)
    try:
      platforms = getattr(values, "CAR", ())
    except Exception:
      continue
    for platform in platforms:
      try:
        docs = platform.config.car_docs
      except Exception:
        continue
      for doc in docs:
        line = str(getattr(doc, "name", "")).strip()
        if not line:
          continue
        maker = line.split(" ", 1)[0]
        makers.setdefault(maker, set()).add(line)
  return sorted(sources), {maker: sorted(names) for maker, names in sorted(makers.items())}


async def api_cars(request: web.Request) -> web.Response:
  try:
    sources, makers = await asyncio.to_thread(load_supported_cars)
  except Exception as exc:
    logger.warning("carrot_server: car list unavailable: %s", exc)
    return web.json_response({"ok": False, "error": str(exc)}, status=500)
  return web.json_response({"ok": True, "sources": sources, "makers": makers})


def register(app: web.Application) -> None:
  app.router.add_get("/api/cars", api_cars)
