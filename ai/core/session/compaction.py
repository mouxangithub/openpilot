"""Event-projection driven session compaction service (G3).

Budget gating uses a deterministic token meter (``core/session/tokens``)
against ``CompactionConfig.max_tokens``: compaction only fires when the
derived message history exceeds ``max_tokens * threshold_ratio``. An explicit
``max_tokens <= 0`` disables automatic compaction entirely (``compact_now``
still works on demand) — the previous behavior of compacting on every step
when unset was a bug.

The summary prefers the injected ``llm_stream``; without one a deterministic
digest (oldest user objective + pruned-result previews + counts) is emitted
so the REPLACE marker still carries useful context into replay.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import uuid

from ai.core.session.log import EventType, SessionLog, SurfaceOp
from ai.core.session.pruner import ToolResultPruner
from ai.core.session.tokens import count_message_tokens, estimate_tokens

DEFAULT_MAX_TOKENS = 32_768


@dataclass
class CompactionConfig:
  threshold_ratio: float = 0.8
  retain_ratio: float = 0.16
  max_tokens: int = DEFAULT_MAX_TOKENS


@dataclass
class CompactionResult:
  compaction_id: str
  summary: str
  shadowed_seqs: list[int]
  shadowed_token_count: int
  replacement_seq: int | None


class CompactionService:
  def __init__(self, session_log: SessionLog, llm_stream: Any = None, config: CompactionConfig | None = None) -> None:
    self.session_log = session_log
    self.llm_stream = llm_stream
    self.config = config or CompactionConfig()
    self._locked = False

  # -- metering ------------------------------------------------------------

  def measure_tokens(self) -> int:
    return count_message_tokens(self.session_log.derive_messages())

  def should_compact(self) -> tuple[bool, int, int]:
    """(should_fire, measured_tokens, budget_tokens) for the current log."""
    budget = int(self.config.max_tokens or 0)
    if budget <= 0:
      return False, 0, 0
    measured = self.measure_tokens()
    return measured > budget * self.config.threshold_ratio, measured, budget

  # -- lifecycle -------------------------------------------------------------

  def _emit_lifecycle(self, kind: str, payload: dict) -> None:
    self.session_log.append(EventType.LIFECYCLE, {"kind": kind, **payload})

  async def compact_if_needed(self, agent: Any, trigger: str = "pressure", signal: Any = None) -> CompactionResult | None:
    if self._locked:
      return None
    should, measured, budget = self.should_compact()
    if not should:
      return None
    return await self.compact_now(agent, signal, measured_tokens=measured, budget_tokens=budget)

  async def compact_now(self, agent: Any, signal: Any = None, *, measured_tokens: int | None = None, budget_tokens: int | None = None) -> CompactionResult | None:
    if self._locked:
      return None
    self._locked = True
    try:
      cid = uuid.uuid4().hex
      measured = self.measure_tokens() if measured_tokens is None else measured_tokens
      budget = int(self.config.max_tokens or 0) if budget_tokens is None else budget_tokens
      self._emit_lifecycle("compaction/start", {
        "compactionId": cid,
        "measuredTokens": measured,
        "budgetTokens": budget,
        "trigger": "explicit" if measured_tokens is None else "pressure",
      })

      # Retain the most recent slice of tool results unpruned so the step
      # that just finished is never shadowed by its own compaction pass.
      tool_result_nodes = [n for n in self.session_log.surface if n.event_type == EventType.TOOL_RESULT]
      retain = int(len(tool_result_nodes) * max(0.0, min(1.0, self.config.retain_ratio)))

      pruner = ToolResultPruner()
      pruned = pruner.prune_session(self.session_log, token_meter=estimate_tokens, retain_recent=retain)
      shadowed = [x.original_seq for x in pruned.pruned]

      summary = await self._summarize(pruned)
      replacement = None
      if summary:
        # APPEND, not REPLACE: the pruner's own REPLACE events already shrank
        # the shadowed tool results, and REPLACE requires contiguous
        # source_seqs — pruned seqs are scattered by threshold, so citing
        # them here would fail strict surface validation. The summary rides
        # as a first-class user marker with full provenance instead.
        ev = self.session_log.append(
          EventType.USER_MESSAGE,
          {
            "content": "[Compaction summary]\n" + summary,
            "compactionId": cid,
            "shadowedSeqs": shadowed,
          },
          surface_op=SurfaceOp.APPEND,
        )
        replacement = ev.seq
      self._emit_lifecycle("compaction/summary", {
        "compactionId": cid, "summary": summary,
        "shadowedSeqs": shadowed, "shadowedTokenCount": pruned.tokens_removed,
      })
      self._emit_lifecycle("compaction/end", {"compactionId": cid})
      return CompactionResult(cid, summary, shadowed, pruned.tokens_removed, replacement)
    finally:
      self._locked = False

  # -- summary -----------------------------------------------------------

  async def _summarize(self, pruned: Any) -> str:
    """LLM summary when a stream is injected; deterministic digest otherwise."""
    if self.llm_stream is not None and callable(self.llm_stream):
      try:
        text = self.llm_stream(self.session_log.derive_messages())
        if hasattr(text, "__await__"):
          text = await text
        summary = str(text or "").strip()
        if summary:
          return summary
      except Exception:
        pass  # fall through to the deterministic digest
    return self._digest_summary(pruned)

  def _digest_summary(self, pruned: Any) -> str:
    """Deterministic, dependency-free summary of what was compacted."""
    entries = list(pruned.pruned) if pruned is not None else []
    parts: list[str] = []
    first_user = next(
      (n for n in self.session_log.surface if n.event_type == EventType.USER_MESSAGE),
      None,
    )
    if first_user is not None:
      content = str((first_user.data or {}).get("content") or "")
      parts.append(f"Session objective: {content[:200]}")
    if entries:
      total_chars = sum(e.chars_before - e.chars_after for e in entries)
      parts.append(
        f"{len(entries)} oversized tool result(s) pruned (~{total_chars} chars, "
        f"~{pruned.tokens_removed} tokens freed); full text remains in spill/prune artifacts."
      )
    else:
      parts.append("No oversized tool results required pruning in this pass.")
    return "\n".join(parts)
