"""Offline mock provider for testing without API keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[dict[str, Any]] = None  # type: ignore[assignment]
    done: bool = False

    def __post_init__(self) -> None:
        if self.tool_calls is None:
            self.tool_calls = []


class OfflineProvider:
    """Deterministic mock provider that responds to simple prompts."""

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> AsyncIterator[ModelTurn]:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    last_user = content
                break

        if "param" in last_user.lower() or "调参" in last_user or "tune" in last_user.lower():
            yield ModelTurn(
                tool_calls=[{
                    "id": "call_write_params",
                    "type": "function",
                    "function": {
                        "name": "write_params",
                        "arguments": '{"params": {"dp_lat_accel_factor": 1.15}}',
                    },
                }],
            )
            yield ModelTurn(done=True)
            return

        if "hello" in last_user.lower() or "hi" in last_user.lower():
            yield ModelTurn(text="Hello from offline mock provider.")
            yield ModelTurn(done=True)
            return

        yield ModelTurn(text=f"Offline echo: {last_user}")
        yield ModelTurn(done=True)
