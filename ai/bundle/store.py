"""Bundle store: list/load/save bundles under the workspace."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ai.bundle.loader import BundleInstallError, BundleLoader
from ai.bundle.manifest import BundleManifest
from ai.bundle.packer import BundlePacker
from ai.system.paths import workspace_path


class BundleStore:
  """Manage bundle archives under ``<workspace>/ai_bundles``."""

  STORE_DIR_NAME = "ai_bundles"

  def __init__(self, store_dir: str | Path | None = None) -> None:
    self.store_dir = Path(store_dir) if store_dir else workspace_path(self.STORE_DIR_NAME)
    self.store_dir.mkdir(parents=True, exist_ok=True)
    self.packer = BundlePacker()
    self.loader = BundleLoader()

  def _bundle_path(self, bundle_id: str) -> Path:
    return self.store_dir / f"{bundle_id}.zip"

  def list_bundles(self) -> list[BundleManifest]:
    """List all bundles currently stored."""
    manifests: list[BundleManifest] = []
    for path in sorted(self.store_dir.glob("*.zip")):
      try:
        manifest, _ = self.loader.load(path)
        manifests.append(manifest)
      except BundleInstallError:
        continue
    return manifests

  def get_bundle(self, bundle_id: str) -> BundleManifest | None:
    """Load a single bundle manifest by id."""
    path = self._bundle_path(bundle_id)
    if not path.is_file():
      return None
    try:
      manifest, _ = self.loader.load(path)
      return manifest
    except BundleInstallError:
      return None

  def save_bundle(
    self,
    source_dir: str | Path,
    manifest: BundleManifest | None = None,
    bundle_id: str | None = None,
  ) -> Path:
    """Pack a directory and persist the bundle archive in the store."""
    if manifest is None:
      manifest = self.packer._infer_manifest(Path(source_dir))
    if bundle_id is not None:
      manifest.id = bundle_id
    path = self._bundle_path(manifest.id)
    self.packer.pack(source_dir, path, manifest=manifest)
    return path

  def remove_bundle(self, bundle_id: str) -> bool:
    """Delete a bundle archive from the store."""
    path = self._bundle_path(bundle_id)
    if not path.is_file():
      return False
    try:
      path.unlink()
      return True
    except OSError:
      return False

  def install_bundle(
    self,
    bundle_id: str,
    install_dir: str | Path,
    *,
    clean: bool = False,
  ) -> BundleManifest:
    """Install a stored bundle into ``install_dir``.

    Validates capability conflicts against other bundles already in the store
    (capabilities are declared via manifest.extra.capabilities). A conflict
    raises BundleInstallError before anything is written.
    """
    path = self._bundle_path(bundle_id)
    if not path.is_file():
      raise BundleInstallError(f"Bundle not found in store: {bundle_id}")

    target, _ = self.loader.load(path)
    conflicts = self._capability_conflicts(bundle_id, target)
    if conflicts:
      shutil.rmtree(Path(path).with_suffix(""), ignore_errors=True)
      raise BundleInstallError(
        f"Bundle '{bundle_id}' capability conflict with existing bundle(s): {', '.join(sorted(conflicts))}"
      )
    return self.loader.install(path, install_dir, clean=clean)

  def _capability_conflicts(self, bundle_id: str, target: BundleManifest) -> set[str]:
    """Return capability names claimed by both ``target`` and an existing bundle."""
    target_caps = target.capabilities()
    if not target_caps:
      return set()
    conflicts: set[str] = set()
    for existing in self.list_bundles():
      if existing.id == bundle_id:
        continue
      overlap = target_caps & existing.capabilities()
      if overlap:
        conflicts |= overlap
    return conflicts

  def to_summary(self) -> dict[str, Any]:
    return {
      "store_dir": str(self.store_dir),
      "bundles": [m.to_dict() for m in self.list_bundles()],
    }
