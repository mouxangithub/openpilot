"""Load ACP packages from disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai.acp.protocol import AcpPackage


class AcpLoadError(Exception):
  """Raised when an ACP package cannot be loaded or validated."""


class AcpLoader:
  """Load ACP packages from JSON files or directories."""

  MANIFEST_NAME = "acp.json"

  def load_file(self, path: str | Path) -> AcpPackage:
    """Load an ACP package from a single JSON file."""
    path = Path(path)
    if not path.is_file():
      raise AcpLoadError(f"ACP manifest not found: {path}")
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
      raise AcpLoadError(f"Invalid JSON in {path}: {e}") from e
    except OSError as e:
      raise AcpLoadError(f"Cannot read {path}: {e}") from e
    return self._parse(data, path)

  def load_directory(self, path: str | Path) -> AcpPackage:
    """Load an ACP package from a directory containing ``acp.json``."""
    path = Path(path)
    manifest = path / self.MANIFEST_NAME
    if not manifest.is_file():
      raise AcpLoadError(f"ACP manifest not found in directory: {path}")
    return self.load_file(manifest)

  def load(self, path: str | Path) -> AcpPackage:
    """Load from a file or directory."""
    path = Path(path)
    if path.is_dir():
      return self.load_directory(path)
    return self.load_file(path)

  def _parse(self, data: Any, path: Path) -> AcpPackage:
    if not isinstance(data, dict):
      raise AcpLoadError(f"ACP manifest must be a JSON object: {path}")
    try:
      return AcpPackage.from_dict(data)
    except Exception as e:
      raise AcpLoadError(f"Failed to parse ACP package from {path}: {e}") from e
