"""SessionManager create/resume/close."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
import time
from typing import Any

from ai.core.session.log import EventType, SessionLog
from ai.core.session.model import SessionHeader, SessionRecord
from ai.core.session.storage import SessionStorage


class SessionLifecycleState(StrEnum):
  """High-level session lifecycle states."""

  PENDING = "pending"
  ACTIVE = "active"
  PAUSED = "paused"
  DISPOSED = "disposed"


class SessionManager:
  """High-level session lifecycle manager."""

  def __init__(self, cwd: str, audit: Any = None) -> None:
    self.cwd = cwd
    self.storage = SessionStorage.for_cwd(cwd)
    if audit is not None:
      self.storage._audit = audit
    self._states: dict[str, SessionLifecycleState] = {}
    self._logs: dict[str, SessionLog] = {}

  def _state(self, session_id: str) -> SessionLifecycleState:
    return self._states.get(session_id, SessionLifecycleState.PENDING)

  def _set_state(self, session_id: str, state: SessionLifecycleState) -> None:
    self._states[session_id] = state

  def _get_or_create_log(self, record: SessionRecord) -> SessionLog:
    """Return a SessionLog for the record, creating it if necessary."""
    log = self._logs.get(record.id)
    if log is None:
      transcript_path = self.storage._transcript_path(record.id)
      log = SessionLog(
        session_id=record.id,
        persist_path=transcript_path,
        load_persisted=True,
      )
      # Sync the in-memory record counter with the number of events already on
      # disk so future storage.append_event calls continue the sequence.
      record.seq_counter = max(record.seq_counter, log.seq)
      self._logs[record.id] = log
    return log

  def create_session(
    self,
    title: str = "",
    origin: str = "",
    parent_session: str = "",
  ) -> SessionRecord:
    """Create a new session and write a lifecycle event."""
    record = self.storage.create_session(
      cwd=self.cwd,
      title=title,
      origin=origin,
      parent_session=parent_session,
    )
    self._set_state(record.id, SessionLifecycleState.ACTIVE)
    log = self._get_or_create_log(record)
    log.append(
      EventType.LIFECYCLE,
      {
        "state": SessionLifecycleState.ACTIVE.value,
        "previous_state": SessionLifecycleState.PENDING.value,
        "action": "create_session",
        "cwd": self.cwd,
        "title": title,
        "origin": origin,
        "parent_session": parent_session,
      },
    )
    log.close()
    return record

  def pause_session(self, session_id: str) -> SessionRecord | None:
    """Pause a session: stop processing but keep resources."""
    record = self.storage.load_session(session_id)
    if record is None:
      return None
    previous = self._state(session_id)
    if previous == SessionLifecycleState.DISPOSED:
      return record
    self._set_state(session_id, SessionLifecycleState.PAUSED)
    log = self._get_or_create_log(record)
    log.append(
      EventType.LIFECYCLE,
      {
        "state": SessionLifecycleState.PAUSED.value,
        "previous_state": previous.value,
        "action": "pause_session",
      },
    )
    return record

  def resume_session(self, session_id: str) -> tuple[SessionRecord | None, list[dict[str, Any]]]:
    """Resume a paused session and repair any interrupted transcript."""
    record = self.storage.load_session(session_id)
    if record is None:
      return None, []
    previous = self._state(session_id)
    if previous == SessionLifecycleState.DISPOSED:
      return record, []
    # D-P0.5: refuse to reuse a session that belongs to a different context
    # (subagent origin / parent lineage / non-default preset / cwd mismatch).
    from ai.core.session.adopt import check_adoptable
    adopt = check_adoptable(record.header, session_id=session_id, cwd=self.cwd)
    if not adopt.ok:
      return record, []
    log = self._get_or_create_log(record)
    # Reload from disk in case storage.append_event wrote events outside this log.
    log.reset()
    from ai.core.session.repair import repair_session_log
    repaired = repair_session_log(log)
    # Sync the record counter with the repaired log so the next storage append
    # continues the sequence instead of colliding with repair events.
    record.seq_counter = max(record.seq_counter, log.seq)
    self.storage._write_record(record)
    self._set_state(session_id, SessionLifecycleState.ACTIVE)
    log.append(
      EventType.LIFECYCLE,
      {
        "state": SessionLifecycleState.ACTIVE.value,
        "previous_state": previous.value,
        "action": "resume_session",
      },
    )
    log.close()
    return record, [ev.to_dict() for ev in repaired]

  def dispose_session(self, session_id: str) -> bool:
    """Dispose a session and close its log."""
    record = self.storage.load_session(session_id)
    if record is None:
      return False
    previous = self._state(session_id)
    self._set_state(session_id, SessionLifecycleState.DISPOSED)
    log = self._logs.pop(session_id, None)
    if log is not None:
      log.append(
        EventType.LIFECYCLE,
        {
          "state": SessionLifecycleState.DISPOSED.value,
          "previous_state": previous.value,
          "action": "dispose_session",
        },
      )
      log.close()
    return True

  # Backward-compatible aliases.
  def create(self, title: str = "", origin: str = "", parent_session: str = "") -> SessionRecord:
    return self.create_session(title=title, origin=origin, parent_session=parent_session)

  def get_or_create(self, session_id: str, *, cwd: str = "") -> SessionRecord:
    if session_id:
      existing = self.storage.load_session(session_id)
      if existing is not None:
        if session_id not in self._states:
          self._set_state(session_id, SessionLifecycleState.ACTIVE)
        return existing
    return self.create_session(title="Resumed session")

  def resume(self, session_id: str) -> tuple[SessionRecord, list[dict[str, Any]]]:
    record, repaired = self.resume_session(session_id)
    if record is None:
      record = self.create_session(title="Resumed session")
    return record, repaired

  def adopt_session(self, session_id: str, title: str = "") -> SessionRecord:
    """Adopt an externally-created session (e.g. from /api/ai/chat log).

    Writes a metadata record with the given id so lifecycle operations such
    as pause/dispose can manage it without requiring a prior create_session.
    """
    record = SessionRecord(
      id=session_id,
      cwd=self.cwd,
      title=title or "Adopted session",
      header=SessionHeader(cwd=self.cwd),
      created_at=int(time.time()),
      updated_at=int(time.time()),
    )
    self.storage._write_record(record)
    self._set_state(session_id, SessionLifecycleState.ACTIVE)
    return record

  def close(self, session_id: str) -> bool:
    """Backwards-compatible close: dispose if active."""
    return self.dispose_session(session_id)
