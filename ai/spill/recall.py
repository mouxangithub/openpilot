"""Recall spilled conversation summaries.

A `SpillRecall` wraps a `SpillStore` and provides synchronous helpers to look
up summaries by locator or session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ai.spill.manager import SpillRef


class SpillStore(Protocol):
  """Minimal protocol for stores that support retrieval."""

  async def get_text(self, locator: str) -> str | None: ...


@dataclass
class RecallHit:
  locator: str
  summary: str
  session_id: str
  retrieval_hint: str


class SpillRecall:
  """Retrieve spilled summaries from a store."""

  def __init__(self, store: Any):
    self.store = store

  async def recall(self, locator: str) -> str | None:
    """Return the text for a locator, or None if not found."""
    if hasattr(self.store, "get_text"):
      return await self.store.get_text(locator)
    # MemorySpillStore fallback.
    data = getattr(self.store, "_data", None)
    if isinstance(data, dict):
      return data.get(locator)
    return None

  async def list_for_session(self, session_id: str) -> list[RecallHit]:
    """List every summary stored for `session_id`."""
    summaries = []
    raw = []
    if hasattr(self.store, "list_summaries"):
      raw = await self.store.list_summaries(session_id)
    else:
      data = getattr(self.store, "_data", None)
      if isinstance(data, dict):
        for locator, summary in data.items():
          if session_id in locator:
            raw.append({"locator": locator, "summary": summary})
    for item in raw:
      summaries.append(
        RecallHit(
          locator=str(item.get("locator", "")),
          summary=str(item.get("summary", "")),
          session_id=session_id,
          retrieval_hint=str(item.get("retrieval_hint", "")),
        )
      )
    return summaries


async def recall_summary(store: Any, locator: str) -> str | None:
  """Standalone helper: recall one summary by locator."""
  return await SpillRecall(store).recall(locator)


async def list_summaries(store: Any, session_id: str) -> list[RecallHit]:
  """Standalone helper: list summaries for a session."""
  return await SpillRecall(store).list_for_session(session_id)
