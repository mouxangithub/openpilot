"""Spill manager: decide when to summarize older messages and store summaries.

The manager is intentionally decoupled from openpilot. It estimates tokens with
a simple character heuristic and can spill older conversation turns to a
pluggable store.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from ai.spill.summarizer import MessageSummarizer


@dataclass(frozen=True)
class SpillRef:
  """A handle to one spilled artifact."""

  locator: str
  bytes: int
  retrieval_hint: str


class SpillStore(Protocol):
  """Backend that persists spilled text and supports retrieval."""

  async def save_text(self, input: dict[str, Any]) -> SpillRef: ...
  async def get_text(self, locator: str) -> str | None: ...


class MemorySpillStore:
  """In-memory spill store for testing and single-process use."""

  def __init__(self) -> None:
    self._data: dict[str, str] = {}

  def _key(self, session_id: str, content: str) -> str:
    digest = hashlib.sha256(f"{session_id}:{content}".encode("utf-8")).hexdigest()[:16]
    return f"spill://memory/{session_id}/{digest}"

  async def save_text(self, input: dict[str, Any]) -> SpillRef:
    session_id = input.get("owner", {}).get("session_id", "default")
    content = input.get("content", "")
    locator = self._key(session_id, content)
    self._data[locator] = content
    return SpillRef(
      locator=locator,
      bytes=len(content.encode("utf-8")),
      retrieval_hint=f"recall with locator {locator}",
    )

  async def get_text(self, locator: str) -> str | None:
    return self._data.get(locator)

  def list_summaries(self, session_id: str) -> list[dict[str, Any]]:
    prefix = f"spill://memory/{session_id}/"
    return [
      {"locator": k, "summary": v, "retrieval_hint": f"recall with locator {k}"}
      for k, v in self._data.items()
      if k.startswith(prefix)
    ]


@dataclass
class SummaryEntry:
  session_id: str
  locator: str
  summary: str
  source_turns: int
  created_at: float = field(default_factory=time.monotonic)


SpillDecisionCallback = Callable[[list[dict[str, Any]]], Awaitable[bool]]


def _estimate_content_tokens(content: Any) -> int:
  if isinstance(content, str):
    text = content
  elif isinstance(content, list):
    parts: list[str] = []
    for part in content:
      if isinstance(part, dict) and part.get("type") == "text":
        parts.append(str(part.get("text") or ""))
    text = " ".join(parts)
  else:
    text = str(content or "")
  n = len(text)
  if not n:
    return 0
  return max(1, int(n / 3.5))


class SpillManager:
  """Decide when a conversation is too long and replace older turns with a summary.

  Parameters:
    max_inline_tokens: budget before spilling is considered.
    reserve_tokens: headroom kept below the budget.
    max_turns_before_spill: optional hard user-turn trigger.
    keep_recent_turns: number of recent user turns to keep untouched.
    store: persistence backend; defaults to in-memory.
    summarizer: async callable or `MessageSummarizer`.
  """

  def __init__(
    self,
    *,
    max_inline_tokens: int = 8000,
    reserve_tokens: int = 1000,
    max_turns_before_spill: int | None = None,
    keep_recent_turns: int = 2,
    store: SpillStore | None = None,
    summarizer: MessageSummarizer | Callable[..., Awaitable[str]] | None = None,
  ):
    self.max_inline_tokens = max(max_inline_tokens, 0)
    self.reserve_tokens = max(reserve_tokens, 0)
    self.max_turns_before_spill = max_turns_before_spill
    self.keep_recent_turns = max(keep_recent_turns, 0)
    self.store = store or MemorySpillStore()
    if isinstance(summarizer, MessageSummarizer) or summarizer is None:
      self.summarizer: MessageSummarizer = summarizer or MessageSummarizer()
    else:
      self.summarizer = MessageSummarizer(summarizer=summarizer)
    self.summaries: list[SummaryEntry] = []

  def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
    """Rough token estimate for a message list."""
    total = 0
    for message in messages:
      total += 4  # role and formatting overhead
      total += _estimate_content_tokens(message.get("content"))
      for tool_call in message.get("tool_calls") or []:
        fn = tool_call.get("function") or {}
        total += _estimate_content_tokens(fn.get("arguments"))
      tool_results = message.get("tool_results") or {}
      if isinstance(tool_results, dict):
        for value in tool_results.values():
          total += _estimate_content_tokens(value)
    return total

  def should_spill(
    self,
    messages: list[dict[str, Any]],
    *,
    force: bool = False,
  ) -> bool:
    """Return True when older messages should be summarized."""
    if force:
      return True
    if not messages:
      return False
    if self.max_turns_before_spill is not None:
      user_turns = sum(1 for m in messages if m.get("role") == "user")
      if user_turns >= self.max_turns_before_spill:
        return True
    budget = self.max_inline_tokens - self.reserve_tokens
    if budget > 0 and self.estimate_tokens(messages) >= budget:
      return True
    return False

  def _split_messages(
    self,
    messages: list[dict[str, Any]],
  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (to_spill, to_keep)."""
    if not messages:
      return [], []
    keep_n = self.keep_recent_turns
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_indices) <= keep_n:
      return [], messages
    cut_idx = user_indices[-keep_n]
    return messages[:cut_idx], messages[cut_idx:]

  async def spill(
    self,
    messages: list[dict[str, Any]],
    *,
    session_id: str = "",
    force: bool = False,
  ) -> list[dict[str, Any]]:
    """Summarize older messages and replace them with a compact system message."""
    if not self.should_spill(messages, force=force):
      return messages

    old_messages, keep_messages = self._split_messages(messages)
    if not old_messages:
      return messages

    summary = await self.summarizer.summarize(old_messages)
    spill_input = {
      "owner": {"session_id": session_id or "default"},
      "source": {"tool_name": "spill", "label": "conversation_summary"},
      "suggested_name": "conversation_summary.txt",
      "content": summary,
    }
    ref = await self.store.save_text(spill_input)
    entry = SummaryEntry(
      session_id=session_id or "default",
      locator=ref.locator,
      summary=summary,
      source_turns=len(old_messages),
    )
    self.summaries.append(entry)

    summary_message = {
      "role": "system",
      "content": (
        "[Earlier conversation summarized and stored]\n"
        f"{summary}\n\n"
        f"({ref.retrieval_hint})"
      ),
    }
    return [summary_message] + keep_messages

  def status(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Return spill diagnostics for a message list."""
    estimated = self.estimate_tokens(messages)
    budget = max(0, self.max_inline_tokens - self.reserve_tokens)
    return {
      "estimatedTokens": estimated,
      "maxInlineTokens": self.max_inline_tokens,
      "reserveTokens": self.reserve_tokens,
      "budgetTokens": budget,
      "keepRecentTurns": self.keep_recent_turns,
      "maxTurnsBeforeSpill": self.max_turns_before_spill,
      "needsSpill": self.should_spill(messages),
      "summaryCount": len(self.summaries),
    }
