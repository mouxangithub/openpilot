"""Tests for ai.core.agent.state."""

import unittest

from ai.core.agent.state import AgentState, CancelCause, CancelCauseKind, InboxTarget


class AgentStateTestCase(unittest.TestCase):
  def test_inbox_claim(self):
    agent = AgentState("a1", "s1")
    from ai.core.agent.state import AgentMessage
    agent.followup(AgentMessage(role="user", content="hello"))
    self.assertTrue(agent.inbox.has_pending)
    claimed = agent.inbox.claim(InboxTarget.NEXT_TURN, 1)
    self.assertEqual(len(claimed), 1)
    self.assertEqual(claimed[0].content, "hello")
    self.assertFalse(agent.inbox.has_pending)

  def test_cancel(self):
    agent = AgentState("a1", "s1")
    agent.cancel(CancelCause(CancelCauseKind.USER))
    self.assertTrue(agent.is_cancelled())
    self.assertEqual(agent.cancel_cause().kind, CancelCauseKind.USER)


if __name__ == "__main__":
  unittest.main()
