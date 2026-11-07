"""Spill — long-context management for conversations.

Ports the deepseek-harness spill concept to Python: when a session's message
history grows beyond a token or turn budget, older turns are summarized and
replaced by a compact "spill" reference that can be recalled later.
"""

from __future__ import annotations

from ai.spill.manager import (
  MemorySpillStore,
  SpillManager,
  SpillRef,
  SpillStore,
  SummaryEntry,
)
from ai.spill.recall import SpillRecall, list_summaries, recall_summary
from ai.spill.summarizer import MessageSummarizer, summarize_messages

__all__ = [
  "MemorySpillStore",
  "MessageSummarizer",
  "SpillManager",
  "SpillRecall",
  "SpillRef",
  "SpillStore",
  "SummaryEntry",
  "list_summaries",
  "recall_summary",
  "summarize_messages",
]
