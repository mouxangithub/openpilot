"""JSONL transcript storage with seq validation and resume."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ai.core.session.model import EventEnvelope, EventType, SessionHeader, SessionRecord
from ai.core.session.repair import repair_session_log


class TranscriptValidationError(ValueError):
    """Raised when transcript seq/session continuity is violated."""


class SessionStorage:
    """Manages session metadata and JSONL transcript files."""

    def __init__(self, sessions_dir: Path, transcripts_dir: Path) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.transcripts_dir = Path(transcripts_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_cwd(cls, cwd: str) -> SessionStorage:
        base = Path(cwd) / ".ai"
        return cls(base / "sessions", base / "transcripts")

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _transcript_path(self, session_id: str) -> Path:
        return self.transcripts_dir / f"{session_id}.jsonl"

    def create_session(
        self,
        cwd: str,
        title: str = "",
        parent_session: str = "",
        origin: str = "",
        delegation_depth: int = 0,
        agent_preset: str = "default",
    ) -> SessionRecord:
        record = SessionRecord.create(
            cwd=cwd,
            title=title,
            parent_session=parent_session,
            origin=origin,
            delegation_depth=delegation_depth,
            agent_preset=agent_preset,
        )
        self._write_record(record)
        self._write_header(record)
        return record

    def _write_record(self, record: SessionRecord) -> None:
        self._session_path(record.id).write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_header(self, record: SessionRecord) -> None:
        path = self._transcript_path(record.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        header_line = json.dumps(
            {
                "format_version": SessionHeader.SESSION_FORMAT_VERSION,
                "session_id": record.id,
                "header": record.header.to_dict(),
                "created_at": record.created_at,
            },
            ensure_ascii=False,
        )
        with path.open("w", encoding="utf-8") as f:
            f.write(header_line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def load_session(self, session_id: str) -> SessionRecord | None:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return SessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def append_event(self, record: SessionRecord, event_type: str, payload: dict[str, Any], ignorable: bool = False) -> EventEnvelope:
        sequence = record.bump_sequence()
        event_id = f"transcript:{record.id}:{sequence}"
        envelope = EventEnvelope(
            event_id=event_id,
            session_id=record.id,
            sequence=sequence,
            type=event_type,
            payload=dict(payload),
            ignorable=ignorable,
            recorded_at=_iso_now(),
        )
        envelope.validate_reserved_fields()
        self._append_line(record.id, envelope.to_dict())
        self._write_record(record)
        return envelope

    def _append_line(self, session_id: str, data: dict[str, Any]) -> None:
        path = self._transcript_path(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def read_transcript(self, record: SessionRecord, limit: int = 0) -> list[EventEnvelope]:
        path = self._transcript_path(record.id)
        if not path.exists():
            return []
        events: list[EventEnvelope] = []
        expected_session = record.id
        last_seq = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if data.get("format_version") is not None or data.get("formatVersion") is not None:
                    # Header line may carry the session id at top level.
                    header_session = data.get("session_id")
                    if header_session and header_session != expected_session:
                        raise TranscriptValidationError(f"Session mismatch: {header_session} != {expected_session}")
                    continue
                envelope = EventEnvelope.from_dict(data)
                # Tolerate legacy/header-style events that may omit session_id.
                if not envelope.session_id:
                    envelope.session_id = expected_session
                if envelope.session_id != expected_session:
                    raise TranscriptValidationError(f"Session mismatch: {envelope.session_id} != {expected_session}")
                # SessionLog events use seq starting at 0; storage events start at 1.
                # Normalize both to a 1-based counter for validation.
                seq = envelope.sequence
                if seq == 0:
                    events.append(envelope)
                    continue
                if seq != last_seq + 1:
                    raise TranscriptValidationError(f"Sequence gap: {last_seq} -> {seq}")
                last_seq = seq
                events.append(envelope)
        if limit > 0:
            events = events[-limit:]
        return events

    def repair_interrupted(self, record: SessionRecord) -> list[EventEnvelope]:
        """Placeholder repair: in production delegates to SessionLog repair."""
        events = self.read_transcript(record)
        closers: list[EventEnvelope] = []
        call_ids: set[str] = set()
        result_ids: set[str] = set()
        for ev in events:
            payload = ev.payload
            if ev.type == EventType.FUNCTION_CALL.value:
                call_ids.add(str(payload.get("call_id") or payload.get("callId") or ""))
            elif ev.type == EventType.FUNCTION_CALL_RESULT.value:
                result_ids.add(str(payload.get("tool_call_id") or payload.get("call_id") or payload.get("callId") or ""))
        for call_id in sorted(call_ids - result_ids):
            closers.append(self.append_event(
                record,
                EventType.FUNCTION_CALL_RESULT.value,
                {"tool_call_id": call_id, "content": "TOOL_OUTCOME_UNKNOWN", "errorCode": "TOOL_OUTCOME_UNKNOWN"},
                ignorable=True,
            ))
        return closers


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
