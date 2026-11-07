"""JSONL transcript replay helpers.

Read an event log from disk and return a list of in-memory events. Supports
forking (taking a prefix of events) so callers can branch a session at a
specific point.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai.core.session.log import EventType, SessionEvent, SurfaceOp


class ReplayError(ValueError):
  """Raised when a transcript cannot be replayed."""


def _event_from_dict(data: dict[str, Any]) -> SessionEvent:
  """Convert a serialized JSONL event dict into a SessionEvent."""
  try:
    event_type = EventType(data.get("type", ""))
  except ValueError as exc:
    raise ReplayError(f"Unknown event type: {data.get('type')}") from exc
  surface_op_raw = data.get("surfaceOp")
  surface_op = SurfaceOp(surface_op_raw) if surface_op_raw else None
  source_seqs_raw = data.get("sourceEventSeqs")
  source_seqs = tuple(source_seqs_raw) if isinstance(source_seqs_raw, list) else None
  return SessionEvent(
    type=event_type,
    seq=int(data.get("seq", 0)),
    time=int(data.get("time", 0)),
    data=data.get("data"),
    surface_op=surface_op,
    source_seqs=source_seqs,
  )


def read_jsonl_events(path: str | Path) -> list[SessionEvent]:
  """Read all events from a JSONL transcript file.

  Skips the format-version header line (any dict containing ``formatVersion``
  without a ``type`` key). Malformed lines are ignored so replay is tolerant.
  """
  events: list[SessionEvent] = []
  file_path = Path(path)
  if not file_path.is_file():
    return events
  with file_path.open("r", encoding="utf-8") as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      try:
        data = json.loads(line)
      except json.JSONDecodeError:
        continue
      if not isinstance(data, dict):
        continue
      # Header line: no "type" but has formatVersion.
      if "formatVersion" in data and "type" not in data:
        continue
      try:
        events.append(_event_from_dict(data))
      except ReplayError:
        continue
  return events


def replay_transcript(path: str | Path) -> list[SessionEvent]:
  """Alias for read_jsonl_events."""
  return read_jsonl_events(path)


def fork_transcript(
  path: str | Path,
  up_to_seq: int,
  *,
  inclusive: bool = True,
) -> list[SessionEvent]:
  """Return the prefix of a transcript up to a target sequence number.

  With ``inclusive=True`` (default) the returned list includes the event whose
  ``seq`` equals ``up_to_seq``. With ``inclusive=False`` it stops before that
  event.

  Raises ``ReplayError`` if the target sequence is not present and strict
  continuity is requested, but here we simply return everything up to (and
  optionally including) the requested seq.
  """
  events = read_jsonl_events(path)
  result: list[SessionEvent] = []
  for event in events:
    if event.seq < up_to_seq:
      result.append(event)
    elif inclusive and event.seq == up_to_seq:
      result.append(event)
    else:
      break
  return result


def fork_transcript_by_index(
  path: str | Path,
  count: int,
) -> list[SessionEvent]:
  """Return the first ``count`` events from a transcript."""
  events = read_jsonl_events(path)
  return events[:max(0, count)]


def events_to_dicts(events: list[SessionEvent]) -> list[dict[str, Any]]:
  """Serialize a list of SessionEvent objects to plain dicts."""
  return [event.to_dict() for event in events]
