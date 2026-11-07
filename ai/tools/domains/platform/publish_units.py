"""Discover git publish units (openpilot, submodules, assistant)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from ai.common.publish_config import assistant_upstream
from ai.common.repo_targets import assistant_repo_path
from ai.system.paths import openpilot_root
from ai.tools.forge import infer_forge_from_url, parse_repo_url, repo_slug
from ai.tools.domains.devops.git_remote_tools import git_remotes_at, git_status_at


def _git_is_repo(path: Path) -> bool:
  try:
    proc = subprocess.run(
      ["git", "-C", str(path), "rev-parse", "--git-dir"],
      capture_output=True,
      text=True,
      timeout=8,
      check=False,
    )
    return proc.returncode == 0
  except OSError:
    return False


def _read_gitmodules(root: Path) -> list[dict[str, str]]:
  gm = root / ".gitmodules"
  if not gm.is_file():
    return []
  try:
    text = gm.read_text(encoding="utf-8", errors="replace")
  except OSError:
    return []
  entries: list[dict[str, str]] = []
  current: dict[str, str] = {}
  for line in text.splitlines():
    line = line.strip()
    if line.startswith("[submodule"):
      if current.get("path"):
        entries.append(current)
      current = {}
      continue
    m = re.match(r'(\w+)\s*=\s*(.+)', line)
    if m and current is not None:
      current[m.group(1)] = m.group(2).strip()
  if current.get("path"):
    entries.append(current)
  return entries


def _unit_id_from_path(rel: str) -> str:
  base = rel.replace("\\", "/").strip("/")
  if base in ("opendbc_repo", "opendbc"):
    return "opendbc"
  if base == "panda":
    return "panda"
  if base.endswith("_repo"):
    return base[:-5]
  return base or "submodule"


def unit_display_name(unit_id: str, *, kind: str = "") -> str:
  uid = (unit_id or "").strip()
  if uid == "assistant" or kind == "assistant":
    return "op助手 (ai)"
  if uid == "openpilot":
    return "openpilot 主仓"
  return uid


def _dedupe_units_by_git_root(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Same git checkout must appear once — prefer assistant over submodule id 'ai'."""
  by_root: dict[str, dict[str, Any]] = {}
  order: list[str] = []
  for unit in units:
    root = unit.get("git_root") or unit.get("root") or ""
    try:
      key = str(Path(root).resolve())
    except OSError:
      key = str(root)
    prev = by_root.get(key)
    if not prev:
      by_root[key] = unit
      order.append(key)
      continue
    if unit.get("kind") == "assistant" and prev.get("kind") != "assistant":
      by_root[key] = unit
    elif unit.get("id") == "assistant" and prev.get("id") in ("ai", "assistant"):
      by_root[key] = unit
  return [by_root[k] for k in order]


def _build_unit(
  *,
  unit_id: str,
  kind: str,
  root: Path,
  git_root: Path,
  path_prefix: str = "",
  parent_id: str | None = None,
) -> dict[str, Any]:
  root = root.resolve()
  git_root = git_root.resolve()
  status = git_status_at(git_root)
  remotes = git_remotes_at(git_root)
  origin = remotes.get("origin") or remotes.get("fork") or ""
  branch = status.get("branch") or ""
  forge = infer_forge_from_url(origin) if origin else "github"
  owner, repo = "", ""
  slug = ""
  if origin:
    try:
      forge, owner, repo = parse_repo_url(origin)
      slug = repo_slug(owner, repo)
    except ValueError:
      slug = origin

  dirty_files: list[str] = []
  for line in status.get("status_lines") or []:
    if line.startswith("##"):
      continue
    part = line[3:].strip() if len(line) > 3 else line.strip()
    if " -> " in part:
      part = part.split(" -> ", 1)[1].strip()
    if part:
      dirty_files.append(part)

  prefix = path_prefix.replace("\\", "/").strip("/")
  if prefix:
    pref = prefix + "/"
    dirty_files = [f for f in dirty_files if f == prefix or f.startswith(pref)]

  upstream = assistant_upstream() if kind == "assistant" else None

  return {
    "id": unit_id,
    "display_name": unit_display_name(unit_id, kind=kind),
    "kind": kind,
    "root": str(root),
    "git_root": str(git_root),
    "path_prefix": prefix,
    "parent_id": parent_id,
    "branch": branch,
    "origin_url": origin,
    "remotes": remotes,
    "forge": forge,
    "repo_slug": slug,
    "dirty_count": len(dirty_files),
    "dirty_files": dirty_files[:80],
    "has_changes": len(dirty_files) > 0,
    "assistant_upstream": upstream,
  }


def discover_publish_units(*, include_clean: bool = True) -> dict[str, Any]:
  units: list[dict[str, Any]] = []
  op_root = openpilot_root().resolve()
  ai_path = assistant_repo_path().resolve()

  if _git_is_repo(op_root):
    units.append(_build_unit(
      unit_id="openpilot",
      kind="project",
      root=op_root,
      git_root=op_root,
    ))
    for entry in _read_gitmodules(op_root):
      rel = entry.get("path", "").strip()
      if not rel:
        continue
      sub = (op_root / rel).resolve()
      if not _git_is_repo(sub):
        continue
      # ai 子模块与 assistant 单元是同一 git 仓，只保留 assistant 条目
      if sub == ai_path:
        continue
      uid = _unit_id_from_path(rel)
      units.append(_build_unit(
        unit_id=uid,
        kind="project",
        root=sub,
        git_root=sub,
        parent_id="openpilot",
      ))

  if _git_is_repo(ai_path):
    units.append(_build_unit(
      unit_id="assistant",
      kind="assistant",
      root=ai_path,
      git_root=ai_path,
    ))
  elif (ai_path / "aid.py").is_file() and _git_is_repo(op_root):
    try:
      ai_path.relative_to(op_root)
      nested = True
    except ValueError:
      nested = False
    if nested:
      units.append(_build_unit(
        unit_id="assistant",
        kind="assistant",
        root=ai_path,
        git_root=op_root,
        path_prefix=str(ai_path.relative_to(op_root)).replace("\\", "/"),
        parent_id="openpilot",
      ))

  if not include_clean:
    units = [u for u in units if u.get("has_changes")]

  units = _dedupe_units_by_git_root(units)

  dirty_total = sum(int(u.get("dirty_count") or 0) for u in units)
  return {
    "ok": True,
    "units": units,
    "dirty_total": dirty_total,
    "has_changes": dirty_total > 0,
    "openpilot_root": str(op_root),
    "assistant_path": str(ai_path),
  }


def get_unit(unit_id: str) -> dict[str, Any] | None:
  data = discover_publish_units(include_clean=True)
  for unit in data.get("units") or []:
    if unit.get("id") == unit_id:
      return unit
  return None
