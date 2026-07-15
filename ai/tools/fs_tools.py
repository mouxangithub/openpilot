"""Filesystem read/write for op助手 admin mode (openpilot repo + AGNOS /data)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ai.system.paths import is_comma_device, openpilot_root

_MAX_READ_BYTES = 2_000_000
_MAX_WRITE_BYTES = 2_000_000
_MAX_LIST_ENTRIES = 500


def _allowed_roots() -> list[Path]:
  roots = [openpilot_root().resolve()]
  if is_comma_device():
    for extra in ("/data", "/persist", "/system", "/var", "/etc"):
      p = Path(extra)
      if p.is_dir():
        roots.append(p.resolve())
  return roots


def _resolve_allowed(path: str) -> tuple[Path | None, str]:
  raw = (path or "").strip()
  if not raw:
    return None, "path is required"
  candidate = Path(raw).expanduser()
  if not candidate.is_absolute():
    candidate = openpilot_root() / candidate
  try:
    resolved = candidate.resolve()
  except OSError as e:
    return None, str(e)

  for root in _allowed_roots():
    try:
      resolved.relative_to(root)
      return resolved, ""
    except ValueError:
      continue
  allowed = ", ".join(str(r) for r in _allowed_roots())
  return None, f"Path outside allowed roots ({allowed}): {raw}"


def list_directory(path: str = ".", *, max_entries: int = _MAX_LIST_ENTRIES) -> dict[str, Any]:
  resolved, err = _resolve_allowed(path)
  if err or resolved is None:
    return {"ok": False, "error": err}
  if not resolved.is_dir():
    return {"ok": False, "error": f"Not a directory: {resolved}"}
  entries: list[dict[str, Any]] = []
  try:
    for i, child in enumerate(sorted(resolved.iterdir(), key=lambda p: p.name.lower())):
      if i >= max_entries:
        entries.append({"name": "...", "truncated": True})
        break
      try:
        st = child.stat()
        entries.append({
          "name": child.name,
          "path": str(child),
          "is_dir": child.is_dir(),
          "size": st.st_size if child.is_file() else None,
        })
      except OSError:
        entries.append({"name": child.name, "path": str(child), "error": "stat failed"})
  except PermissionError:
    return {"ok": False, "error": f"Permission denied: {resolved}"}
  return {"ok": True, "path": str(resolved), "entries": entries}


def read_file(path: str, *, max_bytes: int = _MAX_READ_BYTES) -> dict[str, Any]:
  resolved, err = _resolve_allowed(path)
  if err or resolved is None:
    return {"ok": False, "error": err}
  if not resolved.is_file():
    return {"ok": False, "error": f"Not a file: {resolved}"}
  try:
    size = resolved.stat().st_size
    if size > max_bytes:
      data = resolved.read_bytes()[:max_bytes]
      text = data.decode("utf-8", errors="replace")
      return {
        "ok": True,
        "path": str(resolved),
        "content": text + "\n\n... [truncated] ...",
        "truncated": True,
        "size": size,
      }
    text = resolved.read_text(encoding="utf-8", errors="replace")
    return {"ok": True, "path": str(resolved), "content": text, "size": size}
  except PermissionError:
    return {"ok": False, "error": f"Permission denied: {resolved}"}
  except OSError as e:
    return {"ok": False, "error": str(e)}


def write_file(path: str, content: str, *, create_dirs: bool = True) -> dict[str, Any]:
  resolved, err = _resolve_allowed(path)
  if err or resolved is None:
    return {"ok": False, "error": err}
  if len(content.encode("utf-8")) > _MAX_WRITE_BYTES:
    return {"ok": False, "error": f"Content exceeds {_MAX_WRITE_BYTES} bytes"}
  try:
    if create_dirs:
      resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(resolved), "bytes": len(content.encode("utf-8"))}
  except PermissionError:
    return {"ok": False, "error": f"Permission denied: {resolved}"}
  except OSError as e:
    return {"ok": False, "error": str(e)}


def allowed_roots_summary() -> dict[str, Any]:
  return {"ok": True, "roots": [str(r) for r in _allowed_roots()]}
