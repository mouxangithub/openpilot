"""AgentRegistry — unified lifecycle facade for agent sessions.

Aligns with deepseek-harness' Agent Factory / Registry split: the Agent class
stays the turn/step engine, while this registry owns creation bookkeeping,
active-session discovery and cancellation — without forcing a rewrite of
existing entry points (``run_chat_loop`` / ``Agent``).

Pattern: module-level singleton ``agent_registry``. Every ``create`` /
``resume`` call registers an entry; ``mark_done`` unregisters it. An optional
``cancel_fn`` per entry lets the registry cancel live work by session id.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEntry:
  session_id: str
  agent_id: str
  job_id: str = ""
  created_at: float = field(default_factory=time.time)
  status: str = "running"  # running | done | error | cancelled
  meta: dict[str, Any] = field(default_factory=dict)
  cancel_fn: Callable[[], Awaitable[bool]] | None = None


class AgentRegistry:
  """In-process registry of live agent sessions."""

  def __init__(self) -> None:
    self._entries: dict[str, AgentEntry] = {}
    self._lock = threading.RLock()

  def create(
    self,
    session_id: str,
    agent_id: str,
    *,
    job_id: str = "",
    meta: dict[str, Any] | None = None,
    cancel_fn: Callable[[], Awaitable[bool]] | None = None,
  ) -> AgentEntry:
    key = session_id or f"anon-{agent_id}"
    entry = AgentEntry(
      session_id=session_id,
      agent_id=agent_id,
      job_id=job_id,
      meta=dict(meta or {}),
      cancel_fn=cancel_fn,
    )
    with self._lock:
      self._entries[key] = entry
    return entry

  def resume(
    self,
    session_id: str,
    agent_id: str,
    *,
    job_id: str = "",
    meta: dict[str, Any] | None = None,
    cancel_fn: Callable[[], Awaitable[bool]] | None = None,
  ) -> AgentEntry:
    """Resume an existing entry (re-register with fresh status) or create one."""
    key = session_id or f"anon-{agent_id}"
    with self._lock:
      existing = self._entries.get(key)
    if existing is not None:
      existing.status = "running"
      existing.job_id = job_id
      if cancel_fn is not None:
        existing.cancel_fn = cancel_fn
      return existing
    return self.create(session_id, agent_id, job_id=job_id, meta=meta, cancel_fn=cancel_fn)

  def mark_done(self, session_id: str, status: str = "done") -> None:
    key = session_id or ""
    with self._lock:
      entry = self._entries.get(key)
      if entry is not None:
        entry.status = status

  def get(self, session_id: str) -> AgentEntry | None:
    with self._lock:
      return self._entries.get(session_id or "")

  def list(self, *, active_only: bool = True) -> list[dict[str, Any]]:
    with self._lock:
      entries = list(self._entries.values())
    out = []
    for e in entries:
      if active_only and e.status != "running":
        continue
      out.append({
        "sessionId": e.session_id,
        "agentId": e.agent_id,
        "jobId": e.job_id,
        "status": e.status,
        "createdAt": e.created_at,
        "meta": e.meta,
      })
    return out

  async def cancel_session(self, session_id: str) -> bool:
    with self._lock:
      entry = self._entries.get(session_id or "")
    if entry is None:
      return False
    if entry.cancel_fn is not None:
      try:
        ok = await entry.cancel_fn()
      except Exception:
        ok = False
    else:
      ok = True
    entry.status = "cancelled" if ok else entry.status
    return ok

  def clear(self) -> None:
    with self._lock:
      self._entries.clear()


agent_registry = AgentRegistry()
