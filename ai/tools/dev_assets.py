"""List AI-generated reports and exports for Web UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ai.tools.op_run import OPENPILOT_ROOT

_DATA = Path(__file__).resolve().parents[1] / "data"
_REPORTS = _DATA / "reports"
_EXPORTS = _DATA / "exports"


def _scan_dir(directory: Path, *, kind: str, limit: int = 40) -> list[dict[str, Any]]:
  if not directory.is_dir():
    return []
  items: list[dict[str, Any]] = []
  for path in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
    if not path.is_file():
      continue
    if path.suffix.lower() not in (".html", ".mp4", ".wav", ".json"):
      continue
    try:
      st = path.stat()
    except OSError:
      continue
    items.append({
      "name": path.name,
      "kind": kind,
      "size_bytes": st.st_size,
      "mtime": st.st_mtime,
      "url": f"/api/ai/dev-assets/{kind}/{path.name}",
    })
    if len(items) >= limit:
      break
  return items


def list_dev_assets(*, limit: int = 40) -> dict[str, Any]:
  reports = _scan_dir(_REPORTS, kind="reports", limit=limit)
  exports = _scan_dir(_EXPORTS, kind="exports", limit=limit)
  return {
    "ok": True,
    "reports": reports,
    "exports": exports,
    "reports_dir": str(_REPORTS),
    "exports_dir": str(_EXPORTS),
  }


def resolve_dev_asset(kind: str, name: str) -> Path | None:
  if kind not in ("reports", "exports"):
    return None
  if not name or ".." in name or "/" in name or "\\" in name:
    return None
  base = _REPORTS if kind == "reports" else _EXPORTS
  path = (base / name).resolve()
  try:
    path.relative_to(base.resolve())
  except ValueError:
    return None
  return path if path.is_file() else None
