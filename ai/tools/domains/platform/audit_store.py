"""Append-only audit log with hash chain for op助手 tool calls and writes."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path

_MAX_ENTRIES = 500
_AUDIT_PATH: Path | None = None
_CHAIN_STATE_PATH: Path | None = None
_prev_hash: str = ""


def audit_path() -> Path:
  global _AUDIT_PATH
  if _AUDIT_PATH is None:
    _AUDIT_PATH = workspace_path("ai_audit_trail.jsonl", mkdir=True)
  return _AUDIT_PATH


def _chain_state_path() -> Path:
  global _CHAIN_STATE_PATH
  if _CHAIN_STATE_PATH is None:
    _CHAIN_STATE_PATH = workspace_path("ai_audit_chain.state", mkdir=True)
  return _CHAIN_STATE_PATH


def _load_chain_state() -> str:
  global _prev_hash
  if _prev_hash:
    return _prev_hash
  path = _chain_state_path()
  if path.is_file():
    try:
      _prev_hash = path.read_text(encoding="utf-8").strip()
    except OSError:
      _prev_hash = ""
  return _prev_hash


def _save_chain_state(chain_hash: str) -> None:
  global _prev_hash
  _prev_hash = chain_hash
  try:
    _chain_state_path().write_text(chain_hash, encoding="utf-8")
  except OSError:
    pass


def _compute_hash(prev: str, payload: str) -> str:
  return hashlib.sha256(f"{prev}:{payload}".encode("utf-8")).hexdigest()


def record_audit(
  *,
  action: str,
  tool: str = "",
  detail: dict[str, Any] | None = None,
  ok: bool = True,
  session_id: str = "",
  agent_id: str = "",
) -> dict[str, Any]:
  prev = _load_chain_state()
  entry_core: dict[str, Any] = {
    "ts": int(time.time() * 1000),
    "action": action,
    "tool": tool,
    "ok": ok,
    "detail": detail or {},
  }
  payload = json.dumps(entry_core, ensure_ascii=False, default=str, sort_keys=True)
  chain_hash = _compute_hash(prev, payload)
  entry = {**entry_core, "prev_hash": prev, "hash": chain_hash}
  path = audit_path()
  try:
    with path.open("a", encoding="utf-8") as f:
      f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    _save_chain_state(chain_hash)
    _trim_if_needed(path)
    try:
      from ai.tools.domains.platform.harness_db import record_audit_event
      record_audit_event(
        action=action,
        tool=tool,
        ok=ok,
        detail=detail,
        session_id=session_id,
        agent_id=agent_id,
        chain_hash=chain_hash,
        prev_hash=prev,
      )
    except Exception:
      pass
  except OSError:
    pass
  return entry


def verify_audit_chain(*, limit: int = 200) -> dict[str, Any]:
  """Verify hash chain integrity for recent entries."""
  path = audit_path()
  if not path.is_file():
    return {"ok": True, "verified": 0, "broken": False}
  lines: list[str] = []
  try:
    with path.open(encoding="utf-8") as f:
      lines = [ln.strip() for ln in f.readlines() if ln.strip()]
  except OSError as e:
    return {"ok": False, "error": str(e)}
  lines = lines[-max(1, min(limit, 500)) :]
  prev = ""
  verified = 0
  for line in lines:
    try:
      entry = json.loads(line)
    except json.JSONDecodeError:
      return {"ok": False, "broken": True, "verified": verified, "error": "invalid json"}
    stored_hash = entry.pop("hash", "")
    entry_prev = entry.pop("prev_hash", "")
    if entry_prev != prev:
      return {
        "ok": False,
        "broken": True,
        "verified": verified,
        "error": f"prev_hash mismatch at entry {verified}",
      }
    payload = json.dumps(entry, ensure_ascii=False, default=str, sort_keys=True)
    expected = _compute_hash(prev, payload)
    if stored_hash != expected:
      return {
        "ok": False,
        "broken": True,
        "verified": verified,
        "error": f"hash mismatch at entry {verified}",
      }
    prev = stored_hash
    verified += 1
  return {"ok": True, "broken": False, "verified": verified, "head_hash": prev}


def list_audit_trail(*, limit: int = 50) -> dict[str, Any]:
  limit = max(1, min(int(limit), 200))
  path = audit_path()
  if not path.is_file():
    return {"ok": True, "entries": [], "count": 0, "path": str(path), "chain_ok": True}
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
  chain = verify_audit_chain(limit=limit)
  return {
    "ok": True,
    "entries": entries,
    "count": len(entries),
    "path": str(path),
    "chain_ok": chain.get("ok") and not chain.get("broken"),
    "chain_verified": chain.get("verified", 0),
  }


def _trim_if_needed(path: Path) -> None:
  try:
    with path.open(encoding="utf-8") as f:
      lines = f.readlines()
    if len(lines) <= _MAX_ENTRIES:
      return
    trimmed = lines[-_MAX_ENTRIES:]
    with path.open("w", encoding="utf-8") as f:
      f.writelines(trimmed)
    # Rebuild chain state from last entry
    if trimmed:
      try:
        last = json.loads(trimmed[-1].strip())
        _save_chain_state(str(last.get("hash") or ""))
      except (json.JSONDecodeError, KeyError):
        pass
  except OSError:
    pass
