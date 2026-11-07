"""Durable schedule store with strict validation and event-sink projection."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

MIN_EVERY_INTERVAL_SECONDS = 300
_VALID_KINDS = ("after", "at", "every")

SinkFn = Callable[[dict[str, Any]], None]


class ScheduleInputError(Exception):
  """Typed rejection: the create/delete request violated a schedule invariant."""

  def __init__(self, code: str, message: str) -> None:
    super().__init__(message)
    self.code = code

  def to_dict(self) -> dict[str, Any]:
    return {"ok": False, "error": str(self), "error_code": self.code}


def _now_iso(now: datetime | None = None) -> str:
  return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: str) -> datetime:
  try:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
  except (ValueError, AttributeError) as exc:
    raise ScheduleInputError("invalid_at", f"schedule 'at' must be an RFC 3339 UTC instant, got {value!r}") from exc


def _is_safe_positive_int(value: Any) -> bool:
  return isinstance(value, int) and not isinstance(value, bool) and value > 0


class ScheduleRecord:
  def __init__(
    self,
    *,
    id: str,
    kind: str,
    prompt: str,
    scheduled_at: str,
    after_seconds: int | None = None,
    every_seconds: int | None = None,
    created_at: str = "",
  ) -> None:
    self.id = id
    self.kind = kind
    self.prompt = prompt
    self.scheduled_at = scheduled_at
    self.after_seconds = after_seconds
    self.every_seconds = every_seconds
    self.created_at = created_at

  def to_dict(self) -> dict[str, Any]:
    out: dict[str, Any] = {
      "id": self.id,
      "kind": self.kind,
      "prompt": self.prompt,
      "scheduledAt": self.scheduled_at,
      "createdAt": self.created_at,
    }
    if self.after_seconds is not None:
      out["afterSeconds"] = self.after_seconds
    if self.every_seconds is not None:
      out["everySeconds"] = self.every_seconds
    return out

  @staticmethod
  def from_dict(data: dict[str, Any]) -> ScheduleRecord:
    return ScheduleRecord(
      id=str(data.get("id") or ""),
      kind=str(data.get("kind") or ""),
      prompt=str(data.get("prompt") or ""),
      scheduled_at=str(data.get("scheduledAt") or ""),
      after_seconds=data.get("afterSeconds"),
      every_seconds=data.get("everySeconds"),
      created_at=str(data.get("createdAt") or ""),
    )


class ScheduleStore:
  """JSON-persisted reminder records; one optional event sink projection."""

  def __init__(self, base_dir: Path | str) -> None:
    self.base_dir = Path(base_dir)
    self.base_dir.mkdir(parents=True, exist_ok=True)
    self._path = self.base_dir / "schedules.json"
    self._lock = threading.Lock()
    self._event_sink: SinkFn | None = None
    self._counter = 0

  # -- sink -----------------------------------------------------------------

  def set_event_sink(self, sink: SinkFn | None) -> None:
    self._event_sink = sink

  def _emit(self, record: ScheduleRecord | None, *, tombstone: bool = False, record_id: str = "") -> None:
    if self._event_sink is None:
      return
    try:
      if tombstone:
        snapshot = {"id": record_id, "deleted": True}
      else:
        assert record is not None
        snapshot = record.to_dict()
      self._event_sink({"snapshot": snapshot, "tombstone": tombstone})
    except Exception:
      pass

  # -- persistence ------------------------------------------------------------

  def _load(self) -> dict[str, dict[str, Any]]:
    try:
      data = json.loads(self._path.read_text(encoding="utf-8"))
      if isinstance(data, dict) and isinstance(data.get("schedules"), dict):
        return data["schedules"]
    except (OSError, json.JSONDecodeError):
      pass
    return {}

  def _save(self, schedules: dict[str, dict[str, Any]]) -> None:
    tmp = self._path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"schedules": schedules}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(self._path)

  # -- allocation ---------------------------------------------------------------

  def _allocate_id(self) -> str:
    self._counter += 1
    return f"sch-{int(time.monotonic() * 1000) % 100000000}-{self._counter}"

  # -- creation ------------------------------------------------------------------

  def _create(self, kind: str, prompt: Any, *, after_seconds: Any = None, every_seconds: Any = None, at: Any = None, now: datetime | None = None) -> ScheduleRecord:
    if not isinstance(prompt, str) or not prompt.strip():
      raise ScheduleInputError("invalid_prompt", "schedule_create requires non-empty prompt text")
    prompt = prompt.strip()
    now = now or datetime.now(timezone.utc)

    if kind == "after":
      if not _is_safe_positive_int(after_seconds):
        raise ScheduleInputError("invalid_rule", "after_seconds must be a positive integer number of seconds")
      target = datetime.fromtimestamp(now.timestamp() + after_seconds, tz=timezone.utc)
      record = ScheduleRecord(
        id=self._allocate_id(), kind=kind, prompt=prompt,
        after_seconds=after_seconds, scheduled_at=_now_iso(target), created_at=_now_iso(now),
      )
    elif kind == "at":
      if not isinstance(at, str) or not at.strip():
        raise ScheduleInputError("invalid_rule", "schedule_create 'at' requires an RFC 3339 UTC instant string")
      target = _parse_utc(at.strip())
      if target <= now:
        raise ScheduleInputError("invalid_at", f"schedule 'at' target {at} is not in the future")
      record = ScheduleRecord(
        id=self._allocate_id(), kind=kind, prompt=prompt,
        scheduled_at=_now_iso(target), created_at=_now_iso(now),
      )
    elif kind == "every":
      if not _is_safe_positive_int(every_seconds) or every_seconds < MIN_EVERY_INTERVAL_SECONDS:
        raise ScheduleInputError(
          "invalid_rule",
          f"every_seconds must be at least {MIN_EVERY_INTERVAL_SECONDS} (got {every_seconds})",
        )
      target = datetime.fromtimestamp(now.timestamp() + every_seconds, tz=timezone.utc)
      record = ScheduleRecord(
        id=self._allocate_id(), kind=kind, prompt=prompt,
        every_seconds=every_seconds, scheduled_at=_now_iso(target), created_at=_now_iso(now),
      )
    else:
      raise ScheduleInputError("invalid_rule", f"unknown schedule kind {kind!r}")

    with self._lock:
      schedules = self._load()
      schedules[record.id] = record.to_dict()
      self._save(schedules)
    self._emit(record)
    return record

  def create_after(self, prompt: str, after_seconds: int, *, now: datetime | None = None) -> ScheduleRecord:
    return self._create("after", prompt, after_seconds=after_seconds, now=now)

  def create_at(self, prompt: str, at: str, *, now: datetime | None = None) -> ScheduleRecord:
    return self._create("at", prompt, at=at, now=now)

  def create_every(self, prompt: str, every_seconds: int, *, now: datetime | None = None) -> ScheduleRecord:
    return self._create("every", prompt, every_seconds=every_seconds, now=now)

  # -- query / mutation -----------------------------------------------------------

  def list(self) -> list[ScheduleRecord]:
    with self._lock:
      records = [ScheduleRecord.from_dict(v) for v in self._load().values()]
    return sorted(records, key=lambda r: (r.scheduled_at, r.id))

  def get(self, schedule_id: str) -> ScheduleRecord | None:
    with self._lock:
      raw = self._load().get(schedule_id)
    return ScheduleRecord.from_dict(raw) if raw else None

  def delete(self, schedule_id: str) -> bool:
    if not isinstance(schedule_id, str) or not schedule_id.strip():
      raise ScheduleInputError("invalid_rule", "schedule_delete id must be non-empty without surrounding whitespace")
    schedule_id = schedule_id.strip()
    with self._lock:
      schedules = self._load()
      if schedule_id not in schedules:
        return False
      del schedules[schedule_id]
      self._save(schedules)
    self._emit(None, tombstone=True, record_id=schedule_id)
    return True

  def mark_dispatched(self, record: ScheduleRecord, *, now: datetime | None = None) -> None:
    """After dispatch: one-shots are removed; ``every`` advances to the next
    anchor-aligned occurrence still in the future."""
    now = now or datetime.now(timezone.utc)
    if record.kind != "every":
      self.delete(record.id)
      return
    interval = int(record.every_seconds or 0)
    current = _parse_utc(record.scheduled_at)
    nxt = current
    while nxt <= now:
      nxt = datetime.fromtimestamp(nxt.timestamp() + interval, tz=timezone.utc)
    record.scheduled_at = _now_iso(nxt)
    with self._lock:
      schedules = self._load()
      schedules[record.id] = record.to_dict()
      self._save(schedules)
    self._emit(record)


# -- singleton (mirrors goal/plan/todo stores) -------------------------------

_store: ScheduleStore | None = None


def set_schedule_base_dir(base_dir: Path | str) -> None:
  global _store
  _store = ScheduleStore(base_dir)


def get_schedule_store(base_dir: Path | str | None = None) -> ScheduleStore:
  global _store
  if base_dir is not None:
    _store = ScheduleStore(base_dir)
  if _store is None:
    import os
    default = Path(os.environ.get("AI_WORKSPACE", ".")) / "workspace" / "ai_schedules"
    _store = ScheduleStore(default)
  return _store
