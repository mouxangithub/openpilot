"""Per-brand vehicle settings widgets (mirrors SP BrandSettingsFactory BIG UI)."""

from __future__ import annotations

from typing import Any

# Only brands with non-empty native BIG UI layouts (vehicle/brands/*.py items).
BRAND_WIDGETS: dict[str, list[dict[str, Any]]] = {
  "toyota": [
    {"type": "bool", "param": "ToyotaEnforceStockLongitudinal", "label": "Enforce Factory Longitudinal Control",
     "desc": "sunnypilot will not take over control of gas and brakes. Factory Toyota longitudinal control will be used.",
     "confirm_enable_rich": True, "needs_cycle": True},
    {"type": "bool", "param": "ToyotaStopAndGoHack", "label": "Stop and Go Hack (Alpha)",
     "desc": "sunnypilot will allow some Toyota/Lexus cars to auto resume during stop and go traffic.",
     "confirm_enable_rich": True, "needs_cycle": True},
  ],
  "tesla": [
    {"type": "bool", "param": "TeslaCoopSteering", "label": "Cooperative Steering (Beta)", "offroad_only": True},
    {"type": "multiple_button", "param": "TeslaMadsScreenButton", "label": "MADS Screen Activation",
     "buttons": ["Off", "3-Finger", "4-Finger", "5-Finger"], "offroad_only": True},
  ],
  "hyundai": [
    {"type": "multiple_button", "param": "HyundaiLongitudinalTuning", "label": "Custom Longitudinal Tuning",
     "buttons": ["Off", "Dynamic", "Predictive"], "layout": "stacked"},
  ],
  "subaru": [
    {"type": "bool", "param": "SubaruStopAndGo", "label": "Stop and Go (Beta)", "needs_cycle": True},
    {"type": "bool", "param": "SubaruStopAndGoManualParkingBrake", "label": "Stop and Go Manual Parking Brake",
     "visible_if": {"param": "SubaruStopAndGo", "eq": "1"}, "needs_cycle": True},
  ],
}


def widgets_for_brand(brand: str) -> list[dict[str, Any]]:
  return [dict(w) for w in BRAND_WIDGETS.get((brand or "").lower(), [])]
