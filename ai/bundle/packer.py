"""Create bundle archives from directories and manifests."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ai.bundle.manifest import BundleManifest


class BundlePacker:
  """Pack a directory into a bundle archive (.zip) with a manifest."""

  MANIFEST_NAME = "bundle.json"

  def pack(
    self,
    source_dir: str | Path,
    output_path: str | Path,
    manifest: BundleManifest | None = None,
  ) -> BundleManifest:
    """Create a bundle archive from ``source_dir``.

    If no manifest is supplied, one is generated from the directory contents.
    The manifest is always written as ``bundle.json`` inside the archive.
    """
    source_dir = Path(source_dir)
    output_path = Path(output_path)
    if not source_dir.is_dir():
      raise ValueError(f"Source directory does not exist: {source_dir}")

    if manifest is None:
      manifest = self._infer_manifest(source_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
      for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
          continue
        rel = path.relative_to(source_dir).as_posix()
        if rel == self.MANIFEST_NAME:
          continue
        archive.write(path, rel)
        files.append(rel)

      manifest.files = files
      archive.writestr(self.MANIFEST_NAME, json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))

    return manifest

  def _infer_manifest(self, source_dir: Path) -> BundleManifest:
    name = source_dir.name
    import time
    return BundleManifest(
      id=name,
      name=name,
      version="0.1.0",
      description=f"Auto-generated bundle for {name}",
      created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
