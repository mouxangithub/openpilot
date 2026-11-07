"""Message summarization for spill.

The default summarizer extracts a compact bullet view of older messages.
A real LLM-based summarizer can be injected via the `summarizer` callback.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

SummarizerCallback = Callable[[list[dict[str, Any]], int | None], Awaitable[str]]


def _message_text(content: Any) -> str:
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    parts: list[str] = []
    for part in content:
      if isinstance(part, dict) and part.get("type") == "text":
        parts.append(str(part.get("text") or ""))
    return " ".join(parts)
  return str(content or "")


async def summarize_messages(
  messages: list[dict[str, Any]],
  max_tokens: int | None = None,
  summarizer: SummarizerCallback | None = None,
) -> str:
  """Return a short summary of `messages`.

  If `summarizer` is provided it is awaited and returned verbatim.
  Otherwise a deterministic bullet extract is produced.
  """
  if summarizer is not None:
    return await summarizer(messages, max_tokens)

  lines: list[str] = []
  # Keep the most recent messages; older detail is what we are replacing.
  for message in messages[-20:]:
    role = message.get("role", "?")
    text = _message_text(message.get("content")).strip()
    if not text:
      continue
    # Flatten to one line and cap so the summary stays compact.
    line = " ".join(text.split())[:160]
    lines.append(f"- {role}: {line}")
  if not lines:
    return "(no content to summarize)"
  return "\n".join(lines)


class MessageSummarizer:
  """Injectable summarizer used by `SpillManager`."""

  def __init__(
    self,
    summarizer: SummarizerCallback | None = None,
    max_summary_tokens: int = 400,
  ):
    self.summarizer = summarizer
    self.max_summary_tokens = max_summary_tokens

  async def summarize(self, messages: list[dict[str, Any]]) -> str:
    return await summarize_messages(
      messages,
      max_tokens=self.max_summary_tokens,
      summarizer=self.summarizer,
    )
