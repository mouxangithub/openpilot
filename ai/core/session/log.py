"""Append-only session event log.

Inspired by dsh-session: the log is the single source of truth for model
history. Every model-visible fact is an event; UI and replay derive from it.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable



class EventType(StrEnum):
  TURN_START = "turn/start"
  TURN_END = "turn/end"
  STEP_START = "step/start"
  STEP_END = "step/end"
  USER_MESSAGE = "user/message"
  ASSISTANT_CHUNK = "assistant/chunk"
  ASSISTANT_MESSAGE = "assistant/message"
  TOOL_CALL = "tool/call"
  TOOL_RESULT = "tool/result"
  FUNCTION_CALL = "function_call"
  FUNCTION_CALL_RESULT = "function_call_result"
  REQUEST_HEADER = "request/header"
  REQUEST_CONTEXT = "request/context"
  LIFECYCLE = "lifecycle"
  GOAL_CHANGE = "goal/change"
  PLAN_CHANGE = "plan/change"
  TODO_CHANGE = "todo/change"
  COMPACTION_PRUNE = "compaction/prune"
  SUBAGENT_START = "subagent/start"
  SUBAGENT_END = "subagent/end"
  SCHEDULE_CHANGE = "schedule/change"
  COMMAND_RUN = "command/run"
  COMMAND_DONE = "command/done"
  MCP_TRUST_ASKED = "mcp/trust_asked"
  MCP_TRUST_DECIDED = "mcp/trust_decided"


class SurfaceOp(StrEnum):
  APPEND = "append"
  REPLACE = "replace"


class TurnEndKind(StrEnum):
  COMPLETED = "completed"
  ABORTED = "aborted"
  BLOCKED = "blocked"
  ERROR = "error"
  MAX_TOKENS = "max-tokens"


class CancelCauseKind(StrEnum):
  USER = "user"
  PARENT = "parent"
  HOOK = "hook"
  DISPOSED = "disposed"


# Version of the persisted JSONL format. Bumped only on wire-breaking changes;
# loaders must keep accepting older versions (see _load_from_disk).
SESSION_FORMAT_VERSION = (1, 0)
SESSION_FORMAT_VERSION_STR = ".".join(str(p) for p in SESSION_FORMAT_VERSION)
SESSION_HEADER_KEY = "formatVersion"
SESSION_SCHEMA = "session/event-log"

# Events that produce model-visible history and MUST carry a surface marker.
# (baseline surface.ts eligibility rule).
SURFACE_REQUIRED_EVENTS = frozenset({
  EventType.USER_MESSAGE,
  EventType.ASSISTANT_MESSAGE,
  EventType.TOOL_RESULT,
})


class SurfaceValidationError(ValueError):
  """Raised by the strict surface fold when an event violates the session protocol."""


@dataclass(frozen=True)
class SessionHeader:
  """Session-level metadata recorded in the persisted log header (optional).

  Mirrors the baseline SessionHeader fields. None keeps the field out of the
  wire format so old logs that never wrote a header remain valid.
  """

  provider: str = ""
  model: str = ""
  cwd: str | None = None
  parent_session: str | None = None
  seed_length: int | None = None
  origin: str | None = None
  delegation_depth: int | None = None
  agent_preset: str | None = None

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {"provider": self.provider, "model": self.model}
    fields = {
      "cwd": self.cwd,
      "parentSession": self.parent_session,
      "seedLength": self.seed_length,
      "origin": self.origin,
      "delegationDepth": self.delegation_depth,
      "agentPreset": self.agent_preset,
    }
    for key, value in fields.items():
      if value is not None:
        out[key] = value
    return out

  @staticmethod
  def from_dict(data: dict[str, Any]) -> SessionHeader:
    return SessionHeader(
      provider=str(data.get("provider", "")),
      model=str(data.get("model", "")),
      cwd=data.get("cwd"),
      parent_session=data.get("parentSession"),
      seed_length=data.get("seedLength"),
      origin=data.get("origin"),
      delegation_depth=data.get("delegationDepth"),
      agent_preset=data.get("agentPreset"),
    )


@dataclass(frozen=True)
class CancelCause:
  kind: CancelCauseKind
  reason: str = ""

  def to_dict(self) -> dict[str, Any]:
    return {"kind": self.kind.value, "reason": self.reason}


@dataclass(frozen=True)
class RequestHeader:
  provider: str
  model: str
  system: str | None = None
  tools: list[dict[str, Any]] | None = None
  reasoning_effort: str | None = None
  max_tokens: int | None = None

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {"provider": self.provider, "model": self.model}
    if self.system is not None:
      out["system"] = self.system
    if self.tools is not None:
      out["tools"] = self.tools
    if self.reasoning_effort is not None:
      out["reasoningEffort"] = self.reasoning_effort
    if self.max_tokens is not None:
      out["maxTokens"] = self.max_tokens
    return out

  @staticmethod
  def from_dict(data: dict[str, Any]) -> RequestHeader:
    return RequestHeader(
      provider=str(data.get("provider", "")),
      model=str(data.get("model", "")),
      system=data.get("system"),
      tools=data.get("tools"),
      reasoning_effort=data.get("reasoningEffort"),
      max_tokens=data.get("maxTokens"),
    )

  def equals(self, other: RequestHeader) -> bool:
    return (
      self.provider == other.provider
      and self.model == other.model
      and self.system == other.system
      and _json_eq(self.tools, other.tools)
      and self.reasoning_effort == other.reasoning_effort
      and self.max_tokens == other.max_tokens
    )


def _json_eq(a: Any, b: Any) -> bool:
  return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _lossless_json(value: Any) -> Any:
  """Return a deep copy if value is losslessly JSON-serializable, else raise."""
  # Use json round-trip as a cheap lossless check.
  try:
    return json.loads(json.dumps(value, default=_raise_non_json))
  except (TypeError, ValueError) as e:
    raise ValueError(f"value is not losslessly JSON-serializable: {e}") from e


def _raise_non_json(_obj: Any) -> None:
  raise TypeError("non-JSON-serializable value")


def _deep_freeze(value: Any) -> Any:
  if isinstance(value, dict):
    return type(value)((k, _deep_freeze(v)) for k, v in value.items())
  if isinstance(value, list):
    return type(value)(_deep_freeze(v) for v in value)
  if isinstance(value, tuple):
    return tuple(_deep_freeze(v) for v in value)
  return value


@dataclass(frozen=True)
class SessionEvent:
  type: EventType
  seq: int
  time: int
  data: Any
  surface_op: SurfaceOp | None = None
  source_seqs: tuple[int, ...] | None = None

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {
      "type": self.type.value,
      "seq": self.seq,
      "time": self.time,
      "data": self.data,
    }
    if self.surface_op is not None:
      out["surfaceOp"] = self.surface_op.value
    if self.source_seqs is not None:
      out["sourceEventSeqs"] = list(self.source_seqs)
    return out


@dataclass
class SurfaceNode:
  seq: int
  event_type: EventType
  data: Any


class SessionLog:
  """Append-only event log for one session.

  Events are kept in memory and optionally mirrored to a JSONL file.
  Loading from disk is opt-in so consumers that only need the current
  process history are not surprised by stale events.
  """

  def __init__(
    self,
    session_id: str,
    seed: list[SessionEvent] | None = None,
    *,
    persist_path: str | Path | None = None,
    load_persisted: bool = False,
    strict: bool = False,
    header: SessionHeader | None = None,
  ) -> None:
    self.session_id = session_id
    self._strict = strict
    self._events: list[SessionEvent] = []
    self._surface: list[SurfaceNode] = []
    self._header: RequestHeader | None = None
    self._context: dict[str, Any] | None = None
    self._persist_path = Path(persist_path) if persist_path else None
    self._persist_file: Any = None
    self._session_header = header
    self.version: str | None = None  # parsed from disk header (None => legacy log)
    if load_persisted and self._persist_path is not None and self._persist_path.is_file():
      self._load_from_disk()
    if self._persist_path is not None:
      try:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_file = open(self._persist_path, "a", encoding="utf-8")
        if self._persist_file.tell() == 0:
          # Fresh file: write the format version header once, before any event.
          meta = self._session_header.to_dict() if self._session_header is not None else {}
          self._persist_file.write(_format_header_line(meta) + "\n")
          self._persist_file.flush()
          if self.version is None:
            self.version = SESSION_FORMAT_VERSION_STR
      except Exception:
        self._persist_file = None
    if seed:
      for ev in seed:
        self.append(ev.type, ev.data, surface_op=ev.surface_op, source_seqs=ev.source_seqs)

  @property
  def events(self) -> tuple[SessionEvent, ...]:
    return tuple(self._events)

  @property
  def persist_path(self) -> Path | None:
    return self._persist_path

  def append_domain_event(self, domain: str, snapshot: Any, *, tombstone: bool = False) -> SessionEvent:
    event_type = EventType(f"{domain}/change")
    return self.append(event_type, {"snapshot": snapshot, "tombstone": tombstone})

  def derive_domain_state(self) -> dict[str, Any]:
    from ai.core.session.folds import fold_domain_events
    return fold_domain_events(self._events)

  @property
  def surface(self) -> tuple[SurfaceNode, ...]:
    return tuple(self._surface)

  @property
  def seq(self) -> int:
    return len(self._events)

  def append(
    self,
    event_type: EventType,
    data: Any,
    *,
    surface_op: SurfaceOp | None = None,
    source_seqs: tuple[int, ...] | list[int] | None = None,
  ) -> SessionEvent:
    cleaned = _lossless_json(data)
    event = SessionEvent(
      type=event_type,
      seq=self.seq,
      time=int(time.monotonic() * 1000),
      data=_deep_freeze(cleaned),
      surface_op=surface_op,
      source_seqs=tuple(source_seqs) if source_seqs is not None else None,
    )
    if self._strict:
      validate_surface_event(event, next_seq=self.seq)
      if event.surface_op == SurfaceOp.REPLACE:
        _validate_replace_target(self._surface, event)
    self._events.append(event)
    if surface_op is not None:
      self._apply_surface(event)
    if event_type == EventType.REQUEST_HEADER:
      self._fold_header(cleaned)
    if event_type == EventType.REQUEST_CONTEXT:
      self._context = dict(cleaned)
    self._persist_event(event)
    return event

  def _persist_event(self, event: SessionEvent) -> None:
    if self._persist_file is None:
      return
    try:
      self._persist_file.write(json.dumps(event.to_dict(), ensure_ascii=False, default=str) + "\n")
      self._persist_file.flush()
    except Exception:
      pass

  def _load_from_disk(self) -> None:
    if self._persist_path is None or not self._persist_path.is_file():
      return
    with open(self._persist_path, "r", encoding="utf-8") as f:
      for line in f:
        line = line.strip()
        if not line:
          continue
        try:
          data = json.loads(line)
        except json.JSONDecodeError as e:
          if self._strict:
            raise SurfaceValidationError(f"invalid JSONL line: {e}") from e
          continue
        if not isinstance(data, dict):
          if self._strict:
            raise SurfaceValidationError("expected a JSON object per line")
          continue
        # Version/header line: no "type" key, carries formatVersion.
        if SESSION_HEADER_KEY in data and "type" not in data:
          self.version = str(data.get(SESSION_HEADER_KEY))
          if self._session_header is None:
            self._session_header = SessionHeader.from_dict(
              {k: v for k, v in data.items() if k not in (SESSION_HEADER_KEY, "schema")}
            )
          continue
        try:
          ev_type = EventType(data.get("type", ""))
        except ValueError as e:
          if self._strict:
            raise SurfaceValidationError(f"unknown event type: {e}") from e
          continue
        surface_op = data.get("surfaceOp")
        source_seqs = data.get("sourceEventSeqs")
        # P0 harness storage writes events with payload in "payload"; dsh-style
        # storage uses "data". Normalize both keys.
        event_data = data.get("data")
        if event_data is None:
          event_data = data.get("payload")
        self.append(
          ev_type,
          event_data,
          surface_op=SurfaceOp(surface_op) if surface_op else None,
          source_seqs=tuple(source_seqs) if isinstance(source_seqs, list) else None,
        )

  def close(self) -> None:
    if self._persist_file is not None:
      try:
        self._persist_file.close()
      except Exception:
        pass
      self._persist_file = None

  def __del__(self) -> None:
    self.close()

  def reset(self) -> None:
    """Clear in-memory events and reload from disk on next access."""
    self.close()
    self._events.clear()
    self._surface.clear()
    if self._persist_path is not None and self._persist_path.is_file():
      self._load_from_disk()
    # Reopen append handle.
    if self._persist_path is not None:
      try:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_file = open(self._persist_path, "a", encoding="utf-8")
      except Exception:
        self._persist_file = None

  def _apply_surface(self, event: SessionEvent) -> None:
    _fold_one(self._surface, event)

  def _fold_header(self, data: Any) -> None:
    header_data = data.get("header") if isinstance(data, dict) else data
    if not isinstance(header_data, dict):
      return
    candidate = RequestHeader.from_dict(header_data)
    if self._header is None or not self._header.equals(candidate):
      self._header = candidate

  def request_header(self) -> RequestHeader | None:
    return copy.deepcopy(self._header)

  def request_context(self) -> dict[str, Any] | None:
    return copy.deepcopy(self._context) if self._context else None

  def session_header(self) -> SessionHeader | None:
    return copy.deepcopy(self._session_header)

  def derive_messages(self) -> list[dict[str, Any]]:
    """Derive OpenAI-style message history from the surface."""
    messages: list[dict[str, Any]] = []
    for node in self._surface:
      if node.event_type == EventType.USER_MESSAGE:
        messages.append(_project_user(node.data))
      elif node.event_type == EventType.ASSISTANT_MESSAGE:
        messages.append(_project_assistant(node.data))
      elif node.event_type == EventType.TOOL_RESULT:
        messages.append(_project_tool_result(node.data))
    return messages

  def last_assistant(self) -> dict[str, Any] | None:
    for node in reversed(self._surface):
      if node.event_type == EventType.ASSISTANT_MESSAGE:
        return _project_assistant(node.data)
    return None


def project_domain_state(events: list[SessionEvent]) -> dict[str, Any]:
  """Legacy inline fold kept for compatibility; prefer folds.fold_domain_events."""
  from ai.core.session.folds import fold_domain_events
  return fold_domain_events(events)


def _project_user(data: Any) -> dict[str, Any]:
  if isinstance(data, dict):
    return {"role": "user", "content": data.get("content", "")}
  return {"role": "user", "content": str(data)}


def _project_assistant(data: Any) -> dict[str, Any]:
  if not isinstance(data, dict):
    return {"role": "assistant", "content": str(data)}
  content = data.get("content", "")
  tool_calls = data.get("tool_calls")
  msg: dict[str, Any] = {"role": "assistant"}
  if content:
    msg["content"] = content
  if tool_calls:
    msg["tool_calls"] = tool_calls
  return msg


def _project_tool_result(data: Any) -> dict[str, Any]:
  if isinstance(data, dict):
    return {
      "role": "tool",
      "tool_call_id": data.get("tool_call_id", ""),
      "content": data.get("content", ""),
    }
  return {"role": "tool", "tool_call_id": "", "content": str(data)}


def _replace_target_indices(surface: list[SurfaceNode], event: SessionEvent) -> list[int]:
  """Locate the surface slots a REPLACE event shadows.

  Prefers provenance (source_event_seqs); falls back to the legacy start/end
  data range so pre-existing logs keep replaying unchanged. Returns an empty
  list when no contiguous target can be resolved.
  """
  if event.source_seqs:
    target = {node.seq for node in surface}
    wanted = set(event.source_seqs)
    if wanted <= target:
      indices = [i for i, node in enumerate(surface) if node.seq in wanted]
      indices.sort()
      if indices and indices == list(range(indices[0], indices[-1] + 1)):
        return indices
  if isinstance(event.data, dict):
    start = event.data.get("start")
    end = event.data.get("end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end < len(surface):
      return list(range(start, end + 1))
  return []


def _validate_replace_target(surface: list[SurfaceNode], event: SessionEvent) -> None:
  """Strict: a tool/result REPLACE must shadow a node with the same tool_call_id."""
  indices = _replace_target_indices(surface, event)
  if not indices:
    raise SurfaceValidationError(
      f"REPLACE {event.type.value} resolves no shadowed surface slot"
    )
  if event.type == EventType.TOOL_RESULT:
    new_id = event.data.get("tool_call_id") if isinstance(event.data, dict) else None
    for i in indices:
      old_data = surface[i].data if isinstance(surface[i].data, dict) else {}
      if old_data.get("tool_call_id") != new_id:
        raise SurfaceValidationError(
          "tool/result REPLACE may only change content, not the target tool_call_id"
        )


def _fold_one(surface: list[SurfaceNode], event: SessionEvent) -> None:
  """Apply a single surface event. Legacy behavior: unresolved REPLACE appends."""
  if event.surface_op == SurfaceOp.APPEND:
    surface.append(SurfaceNode(seq=event.seq, event_type=event.type, data=event.data))
    return
  if event.surface_op == SurfaceOp.REPLACE:
    indices = _replace_target_indices(surface, event)
    if indices:
      surface[indices[0]:indices[-1] + 1] = [
        SurfaceNode(seq=event.seq, event_type=event.type, data=event.data)
      ]
    else:
      surface.append(SurfaceNode(seq=event.seq, event_type=event.type, data=event.data))


def _format_header_line(meta: dict[str, Any] | None = None) -> str:
  """Serialize the JSONL format-version header line (distinct from event lines)."""
  row: dict[str, Any] = {
    SESSION_HEADER_KEY: SESSION_FORMAT_VERSION_STR,
    "schema": SESSION_SCHEMA,
  }
  if meta:
    row.update(meta)
  return json.dumps(row, ensure_ascii=False, sort_keys=True)


def validate_surface_event(event: SessionEvent, next_seq: int) -> None:
  """Strict per-event structural surface validation (baseline surface.ts).

  Rules enforced here are surface-independent:
   - seq must be continuous (== next_seq).
   - message-producing events must carry an explicit surface marker.
   - REPLACE must reference shadowed seqs via sourceEventSeqs.

  Replace target-aware checks (tool_call_id stability) are applied by
  fold_surface via _validate_replace_target, which has the surface context.

  Raises SurfaceValidationError on violation; otherwise returns None.
  """
  if event.seq != next_seq:
    raise SurfaceValidationError(
      f"surface seq discontinuity: expected {next_seq}, got {event.seq}"
    )
  if event.type in SURFACE_REQUIRED_EVENTS and event.surface_op is None:
    raise SurfaceValidationError(
      f"{event.type.value} must carry a surface marker (surface_op)"
    )
  if event.surface_op == SurfaceOp.REPLACE and not event.source_seqs:
    raise SurfaceValidationError(
      f"REPLACE {event.type.value} must reference shadowed seqs via sourceEventSeqs"
    )


def fold_surface(
  events: Iterable[SessionEvent],
  *,
  surface: list[SurfaceNode] | None = None,
  strict: bool = False,
) -> list[SurfaceNode]:
  """Fold events into a surface list.

  strict=True validates every event (continuous seq, surface markers, replace
  provenance, tool_call_id stability on tool/result REPLACE) and raises on any
  violation. With strict=False the fold mirrors the legacy append-only behavior
  so old logs keep loading unchanged.
  """
  result: list[SurfaceNode] = list(surface) if surface is not None else []
  next_seq = 0
  for event in events:
    if strict:
      validate_surface_event(event, next_seq)
      if event.surface_op == SurfaceOp.REPLACE:
        _validate_replace_target(result, event)
    _fold_one(result, event)
    next_seq += 1
  return result


@dataclass
class SessionStore:
  """In-memory store of session logs. Disk persistence is handled by SessionLog."""

  _sessions: dict[str, SessionLog] = field(default_factory=dict)

  def get_or_create(
    self,
    session_id: str,
    seed: list[SessionEvent] | None = None,
    *,
    load_persisted: bool = False,
  ) -> SessionLog:
    if session_id not in self._sessions:
      self._sessions[session_id] = SessionLog(session_id, seed=seed, load_persisted=load_persisted)
    return self._sessions[session_id]

  def get(self, session_id: str) -> SessionLog | None:
    return self._sessions.get(session_id)

  def remove(self, session_id: str) -> None:
    self._sessions.pop(session_id, None)


_global_store: SessionStore | None = None


def get_session_store() -> SessionStore:
  global _global_store
  if _global_store is None:
    _global_store = SessionStore()
  return _global_store
