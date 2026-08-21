"""Car platform selection via CarPlatformBundle (Settings → Vehicle)."""

from __future__ import annotations

import json
from typing import Any

from openpilot.common.params import Params

from ai.system.paths import find_repo_file, source_path

_CAR_LIST_CANDIDATES = (
  lambda: source_path("sunnypilot", "selfdrive", "car", "car_list.json"),
  lambda: find_repo_file(
    "openpilot/sunnypilot/selfdrive/car/car_list.json",
    "sunnypilot/selfdrive/car/car_list.json",
  ),
)


def _car_list_json_path() -> str:
  for candidate in _CAR_LIST_CANDIDATES:
    path = candidate()
    if path is not None and path.is_file():
      return str(path)
  return str(source_path("sunnypilot", "selfdrive", "car", "car_list.json"))


CAR_LIST_JSON = _car_list_json_path()

_car_list_cache: dict[str, Any] | None = None


def load_car_list() -> dict[str, Any]:
  global _car_list_cache
  if _car_list_cache is None:
    with open(CAR_LIST_JSON, encoding="utf-8") as f:
      _car_list_cache = json.load(f)
  return _car_list_cache


def resolve_car_platform_bundle(model: str) -> dict[str, Any] | None:
  """Resolve display name or opendbc platform id to a CarPlatformBundle dict."""
  model = model.strip()
  if not model:
    return None

  cars = load_car_list()
  if model in cars:
    return {**cars[model], "name": model}

  for name, data in cars.items():
    if data.get("platform") == model:
      return {**data, "name": name}
  return None


def list_car_platforms(*, brand: str = "", search: str = "", limit: int = 80) -> dict[str, Any]:
  """List entries from this install's car_list.json (CarPlatformBundle options)."""
  cars = load_car_list()
  brand_l = brand.strip().lower()
  search_l = search.strip().lower()
  items: list[dict[str, Any]] = []

  for name, data in cars.items():
    platform = data.get("platform", "")
    entry_brand = str(data.get("brand", "") or "").lower()
    if brand_l and brand_l not in entry_brand and brand_l not in platform.lower():
      continue
    hay = f"{name} {platform}".lower()
    if search_l and search_l not in hay:
      continue
    items.append({
      "name": name,
      "platform": platform,
      "brand": data.get("brand"),
      "year": data.get("year"),
    })

  items.sort(key=lambda x: x["name"])
  if limit > 0:
    items = items[:limit]

  return {
    "ok": True,
    "count": len(items),
    "platforms": items,
    "hint": "select_car_platform(name_or_platform, confirm=true) sets CarPlatformBundle; empty clears to auto.",
  }


def get_car_platform_bundle(params: Params) -> dict[str, Any]:
  raw = params.get("CarPlatformBundle")
  if not raw:
    return {"ok": True, "mode": "auto", "bundle": None}
  if isinstance(raw, bytes):
    import json as _json
    raw = _json.loads(raw.decode(errors="replace"))
  return {"ok": True, "mode": "manual", "bundle": raw}


def put_car_platform_bundle(params: Params, model: str) -> dict[str, Any]:
  model = str(model or "").strip()
  if not model:
    if params.get("CarPlatformBundle"):
      params.remove("CarPlatformBundle")
    return {"ok": True, "mode": "auto"}

  bundle = resolve_car_platform_bundle(model)
  if bundle is None:
    return {"ok": False, "error": f"unknown platform: {model}"}

  params.put("CarPlatformBundle", bundle)
  return {"ok": True, "platform": bundle["platform"], "name": bundle["name"]}


# Backwards-compatible alias naming
select_car_platform = put_car_platform_bundle


def preview_car_platform_change(params: Params, model: str) -> dict[str, Any]:
  model = str(model or "").strip()
  if not model:
    before = params.get("CarPlatformBundle")
    if before is None:
      return {"ok": True, "changes": {}, "change_count": 0}
    return {
      "ok": True,
      "changes": {"CarPlatformBundle": {"before": before, "after": None}},
      "change_count": 1,
    }

  bundle = resolve_car_platform_bundle(model)
  if bundle is None:
    return {"ok": False, "error": f"unknown platform: {model}"}

  from ai.tools.diagnostics_tools import diff_params
  return diff_params(params, {"CarPlatformBundle": bundle})
