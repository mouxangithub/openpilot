"""Replay-safe, model-free tool-result pruning.

Port of dsh ``compaction-tool-result-pruner``: deterministic head/middle/tail
pruning of over-budget tool results on the current surface. Each replacement
preserves the original event data except ``content``, cites the shadowed node
via ``source_seqs`` (REPLACE provenance), and is immediately preceded by a
``compaction/prune`` shadow-price event pricing the shadowed node's char cost,
so pure consumers can subtract it without per-node state.

Text slicing is by Unicode code point, so a retained boundary cannot split a
surrogate pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai.core.session.log import EventType, SessionEvent, SessionLog, SurfaceOp

PRUNE_MARKER = "\n\n[... tool result middle pruned ...]\n\n"

DEFAULT_THRESHOLD_CHARS = 8192
DEFAULT_HEAD_CHARS = 4096
DEFAULT_TAIL_CHARS = 1024


def code_point_length(text: str) -> int:
  return len(text) if text.isascii() else sum(1 for _ in str(text))


@dataclass(frozen=True)
class ResolvedConfig:
  threshold_chars: int
  head_chars: int
  tail_chars: int


def resolve_config(
  *,
  threshold_chars: int | None = None,
  head_chars: int | None = None,
  tail_chars: int | None = None,
) -> ResolvedConfig:
  """Validate pruning budgets: head + marker + tail must fit the threshold."""
  resolved = ResolvedConfig(
    threshold_chars=int(threshold_chars if threshold_chars is not None else DEFAULT_THRESHOLD_CHARS),
    head_chars=int(head_chars if head_chars is not None else DEFAULT_HEAD_CHARS),
    tail_chars=int(tail_chars if tail_chars is not None else DEFAULT_TAIL_CHARS),
  )
  if resolved.threshold_chars <= 0:
    raise ValueError(f"threshold_chars ({resolved.threshold_chars}) must be a positive integer")
  if resolved.head_chars < 0:
    raise ValueError(f"head_chars ({resolved.head_chars}) must be a non-negative integer")
  if resolved.tail_chars < 0:
    raise ValueError(f"tail_chars ({resolved.tail_chars}) must be a non-negative integer")
  emitted = resolved.head_chars + code_point_length(PRUNE_MARKER) + resolved.tail_chars
  if emitted > resolved.threshold_chars:
    raise ValueError(
      f"head_chars + marker + tail_chars ({emitted}) "
      f"must be at most threshold_chars ({resolved.threshold_chars})"
    )
  return resolved


@dataclass
class PrunedEntry:
  original_seq: int
  replacement_seq: int
  tool_call_id: str
  chars_before: int
  chars_after: int


@dataclass
class PruneResult:
  pruned: list[PrunedEntry] = field(default_factory=list)
  chars_removed: int = 0
  tokens_removed: int = 0


class ToolResultPruner:
  """Deterministic head/middle/tail pruning for current tool-result surface nodes."""

  def __init__(
    self,
    *,
    threshold_chars: int | None = None,
    head_chars: int | None = None,
    tail_chars: int | None = None,
  ) -> None:
    self.config = resolve_config(
      threshold_chars=threshold_chars, head_chars=head_chars, tail_chars=tail_chars,
    )

  def measure_content(self, text: str) -> int:
    """Measure text content in Unicode code points."""
    return code_point_length(text)

  def prune_content(self, text: str) -> str | None:
    """Replace an over-budget text middle; ``None`` when within budget."""
    total_chars = self.measure_content(text)
    if total_chars <= self.config.threshold_chars:
      return None

    removed_start = self.config.head_chars
    removed_end = total_chars - self.config.tail_chars
    points = list(str(text))
    head = points[:removed_start]
    tail = points[removed_end:] if removed_end > removed_start else []
    return "".join(head) + PRUNE_MARKER + "".join(tail)

  def prune_session(self, log: SessionLog, *, token_meter=None, retain_recent: int = 0) -> PruneResult:
    """Prune over-budget tool results from one stable surface snapshot.

    ``token_meter`` (optional callable str->int) prices each shadowed node in
    tokens for the ``compaction/prune`` shadow-price event. ``retain_recent``
    leaves the most recent N TOOL_RESULT surface nodes untouched so a just
    finished step is never pruned by the same compaction pass.

    Each replacement is immediately preceded by a ``compaction/prune``
    shadow-price event; the REPLACE cites the shadowed seq via source_seqs
    and keeps the same tool_call_id (strict surface validation requires it).
    """
    nodes = [node for node in log.surface if node.event_type == EventType.TOOL_RESULT]
    protected: set[int] = set()
    if retain_recent > 0:
      protected = {node.seq for node in nodes[len(nodes) - retain_recent:]}

    result = PruneResult()
    for node in nodes:
      seq = node.seq
      if seq in protected:
        continue
      event = log.events[seq]
      data = event.data if isinstance(event.data, dict) else {}
      content = data.get("content")
      if not isinstance(content, str):
        continue
      chars_before = self.measure_content(content)
      pruned_text = self.prune_content(content)
      if pruned_text is None:
        continue
      chars_after = self.measure_content(pruned_text)

      # Shadow-price protocol: metering event and its replacement land
      # synchronously adjacent so pure consumers subtract the shadowed node
      # without per-node state. Priced in Unicode code points; when a token
      # meter is supplied the shadow event also carries the token price.
      shadow_payload: dict = {
        "shadowedRange": {"start": seq, "end": seq},
        "shadowedSeqs": [seq],
        "shadowedCharCount": chars_before,
      }
      if token_meter is not None:
        try:
          tokens_before = int(token_meter(content))
          tokens_after = int(token_meter(pruned_text))
        except Exception:
          tokens_before = tokens_after = 0
        shadow_payload["shadowedTokenCount"] = max(0, tokens_before - tokens_after)
        result.tokens_removed += max(0, tokens_before - tokens_after)
      log.append(
        EventType.COMPACTION_PRUNE,
        shadow_payload,
      )
      replacement = log.append(
        EventType.TOOL_RESULT,
        {**data, "content": pruned_text},
        surface_op=SurfaceOp.REPLACE,
        source_seqs=[seq],
      )
      result.pruned.append(PrunedEntry(
        original_seq=seq,
        replacement_seq=replacement.seq,
        tool_call_id=str(data.get("tool_call_id", "")),
        chars_before=chars_before,
        chars_after=chars_after,
      ))
      result.chars_removed += chars_before - chars_after
    return result


def prune_events(events: list[SessionEvent]) -> dict[str, Any]:
  """Pure projection: net tool-result char cost after applying shadow prices."""
  shadowed: set[int] = set()
  shadow_chars = 0
  for event in events:
    if event.type != EventType.COMPACTION_PRUNE:
      continue
    data = event.data if isinstance(event.data, dict) else {}
    for seq in data.get("shadowedSeqs") or []:
      shadowed.add(int(seq))
    shadow_chars += int(data.get("shadowedCharCount") or 0)
  live_chars = 0
  for event in events:
    if event.type != EventType.TOOL_RESULT or event.seq in shadowed:
      continue
    data = event.data if isinstance(event.data, dict) else {}
    content = data.get("content")
    if isinstance(content, str):
      live_chars += code_point_length(content)
  return {"shadowedSeqs": sorted(shadowed), "shadowedChars": shadow_chars, "liveToolResultChars": live_chars}