"""Externalize large tool results — keep context lean, store via configurable backend.

Supports a retention lease model: callers can acquire a lease when a large
result is produced, renew it while the result is still needed, and release it
when done. An expired lease can be cleaned up via ``sweep_expired``.

Backends:
- ``local`` (default): store under ``workspace_path("tool_results")``.
- ``http``: PUT/GET/DELETE against ``ai_externalize_remote_url``.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai.system.paths import workspace_path
from ai.tools.spill_backend import get_spill_backend

try:
  from ai.common.storage import read_param_bool, read_param
except Exception:  # pragma: no cover - fallback when openpilot params unavailable

  def read_param_bool(_params: Any, key: str, default: bool = False) -> bool:  # noqa: D103
    if _params is not None and key in _params:
      return str(_params[key]).strip().lower() in ("1", "true", "yes", "on")
    return default

  def read_param(_params: Any, key: str, default: Any = None) -> Any:  # noqa: D103
    if _params is not None and key in _params:
      return _params[key]
    return default


_DEFAULT_THRESHOLD = 8192
_MAX_PREVIEW = 2000
_DEFAULT_LEASE_SECONDS = 3600


def _base_dir() -> Path:
  """Base directory for local spill results.

  Kept as a thin wrapper so tests can monkeypatch ``workspace_path``.
  """
  return workspace_path("tool_results")


def externalize_enabled(params: Any = None) -> bool:
  return read_param_bool(params, "ai_externalize_results", True)


def threshold_bytes(params: Any = None) -> int:
  try:
    raw = read_param(params, "ai_externalize_threshold", str(_DEFAULT_THRESHOLD))
    return max(1024, min(int(str(raw or _DEFAULT_THRESHOLD)), 512_000))
  except (TypeError, ValueError):
    return _DEFAULT_THRESHOLD


def _results_dir(session_id: str) -> Path:
  sid = (session_id or "global").replace("/", "_").replace("\\", "_")[:64]
  path = workspace_path("tool_results", sid, mkdir=True)
  path.mkdir(parents=True, exist_ok=True)
  return path


def _summarize(result: Any, *, max_len: int = 600) -> str:
  if isinstance(result, dict):
    if result.get("error"):
      return f"Error: {str(result.get('error'))[:max_len]}"
    if result.get("summary"):
      return str(result["summary"])[:max_len]
    keys = list(result.keys())[:8]
    return f"Dict keys: {', '.join(keys)}"[:max_len]
  text = str(result)
  return text[:max_len] + ("…" if len(text) > max_len else "")


def externalize_if_needed(
  result: Any,
  *,
  session_id: str = "",
  tool_name: str = "",
  params: Any = None,
) -> tuple[Any, dict[str, Any] | None]:
  """
  Return (result_for_context, artifact_meta_or_none).
  If externalized, result_for_context is a compact pointer dict.
  """
  if not externalize_enabled(params):
    return result, None
  try:
    serialized = json.dumps(result, ensure_ascii=False, default=str)
  except (TypeError, ValueError):
    return result, None
  if len(serialized.encode("utf-8")) <= threshold_bytes(params):
    return result, None

  ref_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
  backend = get_spill_backend(params, base_dir=_base_dir())
  store_result = backend.store(
    ref_id,
    serialized.encode("utf-8"),
    session_id=session_id,
    tool_name=tool_name or "tool",
    ext="json",
  )
  if not store_result.get("ok"):
    # Fallback: truncate inline
    preview = serialized[:_MAX_PREVIEW]
    return {
      "ok": True,
      "externalized": False,
      "truncated": True,
      "preview": preview,
      "size_bytes": len(serialized),
    }, None

  preview = serialized[:_MAX_PREVIEW]
  locator = store_result["locator"]
  pointer = {
    "ok": True,
    "externalized": True,
    "ref": f"toolresult://{ref_id}",
    "path": locator,
    "tool": tool_name,
    "size_bytes": len(serialized),
    "summary": _summarize(result),
    "preview": preview,
    "hint": "Full output saved. Use read_file on path/URL if you need the complete data.",
  }
  artifact = {
    "id": f"ext_{ref_id}",
    "kind": "tool_result",
    "title": f"{tool_name} 输出 ({len(serialized)} bytes)",
    "payload": {
      "ref": pointer["ref"],
      "path": locator,
      "preview": preview,
      "summary": pointer["summary"],
      "tool": tool_name,
      "size_bytes": len(serialized),
    },
    "sourceTool": tool_name,
    "createdAt": int(time.time()),
  }
  return pointer, artifact


def read_externalized(ref: str) -> dict[str, Any]:
  """Load externalized result by ref id (toolresult://...)."""
  ref_id = str(ref or "").replace("toolresult://", "").strip()
  if not ref_id:
    return {"ok": False, "error": "Invalid ref"}
  backend = get_spill_backend(base_dir=_base_dir())
  data = backend.load(ref_id)
  if data is None:
    return {"ok": False, "error": f"Not found: {ref_id}"}
  try:
    return {"ok": True, "ref": ref, "data": json.loads(data.decode("utf-8"))}
  except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
    return {"ok": False, "error": str(e)}


# --- Retention lease management ---

@dataclass
class LeaseRecord:
  """Lease metadata persisted alongside an externalized result."""

  ref: str
  path: str
  created_at: int
  expires_at: int
  owner: str = ""
  meta: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "ref": self.ref,
      "path": self.path,
      "created_at": self.created_at,
      "expires_at": self.expires_at,
      "owner": self.owner,
      "meta": self.meta,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> LeaseRecord:
    return cls(
      ref=str(data.get("ref", "")),
      path=str(data.get("path", "")),
      created_at=int(data.get("created_at", 0)),
      expires_at=int(data.get("expires_at", 0)),
      owner=str(data.get("owner", "")),
      meta=dict(data.get("meta") or {}),
    )


def _lease_dir() -> Path:
  path = workspace_path("tool_results", ".leases", mkdir=True)
  path.mkdir(parents=True, exist_ok=True)
  return path


def _lease_path(ref_id: str) -> Path:
  return _lease_dir() / f"{ref_id}.lease.json"


def acquire_lease(
  ref: str,
  *,
  duration_seconds: int = _DEFAULT_LEASE_SECONDS,
  owner: str = "",
  meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Acquire or renew a lease for an externalized result.

  Returns the lease record and whether the underlying artifact still exists.
  """
  ref_id = str(ref or "").replace("toolresult://", "").strip()
  if not ref_id:
    return {"ok": False, "error": "Invalid ref"}
  backend = get_spill_backend(base_dir=_base_dir())
  exists = backend.load(ref_id) is not None
  now = int(time.time())
  record = LeaseRecord(
    ref=ref,
    path=str(_lease_path(ref_id)),
    created_at=now,
    expires_at=now + duration_seconds,
    owner=owner,
    meta=meta or {},
  )
  try:
    _lease_path(ref_id).write_text(json.dumps(record.to_dict(), ensure_ascii=False), encoding="utf-8")
  except OSError as e:
    return {"ok": False, "error": f"Lease write failed: {e}"}
  return {"ok": True, "ref": ref, "expires_at": record.expires_at, "exists": exists}


def release_lease(ref: str) -> dict[str, Any]:
  """Release a lease and delete the externalized artifact."""
  ref_id = str(ref or "").replace("toolresult://", "").strip()
  if not ref_id:
    return {"ok": False, "error": "Invalid ref"}
  backend = get_spill_backend(base_dir=_base_dir())
  removed = backend.remove(ref_id)
  lease = _lease_path(ref_id)
  try:
    lease.unlink()
  except FileNotFoundError:
    pass
  return {"ok": True, "ref": ref, "removed": removed}


def get_lease(ref: str) -> dict[str, Any]:
  """Return current lease info for a ref."""
  ref_id = str(ref or "").replace("toolresult://", "").strip()
  if not ref_id:
    return {"ok": False, "error": "Invalid ref"}
  backend = get_spill_backend(base_dir=_base_dir())
  exists = backend.load(ref_id) is not None
  lease_path = _lease_path(ref_id)
  if not lease_path.exists():
    return {"ok": True, "ref": ref, "leased": False, "exists": exists}
  try:
    record = LeaseRecord.from_dict(json.loads(lease_path.read_text(encoding="utf-8")))
    now = int(time.time())
    return {
      "ok": True,
      "ref": ref,
      "leased": True,
      "expires_at": record.expires_at,
      "expired": now > record.expires_at,
      "owner": record.owner,
      "exists": exists,
    }
  except (OSError, json.JSONDecodeError) as e:
    return {"ok": False, "error": str(e)}


def sweep_expired(*, dry_run: bool = False) -> dict[str, Any]:
  """Delete externalized results whose lease has expired (or have no lease).

  A file without a lease is treated as expired immediately.
  For remote backends, lease sweeping is a no-op and the remote service is
  expected to enforce its own retention policy.
  """
  from ai.tools.spill_backend import LocalSpillBackend

  backend = get_spill_backend(base_dir=_base_dir())
  if not isinstance(backend, LocalSpillBackend):
    return {"ok": True, "removed": [], "skipped": [], "dry_run": dry_run, "backend": "remote"}

  base = _base_dir()
  if not base.is_dir():
    return {"ok": True, "removed": [], "skipped": [], "dry_run": dry_run}
  now = int(time.time())
  removed: list[str] = []
  skipped: list[str] = []
  for path in base.rglob("*"):
    if not path.is_file() or path.name.endswith(".lease.json"):
      continue
    # Extract ref id from filename: <tool>_<ref_id>.<ext>
    name = path.name
    parts = name.rsplit("_", 1)
    if len(parts) != 2:
      continue
    ref_id = parts[1].rsplit(".", 1)[0]
    if not ref_id:
      continue
    lease_path = _lease_path(ref_id)
    expired = False
    if not lease_path.exists():
      expired = True
    else:
      try:
        record = LeaseRecord.from_dict(json.loads(lease_path.read_text(encoding="utf-8")))
        expired = now > record.expires_at
      except (OSError, json.JSONDecodeError):
        expired = True
    if expired:
      if not dry_run:
        try:
          path.unlink()
        except FileNotFoundError:
          pass
        try:
          lease_path.unlink()
        except FileNotFoundError:
          pass
      removed.append(str(path))
    else:
      skipped.append(str(path))
  return {"ok": True, "removed": removed, "skipped": skipped, "dry_run": dry_run}


# --- Spill waterfall (dsh spill-policy port) ---
#
# Mirrors `E:\deepseek-harness\packages\spill\spill-policy\src\index.ts`:
# the model-facing post-execute arm saves the FULL plain-text result to a
# session-scoped spill file and replaces the context copy with a bounded
# head/tail preview plus a spill notice. Best-effort: any failure (no session,
# save error, notice over cap) keeps the original inline content.

_SPILL_NOTICE_TEMPLATE = (
  "({omitted} Full formatted result stored at: {locator}. {hint})"
)


def _omitted_label(omitted_bytes: int) -> str:
  if omitted_bytes >= 1024 * 1024:
    return f"{omitted_bytes / 1024 / 1024:.1f} MiB omitted"
  if omitted_bytes >= 1024:
    return f"{omitted_bytes / 1024:.1f} KiB omitted"
  return f"{omitted_bytes} bytes omitted"


def _spill_notice(omitted_bytes: int, locator: str, hint: str) -> str:
  return _SPILL_NOTICE_TEMPLATE.format(
    omitted=_omitted_label(omitted_bytes),
    locator=locator,
    hint=hint,
  )


def spill_text_if_needed(
  text: str,
  *,
  session_id: str = "",
  tool_name: str = "",
  call_id: str = "",
  max_bytes: int | None = None,
  params: Any = None,
  kind: str = "result",
) -> tuple[str | None, dict[str, Any] | None]:
  """Spill `text` and return (bounded_replacement, ref) or (None, None).

  Port of dsh ``spillReplacement``. ``kind`` records which arm produced the
  spill — ``result`` (model-facing post-execute) or ``dispatch`` (session-log
  copy of a sub-call result) — so artifacts are distinguishable on replay.
  Returns ``None`` (keep original) when: no session owner, save fails, or the
  notice itself exceeds the cap.
  """
  if not externalize_enabled(params):
    return None, None
  cap = max_bytes if max_bytes is not None else threshold_bytes(params)
  total = len(text.encode("utf-8"))
  if total <= cap:
    return None, None
  if not session_id:
    return None, None

  ref_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
  backend = get_spill_backend(params, base_dir=_base_dir())
  store_result = backend.store(
    ref_id,
    text.encode("utf-8"),
    session_id=session_id,
    tool_name=tool_name or "tool",
    ext="txt",
  )
  if not store_result.get("ok"):
    return None, None

  locator = store_result["locator"]
  hint = "Use read_file on this path/URL for the complete data."
  ref = {
    "ref": f"toolresult://{ref_id}",
    "path": locator,
    "tool": tool_name,
    "call_id": call_id,
    "kind": kind if kind in ("result", "dispatch") else "result",
    "size_bytes": total,
    "hint": hint,
  }

  # Reserve the notice's byte cost INSIDE the cap so the replacement never
  # exceeds it. Worst-case omitted count bounds the real one.
  reserve = len(_spill_notice(total, locator, hint).encode("utf-8")) + 2  # \n\n
  budget = max(0, cap - reserve)
  from ai.core.tools.pipeline import truncate_content_head_tail
  preview_text = truncate_content_head_tail(text, budget, notice="")
  omitted = total - len(preview_text.encode("utf-8"))
  notice = _spill_notice(omitted, locator, hint)
  replaced = f"{preview_text}\n\n{notice}" if preview_text else notice
  if len(replaced.encode("utf-8")) > cap:
    # Invariant: never emit a replacement larger than the cap. The already
    # written spill file is a harmless orphan; cleanup is deferred.
    return None, None
  return replaced, ref
