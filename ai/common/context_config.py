"""Context window and session compaction settings (OpenClaw-inspired)."""

from __future__ import annotations

from typing import Any

from ai.common.storage import read_param, read_param_bool

# Model context windows (tokens) — Python constant name uses SCREAMING_SNAKE_CASE;
# dict keys use provider model IDs (often with hyphens, e.g. deepseek-v4-flash).
# Override per device via ai_context_window param in settings.
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
  "deepseek-v4-flash": 128_000,
  "deepseek-chat": 64_000,
  "gpt-4o": 128_000,
  "gpt-4o-mini": 128_000,
  "claude-sonnet-4": 200_000,
  "kimi-k2": 128_000,
  "default": 128_000,
}


def _int_param(key: str, default: int, *, lo: int = 0, hi: int = 2_000_000) -> int:
  try:
    raw = read_param(None, key, str(default))
    val = int(str(raw or default).strip())
    return max(lo, min(hi, val))
  except (TypeError, ValueError):
    return default


def compaction_enabled() -> bool:
  return read_param_bool(None, "ai_compaction_enabled", True)


def compact_after_turns() -> int:
  return _int_param("ai_compact_after_turns", 24, lo=4, hi=200)


def keep_recent_turns() -> int:
  return _int_param("ai_keep_recent_turns", 8, lo=2, hi=100)


def reserve_tokens() -> int:
  return _int_param("ai_reserve_tokens", 8000, lo=0, hi=500_000)


def context_window_for_model(model: str = "", route_override: int = 0) -> int:
  if route_override and route_override > 0:
    return route_override
  override = _int_param("ai_context_window", 0, lo=0, hi=2_000_000)
  if override > 0:
    return override
  m = (model or "").strip().lower()
  for key, window in MODEL_CONTEXT_WINDOWS.items():
    if key != "default" and key in m:
      return window
  return MODEL_CONTEXT_WINDOWS["default"]


def token_trigger_enabled() -> bool:
  """When True, also compact when estimated tokens exceed window - reserve."""
  return _int_param("ai_compaction_token_trigger", 1, lo=0, hi=1) == 1


def estimate_message_tokens(content: Any) -> int:
  """Rough token estimate (chars/3.5 for mixed CJK/Latin)."""
  if isinstance(content, str):
    text = content
  elif isinstance(content, list):
    parts: list[str] = []
    for p in content:
      if isinstance(p, dict) and p.get("type") == "text":
        parts.append(str(p.get("text") or ""))
    text = " ".join(parts)
  else:
    text = str(content or "")
  n = len(text)
  if not n:
    return 0
  return max(1, int(n / 3.5))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
  total = 0
  for m in messages:
    total += 4  # role/overhead
    total += estimate_message_tokens(m.get("content"))
    for tc in m.get("tool_calls") or []:
      fn = tc.get("function") or {}
      total += estimate_message_tokens(fn.get("arguments"))
    tr = m.get("tool_results") or {}
    if isinstance(tr, dict):
      for v in tr.values():
        total += estimate_message_tokens(v if isinstance(v, str) else str(v))
  return total


def compaction_settings(*, model: str = "", context_window: int = 0) -> dict[str, Any]:
  window = context_window_for_model(model, route_override=context_window)
  return {
    "enabled": compaction_enabled(),
    "compactAfterTurns": compact_after_turns(),
    "keepRecentTurns": keep_recent_turns(),
    "reserveTokens": reserve_tokens(),
    "contextWindow": window,
    "tokenTrigger": token_trigger_enabled(),
    "compactThresholdTokens": max(0, window - reserve_tokens()) if token_trigger_enabled() else 0,
  }


def should_compact_by_tokens(messages: list[dict[str, Any]], *, model: str = "", context_window: int = 0) -> bool:
  if not token_trigger_enabled():
    return False
  window = context_window_for_model(model, route_override=context_window)
  threshold = window - reserve_tokens()
  if threshold <= 0:
    return False
  return estimate_messages_tokens(messages) >= threshold
