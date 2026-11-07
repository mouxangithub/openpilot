#!/usr/bin/env python3
"""Clean up cabana route cache files (*.json.gz), oldest first.

CLI:
  python clean_cabana_cache.py [--dir PATH] [--keep N] [--dry-run]

``--dir`` defaults to the cabana cache directory used by the replay module;
``--keep`` is the number of newest cache files to retain (default 32);
``--dry-run`` only prints the deletion list without removing anything.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def default_cache_dir() -> Path:
  """Resolve the cabana cache directory (same candidate order as replay.py)."""
  try:
    from ai.services.cabana.replay import _cabana_cache_dir
    return _cabana_cache_dir()
  except Exception:
    pass
  try:
    from ai.system.paths import openpilot_root
    return Path(openpilot_root()) / "ai" / "cabana_cache"
  except Exception:
    pass
  return Path(__file__).resolve().parent.parent / "services" / "data" / "cabana_cache"


def list_cache_files(cache_dir: Path) -> list[Path]:
  """All *.json.gz files in the cache directory, oldest first."""
  if not cache_dir.is_dir():
    return []
  files = [p for p in cache_dir.iterdir() if p.is_file() and p.name.endswith(".json.gz")]
  files.sort(key=lambda p: p.stat().st_mtime)
  return files


def clean(cache_dir: Path, keep: int, dry_run: bool) -> list[Path]:
  """Delete the oldest cache files beyond ``keep``; returns removed paths."""
  files = list_cache_files(cache_dir)
  if len(files) <= keep:
    return []
  doomed = files[: len(files) - keep]
  if dry_run:
    return doomed
  removed: list[Path] = []
  for path in doomed:
    try:
      path.unlink()
      removed.append(path)
    except OSError as e:
      print(f"warn: failed to remove {path}: {e}", file=sys.stderr)
  return removed


def main() -> int:
  parser = argparse.ArgumentParser(description="Clean cabana route cache files (oldest first).")
  parser.add_argument("--dir", default="", help="Cache directory (default: cabana cache dir)")
  parser.add_argument("--keep", type=int, default=32, help="Number of newest files to keep (default 32)")
  parser.add_argument("--dry-run", action="store_true", help="Print the deletion list only")
  args = parser.parse_args()

  cache_dir = Path(args.dir) if args.dir else default_cache_dir()
  files = list_cache_files(cache_dir)
  print(f"cache dir: {cache_dir}")
  print(f"cache files: {len(files)} (keep {args.keep})")
  removed = clean(cache_dir, max(0, args.keep), args.dry_run)
  if not removed:
    print("nothing to delete")
    return 0
  action = "would delete" if args.dry_run else "deleted"
  for path in removed:
    print(f"{action}: {path.name}")
  print(f"{len(removed)} file(s) {action}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
