"""Serve openpilot UI assets (fonts, icons) from the openpilot tree."""

from __future__ import annotations

from pathlib import Path

from webui.server.deps import openpilot_root


def _search_roots() -> list[Path]:
  root = openpilot_root()
  candidates = [
    root,
    root / "openpilot",
    root / "sunnypilot",
    root / "openpilot" / "sunnypilot",
    root / "openpilot" / "selfdrive",
    root / "openpilot" / "system" / "ui",
    root / "selfdrive",
    root / "system" / "ui",
  ]
  out: list[Path] = []
  seen: set[str] = set()
  for c in candidates:
    key = str(c.resolve()) if c.exists() else str(c)
    if key not in seen:
      seen.add(key)
      out.append(c)
  return out


def resolve_asset(rel_path: str) -> Path | None:
  rel = rel_path.replace("\\", "/").lstrip("/")
  # Normalize sunnypilot-relative paths
  variants = [rel]
  if rel.startswith("sunnypilot/"):
    variants.append(rel.replace("sunnypilot/", "openpilot/sunnypilot/", 1))
    variants.append(rel.replace("sunnypilot/", "", 1))
  if rel.startswith("../../sunnypilot/"):
    variants.append(rel.replace("../../sunnypilot/", "sunnypilot/", 1))

  for base in _search_roots():
    for v in variants:
      path = (base / v).resolve()
      try:
        path.relative_to(base.resolve())
      except ValueError:
        continue
      if path.is_file():
        return path
      # system ui icons
      alt = base / "widgets" / v if "icons/" in v else None
      if alt and alt.is_file():
        return alt
  # Flat icon search
  name = Path(rel).name
  for base in _search_roots():
    for hit in base.rglob(name):
      if hit.is_file() and hit.suffix.lower() in (".png", ".svg", ".ttf", ".otf", ".woff2", ".wav"):
        return hit
  return None
