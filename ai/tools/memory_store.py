"""Agent long-term memory stored in Params (device-persistent)."""

from __future__ import annotations

import json
import time
from typing import Any

from openpilot.common.params import Params

NOTES_KEY = "ai_memory_notes"
PROFILE_KEY = "ai_vehicle_profile"
MAX_NOTES = 80
MAX_NOTE_LEN = 2000


def _load_json(params: Params, key: str, default: Any) -> Any:
  try:
    raw = params.get(key)
    if not raw:
      return default
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    return json.loads(raw)
  except Exception:
    return default


def _save_json(params: Params, key: str, data: Any) -> None:
  params.put(key, json.dumps(data, ensure_ascii=False))


def get_memory(params: Params | None = None) -> dict[str, Any]:
  params = params or Params()
  notes = _load_json(params, NOTES_KEY, [])
  profile = _load_json(params, PROFILE_KEY, {})
  if not isinstance(notes, list):
    notes = []
  if not isinstance(profile, dict):
    profile = {}
  return {"ok": True, "notes": notes, "vehicle_profile": profile}


def append_note(params: Params, text: str, tags: list[str] | None = None) -> dict[str, Any]:
  text = (text or "").strip()
  if not text:
    return {"ok": False, "error": "Note text is empty."}
  if len(text) > MAX_NOTE_LEN:
    text = text[:MAX_NOTE_LEN]
  notes = _load_json(params, NOTES_KEY, [])
  if not isinstance(notes, list):
    notes = []
  entry = {
    "id": f"n_{int(time.time() * 1000)}",
    "text": text,
    "tags": tags or [],
    "at": int(time.time()),
  }
  notes.insert(0, entry)
  notes = notes[:MAX_NOTES]
  _save_json(params, NOTES_KEY, notes)
  return {"ok": True, "note": entry, "count": len(notes)}


def update_vehicle_profile(params: Params, updates: dict[str, Any]) -> dict[str, Any]:
  profile = _load_json(params, PROFILE_KEY, {})
  if not isinstance(profile, dict):
    profile = {}
  for k, v in (updates or {}).items():
    if k and v is not None:
      profile[k] = v
  profile["updated_at"] = int(time.time())
  _save_json(params, PROFILE_KEY, profile)
  return {"ok": True, "vehicle_profile": profile}


def sync_vehicle_profile_from_state(
  params: Params,
  *,
  brand: str = "",
  car_fingerprint: str = "",
  openpilot_longitudinal: bool | None = None,
) -> dict[str, Any]:
  """Auto-update vehicle profile when CarParams / state changes."""
  profile = _load_json(params, PROFILE_KEY, {})
  if not isinstance(profile, dict):
    profile = {}
  changed = False
  if brand and profile.get("brand") != brand:
    profile["brand"] = brand
    changed = True
  if car_fingerprint and profile.get("fingerprint") != car_fingerprint:
    profile["fingerprint"] = car_fingerprint
    changed = True
  if openpilot_longitudinal is not None:
    key = "openpilotLongitudinalControl"
    if profile.get(key) != openpilot_longitudinal:
      profile[key] = openpilot_longitudinal
      changed = True
  if changed:
    profile["updated_at"] = int(time.time())
    _save_json(params, PROFILE_KEY, profile)
  return {"ok": True, "updated": changed, "vehicle_profile": profile}


def delete_note(params: Params, note_id: str) -> dict[str, Any]:
  notes = _load_json(params, NOTES_KEY, [])
  if not isinstance(notes, list):
    notes = []
  new_notes = [n for n in notes if n.get("id") != note_id]
  _save_json(params, NOTES_KEY, new_notes)
  return {"ok": True, "removed": len(notes) - len(new_notes)}


def format_memory_prompt(params: Params, *, max_notes: int = 5) -> str:
  data = get_memory(params)
  profile = data.get("vehicle_profile") or {}
  notes = data.get("notes") or []
  parts: list[str] = []
  prof_lines = [f"- {k}: {v}" for k, v in profile.items() if k != "updated_at" and v]
  if prof_lines:
    parts.append("## Vehicle profile\n" + "\n".join(prof_lines))
  if notes:
    lines = []
    for n in notes[:max_notes]:
      text = (n.get("text") or "").strip()
      if text:
        lines.append(f"- {text}")
    if lines:
      parts.append("## User memory notes\n" + "\n".join(lines))
  if not parts:
    return ""
  return "# Agent memory (device-persistent)\n\n" + "\n\n".join(parts)
