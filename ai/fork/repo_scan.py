"""Scan an openpilot tree — no fixed fork list, evidence-based discovery."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

# Typical upstream / build dirs — excluded from「社区特征目录」
STANDARD_TOP_DIRS = frozenset({
  ".git",
  ".github",
  ".venv",
  "ai",
  "cereal",
  "common",
  "docs",
  "msgq_repo",
  "opendbc",
  "panda",
  "rednose_repo",
  "release",
  "selfdrive",
  "site_scons",
  "system",
  "third_party",
  "tools",
  "tinygrad_repo",
  "__pycache__",
})

README_CANDIDATES = ("README.md", "README", "docs/README.md")
PARAMS_KEYS_PATHS = ("common/params_keys.h", "openpilot/common/params_keys.h")
LAUNCH_SCRIPTS = (
  "launch_chffrplus.sh",
  "launch_openpilot.sh",
  "launch_env.sh",
)


def _run_git(args: list[str], *, cwd: Path) -> str | None:
  try:
    proc = subprocess.run(
      ["git", *args],
      cwd=str(cwd),
      capture_output=True,
      text=True,
      timeout=25,
    )
  except (OSError, subprocess.TimeoutExpired):
    return None
  if proc.returncode != 0:
    return None
  return (proc.stdout or "").strip()


def _read_excerpt(path: Path, limit: int = 3500) -> str:
  try:
    return path.read_text(encoding="utf-8", errors="replace")[:limit]
  except OSError:
    return ""


def _parse_params_keys(path: Path) -> tuple[list[str], dict[str, int]]:
  keys: list[str] = []
  try:
    text = path.read_text(encoding="utf-8", errors="replace")
  except OSError:
    return keys, {}
  for m in re.finditer(r'\{"([^"]+)"', text):
    keys.append(m.group(1))
  prefixes: Counter[str] = Counter()
  for key in keys:
    if "_" in key:
      prefixes[key.split("_", 1)[0] + "_"] += 1
    elif key and key[0].islower():
      prefixes[key[:3]] += 1
  # Drop single-char noise; keep prefixes with 2+ keys or known patterns
  ranked = {
    p: c for p, c in prefixes.most_common(40)
    if c >= 2 or len(p) >= 3
  }
  return keys, ranked


def _find_settings_modules(root: Path) -> list[dict[str, str]]:
  """Find Python modules that likely declare Param ITEMS (any fork layout)."""
  found: list[dict[str, str]] = []
  seen: set[str] = set()
  for path in root.rglob("*.py"):
    if len(found) >= 30:
      break
    try:
      rel = str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
      continue
    if any(part in rel for part in ("/tests/", "/test/", ".venv/", "opendbc/")):
      continue
    if "settings" not in rel.lower() and "dragonpilot" not in rel.lower():
      continue
    try:
      if path.stat().st_size > 180_000:
        continue
      head = path.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
      continue
    if "ITEMS" not in head or '"key"' not in head:
      continue
    if rel in seen:
      continue
    seen.add(rel)
    found.append({"path": rel, "excerpt": head[:1200]})
  return found


def _distinctive_top_dirs(root: Path) -> list[str]:
  out: list[str] = []
  try:
    for child in sorted(root.iterdir()):
      if not child.is_dir():
        continue
      name = child.name
      if name.startswith(".") or name in STANDARD_TOP_DIRS:
        continue
      out.append(name)
  except OSError:
    pass
  return out[:30]


def _parse_remote_identity(remotes: list[str]) -> dict[str, Any]:
  for remote in remotes:
    m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", remote, re.I)
    if m:
      owner, repo = m.group(1).lower(), m.group(2).lower()
      return {
        "owner": owner,
        "repo": repo,
        "slug": f"{owner}/{repo}",
        "url": remote,
      }
  return {}


def scan_openpilot_repo(root: Path) -> dict[str, Any]:
  """Collect structured evidence from the installed openpilot tree."""
  root = root.resolve()
  remotes_raw = _run_git(["remote", "-v"], cwd=root) or ""
  remotes = []
  for line in remotes_raw.splitlines():
    parts = line.split()
    if len(parts) >= 2:
      remotes.append(parts[1])

  readme_path = None
  readme_excerpt = ""
  for rel in README_CANDIDATES:
    p = root / rel
    if p.is_file():
      readme_path = rel
      readme_excerpt = _read_excerpt(p, 4000)
      break

  params_path = None
  param_keys: list[str] = []
  param_prefixes: dict[str, int] = {}
  for rel in PARAMS_KEYS_PATHS:
    p = root / rel
    if p.is_file():
      params_path = rel
      param_keys, param_prefixes = _parse_params_keys(p)
      break

  launch_scripts = [n for n in LAUNCH_SCRIPTS if (root / n).is_file()]
  settings_modules = _find_settings_modules(root)
  distinctive_dirs = _distinctive_top_dirs(root)

  # Notable single files at repo root
  root_files = []
  for name in (
    "generate_settings.py",
    "SConstruct",
    "prebuilt",
    "launch_chffrplus.sh",
    "pyproject.toml",
  ):
    if (root / name).is_file():
      root_files.append(name)

  title = ""
  if readme_excerpt:
    for line in readme_excerpt.splitlines()[:20]:
      line = line.strip()
      if line.startswith("#"):
        title = line.lstrip("#").strip()
        break

  return {
    "openpilot_root": str(root),
    "git_branch": _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root),
    "git_commit": _run_git(["rev-parse", "--short", "HEAD"], cwd=root),
    "git_remotes": remotes[:8],
    "remote_identity": _parse_remote_identity(remotes),
    "readme_path": readme_path,
    "readme_title": title,
    "readme_excerpt": readme_excerpt,
    "launch_scripts": launch_scripts,
    "root_files": root_files,
    "distinctive_dirs": distinctive_dirs,
    "params_keys_path": params_path,
    "param_key_count": len(param_keys),
    "param_prefixes": param_prefixes,
    "param_keys_sample": param_keys[:80],
    "settings_modules": settings_modules,
    "has_prebuilt": (root / "prebuilt").is_file(),
    "has_sconstruct": (root / "SConstruct").is_file(),
  }


def derive_fork_identity(scan: dict[str, Any]) -> dict[str, Any]:
  """Heuristic label from scan only — not a fixed enum."""
  reasons: list[str] = []
  remote = scan.get("remote_identity") or {}
  fork_id = remote.get("slug") or "unknown-fork"
  fork_label = scan.get("readme_title") or remote.get("repo") or fork_id
  confidence = "low"

  if remote.get("slug"):
    reasons.append(f"git remote → {remote['slug']}")
    confidence = "medium"

  dirs = scan.get("distinctive_dirs") or []
  if dirs:
    reasons.append(f"特征目录: {', '.join(dirs[:6])}")
    if not remote.get("slug"):
      fork_id = dirs[0].lower().replace(" ", "-")
      fork_label = dirs[0]
    confidence = "medium" if confidence == "low" else confidence

  prefixes = scan.get("param_prefixes") or {}
  if prefixes:
    top = list(prefixes.keys())[:5]
    reasons.append(f"Param 前缀: {', '.join(top)}")
    confidence = "medium"

  if scan.get("readme_title"):
    reasons.append(f"README: {scan['readme_title'][:80]}")

  if scan.get("settings_modules"):
    reasons.append(f"发现 {len(scan['settings_modules'])} 个 settings/ITEMS 模块")

  return {
    "fork_id": fork_id,
    "fork_label": fork_label,
    "confidence": confidence,
    "reasons": reasons,
  }


def compact_scan_for_api(scan: dict[str, Any]) -> dict[str, Any]:
  """Smaller payload for JSON API / LLM prompts."""
  settings = scan.get("settings_modules") or []
  return {
    **{k: scan[k] for k in (
      "openpilot_root",
      "git_branch",
      "git_commit",
      "git_remotes",
      "remote_identity",
      "readme_title",
      "launch_scripts",
      "root_files",
      "distinctive_dirs",
      "params_keys_path",
      "param_key_count",
      "param_prefixes",
      "has_prebuilt",
      "has_sconstruct",
    ) if k in scan},
    "param_keys_sample": (scan.get("param_keys_sample") or [])[:40],
    "settings_module_paths": [s["path"] for s in settings[:15]],
    "readme_excerpt": (scan.get("readme_excerpt") or "")[:2000],
  }
