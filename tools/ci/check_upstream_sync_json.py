#!/usr/bin/env python3
"""Lint `upstream-sync.json` against the working tree.

Fails when the manifest is missing/stale relative to the current submodule
state — i.e. a submodule pointer was bumped (or its tree changed) without
regenerating the provenance manifest, or a submodule has uncommitted changes
that would make the pinned tree hash a lie.

Run tools/ci/gen_upstream_sync_json.py --update to re-baseline.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "upstream-sync.json"


def git(*args: str, cwd: Path = ROOT) -> str:
  return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def submodule_paths() -> list[str]:
  out = git("config", "-f", ".gitmodules", "--get-regexp", r"submodule\..*\.path")
  return sorted(
    (line.split("=", 1)[1] if "=" in line else line.split(None, 1)[1]).strip()
    for line in out.splitlines())


def main() -> int:
  errors: list[str] = []
  if not MANIFEST.exists():
    print(f"::error::upstream-sync.json missing; run tools/ci/gen_upstream_sync_json.py --update")
    return 1
  try:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
  except json.JSONDecodeError as error:
    print(f"::error::upstream-sync.json is not valid JSON: {error}")
    return 1

  pinned = manifest.get("submodules", {})
  current_paths = set(submodule_paths())
  manifest_paths = set(pinned)

  for path in sorted(current_paths - manifest_paths):
    errors.append(f"submodule '{path}' is not recorded in the manifest; regenerate upstream-sync.json")
  for path in sorted(manifest_paths - current_paths):
    errors.append(f"manifest records submodule '{path}' which is no longer registered; regenerate upstream-sync.json")

  for path in sorted(current_paths & manifest_paths):
    cwd = ROOT / path
    entry = pinned[path]
    actual_commit = git("rev-parse", "HEAD", cwd=cwd)
    if entry.get("commit") != actual_commit:
      errors.append(
        f"submodule '{path}': manifest pins {str(entry.get('commit'))[:12]} but the tree is at "
        f"{actual_commit[:12]}; regenerate upstream-sync.json (tools/ci/gen_upstream_sync_json.py --update)")
      continue
    actual_tree = git("rev-parse", "HEAD^{tree}", cwd=cwd)
    if entry.get("tree") != actual_tree:
      errors.append(
        f"submodule '{path}': pinned tree hash drift (manifest {str(entry.get('tree'))[:12]} vs "
        f"actual {actual_tree[:12]}); regenerate upstream-sync.json")
    dirty = git("status", "--porcelain", cwd=cwd)
    if dirty:
      errors.append(
        f"submodule '{path}' has uncommitted changes; the pinned tree hash is not what would ship:\n"
        + "\n".join(f"    {line}" for line in dirty.splitlines()[:10]))

  for error in errors:
    print(f"::error::{error}")
  if errors:
    print(f"\nupstream-sync provenance gate FAILED with {len(errors)} violation(s)")
    return 1
  print(f"upstream-sync provenance gate OK ({len(current_paths & manifest_paths)} submodules pinned)")
  return 0


if __name__ == "__main__":
  sys.exit(main())
