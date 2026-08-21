"""openpilot settings catalog + current values (merged UI discovery)."""

from __future__ import annotations

from typing import Any

from openpilot.common.params import Params

from ai.tools.domains.platform.catalog_builder import build_merged_catalog
from ai.system.hardware_lite import LITE_UNAVAILABLE_NOTE, LITE_UNAVAILABLE_PARAMS, is_lite_hw, lite_profile

_BOOL_KEYS = frozenset({
  "ExperimentalMode", "SpDevBeep", "RecordAudio", "RecordFront", "AlwaysOnDM", "DistractionDetectionLevel",
  "Mads", "LagdToggle",
  "LaneTurnDesire", "NeuralNetworkLateralControl", "DynamicExperimentalControl",
  "SmartCruiseControlMap", "SmartCruiseControlVision", "CustomTorqueParams",
  "LiveTorqueParamsToggle", "LiveTorqueParamsRelaxedToggle", "TorqueParamsOverrideEnabled",
  "EnforceTorqueControl", "BlindSpot", "RainbowMode", "QuietMode", "OsmLocal",
  "SunnylinkEnabled", "EnableSunnylinkUploader", "ShowAdvancedControls",
  "EnableGithubRunner", "EnableCopyparty", "QuickBootToggle", "OnroadUploads",
  "ToyotaStopAndGoHack", "ToyotaEnforceStockLongitudinal", "SubaruStopAndGo",
  "TeslaCoopSteering", "IntelligentCruiseButtonManagement", "CustomAccIncrementsEnabled",
  "LeadDepartAlert", "GreenLightAlert", "StandstillTimer", "RoadNameToggle",
  "TrueVEgoUI", "HideVEgoUI", "ShowTurnSignals", "RocketFuel", "TorqueBar",
})


def _read_param(params: Params, key: str, entry: dict[str, Any]) -> Any:
  if entry.get("tier") == "read_redacted":
    return None
  try:
    if key.endswith("Toggle") or key in _BOOL_KEYS:
      if params.get(key) is not None:
        try:
          return params.get_bool(key)
        except Exception:
          pass
    val = params.get(key, return_default=True)
    if val is None:
      val = params.get(key)
    if isinstance(val, bytes):
      return val.decode("utf-8", errors="replace")
    return val
  except Exception:
    return None


def list_sp_settings(params: Params | None = None, brand: str = "") -> dict[str, Any]:
  """Return openpilot tunable params grouped by section with current values (merged catalog)."""
  params = params or Params()
  catalog = build_merged_catalog()
  sections: dict[str, list[dict[str, Any]]] = {}
  lite = is_lite_hw()
  lp = lite_profile(params) if lite else None

  for key, entry in sorted(catalog.items()):
    if entry.get("tier") == "write_forbidden":
      continue
    brands = entry.get("brands")
    if brands and brand and brand.lower() not in [b.lower() for b in brands]:
      continue
    section = entry.get("section", "General")
    item: dict[str, Any] = {
      "key": key,
      "section": section,
      "title": entry.get("title") or entry.get("summary", key),
      "description": entry.get("summary", ""),
      "tier": entry.get("tier", "read_always"),
      "current_value": _read_param(params, key, entry),
      "brands": brands,
      "ui_source": entry.get("ui_source"),
    }
    if lite and key in LITE_UNAVAILABLE_PARAMS:
      item["lite_unavailable"] = True
      item["lite_note"] = LITE_UNAVAILABLE_NOTE
    sections.setdefault(section, []).append(item)

  sections_out = [{"title": title, "settings": items} for title, items in sorted(sections.items())]
  out: dict[str, Any] = {
    "ok": True,
    "stack": "openpilot",
    "brand": brand,
    "catalog_source": "merged",
    "catalog_count": len(catalog),
    "sections": sections_out,
    "setting_count": sum(len(s["settings"]) for s in sections_out),
  }
  if lp is not None:
    out["lite_hardware"] = lp
  return out


list_dp_settings = list_sp_settings
