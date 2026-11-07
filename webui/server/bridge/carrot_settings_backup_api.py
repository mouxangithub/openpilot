"""Carrot settings backup / restore / profiles / favorites for sunnypilot webui.

Ported from CarrotPilot (cp):
  * selfdrive/carrot/server/services/params.py        (backup / restore + QR)
  * selfdrive/carrot/server/services/setting_profiles.py
  * selfdrive/carrot/server/services/setting_favorites.py

Adaptations for sunnypilot (sp)
--------------------------------
cp keys its backup / profiles / favorites against the full ``carrot_settings.json``
catalog (via ``get_settings_cached``). sp exposes its carrot tuning surface through
``CARROT_TUNING_DEFAULTS`` in ``carrot_tuning_api``, so we reuse that as the key
whitelist instead of porting ``carrot_settings.json`` (which is a separate, larger
alignment job and would collide with other work). This keeps the design
self-contained: the storage + API need no carrot_settings.json metadata.

Other deltas from cp:
  * Storage paths default to ``/data/carrot/state`` (runtime, survives a git
    reset) and are overridable via ``CARROT_SETTINGS_STATE_DIR`` for PC dev / CI.
  * No new openpilot Params keys are introduced — profiles / favorites live in
    JSON files, exactly like cp. (Any new Params key would have to be registered
    in ``common/params_keys.h``; we deliberately avoid that here.)
  * The QR payload is produced through the existing ``qr_data_url`` helper
    (``openpilot.common.qrcode`` on-device), so no new dependency is added. A
    payload larger than a single QR's capacity yields ``qr_too_large``; the JSON
    download endpoint remains the source of truth.

Security
--------
``restore`` / ``apply`` are offroad-only (see the offroad guard in
``routes/__init__.py``). Uploaded JSON is validated against the known-key
whitelist and coerced by declared type before any write — an unknown key is
rejected, never written. This prevents a backup from silently clobbering system
Params (a brick vector).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from webui.server.bridge.carrot_tuning_api import (
  CARROT_TUNING_DEFAULTS,
  carrot_put,
  carrot_value_str,
  is_carrot_key,
)


# --- paths -----------------------------------------------------------------
DEFAULT_STATE_DIR = "/data/carrot/state"
STATE_DIR = os.environ.get("CARROT_SETTINGS_STATE_DIR", DEFAULT_STATE_DIR)
PROFILES_PATH = os.path.join(STATE_DIR, "setting_profiles.json")
FAVORITES_PATH = os.path.join(STATE_DIR, "setting_favorites.json")

MAX_PROFILES = 40
MAX_PROFILE_NAME_LEN = 40
MAX_FAVORITES = 200

BACKUP_VERSION = 1


# --- helpers ----------------------------------------------------------------
def _now_iso() -> str:
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- backup / restore ------------------------------------------------------
def export_params_backup() -> Dict[str, Any]:
  """Return a serialisable snapshot of every known carrot tuning key."""
  values: Dict[str, str] = {}
  for key in sorted(CARROT_TUNING_DEFAULTS.keys()):
    values[key] = carrot_value_str(key) or ""
  return {
    "version": BACKUP_VERSION,
    "created_at": _now_iso(),
    "count": len(values),
    "values": values,
  }


def _clean_restore_values(values: Dict[str, Any]) -> tuple[Dict[str, str], List[str]]:
  """Keep only whitelisted keys; return (clean_values, unknown_keys)."""
  clean: Dict[str, str] = {}
  unknown: List[str] = []
  for key, value in (values or {}).items():
    key = str(key)
    if not is_carrot_key(key):
      unknown.append(key)
      continue
    clean[key] = "" if value is None else str(value)
  return clean, unknown


def restore_params_backup(values: Dict[str, Any]) -> Dict[str, Any]:
  """Validate + write a dict of carrot tuning values.

  Keys outside the whitelist are rejected and never written. Each known key is
  coerced by its declared type and written through the standard carrot tuning
  put path (``carrot_put``), so types / bounds stay consistent with the UI.
  """
  clean, unknown = _clean_restore_values(values)
  ok_cnt = 0
  fails: List[Dict[str, str]] = []
  for key, value in clean.items():
    res = carrot_put(key, value)
    if res.get("ok"):
      ok_cnt += 1
    else:
      fails.append({"key": key, "error": res.get("error", "write failed")})
  return {
    "ok": (not fails and not unknown),
    "ok_cnt": ok_cnt,
    "fail_cnt": len(fails),
    "unknown_keys": unknown,
    "fails": fails[:30],
  }


def build_params_qr_backup(values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
  """Produce a QR data URL encoding the backup JSON.

  Reuses ``webui.server.bridge.qr_data_url`` (``openpilot.common.qrcode`` on the
  device). If the payload exceeds a single QR's capacity the encoder returns ""
  and we report ``qr_too_large`` rather than failing — the JSON download stays
  authoritative.
  """
  if values is None:
    backup = export_params_backup()
  else:
    backup = {
      "version": BACKUP_VERSION,
      "created_at": _now_iso(),
      "count": len(values or {}),
      "values": {str(k): ("" if v is None else str(v)) for k, v in (values or {}).items()},
    }
  payload = json.dumps(backup, ensure_ascii=False, separators=(",", ":"))
  try:
    from webui.server.bridge.qr_data_url import qr_data_url
    data_url = qr_data_url(payload)
  except Exception:
    data_url = ""
  if not data_url:
    return {
      "ok": False,
      "error": "qr_too_large_or_encoder_unavailable",
      "payload_chars": len(payload),
    }
  return {
    "ok": True,
    "data_url": data_url,
    "payload_chars": len(payload),
  }


# --- profiles --------------------------------------------------------------
def _clean_name(value: Any) -> str:
  name = str(value or "").strip()
  name = " ".join(name.split())
  return name[:MAX_PROFILE_NAME_LEN]


def _clean_values(values: Any) -> Dict[str, Any]:
  if not isinstance(values, dict):
    return {}
  return {str(k): v for k, v in values.items() if is_carrot_key(str(k))}


def _sanitize_profile(raw: Any) -> Optional[Dict[str, Any]]:
  if not isinstance(raw, dict):
    return None
  pid = str(raw.get("id") or "").strip()
  name = _clean_name(raw.get("name"))
  values = _clean_values(raw.get("values"))
  if not pid or not name or not values:
    return None
  created = str(raw.get("created_at") or "").strip()
  updated = str(raw.get("updated_at") or created).strip()
  return {
    "id": pid,
    "name": name,
    "created_at": created,
    "updated_at": updated,
    "values": values,
  }


def read_setting_profiles() -> Dict[str, Any]:
  try:
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
      raw = json.load(f)
  except Exception:
    raw = {}
  profiles = raw.get("profiles") if isinstance(raw, dict) else []
  clean: List[Dict[str, Any]] = []
  seen = set()
  for item in profiles if isinstance(profiles, list) else []:
    p = _sanitize_profile(item)
    if not p or p["id"] in seen:
      continue
    seen.add(p["id"])
    clean.append(p)
    if len(clean) >= MAX_PROFILES:
      break
  return {"profiles": clean}


def write_setting_profiles(data: Dict[str, Any]) -> Dict[str, Any]:
  clean = {"profiles": []}
  seen = set()
  for item in data.get("profiles", []) if isinstance(data, dict) else []:
    p = _sanitize_profile(item)
    if not p or p["id"] in seen:
      continue
    seen.add(p["id"])
    clean["profiles"].append(p)
    if len(clean["profiles"]) >= MAX_PROFILES:
      break
  os.makedirs(os.path.dirname(PROFILES_PATH), exist_ok=True)
  tmp = PROFILES_PATH + ".tmp"
  with open(tmp, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
  os.replace(tmp, PROFILES_PATH)
  return clean


def snapshot_current_setting_values() -> Dict[str, Any]:
  return {k: (carrot_value_str(k) or "") for k in sorted(CARROT_TUNING_DEFAULTS.keys())}


def create_setting_profile(name: str) -> Dict[str, Any]:
  clean_name = _clean_name(name)
  if not clean_name:
    raise ValueError("PROFILE_NAME_REQUIRED")
  data = read_setting_profiles()
  if len(data["profiles"]) >= MAX_PROFILES:
    raise ValueError("PROFILE_LIMIT")
  now = _now_iso()
  profile = {
    "id": uuid.uuid4().hex,
    "name": clean_name,
    "created_at": now,
    "updated_at": now,
    "values": _clean_values(snapshot_current_setting_values()),
  }
  data["profiles"].append(profile)
  write_setting_profiles(data)
  return profile


def update_setting_profile(profile_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
  profile_id = str(profile_id or "").strip()
  data = read_setting_profiles()
  for p in data["profiles"]:
    if p["id"] != profile_id:
      continue
    if "name" in updates:
      n = _clean_name(updates.get("name"))
      if not n:
        raise ValueError("PROFILE_NAME_REQUIRED")
      p["name"] = n
    if "values" in updates:
      cleaned = _clean_values(updates.get("values"))
      if not cleaned:
        raise ValueError("PROFILE_NO_VALUES")
      p["values"] = cleaned
    p["updated_at"] = _now_iso()
    write_setting_profiles(data)
    return p
  raise KeyError("profile not found")


def delete_setting_profile(profile_id: str) -> None:
  profile_id = str(profile_id or "").strip()
  data = read_setting_profiles()
  nxt = [p for p in data["profiles"] if p["id"] != profile_id]
  if len(nxt) == len(data["profiles"]):
    raise KeyError("profile not found")
  data["profiles"] = nxt
  write_setting_profiles(data)


def apply_setting_profile(profile_id: str, values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
  profile_id = str(profile_id or "").strip()
  profile = next((p for p in read_setting_profiles()["profiles"] if p["id"] == profile_id), None)
  if profile is None:
    raise KeyError("profile not found")
  restore_values = _clean_values(values) if values is not None else profile["values"]
  return restore_params_backup(restore_values)


def preview_setting_profile(profile_id: str, values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
  profile_id = str(profile_id or "").strip()
  profile = next((p for p in read_setting_profiles()["profiles"] if p["id"] == profile_id), None)
  if profile is None:
    raise KeyError("profile not found")
  restore_values = _clean_values(values) if values is not None else profile["values"]
  current = snapshot_current_setting_values()
  entries = []
  for key in sorted(restore_values.keys()):
    new_val = str(restore_values[key])
    cur = current.get(key, "")
    entries.append({"key": key, "current": cur, "value": new_val, "changed": cur != new_val})
  return {"profile_id": profile_id, "count": len(entries), "entries": entries}


# --- favorites -------------------------------------------------------------
def _normalize_favorites(value: Any) -> List[str]:
  if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes, bytearray, dict)):
    return []
  out: List[str] = []
  seen = set()
  for item in value:
    name = str(item or "").strip()
    if not name or name in seen or not is_carrot_key(name):
      continue
    seen.add(name)
    out.append(name)
    if len(out) >= MAX_FAVORITES:
      break
  return out


def read_setting_favorites() -> Dict[str, Any]:
  try:
    with open(FAVORITES_PATH, "r", encoding="utf-8") as f:
      raw = json.load(f)
  except Exception:
    raw = {}
  favs = raw.get("favorites") if isinstance(raw, dict) else None
  return {"favorites": _normalize_favorites(favs)}


def write_setting_favorites(settings: Dict[str, Any]) -> Dict[str, Any]:
  if isinstance(settings, dict) and "favorites" in settings:
    favs = _normalize_favorites(settings.get("favorites"))
  elif isinstance(settings, (list, tuple)):
    favs = _normalize_favorites(settings)
  else:
    favs = []
  clean = {"favorites": favs}
  os.makedirs(os.path.dirname(FAVORITES_PATH), exist_ok=True)
  tmp = FAVORITES_PATH + ".tmp"
  with open(tmp, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
  os.replace(tmp, FAVORITES_PATH)
  return clean


def update_setting_favorites(updates: Dict[str, Any]) -> Dict[str, Any]:
  current = read_setting_favorites()
  if isinstance(updates, dict) and "favorites" in updates:
    current["favorites"] = _normalize_favorites(updates.get("favorites"))
  elif isinstance(updates, (list, tuple)):
    current["favorites"] = _normalize_favorites(updates)
  return write_setting_favorites(current)
