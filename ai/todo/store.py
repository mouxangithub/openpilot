"""Todo store — durable JSON persistence for whole-list replacement."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from ai.todo.models import TodoCounts, TodoItem


class TodoStore:
  def __init__(self, base_dir: Path | str) -> None:
    self.base_dir = Path(base_dir)
    self.base_dir.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()
    self._event_sink: Any = None

  def set_event_sink(self, sink: Any) -> None:
    """Bind an optional domain-event sink: sink(snapshot_dict, tombstone).

    Every successful write (including clear) emits a full-snapshot
    ``todo/change`` event; clearing emits a tombstone since the list is
    emptied wholesale. Unbound stores keep the legacy JSON-only behavior.
    """
    self._event_sink = sink

  def _emit_domain(self, snapshot: Any, tombstone: bool = False) -> None:
    sink = self._event_sink
    if sink is None:
      return
    try:
      sink(snapshot, tombstone)
    except Exception:
      # Best-effort projection; JSON store remains authoritative for now.
      pass

  @property
  def _state_path(self) -> Path:
    return self.base_dir / "todos.json"

  def _load(self) -> dict[str, Any]:
    if not self._state_path.exists():
      return {"todos": [], "updatedAt": 0}
    try:
      with open(self._state_path, encoding="utf-8") as f:
        return json.load(f)
    except (json.JSONDecodeError, OSError):
      return {"todos": [], "updatedAt": 0}

  def _save(self, data: dict[str, Any]) -> None:
    tmp = self._state_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
      f.flush()
      os.fsync(f.fileno())
    tmp.replace(self._state_path)

  @staticmethod
  def _normalize(raw: list[dict[str, Any]] | list[TodoItem], allow_parallel: bool) -> list[TodoItem]:
    items: list[TodoItem] = []
    for entry in raw:
      item = TodoItem.from_dict(entry) if isinstance(entry, dict) else entry
      items.append(item)
    seen: set[str] = set()
    for item in items:
      content = item.content.strip()
      if not content:
        raise ValueError("todo content must be non-empty")
      if content in seen:
        raise ValueError(f"duplicate todo content: {content}")
      seen.add(content)
    if not allow_parallel:
      active = sum(1 for item in items if item.status == "in_progress")
      if active > 1:
        raise ValueError(f"at most one todo may be in_progress (got {active})")
    return items

  def write(
    self,
    todos: list[dict[str, Any]] | list[TodoItem],
    *,
    allow_parallel: bool = True,
    metadata: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    items = self._normalize(todos, allow_parallel)
    counts = self._counts(items)
    with self._lock:
      self._save({
        "todos": [t.to_dict() for t in items],
        "updatedAt": int(time.monotonic() * 1000),
        "metadata": dict(metadata or {}),
      })
    self._emit_domain(
      {"todos": [t.to_dict() for t in items], "metadata": dict(metadata or {})},
      tombstone=not items,
    )
    return {
      "todos": [t.to_dict() for t in items],
      "counts": counts.to_dict(),
    }

  def get(self) -> dict[str, Any]:
    data = self._load()
    items = [TodoItem.from_dict(t) for t in data.get("todos", [])]
    return {
      "todos": [t.to_dict() for t in items],
      "counts": self._counts(items).to_dict(),
      "updatedAt": data.get("updatedAt", 0),
      "metadata": dict(data.get("metadata") or {}),
    }

  def clear(self) -> dict[str, Any]:
    return self.write([], allow_parallel=True)

  @staticmethod
  def _counts(items: list[TodoItem]) -> TodoCounts:
    return TodoCounts(
      pending=sum(1 for t in items if t.status == "pending"),
      in_progress=sum(1 for t in items if t.status == "in_progress"),
      completed=sum(1 for t in items if t.status == "completed"),
    )


_store: TodoStore | None = None


def set_todo_base_dir(base_dir: Path | str) -> None:
  global _store
  _store = TodoStore(base_dir)


def get_todo_store(base_dir: Path | str | None = None) -> TodoStore:
  global _store
  if base_dir is not None:
    return TodoStore(base_dir)
  if _store is None:
    default = Path(os.environ.get("AI_WORKSPACE", ".")) / "workspace" / "ai_todos"
    _store = TodoStore(default)
  return _store
