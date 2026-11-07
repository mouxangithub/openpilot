"""Bundle manifest schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BundlePackageRef:
  """Reference to an ACP package embedded in a bundle."""

  id: str
  version: str
  path: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "version": self.version,
      "path": self.path,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> BundlePackageRef:
    return BundlePackageRef(
      id=str(data.get("id", "")),
      version=str(data.get("version", "")),
      path=str(data.get("path", "")),
    )


@dataclass
class BundleManifest:
  """Manifest describing a bundle archive and its contents."""

  id: str
  name: str
  version: str
  description: str = ""
  author: str = ""
  created_at: str = ""
  packages: list[BundlePackageRef] = field(default_factory=list)
  files: list[str] = field(default_factory=list)
  extra: dict[str, Any] = field(default_factory=dict)

  def patch_operations(self) -> list[dict[str, Any]]:
    """Parse the dsh.bundle.patch operation list from extra (backward compatible).

    Format (optionally under ``extra``):
      {"dsh": {"bundle": {"patch": [{"op": "set", "path": "ai_*", "value": ...}]}}}
      or flat {"patch": [op, ...]}.
    Returns an empty list when absent.
    """
    extra_raw = self.extra.get("dsh") if isinstance(self.extra.get("dsh"), dict) else {}
    bundle = extra_raw.get("bundle") if isinstance(extra_raw.get("bundle"), dict) else {}
    raw = bundle.get("patch")
    if raw is None:
      raw = self.extra.get("patch")
    if isinstance(raw, list):
      return [dict(x) for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
      return [dict(raw)]
    return []

  def profile_bundles(self) -> list[str]:
    """Parse ordered bundle ids referenced by a profile (``dsh.profile.bundles``)."""
    extra_raw = self.extra.get("dsh") if isinstance(self.extra.get("dsh"), dict) else {}
    profile = extra_raw.get("profile") if isinstance(extra_raw.get("profile"), dict) else {}
    raw = profile.get("bundles")
    if raw is None:
      raw = self.extra.get("bundles")
    if isinstance(raw, list):
      return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str):
      return [x.strip() for x in raw.split(",") if x.strip()]
    return []

  def capabilities(self) -> set[str]:
    """Set of capability names this bundle provides/claims (e.g. tools, mcp)."""
    raw = self.extra.get("capabilities")
    if isinstance(raw, list):
      return {str(x).strip() for x in raw if str(x).strip()}
    if isinstance(raw, str):
      return {x.strip() for x in raw.split(",") if x.strip()}
    return set()

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "name": self.name,
      "version": self.version,
      "description": self.description,
      "author": self.author,
      "created_at": self.created_at,
      "packages": [p.to_dict() for p in self.packages],
      "files": self.files,
      "extra": self.extra,
    }

  @staticmethod
  def from_dict(data: dict[str, Any]) -> BundleManifest:
    packages: list[BundlePackageRef] = []
    for item in data.get("packages") or []:
      if isinstance(item, dict):
        packages.append(BundlePackageRef.from_dict(item))

    return BundleManifest(
      id=str(data.get("id", "")),
      name=str(data.get("name", "")),
      version=str(data.get("version", "")),
      description=str(data.get("description", "")),
      author=str(data.get("author", "")),
      created_at=str(data.get("created_at", "")),
      packages=packages,
      files=[str(f) for f in (data.get("files") or [])],
      extra=dict(data.get("extra") or {}),
    )
