"""SecOC support tier lookup (read-only, no keys)."""

from __future__ import annotations

from typing import Any

# Subset of optskug/docs tiers — expand as community list updates.
_TIERS: dict[str, list[str]] = {
  "green": [
    "TOYOTA COROLLA TSS2 2019",
    "TOYOTA RAV4 TSS2 2019",
    "TOYOTA CAMRY TSS2 2021",
    "TOYOTA HIGHLANDER TSS2 2020",
    "LEXUS ES TSS2 2019",
    "LEXUS RX TSS2 2020",
    "LEXUS NX TSS2 2020",
  ],
  "yellow": [
    "TOYOTA SIENNA 4TH GEN",
    "TOYOTA SIENNA 2024",
    "LEXUS RX 500H 2023",
  ],
  "red": [
    "TOYOTA TUNDRA 2022",
    "TOYOTA SEQUOIA 2023",
    "LEXUS BZ4X 2023",
  ],
}

_KEYWORDS: dict[str, list[str]] = {
  "green": ["corolla", "rav4", "camry", "highlander", "es", "rx", "nx", "prius"],
  "yellow": ["sienna", "2024", "500h", "experimental"],
  "red": ["tundra", "sequoia", "bz4x", "hsm"],
}


def lookup_secoc_tier(car_fingerprint: str = "", brand: str = "") -> dict[str, Any]:
  fp = (car_fingerprint or "").upper().strip()
  brand_l = (brand or "").lower()

  if brand_l and brand_l not in ("toyota", "lexus"):
    return {
      "ok": True,
      "tier": "n/a",
      "message": "SecOC lookup is for Toyota/Lexus platforms; this brand may not use EPS SecOC.",
      "docs": "https://github.com/optskug/docs",
    }

  for tier, cars in _TIERS.items():
    for car in cars:
      if car in fp or fp in car:
        return _tier_response(tier, matched=car)

  fp_l = fp.lower()
  for tier, kws in _KEYWORDS.items():
    if any(k in fp_l for k in kws):
      return _tier_response(tier, matched="keyword")

  return {
    "ok": True,
    "tier": "unknown",
    "message": "Not in built-in SecOC tier list. Check optskug/docs and comma Discord #toyota-security.",
    "docs": "https://github.com/optskug/docs",
    "hint": "🟢 standard setup | 🟡 experimental | 🔴 not supported yet",
  }


def _tier_response(tier: str, *, matched: str) -> dict[str, Any]:
  messages = {
    "green": "Likely 🟢: use op 助手 → Settings → SecOC or tsk_run_pipeline / tsk_extract_key (RAV4 Prime/Sienna).",
    "yellow": "Likely 🟡 experimental: try SecOC panel or community tools; confirm with lookup_secoc_tier.",
    "red": "Likely 🔴: SecOC not crackable yet; dashcam-only until upstream support.",
  }
  emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(tier, "?")
  return {
    "ok": True,
    "tier": tier,
    "emoji": emoji,
    "matched": matched,
    "message": messages.get(tier, ""),
    "docs": "https://github.com/optskug/docs",
    "settings_url": "/?settings=secoc",
    "ai_rule": "Never write SecOCKey via write_params; use tsk_install_secoc_key or SecOC settings panel.",
  }
