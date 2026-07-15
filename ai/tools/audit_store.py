"""Append-only audit log for op助手 tool calls and writes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path

_MAX_ENTRIES = 500
_AUDIT_PATH: Path | None = None


def audit_path() -> Path:
  global _AUDIT_PATH
  if _AUDIT_PATH is None:
    _AUDIT_PATH = workspace_path("ai_audit_trail.jsonl", mkdir=True)
  return _AUDIT_PATH


def record_audit(
  *,
  action: str,
  tool: str = "",
  detail: dict[str, Any] | None = None,
  ok: bool = True,
) -> None:
  entry = {
    "ts": int(time.time() * 1000),
    "action": action,
    "tool": tool,
    "ok": ok,
    "detail": detail or {},
  }
  path = audit_path()
  try:
    with path.open("a", encoding="utf-8") as f:
      f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    _trim_if_needed(path)
  except OSError:
    pass


def list_audit_trail(*, limit: int = 50) -> dict[str, Any]:
  limit = max(1, min(int(limit), 200))
  path = audit_path()
  if not path.is_file():
    return {"ok": True, "entries": [], "count": 0, "path": str(path)}
  lines: list[str] = []
  try:
    with path.open(encoding="utf-8") as f:
      lines = f.readlines()
  except OSError as e:
    return {"ok": False, "error": str(e)}
  entries: list[dict[str, Any]] = []
  for line in lines[-limit:]:
    line = line.strip()
    if not line:
      continue
    try:
      entries.append(json.loads(line))
    except json.JSONDecodeError:
      continue
  entries.reverse()
  return {"ok": True, "entries": entries, "count": len(entries), "path": str(path)}


def _trim_if_needed(path: Path) -> None:
  try:
    with path.open(encoding="utf-8") as f:
      lines = f.readlines()
    if len(lines) <= _MAX_ENTRIES:
      return
    with path.open("w", encoding="utf-8") as f:
      f.writelines(lines[-_MAX_ENTRIES:])
  except OSError:
    pass
