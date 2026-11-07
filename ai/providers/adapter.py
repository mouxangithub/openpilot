"""Provider adapter interface."""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol


class ProviderAdapter(Protocol):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Any]:
        ...
