"""File search for composer @-mentions (openpilot + C3 system roots)."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator

from ai.system.paths import is_comma_device, openpilot_root

_SKIP_DIRS = frozenset({
  ".git",
  ".cursor",
  ".idea",
  ".vscode",
  ".venv",
  "venv",
  "__pycache__",
  "node_modules",
  "build",
  "dist",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  "site-packages",
})

_SKIP_SYSTEM_DIRS = frozenset({
  "proc",
  "sys",
  "dev",
  "run",
  "tmp",
  "cache",
  "lib",
  "spool",
})

_SKIP_EXTENSIONS = frozenset({
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".ico",
  ".svg",
  ".zip",
  ".gz",
  ".tar",
  ".xz",
  ".7z",
  ".mp4",
  ".mkv",
  ".avi",
  ".mov",
  ".mp3",
  ".wav",
  ".woff",
  ".woff2",
  ".ttf",
  ".eot",
  ".pyc",
  ".pyo",
  ".so",
  ".dll",
  ".dylib",
  ".exe",
  ".bin",
  ".o",
  ".a",
  ".class",
  ".jar",
  ".db",
  ".sqlite",
  ".sqlite3",
  ".qlog",
  ".rlog",
  ".hevc",
})

_INDEX_TTL_SEC = 300
_MAX_INDEX_ENTRIES = 80_000
_COMPOSER_MAX_CHARS = 48_000
_index_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _should_skip_dir(name: str, *, system_root: bool = False) -> bool:
  if name in _SKIP_DIRS:
    return True
  if system_root and name in _SKIP_SYSTEM_DIRS:
    return True
  return name.startswith(".")


def _rel_path(root: Path, path: Path) -> str:
  try:
    rel = path.relative_to(root)
  except ValueError:
    return path.name
  text = rel.as_posix()
  return text if text != "." else path.name


def _search_roots(*, include_system: bool = False) -> list[tuple[Path, str, int, int | None]]:
  """path, label, priority, max_depth (None = unlimited)."""
  roots: list[tuple[Path, str, int, int | None]] = [
    (openpilot_root().resolve(), "openpilot", 100, None),
  ]
  if include_system and is_comma_device():
    for raw, label, priority, max_depth in (
      ("/data", "data", 70, 9),
      ("/persist", "persist", 65, 9),
      ("/etc", "etc", 50, 12),
      ("/var", "var", 45, 7),
      ("/system", "system", 25, 5),
    ):
      path = Path(raw)
      if path.is_dir():
        roots.append((path.resolve(), label, priority, max_depth))
  return roots


def _walk_root(
  root: Path,
  *,
  label: str,
  priority: int,
  max_depth: int | None,
  op_root: Path,
  skip_under_op: bool,
) -> Iterator[dict[str, Any]]:
  root = root.resolve()
  root_depth = len(root.parts)
  for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
    current = Path(dirpath)
    depth = len(current.parts) - root_depth
    if max_depth is not None and depth >= max_depth:
      dirnames.clear()
      continue
    system_root = label in {"var", "system", "etc", "data", "persist"}
    dirnames[:] = [d for d in dirnames if not _should_skip_dir(d, system_root=system_root)]

    for name in dirnames:
      full = current / name
      try:
        if not full.is_dir():
          continue
        resolved = full.resolve()
      except OSError:
        continue
      if skip_under_op:
        try:
          resolved.relative_to(op_root)
          continue
        except ValueError:
          pass
      rel_within = _rel_path(root, resolved)
      display_rel = rel_within if label == "openpilot" else f"{label}/{rel_within}"
      yield {
        "name": name,
        "rel": display_rel,
        "path": str(resolved),
        "ext": "",
        "kind": "dir",
        "root": label,
        "priority": priority,
      }

    for name in filenames:
      if name.startswith("."):
        continue
      ext = Path(name).suffix.lower()
      if ext in _SKIP_EXTENSIONS:
        continue
      full = current / name
      try:
        if not full.is_file():
          continue
        resolved = full.resolve()
      except OSError:
        continue
      if skip_under_op:
        try:
          resolved.relative_to(op_root)
          continue
        except ValueError:
          pass
      rel_within = _rel_path(root, resolved)
      display_rel = rel_within if label == "openpilot" else f"{label}/{rel_within}"
      yield {
        "name": name,
        "rel": display_rel,
        "path": str(resolved),
        "ext": ext.lstrip("."),
        "kind": "file",
        "root": label,
        "priority": priority,
      }


def _entry(
  *,
  name: str,
  rel: str,
  path: str,
  kind: str,
  root: str,
  priority: int,
  ext: str = "",
) -> dict[str, Any]:
  return {
    "name": name,
    "rel": rel,
    "path": path,
    "ext": ext,
    "kind": kind,
    "root": root,
    "priority": priority,
  }


def _openpilot_git_index(op_root: Path) -> list[dict[str, Any]] | None:
  git_dir = op_root / ".git"
  if not git_dir.exists():
    return None
  try:
    proc = subprocess.run(
      ["git", "-C", str(op_root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
      capture_output=True,
      timeout=20,
      check=False,
    )
  except (OSError, subprocess.TimeoutExpired):
    return None
  if proc.returncode != 0:
    return None

  entries: list[dict[str, Any]] = []
  seen_paths: set[str] = set()
  seen_dirs: set[str] = set()

  def add_dir(dir_rel: str) -> None:
    if not dir_rel or dir_rel in seen_dirs:
      return
    seen_dirs.add(dir_rel)
    full = op_root / dir_rel
    path = str(full)
    if path in seen_paths:
      return
    seen_paths.add(path)
    entries.append(_entry(
      name=Path(dir_rel).name,
      rel=dir_rel,
      path=path,
      kind="dir",
      root="openpilot",
      priority=100,
    ))

  for raw in proc.stdout.split(b"\0"):
    if not raw:
      continue
    rel = raw.decode("utf-8", errors="replace").strip()
    if not rel:
      continue
    parts = Path(rel).parts
    for i in range(1, len(parts)):
      add_dir("/".join(parts[:i]))
    full = op_root / rel
    path = str(full)
    if path in seen_paths:
      continue
    seen_paths.add(path)
    entries.append(_entry(
      name=Path(rel).name,
      rel=rel,
      path=path,
      kind="file",
      root="openpilot",
      priority=100,
      ext=Path(rel).suffix.lower().lstrip("."),
    ))

  try:
    for child in op_root.iterdir():
      if not child.is_dir() or _should_skip_dir(child.name):
        continue
      add_dir(child.name)
  except OSError:
    pass

  return entries or None


def _build_index(*, scope: str = "repo") -> list[dict[str, Any]]:
  op_root = openpilot_root().resolve()
  include_system = scope == "all"
  if not include_system:
    git_entries = _openpilot_git_index(op_root)
    if git_entries:
      return git_entries[:_MAX_INDEX_ENTRIES]

  entries: list[dict[str, Any]] = []
  seen_paths: set[str] = set()

  for root, label, priority, max_depth in _search_roots(include_system=include_system):
    if len(entries) >= _MAX_INDEX_ENTRIES:
      break
    skip_under_op = label != "openpilot"
    try:
      walker = _walk_root(
        root,
        label=label,
        priority=priority,
        max_depth=max_depth,
        op_root=op_root,
        skip_under_op=skip_under_op,
      )
    except OSError:
      continue
    for entry in walker:
      path_key = entry["path"]
      if path_key in seen_paths:
        continue
      seen_paths.add(path_key)
      entries.append(entry)
      if len(entries) >= _MAX_INDEX_ENTRIES:
        break
  return entries


def _resolve_scope(query: str, scope: str | None) -> str:
  if scope in ("repo", "all"):
    return scope
  q = (query or "").strip().lower()
  if q.startswith(("data/", "data:", "/data/", "persist/", "etc/", "var/", "system/")):
    return "all"
  return "repo"


def _file_index(*, scope: str = "repo", force: bool = False) -> list[dict[str, Any]]:
  global _index_cache
  scope = _resolve_scope("", scope)
  now = time.time()
  cached = _index_cache.get(scope)
  if not force and cached and now - cached[0] < _INDEX_TTL_SEC:
    return cached[1]
  entries = _build_index(scope=scope)
  _index_cache[scope] = (now, entries)
  return entries


def _score(query: str, entry: dict[str, Any]) -> int:
  priority_boost = int(entry.get("priority") or 0)
  is_dir = str(entry.get("kind") or "file") == "dir"
  if not query:
    return priority_boost + (5 if is_dir else 0)
  name = str(entry.get("name") or "").lower()
  rel = str(entry.get("rel") or "").lower()
  root = str(entry.get("root") or "").lower()
  segments = [s for s in rel.split("/") if s]
  if name == query:
    base = 110 if is_dir else 100
  elif rel == query or rel.rstrip("/") == query:
    base = 105 if is_dir else 95
  elif name.startswith(query):
    base = 90 if is_dir else 80
  elif any(seg == query for seg in segments):
    base = 88 if is_dir else 42
  elif any(seg.startswith(query) for seg in segments):
    base = 82 if is_dir else 40
  elif query in name:
    base = 75 if is_dir else 60
  elif query in rel:
    base = 35 if is_dir else 45
  elif query in root:
    base = 30
  else:
    parts = [p for p in query.split("/") if p]
    if parts and all(any(part in segment for segment in segments) for part in parts):
      base = 25 if is_dir else 20
    else:
      return 0
  return base + priority_boost


def search_repo_files(query: str = "", *, limit: int = 25, scope: str | None = None) -> dict[str, Any]:
  q = (query or "").strip().lower()
  limit = max(1, min(int(limit or 25), 50))
  resolved_scope = _resolve_scope(q, scope)
  try:
    entries = _file_index(scope=resolved_scope)
  except Exception as exc:
    return {"ok": False, "error": str(exc)}

  roots = sorted({str(e.get("root") or "openpilot") for e in entries})

  if not q:
    preview = sorted(entries, key=lambda e: (-int(e.get("priority") or 0), str(e.get("rel") or "")))[:limit]
    return {
      "ok": True,
      "query": q,
      "files": preview,
      "total": len(entries),
      "roots": roots,
      "scope": resolved_scope,
      "device": is_comma_device(),
    }

  scored: list[tuple[int, dict[str, Any]]] = []
  for entry in entries:
    score = _score(q, entry)
    if score > 0:
      scored.append((score, entry))
  scored.sort(
    key=lambda item: (
      -item[0],
      0 if str(item[1].get("kind") or "file") == "dir" else 1,
      str(item[1].get("rel") or ""),
    )
  )
  files = [item[1] for item in scored[:limit]]
  return {
    "ok": True,
    "query": q,
    "files": files,
    "total": len(scored),
    "roots": roots,
    "scope": resolved_scope,
    "device": is_comma_device(),
  }


def _format_dir_listing(path: Path, *, max_chars: int) -> str:
  lines = [f"# {path.name}/", ""]
  root_depth = len(path.parts)
  for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
    current = Path(dirpath)
    depth = len(current.parts) - root_depth
    if depth > 4:
      dirnames.clear()
      continue
    dirnames[:] = sorted(d for d in dirnames if not _should_skip_dir(d))
    rel_dir = _rel_path(path, current)
    prefix = "" if rel_dir == path.name else rel_dir
    for name in sorted(dirnames):
      indent = "  " * (depth + 1)
      lines.append(f"{indent}{name}/")
    for name in sorted(filenames):
      if name.startswith("."):
        continue
      ext = Path(name).suffix.lower()
      if ext in _SKIP_EXTENSIONS:
        continue
      indent = "  " * (depth + 1)
      shown = f"{prefix}/{name}" if prefix and prefix != path.name else name
      lines.append(f"{indent}{shown}")
      if sum(len(line) + 1 for line in lines) >= max_chars:
        lines.append("... [truncated]")
        return "\n".join(lines)
  return "\n".join(lines)


def read_repo_file_snippet(path: str, *, max_chars: int = _COMPOSER_MAX_CHARS) -> dict[str, Any]:
  max_chars = max(1, min(int(max_chars or _COMPOSER_MAX_CHARS), 100_000))
  resolved = Path(path).expanduser()
  try:
    resolved = resolved.resolve()
  except OSError as exc:
    return {"ok": False, "error": str(exc)}
  if resolved.is_dir():
    content = _format_dir_listing(resolved, max_chars=max_chars)
    op_root = openpilot_root().resolve()
    try:
      resolved.relative_to(op_root)
      rel = _rel_path(op_root, resolved)
      root = "openpilot"
    except ValueError:
      text = resolved.as_posix()
      root = "system"
      rel = text
    return {
      "ok": True,
      "path": str(resolved),
      "rel": rel,
      "root": root,
      "kind": "dir",
      "content": content,
      "truncated": len(content) >= max_chars,
    }

  try:
    from ai.tools.fs_tools import read_file
  except ImportError:
    return {"ok": False, "error": "file reader unavailable"}
  result = read_file(path, max_bytes=max_chars * 4)
  if not result.get("ok"):
    return result
  content = str(result.get("content") or "")
  if len(content) > max_chars:
    content = content[:max_chars] + "\n\n... [truncated] ..."
    result["truncated"] = True
  resolved = Path(str(result.get("path") or path)).resolve()
  op_root = openpilot_root().resolve()
  try:
    resolved.relative_to(op_root)
    rel = _rel_path(op_root, resolved)
    root = "openpilot"
  except ValueError:
    text = resolved.as_posix()
    root = "system"
    rel = text
    for label, prefix in (
      ("data", "/data/"),
      ("persist", "/persist/"),
      ("etc", "/etc/"),
      ("var", "/var/"),
      ("system", "/system/"),
    ):
      if text.startswith(prefix) or text == prefix.rstrip("/"):
        root = label
        rel = f"{label}/{text[len(prefix):]}"
        break
  result["rel"] = rel
  result["root"] = root
  result["kind"] = "file"
  result["content"] = content
  return result


def invalidate_file_index() -> None:
  global _index_cache
  _index_cache = {}


def warm_file_index(*, scope: str = "repo") -> int:
  return len(_file_index(scope=scope))
