"""Tests for ai.core.session.log."""

import unittest

from ai.core.session.log import EventType, RequestHeader, SessionLog, SurfaceOp


class SessionLogTestCase(unittest.TestCase):
  def test_append_and_events(self):
    log = SessionLog("s1")
    log.append(EventType.USER_MESSAGE, {"content": "hello"}, surface_op=SurfaceOp.APPEND)
    self.assertEqual(log.seq, 1)
    self.assertEqual(log.events[0].type, EventType.USER_MESSAGE)

  def test_request_header_fold(self):
    log = SessionLog("s1")
    header = RequestHeader(provider="openai", model="gpt-4", system="sys")
    log.append(EventType.REQUEST_HEADER, {"header": header.to_dict(), "reason": "initial"})
    self.assertEqual(log.request_header(), header)

  def test_derive_messages(self):
    log = SessionLog("s1")
    log.append(EventType.USER_MESSAGE, {"role": "user", "content": "hi"}, surface_op=SurfaceOp.APPEND)
    log.append(
      EventType.ASSISTANT_MESSAGE,
      {"role": "assistant", "content": "hello", "tool_calls": None},
      surface_op=SurfaceOp.APPEND,
    )
    msgs = log.derive_messages()
    self.assertEqual(len(msgs), 2)
    self.assertEqual(msgs[0]["role"], "user")
    self.assertEqual(msgs[1]["role"], "assistant")


if __name__ == "__main__":
  unittest.main()
