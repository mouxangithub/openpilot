"""Tests for ai.permissions.approval."""

from __future__ import annotations

import unittest

from ai.permissions.approval import (
  EVENT_APPROVAL_ASKED,
  EVENT_APPROVAL_DECIDED,
  ApprovalService,
  ApprovalState,
)
from ai.permissions.hitl import ApprovalRequest, HumanInLoop


class RejectingHITL(HumanInLoop):
  """HITL mock that always rejects."""

  async def request_approval(self, request: ApprovalRequest) -> bool:
    return False


class TestApprovalService(unittest.TestCase):
  def test_headless_rejects_immediately(self) -> None:
    service = ApprovalService()
    state = service.ask("s1", "vehicle_flash", "c1", "flash firmware")
    self.assertEqual(state, ApprovalState.REJECTED)

  def test_headless_generates_asked_and_decided(self) -> None:
    service = ApprovalService()
    service.ask("s1", "vehicle_flash", "c1", "flash firmware")
    types = [e["type"] for e in service.events]
    self.assertEqual(types, [EVENT_APPROVAL_ASKED, EVENT_APPROVAL_DECIDED])

  def test_hitl_approval_allowed(self) -> None:
    hitl = HumanInLoop()
    service = ApprovalService(hitl=hitl, approval_policy="ask")
    state = service.ask("s1", "workspace_write", "c2", "write file")
    self.assertEqual(state, ApprovalState.ALLOWED)

  def test_hitl_rejection(self) -> None:
    hitl = RejectingHITL()
    service = ApprovalService(hitl=hitl, approval_policy="ask")
    state = service.ask("s1", "workspace_write", "c3", "write file")
    self.assertEqual(state, ApprovalState.REJECTED)

  def test_decided_event_contains_approval_result(self) -> None:
    service = ApprovalService()
    service.ask("s1", "shell_exec", "c4", "run command")
    decided = [e for e in service.events if e["type"] == EVENT_APPROVAL_DECIDED]
    self.assertEqual(len(decided), 1)
    self.assertFalse(decided[0]["payload"]["approved"])

  def test_event_order(self) -> None:
    service = ApprovalService()
    service.ask("s1", "shell_exec", "c5", "run command")
    self.assertEqual(service.events[0]["type"], EVENT_APPROVAL_ASKED)
    self.assertEqual(service.events[1]["type"], EVENT_APPROVAL_DECIDED)


if __name__ == "__main__":
  unittest.main()
