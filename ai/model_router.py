"""Chat model selection — always uses the configured primary model."""

from __future__ import annotations

from typing import Any

from ai.client import AIConfig


def resolve_chat_config(
  base: AIConfig,
  params,
  *,
  workflow_id: str = "",
  user_text: str = "",
  body: dict[str, Any] | None = None,
) -> AIConfig:
  """Return the primary chat config (fast/deep routing removed)."""
  del params, workflow_id, user_text, body
  return base
