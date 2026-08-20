"""Vehicle platform tree (car_list.json)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from webui.server.deps import openpilot_root


def _car_list_path() -> Path | None:
  root = openpilot_root()
  candidates = [
    root / "openpilot" / "sunnypilot" / "selfdrive" / "car" / "car_list.json",
    root / "sunnypilot" / "selfdrive" / "car" / "car_list.json",
  ]
  for p in candidates:
    if p.is_file():
      return p
  return None


def _platform_display(bundle: Any) -> str:
  if not bundle:
    return ""
  if isinstance(bundle, str):
    try:
      data = json.loads(bundle)
      if isinstance(data, dict):
        return _platform_display(data)
    except Exception:
      pass
    return bundle
  if isinstance(bundle, dict):
    return str(
      bundle.get("name")
      or bundle.get("platform")
      or bundle.get("bundle")
      or "",
    )
  getter = getattr(bundle, "get", None)
  if callable(getter):
    return str(getter("name") or getter("platform") or getter("bundle") or "")
  return str(bundle)


def _build_vehicle_tree(data: dict[str, Any]) -> list[dict[str, Any]]:
  grouped: dict[str, list[dict[str, str]]] = {}
  for name, entry in data.items():
    if not isinstance(entry, dict):
      continue
    make = str(entry.get("make") or entry.get("brand") or "Other")
    grouped.setdefault(make, []).append({"bundle": name, "label": name})
  tree: list[dict[str, Any]] = []
  for make in sorted(grouped):
    tree.append({
      "name": make,
      "platforms": sorted(grouped[make], key=lambda item: item["label"]),
    })
  return tree


def _lookup_platform_bundle(platform_name: str) -> dict[str, Any] | None:
  path = _car_list_path()
  if not path or not platform_name:
    return None
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data.get(platform_name)
    if isinstance(entry, dict):
      return {**entry, "name": platform_name}
  except Exception:
    pass
  return None


def _cached_car_params() -> tuple[str, str]:
  """Return (car_fingerprint, brand) from Params / cereal (mirrors ui_state.update_params)."""
  try:
    from openpilot.common.params import Params
    import openpilot.cereal.messaging as messaging
    from opendbc.car.structs import car

    p = Params()
    for key in ("CarParamsPersistent", "CarParamsCache"):
      raw = p.get(key)
      if not raw:
        continue
      cp = messaging.log_from_bytes(raw, car.CarParams)
      fp = str(cp.carFingerprint or "")
      brand = str(cp.brand or "").lower()
      if fp and fp != "MOCK":
        return fp, brand
      if brand:
        return "", brand
  except Exception:
    pass

  try:
    import openpilot.cereal.messaging as messaging

    sm = messaging.SubMaster(["carParams"], poll="carParams")
    if sm.update(200) and sm.valid.get("carParams"):
      cp = sm["carParams"]
      fp = str(cp.carFingerprint or "")
      brand = str(cp.brand or "").lower()
      if fp and fp != "MOCK":
        return fp, brand
      if brand:
        return "", brand
  except Exception:
    pass

  try:
    from openpilot.selfdrive.ui.ui_state import ui_state

    if ui_state.CP is not None:
      fp = str(getattr(ui_state.CP, "carFingerprint", "") or "")
      brand = str(getattr(ui_state.CP, "brand", "") or "").lower()
      if fp and fp != "MOCK":
        return fp, brand
      if brand:
        return "", brand
  except Exception:
    pass

  return "", ""


def _platform_status() -> tuple[str, str]:
  """Return (display_name, status) where status is auto|manual|unknown."""
  try:
    from openpilot.common.params import Params

    bundle = Params().get("CarPlatformBundle")
    if bundle:
      return _platform_display(bundle), "manual"
    fp, _ = _cached_car_params()
    if fp:
      return fp, "auto"
  except Exception:
    pass
  return "", "unknown"


def vehicle_platforms() -> dict[str, Any]:
  if os.environ.get("WEBUI_DEV_PC") == "1":
    from webui.dev.mock_runtime import SIM

    fp = str(SIM.get("car_fingerprint") or "")
    display, status = (fp, "auto") if fp else ("", "unknown")
    return {
      "ok": True,
      "tree": [
        {"name": "Toyota", "platforms": [
          {"bundle": "TOYOTA_COROLLA_TSS2_2019", "label": "Toyota Corolla TSS2 2019"},
          {"bundle": "TOYOTA_RAV4_TSS2_2021", "label": "Toyota RAV4 TSS2 2021"},
          {"bundle": "TOYOTA_WILDLANDER_PHEV", "label": "Toyota Wildlander PHEV"},
        ]},
        {"name": "Hyundai", "platforms": [
          {"bundle": "HYUNDAI_SONATA_DN8", "label": "Hyundai Sonata DN8"},
        ]},
      ],
      "active": fp,
      "display": display,
      "status": status,
      "manual": False,
      "dev_pc": True,
    }

  try:
    from openpilot.common.params import Params
    p = Params()
    bundle = p.get("CarPlatformBundle")
    display, status = _platform_status()
    path = _car_list_path()
    if not path:
      return {"ok": False, "error": "car_list.json not found"}
    data = json.loads(path.read_text(encoding="utf-8"))
    tree = _build_vehicle_tree(data)
    return {
      "ok": True,
      "tree": tree,
      "active": _platform_display(bundle),
      "display": display,
      "status": status,
      "manual": bool(bundle),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def vehicle_select(bundle: str) -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    p = Params()
    if not bundle:
      p.remove("CarPlatformBundle")
      display, status = _platform_status()
      return {"ok": True, "bundle": "", "display": display, "status": status, "manual": False}
    payload = _lookup_platform_bundle(bundle)
    if payload is None:
      payload = {"name": bundle, "platform": bundle}
    p.put("CarPlatformBundle", payload, block=True)
    display = _platform_display(payload)
    return {
      "ok": True,
      "bundle": bundle,
      "display": display,
      "status": "manual",
      "manual": True,
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _brand_from_bundle(bundle: Any) -> str:
  if not bundle:
    return ""
  try:
    data = json.loads(bundle) if isinstance(bundle, str) else bundle
    if isinstance(data, dict):
      brand = data.get("brand")
      if brand:
        return str(brand).lower()
      platform = data.get("platform") or data.get("name")
      if platform:
        entry = _lookup_platform_bundle(str(platform))
        if entry and entry.get("brand"):
          return str(entry["brand"]).lower()
  except Exception:
    pass
  return ""


def _detect_brand() -> str:
  import os
  if os.environ.get("WEBUI_DEV_PC") == "1":
    return "toyota"
  try:
    from openpilot.common.params import Params
    p = Params()
    bundle = p.get("CarPlatformBundle")
    brand = _brand_from_bundle(bundle)
    if brand:
      return brand
    _, brand = _cached_car_params()
    if brand:
      return brand
  except Exception:
    pass
  return ""


def vehicle_brand_widgets() -> dict[str, Any]:
  from webui.server.bridge.vehicle_brand_catalog import widgets_for_brand
  from webui.server.bridge.params_api import _param_type_name, _serialize_value

  brand = _detect_brand()
  widgets = widgets_for_brand(brand)
  if not brand:
    return {"ok": True, "brand": "", "widgets": [], "values": {}}

  try:
    from openpilot.common.params import Params
    p = Params()
    values: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for w in widgets:
      key = w.get("param")
      if not key:
        out.append({**w, "available": True})
        continue
      ptype = _param_type_name(p, key)
      if ptype is None:
        out.append({**w, "available": False, "missing": True})
        continue
      val = _serialize_value(p.get(key))
      values[key] = val
      locked = False
      try:
        locked = p.get_bool(key + "Lock")
      except Exception:
        pass
      out.append({**w, "available": True, "value": val, "param_type": ptype, "locked": locked})
    return {"ok": True, "brand": brand, "widgets": out, "values": values}
  except Exception as exc:
    return {"ok": False, "error": str(exc)}
