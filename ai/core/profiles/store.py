"""File-based profile store.

Profiles are stored as JSON under ``<base_dir>/<domain>/<id>.json``.
No openpilot imports here so it stays testable on PC.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai.core.profiles.profile import Profile, ProfileDomain


class ProfileStore:
  def __init__(self, base_dir: str | Path) -> None:
    self.base_dir = Path(base_dir)
    self.base_dir.mkdir(parents=True, exist_ok=True)

  def _path(self, profile: Profile) -> Path:
    domain_dir = self.base_dir / profile.domain.value
    domain_dir.mkdir(parents=True, exist_ok=True)
    return domain_dir / f"{profile.id}.json"

  def save(self, profile: Profile) -> Path:
    path = self._path(profile)
    path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path

  def get(self, domain: ProfileDomain, profile_id: str) -> Profile | None:
    path = self.base_dir / domain.value / f"{profile_id}.json"
    if not path.is_file():
      return None
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
      return Profile.from_dict(data)
    except (json.JSONDecodeError, OSError):
      return None

  def list(self, domain: ProfileDomain | None = None) -> list[Profile]:
    out: list[Profile] = []
    domains = [domain] if domain else list(ProfileDomain)
    for d in domains:
      domain_dir = self.base_dir / d.value
      if not domain_dir.is_dir():
        continue
      for path in sorted(domain_dir.glob("*.json")):
        try:
          data = json.loads(path.read_text(encoding="utf-8"))
          out.append(Profile.from_dict(data))
        except (json.JSONDecodeError, OSError):
          continue
    return out

  def remove(self, domain: ProfileDomain, profile_id: str) -> bool:
    path = self.base_dir / domain.value / f"{profile_id}.json"
    if not path.is_file():
      return False
    try:
      path.unlink()
      return True
    except OSError:
      return False

  def export_all(self) -> dict[str, Any]:
    return {
      "profiles": [p.to_dict() for p in self.list()],
      "version": 1,
    }

  def import_all(self, payload: dict[str, Any], *, replace: bool = False) -> list[Profile]:
    imported: list[Profile] = []
    for item in payload.get("profiles") or []:
      profile = Profile.from_dict(item)
      if not replace and self.get(profile.domain, profile.id) is not None:
        continue
      self.save(profile)
      imported.append(profile)
    return imported
