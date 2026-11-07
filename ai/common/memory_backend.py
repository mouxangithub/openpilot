"""Unified memory backend abstraction (T-P1.2).

Consolidates the two memory systems that previously lived side-by-side:
- ``memory_store`` : short-term / structured notes + vehicle profile (Params-backed)
- ``daily_memory`` : long-term / per-day timeline files (workspace-backed)

Instead of rewriting either module, this abstraction defines a single interface
backed by both, plus ``append_unified_memory`` which fans out an observation to
both backends so long-term memory is no longer fragmented. Existing call sites
keep working.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol


class MemoryBackend(Protocol):
  """Protocol any memory backend must satisfy (T-P1.2)."""

  def kind(self) -> str: ...

  def append(self, text: str, *, tags: list[str] | None = None, session_id: str = "", title: str = "") -> dict[str, Any]: ...

  def read(self, *, limit: int = 5) -> Any: ...


class AbstractMemoryBackend(ABC):
  """Shared base with a stable ``kind`` default."""

  def kind(self) -> str:  # noqa: D401
    return type(self).__name__.lower().replace("backend", "")


class NotesMemoryBackend(AbstractMemoryBackend):
  """Adapter over ``ai.tools.domains.core.memory_store`` (short-term notes)."""

  def __init__(self, params: Any = None) -> None:
    self._params = params

  def _mod(self):
    from ai.tools.domains.core import memory_store
    return memory_store

  def append(self, text: str, *, tags: list[str] | None = None, session_id: str = "", title: str = "") -> dict[str, Any]:
    return self._mod().append_note(self._params, text, tags=tags)

  def read(self, *, limit: int = 5) -> Any:
    mem = self._mod().get_memory(self._params)
    return (mem.get("notes") or [])[-limit:]

  def count(self) -> int:
    mem = self._mod().get_memory(self._params)
    return len(mem.get("notes") or [])


class DailyMemoryBackend(AbstractMemoryBackend):
  """Adapter over ``ai.tools.domains.core.daily_memory`` (long-term timeline)."""

  def append(self, text: str, *, tags: list[str] | None = None, session_id: str = "", title: str = "") -> dict[str, Any]:
    from ai.tools.domains.core import daily_memory
    return daily_memory.append_daily_memory(
      bullets=[text],
      session_id=session_id,
      title=title or None,
    )

  def read(self, *, limit: int = 5) -> Any:
    from ai.tools.domains.core import daily_memory
    return daily_memory.read_recent_daily_memories(days=max(1, limit))


def default_backends(params: Any = None) -> list[MemoryBackend]:
  """Return the standard backend set, memory_store first."""
  return [NotesMemoryBackend(params), DailyMemoryBackend()]


def append_unified_memory(
  text: str,
  *,
  params: Any = None,
  tags: list[str] | None = None,
  session_id: str = "",
  title: str = "",
  backends: list[MemoryBackend] | None = None,
) -> dict[str, Any]:
  """Persist an observation to all configured backends (short + long term).

  This is the single entry point callers use when a session should end with
  both a structured note and a daily-timeline bullet.
  """
  selected = backends or default_backends(params)
  results: dict[str, Any] = {}
  for backend in selected:
    try:
      results[backend.kind()] = backend.append(
        text, tags=tags, session_id=session_id, title=title
      )
    except Exception as exc:  # keep going; one backend must not break the others
      results[backend.kind()] = {"ok": False, "error": str(exc)}
  return {"ok": True, "backends": list(results), "results": results}


__all__ = [
  "AbstractMemoryBackend",
  "DailyMemoryBackend",
  "MemoryBackend",
  "NotesMemoryBackend",
  "append_unified_memory",
  "default_backends",
]