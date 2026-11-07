"""Token estimation meter for compaction budgets.

A deterministic heuristic meter (no tokenizer dependency on device): ASCII
runs average ~4 characters per token, CJK runs ~1.6 characters per token.
Accurate enough for budget gating (±20%); the authoritative count remains
the provider's usage figure.
"""

from __future__ import annotations

from typing import Any, Iterable

_ASCII_CHARS_PER_TOKEN = 4.0
_CJK_CHARS_PER_TOKEN = 1.6


def _is_cjk(ch: str) -> bool:
  code = ord(ch)
  return (
    0x2E80 <= code <= 0x9FFF      # CJK radicals, blocks, ideographs
    or 0xF900 <= code <= 0xFAFF   # CJK compatibility ideographs
    or 0xFF00 <= code <= 0xFFEF   # fullwidth forms
    or 0x3000 <= code <= 0x303F   # CJK punctuation
  )


def estimate_tokens(text: str) -> int:
  """Estimate the token count of one string (>=0)."""
  if not text:
    return 0
  cjk = sum(1 for ch in text if _is_cjk(ch))
  ascii_chars = len(text) - cjk
  estimate = ascii_chars / _ASCII_CHARS_PER_TOKEN + cjk / _CJK_CHARS_PER_TOKEN
  return max(1, int(estimate + 0.5))


def count_message_tokens(messages: Iterable[dict[str, Any]]) -> int:
  """Estimate the total token count of OpenAI-style messages (role+content)."""
  total = 0
  for message in messages:
    if not isinstance(message, dict):
      continue
    total += 4  # per-message framing overhead (role, delimiters)
    total += estimate_tokens(str(message.get("role") or ""))
    content = message.get("content")
    if isinstance(content, str):
      total += estimate_tokens(content)
    elif content is not None:
      total += estimate_tokens(str(content))
  return total
