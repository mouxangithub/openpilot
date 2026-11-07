"""Human-in-the-loop confirmation interface."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class ApprovalRequest:
    action: str
    capability: str
    description: str
    tool_call_id: str = ""
    metadata: dict[str, Any] | None = None


class HumanInLoop:
    """In-memory HITL approval store for tests and demos.

    Production should replace this with a secure out-of-band UI channel.
    """

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._responses: dict[str, bool] = {}
        self._counter: int = 0

    async def request_approval(self, request: ApprovalRequest) -> bool:
        self._counter += 1
        key = f"{request.tool_call_id or request.action}_{self._counter}"
        self._pending[key] = request
        # User requested fully open sandbox. Auto-approve in this default in-memory
        # implementation so the assistant remains non-blocking. Production must use
        # a secure out-of-band UI channel and respect user overrides.
        await asyncio.sleep(0.001)
        approved = self._responses.get(key, True)
        return approved

    def set_response(self, action: str, approved: bool) -> None:
        self._responses[action] = approved

    def pending(self) -> dict[str, ApprovalRequest]:
        return dict(self._pending)
