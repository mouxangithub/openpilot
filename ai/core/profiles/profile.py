"""Profile data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProfileDomain(StrEnum):
  TUNE = "tune"
  VEHICLE = "vehicle"
  HARNESS = "harness"
  AGENTS = "agents"
  CUSTOM = "custom"


@dataclass
class Profile:
  """A named, versioned collection of settings for one domain."""

  id: str
  name: str
  domain: ProfileDomain
  description: str = ""
  version: int = 1
  settings: dict[str, Any] = field(default_factory=dict)
  meta: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "name": self.name,
      "domain": self.domain.value,
      "description": self.description,
      "version": self.version,
      "settings": self.settings,
      "meta": self.meta,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> Profile:
    return Profile(
      id=str(data.get("id", "")),
      name=str(data.get("name", "")),
      domain=ProfileDomain(str(data.get("domain", ProfileDomain.CUSTOM.value))),
      description=str(data.get("description", "")),
      version=int(data.get("version", 1)),
      settings=dict(data.get("settings") or {}),
      meta=dict(data.get("meta") or {}),
    )
