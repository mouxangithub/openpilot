"""Session event protocol models."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


SESSION_FORMAT_VERSION: str = "1"


class EventType(str, Enum):
    MESSAGE = "message"
    REASONING = "reasoning"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_RESULT = "function_call_result"
    STEP_END = "step_end"
    TURN_END = "turn_end"
    FILE_SNAPSHOT = "file_snapshot"
    AI_TITLE = "ai_title"
    REPAIR = "repair"


class SurfaceOperation(str, Enum):
    APPEND = "APPEND"
    REPLACE = "REPLACE"


@dataclass
class SessionHeader:
    """Immutable session metadata written once at session creation."""

    SESSION_FORMAT_VERSION: str = SESSION_FORMAT_VERSION
    cwd: str = ""
    parent_session: str = ""
    seed_length: int = 0
    origin: str = ""
    delegation_depth: int = 0
    agent_preset: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "SESSION_FORMAT_VERSION": self.SESSION_FORMAT_VERSION,
            "cwd": self.cwd,
            "parent_session": self.parent_session,
            "seed_length": self.seed_length,
            "origin": self.origin,
            "delegation_depth": self.delegation_depth,
            "agent_preset": self.agent_preset,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionHeader:
        return cls(
            SESSION_FORMAT_VERSION=str(data.get("SESSION_FORMAT_VERSION", SESSION_FORMAT_VERSION)),
            cwd=str(data.get("cwd", "")),
            parent_session=str(data.get("parent_session", "")),
            seed_length=int(data.get("seed_length", 0)),
            origin=str(data.get("origin", "")),
            delegation_depth=int(data.get("delegation_depth", 0)),
            agent_preset=str(data.get("agent_preset", "default")),
        )


@dataclass
class SessionRecord:
    """Runtime handle for a session."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cwd: str = ""
    title: str = ""
    header: SessionHeader = field(default_factory=SessionHeader)
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    seq_counter: int = 0

    @classmethod
    def create(
        cls,
        cwd: str,
        title: str = "",
        parent_session: str = "",
        origin: str = "",
        delegation_depth: int = 0,
        agent_preset: str = "default",
    ) -> SessionRecord:
        header = SessionHeader(
            cwd=cwd,
            parent_session=parent_session or "",
            seed_length=0,
            origin=origin or "",
            delegation_depth=delegation_depth,
            agent_preset=agent_preset,
        )
        return cls(
            id=uuid.uuid4().hex,
            cwd=cwd,
            title=title or "Untitled session",
            header=header,
            created_at=int(time.time()),
            updated_at=int(time.time()),
            seq_counter=0,
        )

    def bump_sequence(self) -> int:
        self.seq_counter += 1
        self.updated_at = int(time.time())
        return self.seq_counter

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cwd": self.cwd,
            "title": self.title,
            "header": self.header.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "seq_counter": self.seq_counter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionRecord:
        return cls(
            id=str(data.get("id", uuid.uuid4().hex)),
            cwd=str(data.get("cwd", "")),
            title=str(data.get("title", "Untitled session")),
            header=SessionHeader.from_dict(data.get("header") or {}),
            created_at=int(data.get("created_at", 0)),
            updated_at=int(data.get("updated_at", 0)),
            seq_counter=int(data.get("seq_counter", 0)),
        )


@dataclass
class EventEnvelope:
    """A single transcript event."""

    event_id: str = ""
    session_id: str = ""
    sequence: int = 0
    type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    ignorable: bool = False
    recorded_at: str = ""

    RESERVED_FIELDS: set[str] = field(
        default_factory=lambda: {"event_id", "session_id", "sequence", "type", "recorded_at"},
        repr=False,
    )

    def validate_reserved_fields(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if not self.session_id:
            raise ValueError("session_id is required")
        if self.sequence <= 0:
            raise ValueError("sequence must be positive")
        if not self.type:
            raise ValueError("type is required")
        if not self.recorded_at:
            raise ValueError("recorded_at is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "type": self.type,
            "payload": dict(self.payload),
            "ignorable": self.ignorable,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventEnvelope:
        # SessionLog uses "seq"; storage uses "sequence". Accept both.
        seq = data.get("sequence")
        if seq is None:
            seq = data.get("seq", 0)
        return cls(
            event_id=str(data.get("event_id", "")),
            session_id=str(data.get("session_id", "")),
            sequence=int(seq),
            type=str(data.get("type", "")),
            payload=dict(data.get("payload") or data.get("data") or {}),
            ignorable=bool(data.get("ignorable", False)),
            recorded_at=str(data.get("recorded_at", "")),
        )
