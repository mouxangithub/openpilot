from collections.abc import Iterable
import json
import os
from typing import Any

from ..config import CARROT_SETTING_FAVORITES_PATH


MAX_SETTING_FAVORITES = 200
MAX_FAVORITE_SLOTS = 3
DEFAULT_SETTING_FAVORITES: dict[str, Any] = {
  "favorites": [],
  "slots": [],
}


def _normalize_favorites(value: Any) -> list[str]:
  if not isinstance(value, Iterable) or isinstance(value, (str, bytes, bytearray, dict)):
    return []

  out: list[str] = []
  seen = set()
  for item in value:
    name = str(item or "").strip()
    if not name or name in seen:
      continue
    seen.add(name)
    out.append(name)
    if len(out) >= MAX_SETTING_FAVORITES:
      break
  return out


def _normalize_slots(value: Any) -> list[dict[str, Any]]:
  """Executable favorite slots, stored alongside the names-only list.

  A slot is ``{"key": "<setting name>"}`` or an explicit null (empty slot).
  Keys are NOT validated against the catalog here - the catalog changes with
  settings releases, and a stored key that no longer exists must stay visible
  as an empty/stale slot rather than silently vanishing from the file. Apply
  time validation lives in services.favorite_slots."""
  if not isinstance(value, list):
    return []
  out: list[dict[str, Any]] = []
  for item in value[:MAX_FAVORITE_SLOTS]:
    if not isinstance(item, dict):
      out.append({"key": ""})
      continue
    key = str(item.get("key") or "").strip()
    out.append({"key": key if len(key) <= 128 else ""})
  return out


def sanitize_setting_favorites(raw: dict[str, Any] | None) -> dict[str, Any]:
  raw = raw or {}
  return {
    "favorites": _normalize_favorites(raw.get("favorites")),
    "slots": _normalize_slots(raw.get("slots")),
  }


def read_setting_favorites() -> dict[str, Any]:
  try:
    with open(CARROT_SETTING_FAVORITES_PATH, encoding="utf-8") as f:
      raw = json.load(f)
  except Exception:
    return dict(DEFAULT_SETTING_FAVORITES)
  return sanitize_setting_favorites(raw if isinstance(raw, dict) else {})


def write_setting_favorites(settings: dict[str, Any]) -> dict[str, Any]:
  clean = sanitize_setting_favorites(settings)
  os.makedirs(os.path.dirname(CARROT_SETTING_FAVORITES_PATH), exist_ok=True)
  tmp_path = CARROT_SETTING_FAVORITES_PATH + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
  os.replace(tmp_path, CARROT_SETTING_FAVORITES_PATH)
  return clean


def update_setting_favorites(updates: dict[str, Any]) -> dict[str, Any]:
  if not isinstance(updates, dict):
    updates = {}
  current = read_setting_favorites()
  if "favorites" in updates:
    current["favorites"] = updates.get("favorites")
  if "slots" in updates:
    current["slots"] = updates.get("slots")
  return write_setting_favorites(current)
