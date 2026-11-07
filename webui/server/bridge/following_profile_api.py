"""Following Profile settings API — the web-side editor for the
LongitudinalFollowingProfile JSON param.

BIG UI exposes this through FollowingProfileToggles (per-personality preset
buttons backed by following_profile_store.py). This API reuses the same store
helpers, so the JSON the web UI writes is exactly the document the engine
validates - one canonical shape, no drift.

GET  /api/opui/following-profile  -> snapshot (enabled flag + per-personality preset)
PUT  /api/opui/following-profile  -> body {enabled?, selection? {aggressive|standard|relaxed: preset}}
"""

from __future__ import annotations

from typing import Any

PROFILE_ENABLED_KEY = "LongitudinalFollowingProfileEnabled"

PERSONALITY_LABELS: dict[str, str] = {
  "aggressive": "Aggressive",
  "standard": "Standard",
  "relaxed": "Relaxed",
}


def _store():
  from openpilot.selfdrive.ui.sunnypilot.lib.following_profile_store import (
    PRESET_ORDER,
    PROFILE_PARAM_KEY,
    default_selection,
    selection_from_raw,
  )
  return PRESET_ORDER, PROFILE_PARAM_KEY, default_selection, selection_from_raw


def snapshot_following_profile() -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    PRESET_ORDER, PROFILE_PARAM_KEY, default_selection, selection_from_raw = _store()
    p = Params()
    raw = p.get(PROFILE_PARAM_KEY)
    selection = selection_from_raw(raw if raw is None else _as_str(raw))
    return {
      "ok": True,
      "enabled": p.get_bool(PROFILE_ENABLED_KEY),
      "selection": selection,
      "personalities": PERSONALITY_LABELS,
      "presets": list(PRESET_ORDER),
      "defaults": default_selection(),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def apply_following_profile(body: dict[str, Any]) -> dict[str, Any]:
  try:
    from openpilot.common.params import Params
    PRESET_ORDER, PROFILE_PARAM_KEY, _default_selection, selection_from_raw = _store()
    from openpilot.selfdrive.ui.sunnypilot.lib.following_profile_store import serialize_selection

    p = Params()
    raw = p.get(PROFILE_PARAM_KEY)
    selection = selection_from_raw(raw if raw is None else _as_str(raw))

    incoming = body.get("selection")
    if isinstance(incoming, dict):
      for personality in PERSONALITY_LABELS:
        preset = incoming.get(personality)
        if preset in PRESET_ORDER:
          selection[personality] = preset

    out: dict[str, Any] = {"ok": True}

    if "enabled" in body:
      enabled = bool(body.get("enabled"))
      p.put_bool(PROFILE_ENABLED_KEY, enabled, block=True)
      out["enabled"] = enabled

    p.put(PROFILE_PARAM_KEY, serialize_selection(selection), block=True)
    out["selection"] = selection
    return out
  except Exception as exc:
    return {"ok": False, "error": str(exc)}


def _as_str(raw: Any) -> str:
  if isinstance(raw, bytes):
    return raw.decode("utf-8", "replace")
  return str(raw)
