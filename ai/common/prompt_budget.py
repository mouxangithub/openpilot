"""Prompt budget assembly — cap system blocks by token budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai.common.context_config import context_window_for_model, estimate_message_tokens, reserve_tokens


def _estimate_text_tokens(text: str) -> int:
  return estimate_message_tokens(text)


def _trim_text(text: str, max_tokens: int) -> str:
  if max_tokens <= 0 or not text:
    return ""
  est = _estimate_text_tokens(text)
  if est <= max_tokens:
    return text
  # chars heuristic: tokens * 3.5
  max_chars = int(max_tokens * 3.5)
  if len(text) <= max_chars:
    return text
  return text[:max_chars].rstrip() + "\n…[truncated by prompt budget]"


@dataclass
class PromptBudget:
  model: str = ""
  total_window: int = 128_000
  reserve: int = 8_000
  system_max: int = 2_500
  memory_max: int = 1_500
  skills_max: int = 3_000
  workflow_max: int = 1_200
  blocks: list[dict[str, Any]] = field(default_factory=list)

  @classmethod
  def for_model(cls, model: str = "", params: Any = None) -> PromptBudget:
    window = context_window_for_model(model)
    reserve = reserve_tokens()
    return cls(model=model, total_window=window, reserve=reserve)

  @property
  def available(self) -> int:
    return max(0, self.total_window - self.reserve)

  def add_block(self, label: str, text: str, *, max_tokens: int, priority: int = 0) -> str:
    trimmed = _trim_text(text, max_tokens)
    used = _estimate_text_tokens(trimmed)
    self.blocks.append({
      "label": label,
      "tokens": used,
      "max_tokens": max_tokens,
      "priority": priority,
      "truncated": used < _estimate_text_tokens(text),
    })
    return trimmed

  def assemble_system_parts(self, parts: list[tuple[str, str, int, int]]) -> tuple[list[str], dict[str, Any]]:
    """
    parts: list of (label, text, max_tokens, priority).
    Returns (trimmed_texts, budget_report).
    """
    out: list[str] = []
    for label, text, max_tok, _prio in parts:
      if not (text or "").strip():
        continue
      trimmed = self.add_block(label, text, max_tokens=max_tok)
      if trimmed:
        out.append(trimmed)

    system_used = sum(b["tokens"] for b in self.blocks)
    report = {
      "total_window": self.total_window,
      "reserve": self.reserve,
      "available": self.available,
      "system_tokens": system_used,
      "blocks": list(self.blocks),
      "history_budget": max(0, self.available - system_used),
    }
    return out, report
