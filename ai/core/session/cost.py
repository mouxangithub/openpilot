"""Model routing cost tracking.

Accumulates token usage and cost per provider/model and exposes a summary.
This module is intentionally dependency-light: it records usage events and
aggregates them in memory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class CostTrackingError(ValueError):
  """Raised when cost tracking state is inconsistent."""


@dataclass
class UsageRecord:
  """One usage observation."""

  provider: str
  model: str
  input_tokens: int
  output_tokens: int
  cost: float
  recorded_at: int

  def to_dict(self) -> dict[str, Any]:
    return {
      "provider": self.provider,
      "model": self.model,
      "input_tokens": self.input_tokens,
      "output_tokens": self.output_tokens,
      "cost": self.cost,
      "recorded_at": self.recorded_at,
    }


@dataclass
class ModelCostSummary:
  """Aggregated cost information for a provider/model pair."""

  provider: str
  model: str
  requests: int = 0
  input_tokens: int = 0
  output_tokens: int = 0
  total_tokens: int = 0
  cost: float = 0.0

  def to_dict(self) -> dict[str, Any]:
    return {
      "provider": self.provider,
      "model": self.model,
      "requests": self.requests,
      "input_tokens": self.input_tokens,
      "output_tokens": self.output_tokens,
      "total_tokens": self.total_tokens,
      "cost": self.cost,
    }


@dataclass
class CostTracker:
  """In-memory token/cost accumulator with optional JSONL persistence."""

  _records: list[UsageRecord] = field(default_factory=list)
  _persist_path: Path | None = None

  def __init__(self, persist_path: str | Path | None = None) -> None:
    self._records = []
    self._persist_path = Path(persist_path) if persist_path else None
    if self._persist_path is not None:
      self._persist_path.parent.mkdir(parents=True, exist_ok=True)

  def record_usage(
    self,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    *,
    timestamp: int | None = None,
  ) -> UsageRecord:
    """Record one inference request's usage."""
    record = UsageRecord(
      provider=str(provider or ""),
      model=str(model or ""),
      input_tokens=max(0, int(input_tokens)),
      output_tokens=max(0, int(output_tokens)),
      cost=float(cost),
      recorded_at=timestamp or int(time.time()),
    )
    self._records.append(record)
    self._persist(record)
    return record

  def _persist(self, record: UsageRecord) -> None:
    if self._persist_path is None:
      return
    try:
      import json
      with self._persist_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        f.flush()
    except Exception:
      # Persistence is best-effort; do not break recording.
      pass

  def get_cost_summary(self) -> dict[str, Any]:
    """Return aggregated cost summary grouped by provider and model."""
    summaries: dict[tuple[str, str], ModelCostSummary] = {}
    for record in self._records:
      key = (record.provider, record.model)
      summary = summaries.setdefault(
        key,
        ModelCostSummary(provider=record.provider, model=record.model),
      )
      summary.requests += 1
      summary.input_tokens += record.input_tokens
      summary.output_tokens += record.output_tokens
      summary.total_tokens += record.input_tokens + record.output_tokens
      summary.cost += record.cost

    by_model = [summary.to_dict() for summary in summaries.values()]
    total_cost = sum(summary.cost for summary in summaries.values())
    total_tokens = sum(summary.total_tokens for summary in summaries.values())
    return {
      "total_cost": round(total_cost, 6),
      "total_tokens": total_tokens,
      "total_requests": len(self._records),
      "by_model": sorted(by_model, key=lambda x: (x["provider"], x["model"])),
    }

  def records(self) -> list[UsageRecord]:
    """Return a defensive copy of all recorded usage."""
    return list(self._records)

  def reset(self) -> None:
    """Clear all in-memory records. Does not delete the persisted file."""
    self._records.clear()


_global_tracker: CostTracker | None = None


def get_global_cost_tracker(persist_path: str | Path | None = None) -> CostTracker:
  """Return the process-wide cost tracker, creating it if needed."""
  global _global_tracker
  if _global_tracker is None:
    _global_tracker = CostTracker(persist_path=persist_path)
  return _global_tracker


def record_usage(
  provider: str,
  model: str,
  input_tokens: int,
  output_tokens: int,
  cost: float,
) -> UsageRecord:
  """Record usage on the global tracker."""
  return get_global_cost_tracker().record_usage(
    provider=provider,
    model=model,
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    cost=cost,
  )


def get_cost_summary() -> dict[str, Any]:
  """Return the global cost summary."""
  return get_global_cost_tracker().get_cost_summary()
