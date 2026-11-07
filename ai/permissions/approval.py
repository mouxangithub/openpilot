"""Approval service for high-consequence tool calls.

Produces ``approval/asked`` and ``approval/decided`` events and delegates
the actual human decision to an optional ``HumanInLoop`` instance. In
headless mode (no HITL, policy=never) approvals are immediately rejected.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from ai.permissions.hitl import ApprovalRequest, HumanInLoop


class ApprovalState(StrEnum):
  PENDING = "pending"
  ALLOWED = "allowed"
  REJECTED = "rejected"
  CANCELLED = "cancelled"
  UNAVAILABLE = "unavailable"


EVENT_APPROVAL_ASKED = "approval/asked"
EVENT_APPROVAL_DECIDED = "approval/decided"

EventSink = Callable[[str, dict[str, Any]], None]


@dataclass
class ApprovalService:
  """Standard HITL approval flow with event generation.

  Attributes:
    hitl: Optional human-in-the-loop channel. If ``None`` the service runs in
      headless mode.
    approval_policy: ``ask`` to request human approval, ``never`` to reject
      immediately. Defaults to ``never`` for headless safety.
    event_sink: Optional callable ``(event_type, payload)`` to emit events.
      If omitted, events are accumulated in ``events``.
  """

  hitl: HumanInLoop | None = None
  approval_policy: str = "never"
  event_sink: EventSink | None = None
  events: list[dict[str, Any]] = field(default_factory=list)

  def ask(
    self,
    session_id: str,
    tool_name: str,
    call_id: str,
    reason: str,
  ) -> ApprovalState:
    """Request approval for a high-consequence tool call.

    Args:
      session_id: Session identifier.
      tool_name: Name of the tool requesting execution.
      call_id: Unique tool-call id.
      reason: Human-readable reason for the request.

    Returns:
      Final approval state.
    """
    approval_id = f"{session_id}:{call_id}:{uuid.uuid4().hex[:8]}"
    asked_payload = {
      "approval_id": approval_id,
      "session_id": session_id,
      "action": tool_name,
      "capability": tool_name,
      "description": reason,
      "tool_call_id": call_id,
      "metadata": {"session_id": session_id, "tool_name": tool_name},
    }
    self._emit(EVENT_APPROVAL_ASKED, asked_payload)

    if self.approval_policy == "never" or self.hitl is None:
      decided_payload = {
        "approval_id": approval_id,
        "approved": False,
        "decided_by": "headless",
        "reason": "headless mode: approval policy is never",
      }
      self._emit(EVENT_APPROVAL_DECIDED, decided_payload)
      return ApprovalState.REJECTED

    request = ApprovalRequest(
      action=tool_name,
      capability=tool_name,
      description=reason,
      tool_call_id=call_id,
      metadata={"approval_id": approval_id, "session_id": session_id},
    )
    approved = self._request_hitl(request)
    decided_payload = {
      "approval_id": approval_id,
      "approved": approved,
      "decided_by": "human",
      "reason": "approved by human" if approved else "rejected by human",
    }
    self._emit(EVENT_APPROVAL_DECIDED, decided_payload)
    return ApprovalState.ALLOWED if approved else ApprovalState.REJECTED

  def _request_hitl(self, request: ApprovalRequest) -> bool:
    """Run the async HITL request from synchronous code."""
    if self.hitl is None:
      return False
    try:
      return asyncio.run(self.hitl.request_approval(request))
    except Exception:
      return False

  def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
    entry = {"type": event_type, "payload": dict(payload)}
    self.events.append(entry)
    if self.event_sink is not None:
      self.event_sink(event_type, payload)
