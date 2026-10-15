"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Client-side preferences the app keeps on the device: web settings, favorites, profiles.

These are *not* parameters. They describe how a particular phone likes to see the device
(layout, language, which settings it pinned), so they live in their own JSON files instead
of Params - putting them there would make every tuning backup carry someone else's UI
preferences, and would need a params key per preference.

Setting *profiles* are the exception: they hold real parameter values, so creating one
snapshots the carrot catalog through `UnifiedParams` and applying one goes back through
`params_backup.restore_param_values_validated` - the same validated path a restore uses.
"""

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, UTC
from typing import Any

from ..config import (
  CARROT_SETTING_FAVORITES_PATH,
  CARROT_SETTING_PROFILES_PATH,
  CARROT_WEB_SETTINGS_PATH,
)

MAX_SETTING_FAVORITES = 200
MAX_SETTING_PROFILES = 40
MAX_PROFILE_NAME_LEN = 40

REPO_DIR = "/data/openpilot"


class SettingProfileError(ValueError):
  """A rejected profile operation carrying a stable code the UI can translate."""

  def __init__(self, code: str, message: str) -> None:
    self.code = code
    super().__init__(message)


def _read_json(path: str) -> Any:
  try:
    with open(path, encoding="utf-8") as f:
      return json.load(f)
  except Exception:
    return None


def _write_json(path: str, payload: Any) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp_path = path + ".tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp_path, path)


# ------------------------------- web settings -------------------------------

# Only keys the app actually sends. Anything else is dropped rather than persisted, so a
# newer app cannot leave junk on the device that an older one then chokes on.
DEFAULT_WEB_SETTINGS: dict[str, Any] = {
  "language": "",
  "theme": "system",
  "last_page": "carrot",
  "carrot_navi_horizontal_mode": "split",
  "carrot_navi_horizontal_area_1": "vision",
  "carrot_navi_horizontal_area_2": "navigation",
  "carrot_navi_vertical_mode": "split",
  "carrot_navi_vertical_area_1": "vision",
  "carrot_navi_vertical_area_2": "navigation",
}

_WEB_ENUMS: dict[str, tuple] = {
  "language": ("", "en", "ko", "zh"),
  "theme": ("system", "light", "dark"),
  "last_page": ("last", "carrot", "setting", "tools", "logs"),
  "carrot_navi_horizontal_mode": ("split", "area_1", "area_2"),
  "carrot_navi_vertical_mode": ("split", "area_1", "area_2"),
  "carrot_navi_horizontal_area_1": ("vision", "navigation"),
  "carrot_navi_horizontal_area_2": ("vision", "navigation"),
  "carrot_navi_vertical_area_1": ("vision", "navigation"),
  "carrot_navi_vertical_area_2": ("vision", "navigation"),
}

# What this fork's 7000 surface can and cannot do. Advertised so a client never offers a
# button that can only answer 501.
WEB_CAPABILITIES: dict[str, bool] = {
  "compactState": False,
  "dashcam": False,
  "screenrecord": False,
  "terminal": False,
  "supportTerminal": False,
  "youtubeLive": False,
  "visionDiag": False,
  "paramsBackup": True,
  "settingProfiles": True,
  "carrotNavi": True,
  "cameraStream": True,
  "egpuCompile": False,
}


def sanitize_web_settings(raw: Any) -> dict[str, Any]:
  raw = raw if isinstance(raw, dict) else {}
  clean = dict(DEFAULT_WEB_SETTINGS)
  for key in DEFAULT_WEB_SETTINGS:
    if key not in raw:
      continue
    value = raw[key]
    allowed = _WEB_ENUMS.get(key)
    if allowed and value not in allowed:
      continue
    clean[key] = value
  return clean


def read_web_settings() -> dict[str, Any]:
  return sanitize_web_settings(_read_json(CARROT_WEB_SETTINGS_PATH))


def update_web_settings(updates: dict[str, Any]) -> dict[str, Any]:
  if not isinstance(updates, dict):
    updates = {}
  merged = dict(read_web_settings())
  merged.update(updates)
  clean = sanitize_web_settings(merged)
  _write_json(CARROT_WEB_SETTINGS_PATH, clean)
  return clean


def resolve_web_capabilities(_settings: dict[str, Any] | None = None) -> dict[str, bool]:
  return dict(WEB_CAPABILITIES)


# ------------------------------- favorites ----------------------------------


def sanitize_favorites(raw: Any) -> dict[str, Any]:
  raw = raw if isinstance(raw, dict) else {}
  names: list[str] = []
  seen = set()
  for item in raw.get("favorites") or []:
    if not isinstance(item, str):
      continue
    name = item.strip()
    if not name or name in seen:
      continue
    seen.add(name)
    names.append(name)
    if len(names) >= MAX_SETTING_FAVORITES:
      break
  return {"favorites": names}


def read_setting_favorites() -> dict[str, Any]:
  return sanitize_favorites(_read_json(CARROT_SETTING_FAVORITES_PATH))


def update_setting_favorites(updates: dict[str, Any]) -> dict[str, Any]:
  if not isinstance(updates, dict):
    updates = {}
  current = read_setting_favorites()
  if "favorites" in updates:
    current["favorites"] = updates.get("favorites")
  clean = sanitize_favorites(current)
  _write_json(CARROT_SETTING_FAVORITES_PATH, clean)
  return clean


# ------------------------------- profiles -----------------------------------


def _now_iso() -> str:
  return datetime.now(UTC).replace(microsecond=0).isoformat()


def _git(args: list[str], timeout: float = 3.0) -> str:
  try:
    out = subprocess.check_output(["git", *args], cwd=REPO_DIR, stderr=subprocess.DEVNULL, timeout=timeout)
    return out.decode("utf-8", "replace").strip()
  except Exception:
    return ""


def _commit_url(remote: str, commit: str) -> str:
  remote = str(remote or "").strip()
  commit = str(commit or "").strip()
  if not remote or not commit:
    return ""
  match = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", remote)
  if not match:
    match = re.match(r"^git@github\.com:([^/]+)/(.+?)(?:\.git)?$", remote)
  if not match:
    return ""
  owner, repo = match.groups()
  return f"https://github.com/{owner}/{repo}/commit/{commit}"


def git_profile_meta() -> dict[str, Any]:
  commit = _git(["rev-parse", "HEAD"])
  remote = _git(["config", "--get", "remote.origin.url"])
  return {
    "branch": _git(["branch", "--show-current"]),
    "commit": commit,
    "commit_short": commit[:7] if commit else "",
    "commit_date": _git(["show", "-s", "--format=%cI", "HEAD"]),
    "remote": remote,
    "commit_url": _commit_url(remote, commit),
  }


def _clean_name(value: Any) -> str:
  name = re.sub(r"\s+", " ", str(value or "").strip())
  return name[:MAX_PROFILE_NAME_LEN]


def _catalog_defaults() -> dict[str, Any]:
  from .settings import carrot_defaults

  return carrot_defaults()


def _clean_values(values: Any) -> dict[str, Any]:
  if not isinstance(values, dict):
    return {}
  allowed = set(_catalog_defaults())
  return {str(key): value for key, value in values.items() if str(key) in allowed}


def snapshot_current_setting_values() -> dict[str, Any]:
  from .settings import carrot_values

  return carrot_values()


def _sanitize_profile(raw: Any) -> dict[str, Any] | None:
  if not isinstance(raw, dict):
    return None
  profile_id = str(raw.get("id") or "").strip()
  name = _clean_name(raw.get("name"))
  values = _clean_values(raw.get("values"))
  if not profile_id or not name or not values:
    return None
  created_at = str(raw.get("created_at") or "").strip()
  meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
  return {
    "id": profile_id,
    "name": name,
    "created_at": created_at,
    "updated_at": str(raw.get("updated_at") or created_at).strip(),
    "meta": {
      "branch": str(meta.get("branch") or ""),
      "commit": str(meta.get("commit") or ""),
      "commit_short": str(meta.get("commit_short") or ""),
      "commit_date": str(meta.get("commit_date") or ""),
      "remote": str(meta.get("remote") or ""),
      "commit_url": str(meta.get("commit_url") or ""),
    },
    "values": values,
  }


def read_setting_profiles() -> dict[str, Any]:
  raw = _read_json(CARROT_SETTING_PROFILES_PATH)
  items = raw.get("profiles") if isinstance(raw, dict) else []
  clean: list[dict[str, Any]] = []
  seen = set()
  for item in items if isinstance(items, list) else []:
    profile = _sanitize_profile(item)
    if not profile or profile["id"] in seen:
      continue
    seen.add(profile["id"])
    clean.append(profile)
    if len(clean) >= MAX_SETTING_PROFILES:
      break
  return {"profiles": clean}


def get_setting_profile(profile_id: str) -> dict[str, Any] | None:
  for profile in read_setting_profiles()["profiles"]:
    if profile["id"] == str(profile_id or "").strip():
      return profile
  return None


def create_setting_profile(name: str) -> dict[str, Any]:
  clean_name = _clean_name(name)
  if not clean_name:
    raise SettingProfileError("PROFILE_NAME_REQUIRED", "missing profile name")

  data = read_setting_profiles()
  if len(data["profiles"]) >= MAX_SETTING_PROFILES:
    raise SettingProfileError("PROFILE_LIMIT", "profile limit reached")

  now = _now_iso()
  profile = {
    "id": uuid.uuid4().hex,
    "name": clean_name,
    "created_at": now,
    "updated_at": now,
    "meta": git_profile_meta(),
    "values": _clean_values(snapshot_current_setting_values()),
  }
  data["profiles"].append(profile)
  _write_json(CARROT_SETTING_PROFILES_PATH, data)
  return profile


def update_setting_profile(profile_id: str, updates: dict[str, Any]) -> dict[str, Any]:
  data = read_setting_profiles()
  for profile in data["profiles"]:
    if profile["id"] != profile_id:
      continue
    if "name" in updates:
      name = _clean_name(updates.get("name"))
      if not name:
        raise SettingProfileError("PROFILE_NAME_REQUIRED", "missing profile name")
      profile["name"] = name
    if "values" in updates:
      cleaned = _clean_values(updates.get("values"))
      # A profile with no values is dropped on the next read, so an update that cleans down
      # to nothing would delete the profile as a side effect. Reject it instead.
      if not cleaned:
        raise SettingProfileError("PROFILE_NO_VALUES", "no valid values to save")
      profile["values"] = cleaned
    profile["updated_at"] = _now_iso()
    _write_json(CARROT_SETTING_PROFILES_PATH, data)
    return profile
  raise KeyError("profile not found")


def delete_setting_profile(profile_id: str) -> None:
  data = read_setting_profiles()
  remaining = [profile for profile in data["profiles"] if profile["id"] != profile_id]
  if len(remaining) == len(data["profiles"]):
    raise KeyError("profile not found")
  _write_json(CARROT_SETTING_PROFILES_PATH, {"profiles": remaining})


def preview_setting_profile(profile_id: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
  from openpilot.common.params import Params

  from .params_backup import preview_param_restore_values

  profile = get_setting_profile(profile_id)
  if profile is None:
    raise KeyError("profile not found")
  restore_values = _clean_values(values) if values is not None else profile["values"]
  return preview_param_restore_values(Params(), restore_values)


def apply_setting_profile(profile_id: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
  from openpilot.common.params import Params

  from .params_backup import restore_param_values_validated

  profile = get_setting_profile(profile_id)
  if profile is None:
    raise KeyError("profile not found")
  restore_values = _clean_values(values) if values is not None else profile["values"]
  return restore_param_values_validated(Params(), restore_values, source="profile")
