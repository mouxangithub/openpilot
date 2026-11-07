"""MCP server trust workflow.

Provides a lightweight trust decision framework for MCP servers and deferred
tools. Each server configuration is fingerprinted so configuration changes
invalidate prior trust decisions. Trust confirmations are recorded as
``mcp/trust_asked`` and ``mcp/trust_decided`` events in the session log.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai.core.session.log import EventType, SessionLog


class MCPTrustError(Exception):
  """Raised when trust state is inconsistent or invalid."""

  def __init__(self, message: str, code: str = "MCP_TRUST_ERROR") -> None:
    super().__init__(message)
    self.message = message
    self.code = code


@dataclass
class MCPServerFingerprint:
  """Immutable fingerprint of an MCP server configuration."""

  server_id: str
  command: str
  args: tuple[str, ...]
  env_keys: tuple[str, ...]
  digest: str

  def to_dict(self) -> dict[str, Any]:
    return {
      "server_id": self.server_id,
      "command": self.command,
      "args": list(self.args),
      "env_keys": list(self.env_keys),
      "digest": self.digest,
    }


def fingerprint_server_config(
  server_id: str,
  *,
  command: str = "",
  args: list[str] | None = None,
  env: dict[str, str] | None = None,
) -> MCPServerFingerprint:
  """Create a stable fingerprint for an MCP server configuration.

  The digest covers the command, arguments, and sorted environment entries.
  Values of sensitive environment variables are hashed so the fingerprint
  changes when secrets change without exposing them.
  """
  server_id = str(server_id or "")
  command = str(command or "")
  args = tuple(str(a) for a in (args or []))
  env = dict(env or {})
  sorted_env = sorted((str(k), str(v)) for k, v in env.items())
  canonical = {
    "server_id": server_id,
    "command": command,
    "args": list(args),
    "env": sorted_env,
  }
  digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
  return MCPServerFingerprint(
    server_id=server_id,
    command=command,
    args=args,
    env_keys=tuple(k for k, _ in sorted_env),
    digest=digest,
  )


@dataclass
class MCPTrustDecision:
  """A recorded trust decision for one server fingerprint."""

  server_id: str
  fingerprint_digest: str
  decision: str
  decided_at: int
  reason: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {
      "server_id": self.server_id,
      "fingerprint_digest": self.fingerprint_digest,
      "decision": self.decision,
      "decided_at": self.decided_at,
      "reason": self.reason,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> MCPTrustDecision:
    return cls(
      server_id=str(data.get("server_id", "")),
      fingerprint_digest=str(data.get("fingerprint_digest", "")),
      decision=str(data.get("decision", "")),
      decided_at=int(data.get("decided_at", 0)),
      reason=str(data.get("reason", "")),
    )


class MCPTrustStore:
  """Persist trusted server fingerprints and decisions to disk.

  Uses a simple JSON file stored under ``<base_dir>/mcp_trust.json``.
  """

  def __init__(self, base_dir: str | Path) -> None:
    self.base_dir = Path(base_dir)
    self.base_dir.mkdir(parents=True, exist_ok=True)
    self._path = self.base_dir / "mcp_trust.json"
    self._whitelist: dict[str, MCPTrustDecision] = {}
    self._load()

  def _load(self) -> None:
    if not self._path.exists():
      return
    try:
      data = json.loads(self._path.read_text(encoding="utf-8"))
      entries = data if isinstance(data, list) else []
      self._whitelist = {
        str(entry.get("server_id", "")): MCPTrustDecision.from_dict(entry)
        for entry in entries
        if isinstance(entry, dict) and entry.get("server_id")
      }
    except (OSError, json.JSONDecodeError):
      self._whitelist = {}

  def _save(self) -> None:
    tmp_path = self._path.with_suffix(".tmp")
    try:
      tmp_path.write_text(
        json.dumps(
          [decision.to_dict() for decision in self._whitelist.values()],
          ensure_ascii=False,
          indent=2,
        ),
        encoding="utf-8",
      )
      tmp_path.replace(self._path)
    except OSError as exc:
      raise MCPTrustError(f"Failed to save trust store: {exc}", "TRUST_STORE_WRITE_FAILED") from exc
    finally:
      tmp_path.unlink(missing_ok=True)

  def is_trusted(self, fingerprint: MCPServerFingerprint) -> bool:
    """Return True if the server fingerprint is currently trusted."""
    decision = self._whitelist.get(fingerprint.server_id)
    if decision is None:
      return False
    return decision.decision == "allow" and decision.fingerprint_digest == fingerprint.digest

  def decide(
    self,
    fingerprint: MCPServerFingerprint,
    decision: str,
    *,
    reason: str = "",
    timestamp: int | None = None,
  ) -> MCPTrustDecision:
    """Record a trust decision for a server fingerprint."""
    if decision not in ("allow", "deny", "ask"):
      raise MCPTrustError(f"Invalid trust decision: {decision}", "INVALID_DECISION")
    record = MCPTrustDecision(
      server_id=fingerprint.server_id,
      fingerprint_digest=fingerprint.digest,
      decision=decision,
      decided_at=timestamp or _now(),
      reason=reason,
    )
    self._whitelist[fingerprint.server_id] = record
    self._save()
    return record

  def remove(self, server_id: str) -> bool:
    """Remove a stored decision. Returns True if it existed."""
    existed = server_id in self._whitelist
    self._whitelist.pop(server_id, None)
    if existed:
      self._save()
    return existed

  def list_decisions(self) -> list[dict[str, Any]]:
    """Return all recorded trust decisions as dicts."""
    return [decision.to_dict() for decision in self._whitelist.values()]


@dataclass
class MCPTrustRequest:
  """A pending trust confirmation for a deferred tool call."""

  request_id: str
  server_id: str
  tool_name: str
  fingerprint_digest: str
  asked_at: int
  args_preview: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "request_id": self.request_id,
      "server_id": self.server_id,
      "tool_name": self.tool_name,
      "fingerprint_digest": self.fingerprint_digest,
      "asked_at": self.asked_at,
      "args_preview": self.args_preview,
    }


def _now() -> int:
  import time
  return int(time.time())


def ask_trust_before_tool(
  session_log: SessionLog,
  request_id: str,
  server_id: str,
  fingerprint: MCPServerFingerprint,
  tool_name: str,
  args_preview: dict[str, Any] | None = None,
) -> MCPTrustRequest:
  """Write an ``mcp/trust_asked`` event and return the request handle."""
  request = MCPTrustRequest(
    request_id=request_id,
    server_id=server_id,
    tool_name=tool_name,
    fingerprint_digest=fingerprint.digest,
    asked_at=_now(),
    args_preview=dict(args_preview or {}),
  )
  session_log.append(EventType.MCP_TRUST_ASKED, request.to_dict())
  return request


def decide_trust_for_tool(
  session_log: SessionLog,
  request: MCPTrustRequest,
  decision: str,
  *,
  reason: str = "",
  timestamp: int | None = None,
) -> dict[str, Any]:
  """Write an ``mcp/trust_decided`` event for a prior trust request."""
  if decision not in ("allow", "deny", "ask"):
    raise MCPTrustError(f"Invalid trust decision: {decision}", "INVALID_DECISION")
  payload = {
    "request_id": request.request_id,
    "server_id": request.server_id,
    "tool_name": request.tool_name,
    "fingerprint_digest": request.fingerprint_digest,
    "decision": decision,
    "reason": reason,
    "decided_at": timestamp or _now(),
  }
  session_log.append(EventType.MCP_TRUST_DECIDED, payload)
  return payload


def create_trust_store(base_dir: str | Path) -> MCPTrustStore:
  """Factory helper for tests and callers."""
  return MCPTrustStore(base_dir)
