"""Profile discovery and ordered patch-layer composition (dsh app-boot profile port).

A profile is a directory under ``<workspace>/profiles/<name>`` holding:

- ``profile.json`` — the profile manifest: ``{"name": ..., "bundles": [...],
  "patchReload": "live"|"startup"}`` where ``bundles`` is the *ordered*
  bundle-id list whose patch layers are applied first;
- ``cordis.patch.json`` — the user's own patch layer, applied after every
  bundle layer (JSON instead of dsh's ``cordis.patch.yml`` — no yaml
  dependency on device).

A bundle layer is the bundle manifest's ``extra["patch"]`` section:
``{"include": [entry...], "exclude": [id|entry...]}``. An *entry* is
``{"id": str, "options": dict}``. Composition applies each bundle's patch in
``bundles`` order over an empty entry list, then the profile's own patch
layer, then any launcher layers (``extra_layers``). Unknown bundle ids and
duplicate layer entries fail loud with a typed error (no silent skipping).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROFILES_DIR = "profiles"
PROFILE_PATCH_FILENAME = "cordis.patch.json"
PROFILE_MANIFEST_FILENAME = "profile.json"

VALID_PATCH_RELOAD = ("live", "startup")


class ProfileError(Exception):
  """Typed refusal: the profile tree or a patch layer is invalid."""

  def __init__(self, code: str, message: str) -> None:
    super().__init__(message)
    self.code = code

  def to_dict(self) -> dict[str, Any]:
    return {"ok": False, "error": str(self), "error_code": self.code}


# -- entry-patch semantics -----------------------------------------------------


def _normalize_entry(raw: Any) -> dict[str, Any]:
  if isinstance(raw, str):
    if not raw.strip():
      raise ProfileError("invalid_patch", "patch include entry id must be non-empty")
    return {"id": raw.strip(), "options": {}}
  if isinstance(raw, dict) and isinstance(raw.get("id"), str) and raw["id"].strip():
    options = raw.get("options")
    return {"id": raw["id"].strip(), "options": dict(options) if isinstance(options, dict) else {}}
  raise ProfileError("invalid_patch", f"patch entries must be ids or {{id, options}} objects, got {raw!r}")


def normalize_patch(patch: Any) -> dict[str, list[dict[str, Any]]]:
  """Validate one patch layer: {"include": [...], "exclude": [...]}."""
  if patch is None:
    return {"include": [], "exclude": []}
  if not isinstance(patch, dict):
    raise ProfileError("invalid_patch", f"patch layer must be an object, got {type(patch).__name__}")
  include_raw = patch.get("include") or []
  exclude_raw = patch.get("exclude") or []
  if not isinstance(include_raw, list) or not isinstance(exclude_raw, list):
    raise ProfileError("invalid_patch", "patch include/exclude must be arrays")
  return {
    "include": [_normalize_entry(e) for e in include_raw],
    "exclude": [_normalize_entry(e) for e in exclude_raw],
  }


def apply_patch(entries: list[dict[str, Any]], patch: Any) -> list[dict[str, Any]]:
  """Compose one layer over the current entry list (later options win per key)."""
  layer = normalize_patch(patch)
  excluded = {e["id"] for e in layer["exclude"]}
  out = [e for e in entries if e["id"] not in excluded]
  for inc in layer["include"]:
    existing = next((e for e in out if e["id"] == inc["id"]), None)
    if existing is not None:
      merged = dict(existing["options"])
      merged.update(inc["options"])
      existing["options"] = merged
    else:
      out.append({"id": inc["id"], "options": dict(inc["options"])})
  return out


# -- profile discovery ----------------------------------------------------------


def profiles_root(base: Path | str | None = None) -> Path:
  if base is not None:
    return Path(base)
  return Path(os.environ.get("AI_WORKSPACE", ".")) / "workspace" / PROFILES_DIR


def profile_dir(name: str, base: Path | str | None = None) -> Path:
  if not isinstance(name, str) or not name.strip() or "/" in name or "\\" in name or name.strip() in (".", ".."):
    raise ProfileError("invalid_profile", f"profile name must be a plain directory name, got {name!r}")
  return profiles_root(base) / name.strip()


def load_profile_manifest(directory: Path | str) -> dict[str, Any]:
  path = Path(directory) / PROFILE_MANIFEST_FILENAME
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as exc:
    raise ProfileError("profile_not_found", f"missing {PROFILE_MANIFEST_FILENAME} in {path.parent}") from exc
  except json.JSONDecodeError as exc:
    raise ProfileError("invalid_profile", f"{path} is not valid JSON: {exc}") from exc
  if not isinstance(data, dict) or not str(data.get("name") or "").strip():
    raise ProfileError("invalid_profile", f"{path} must declare a non-empty name")
  bundles = data.get("bundles") or []
  if not isinstance(bundles, list) or any(not isinstance(b, str) or not b.strip() for b in bundles):
    raise ProfileError("invalid_profile", "profile bundles must be an array of bundle ids")
  reload = data.get("patchReload", "startup")
  if reload not in VALID_PATCH_RELOAD:
    raise ProfileError("invalid_profile", f"patchReload must be one of {VALID_PATCH_RELOAD}, got {reload!r}")
  return data


def load_profile_patch(directory: Path | str) -> dict[str, list[dict[str, Any]]]:
  """The user patch layer; a missing file is an empty layer, a malformed one fails."""
  path = Path(directory) / PROFILE_PATCH_FILENAME
  if not path.is_file():
    return {"include": [], "exclude": []}
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as exc:
    raise ProfileError("invalid_patch", f"{path} is not valid JSON: {exc}") from exc
  return normalize_patch(data)


# -- composition ------------------------------------------------------------------


def compose_profile(
  name: str,
  *,
  store: Any = None,
  base: Path | str | None = None,
  extra_layers: list[Any] | None = None,
) -> dict[str, Any]:
  """Compose the full ordered entry list for a profile.

  Layer order (dsh profile.ts): each bundle's patch in ``bundles`` order over
  an empty list, then the profile's own ``cordis.patch.json``, then launcher
  ``extra_layers``. Returns the entries plus per-layer attribution.
  """
  directory = profile_dir(name, base)
  manifest = load_profile_manifest(directory)
  bundles: list[str] = manifest["bundles"]

  if store is None:
    from ai.bundle.store import BundleStore
    store = BundleStore()

  seen: set[str] = set()
  for bundle_id in bundles:
    if bundle_id in seen:
      raise ProfileError("duplicate_bundle", f"profile {name} lists bundle {bundle_id!r} more than once")
    seen.add(bundle_id)
    if store.get_bundle(bundle_id) is None:
      raise ProfileError(
        "bundle_not_found",
        f"profile {name} requires bundle {bundle_id!r} which is not installed",
      )

  entries: list[dict[str, Any]] = []
  layers: list[dict[str, Any]] = []

  for bundle_id in bundles:
    bundle = store.get_bundle(bundle_id)
    patch = (bundle.extra or {}).get("patch")
    normalized = normalize_patch(patch)
    if not normalized["include"] and not normalized["exclude"]:
      layers.append({"source": f"bundle:{bundle_id}", "patch": {"include": [], "exclude": []}})
      continue
    entries = apply_patch(entries, normalized)
    layers.append({"source": f"bundle:{bundle_id}", "patch": normalized})

  user_patch = load_profile_patch(directory)
  if user_patch["include"] or user_patch["exclude"]:
    entries = apply_patch(entries, user_patch)
  layers.append({"source": "profile", "patch": user_patch})

  for index, patch in enumerate(extra_layers or []):
    normalized = normalize_patch(patch)
    entries = apply_patch(entries, normalized)
    layers.append({"source": f"launcher:{index}", "patch": normalized})

  return {
    "ok": True,
    "profile": name,
    "entries": [dict(e) for e in entries],
    "layers": layers,
    "patchReload": manifest.get("patchReload", "startup"),
  }


def list_profiles(base: Path | str | None = None) -> list[str]:
  root = profiles_root(base)
  if not root.is_dir():
    return []
  return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / PROFILE_MANIFEST_FILENAME).is_file())
