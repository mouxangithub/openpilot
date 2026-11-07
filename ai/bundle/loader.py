"""Load and install bundle archives."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from ai.acp.loader import AcpLoader
from ai.acp.protocol import AcpPackage
from ai.bundle.manifest import BundleManifest


class BundleInstallError(Exception):
  """Raised when a bundle cannot be loaded or installed."""


class BundleLoader:
  """Load bundle archives and install their contents."""

  MANIFEST_NAME = "bundle.json"

  def __init__(self, acp_loader: AcpLoader | None = None) -> None:
    self.acp_loader = acp_loader or AcpLoader()

  def load(self, bundle_path: str | Path) -> tuple[BundleManifest, Path]:
    """Load a bundle archive, returning its manifest and a temporary extraction path."""
    bundle_path = Path(bundle_path)
    if not bundle_path.is_file():
      raise BundleInstallError(f"Bundle archive not found: {bundle_path}")

    extract_dir = Path(bundle_path).with_suffix("")
    if extract_dir.exists():
      shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
      with zipfile.ZipFile(bundle_path, "r") as archive:
        archive.extractall(extract_dir)
    except zipfile.BadZipFile as e:
      raise BundleInstallError(f"Invalid bundle archive: {bundle_path}") from e

    manifest_path = extract_dir / self.MANIFEST_NAME
    if not manifest_path.is_file():
      shutil.rmtree(extract_dir, ignore_errors=True)
      raise BundleInstallError(f"Bundle manifest not found in {bundle_path}")

    try:
      data = json.loads(manifest_path.read_text(encoding="utf-8"))
      manifest = BundleManifest.from_dict(data)
    except json.JSONDecodeError as e:
      shutil.rmtree(extract_dir, ignore_errors=True)
      raise BundleInstallError(f"Invalid bundle manifest JSON: {e}") from e

    return manifest, extract_dir

  def install(
    self,
    bundle_path: str | Path,
    install_dir: str | Path,
    *,
    clean: bool = False,
  ) -> BundleManifest:
    """Extract a bundle into ``install_dir`` and return its manifest.

    Atomic: if anything fails mid-copy, the pre-existing ``install_dir`` is
    restored from a backup so the target never ends up half-installed.
    """
    manifest, extract_dir = self.load(bundle_path)
    install_dir = Path(install_dir)
    backup_dir: Path | None = None

    if install_dir.exists():
      backup_dir = install_dir.with_name(install_dir.name + ".bak-atomic")
      if backup_dir.exists():
        shutil.rmtree(backup_dir)
      shutil.move(str(install_dir), str(backup_dir))

    try:
      install_dir.mkdir(parents=True, exist_ok=True)
      for src in extract_dir.rglob("*"):
        if not src.is_file():
          continue
        rel = src.relative_to(extract_dir)
        dst = install_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except Exception:
      # Rollback: restore backup, remove partial install.
      shutil.rmtree(install_dir, ignore_errors=True)
      if backup_dir is not None and backup_dir.exists():
        shutil.move(str(backup_dir), str(install_dir))
      shutil.rmtree(extract_dir, ignore_errors=True)
      raise BundleInstallError(f"Bundle install failed and was rolled back: {bundle_path}")

    if backup_dir is not None and backup_dir.exists():
      shutil.rmtree(backup_dir, ignore_errors=True)
    shutil.rmtree(extract_dir, ignore_errors=True)
    return manifest

  def install_acp_packages(
    self,
    bundle_path: str | Path,
    install_dir: str | Path,
    *,
    clean: bool = False,
  ) -> list[AcpPackage]:
    """Install a bundle and load every ACP package referenced by its manifest."""
    manifest = self.install(bundle_path, install_dir, clean=clean)
    base_dir = Path(install_dir)
    packages: list[AcpPackage] = []
    for ref in manifest.packages:
      pkg_dir = base_dir / ref.path if ref.path else base_dir / ref.id
      if pkg_dir.is_dir():
        packages.append(self.acp_loader.load_directory(pkg_dir))
      else:
        pkg_file = pkg_dir.with_suffix(".json")
        if pkg_file.is_file():
          packages.append(self.acp_loader.load_file(pkg_file))
    return packages

  def inspect(self, bundle_path: str | Path) -> dict[str, Any]:
    """Return a quick inspection dict for a bundle archive without installing."""
    manifest, _ = self.load(bundle_path)
    return {
      "manifest": manifest.to_dict(),
      "package_count": len(manifest.packages),
      "file_count": len(manifest.files),
    }
